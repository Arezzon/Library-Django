from django.db import transaction
from django.db.models import ProtectedError
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status, viewsets
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response

from authentication.permissions import IsSignedIn, ReadOnlyOrLibrarian
from events.searches import record_search, search_identity
from events.services import EventQueueUnavailable

from .embeddings import EmbeddingGenerationError
from .models import Book
from .recommendations import recommend_books
from .search import search_books, validate_query
from .serializers import (
    BookRecommendationSerializer,
    BookSearchSerializer,
    BookSerializer,
    RecommendationParameters,
)


class BookViewSet(viewsets.ModelViewSet):
    permission_classes = [ReadOnlyOrLibrarian]
    queryset = Book.objects.prefetch_related("authors").order_by("id")
    serializer_class = BookSerializer
    refusals = {
        "destroy": {
            "409": "The book has borrowing or reservation history; nothing changed."
        }
    }

    def get_queryset(self):
        # Counted per request, so a reservation stops holding its copy at its
        # deadline (FR-013); a class-level annotation would keep the import's time.
        return super().get_queryset().with_availability()

    def destroy(self, request, *args, **kwargs):
        book = self.get_object()
        try:
            with transaction.atomic():
                # Locked, as the web view does, so a loan started meanwhile waits.
                Book.objects.select_for_update().get(pk=book.pk).delete()
        except ProtectedError:
            return Response(
                {"detail": Book.DELETION_REFUSAL}, status=status.HTTP_409_CONFLICT
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class BookSearchView(GenericAPIView):
    permission_classes = [IsSignedIn]
    serializer_class = BookSearchSerializer

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "search_id",
                str,
                description="UUID for one search action; reuse on retries, change for a new submission.",
            ),
            OpenApiParameter(
                "q",
                str,
                required=True,
                description="Semantic query (1–512 characters). Returns up to 20 books ranked by cosine similarity.",
            ),
        ],
        responses={200: BookSearchSerializer(many=True)},
    )
    def get(self, request):
        try:
            query = validate_query(request.query_params.get("q", ""))
            identity = search_identity(request.query_params.get("search_id"))
        except ValueError:
            return Response({"q": "Invalid query parameter."}, status=400)
        try:
            books = search_books(
                Book.objects.with_availability().prefetch_related("authors"), query
            )
        except EmbeddingGenerationError as _error:
            return Response({"detail": "Service temporarily unavailable."}, status=503)
        data = self.get_serializer(books, many=True).data
        headers = {
            "X-Search-Event-ID": str(identity),
            "Cache-Control": "private, no-store",
        }
        try:
            record_search(request, identity, query)
        except EventQueueUnavailable:
            headers["Retry-After"] = "5"
            return Response(
                {
                    "detail": "Search history is temporarily unavailable. Retry with the same search_id."
                },
                status=503,
                headers=headers,
            )
        return Response(data, headers=headers)


class BookRecommendationsView(GenericAPIView):
    permission_classes = [IsSignedIn]
    serializer_class = BookRecommendationSerializer

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "limit", int, description="Number of books, 1–20 (default 10)."
            )
        ],
        responses={200: BookRecommendationSerializer(many=True)},
        description="Available book recommendations with a personal, evidence-based reason for the signed-in account only.",
    )
    def get(self, request):
        if set(request.query_params) - {"limit"}:
            return Response(
                {"detail": "Only the limit parameter is accepted."}, status=400
            )
        parameters = RecommendationParameters(data=request.query_params)
        parameters.is_valid(raise_exception=True)
        books = recommend_books(request.user, parameters.validated_data["limit"])
        return Response(self.get_serializer(books, many=True).data)

from django.db import transaction
from django.db.models import ProtectedError
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status, viewsets
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response

from authentication.permissions import IsSignedIn, ReadOnlyOrLibrarian

from .embeddings import EmbeddingGenerationError
from .models import Book
from .search import search_books, validate_query
from .serializers import BookSearchSerializer, BookSerializer


class BookViewSet(viewsets.ModelViewSet):
    permission_classes = [ReadOnlyOrLibrarian]
    queryset = (
        Book.objects.with_availability().prefetch_related("authors").order_by("id")
    )
    serializer_class = BookSerializer
    refusals = {
        "destroy": {
            "409": "The book has borrowing or reservation history; nothing changed."
        }
    }

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
                "q",
                str,
                required=True,
                description="Semantic query (1–512 characters). Returns up to 20 books ranked by cosine similarity.",
            )
        ],
        responses={200: BookSearchSerializer(many=True)},
    )
    def get(self, request):
        try:
            query = validate_query(request.query_params.get("q", ""))
        except ValueError:
            return Response({"q": "Invalid query parameter."}, status=400)
        try:
            books = search_books(
                Book.objects.with_availability().prefetch_related("authors"), query
            )
        except EmbeddingGenerationError as _error:
            return Response({"detail": "Service temporarily unavailable."}, status=503)
        return Response(self.get_serializer(books, many=True).data)

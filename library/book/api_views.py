from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import viewsets
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response

from .embeddings import EmbeddingGenerationError
from .models import Book
from .search import search_books, validate_query
from .serializers import BookSearchSerializer, BookSerializer


class BookViewSet(viewsets.ModelViewSet):
    queryset = (
        Book.objects.with_availability().prefetch_related("authors").order_by("id")
    )
    serializer_class = BookSerializer


class BookSearchView(GenericAPIView):
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
        except EmbeddingGenerationError as error:
            return Response({"detail": str(error)}, status=503)
        return Response(self.get_serializer(books, many=True).data)

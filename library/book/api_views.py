from rest_framework import viewsets
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiParameter
from .search import search_books, validate_query
from .embeddings import EmbeddingGenerationError
from .models import Book
from .serializers import BookSerializer, BookSearchSerializer


class BookViewSet(viewsets.ModelViewSet):
    queryset = Book.objects.with_availability().prefetch_related('authors').order_by('id')
    serializer_class = BookSerializer


class BookSearchView(GenericAPIView):
    serializer_class = BookSearchSerializer

    @extend_schema(
        parameters=[OpenApiParameter('q', str, required=True,
                                     description='Semantic query (1–512 characters). Returns up to 20 books ranked by cosine similarity.')],
        responses={200: BookSearchSerializer(many=True)},
    )
    def get(self, request):
        try:
            query = validate_query(request.query_params.get('q', ''))
        except ValueError as error:
            return Response({'q': str(error)}, status=400)
        try:
            books = search_books(Book.objects.with_availability().prefetch_related('authors'), query)
        except EmbeddingGenerationError as error:
            return Response({'detail': str(error)}, status=503)
        return Response(self.get_serializer(books, many=True).data)

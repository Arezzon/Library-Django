from rest_framework import viewsets
from .models import Book
from .serializers import BookSerializer


class BookViewSet(viewsets.ModelViewSet):
    queryset = Book.objects.with_availability().prefetch_related('authors').order_by('id')
    serializer_class = BookSerializer

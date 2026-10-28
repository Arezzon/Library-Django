from rest_framework import viewsets

from authentication.permissions import ReadOnlyOrLibrarian

from .models import Author
from .serializers import AuthorSerializer


class AuthorViewSet(viewsets.ModelViewSet):
    permission_classes = [ReadOnlyOrLibrarian]
    queryset = Author.objects.all().order_by("id")
    serializer_class = AuthorSerializer

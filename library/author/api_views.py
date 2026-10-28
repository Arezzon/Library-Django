from rest_framework import status, viewsets
from rest_framework.response import Response

from authentication.permissions import ReadOnlyOrLibrarian

from .models import Author
from .serializers import AuthorSerializer


class AuthorViewSet(viewsets.ModelViewSet):
    permission_classes = [ReadOnlyOrLibrarian]
    queryset = Author.objects.prefetch_related("books").order_by("id")
    serializer_class = AuthorSerializer
    refusals = {"destroy": {"409": "The author is attached to books; nothing changed."}}

    def destroy(self, request, *args, **kwargs):
        author = self.get_object()
        refusal = author.deletion_refusal()
        if refusal:
            return Response({"detail": refusal}, status=status.HTTP_409_CONFLICT)
        self.perform_destroy(author)
        return Response(status=status.HTTP_204_NO_CONTENT)

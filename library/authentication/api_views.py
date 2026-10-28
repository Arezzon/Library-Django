from collections.abc import Mapping

from rest_framework import viewsets

from .models import CustomUser
from .permissions import IsLibrarian, IsSelfOrLibrarian, is_librarian
from .serializers import CustomUserSerializer
from .services import check_changes


class CustomUserViewSet(viewsets.ModelViewSet):
    """Accounts. Librarians manage every account; a reader reads and renames their
    own, and another reader's account answers 404."""

    serializer_class = CustomUserSerializer
    permission_classes = [IsLibrarian]
    permission_classes_by_action = {
        "retrieve": [IsSelfOrLibrarian],
        "update": [IsSelfOrLibrarian],
        "partial_update": [IsSelfOrLibrarian],
    }

    def get_permissions(self):
        classes = self.permission_classes_by_action.get(
            self.action, self.permission_classes
        )
        return [permission() for permission in classes]

    def get_queryset(self):
        accounts = CustomUser.objects.all().order_by("id")
        user = getattr(self.request, "user", None)
        if not is_librarian(user):
            accounts = accounts.filter(pk=getattr(user, "pk", None))
        return accounts

    def update(self, request, *args, **kwargs):
        # A forbidden field is refused before validation, whatever its value. A body
        # that is not an object is left to validation, which answers 400.
        if isinstance(request.data, Mapping):
            check_changes(request.user, self.get_object(), request.data)
        return super().update(request, *args, **kwargs)

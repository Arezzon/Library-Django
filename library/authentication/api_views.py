from collections.abc import Mapping

from django.core.exceptions import PermissionDenied
from rest_framework import viewsets

from .models import CustomUser
from .permissions import IsLibrarian, IsSelfOrLibrarian, is_librarian
from .serializers import CustomUserSerializer
from .services import check_changes, may_change_account


class CustomUserViewSet(viewsets.ModelViewSet):
    """Accounts. Librarians manage every account except an administrator's, which only
    administrators change; a reader reads and renames their own, and another reader's
    account answers 404."""

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

    def create(self, request, *args, **kwargs):
        # As for update: a role only an administrator may set is refused first.
        if isinstance(request.data, Mapping):
            check_changes(request.user, None, request.data)
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        # A forbidden field is refused before validation, whatever its value. A body
        # that is not an object is left to validation, which answers 400.
        if isinstance(request.data, Mapping):
            check_changes(request.user, self.get_object(), request.data)
        return super().update(request, *args, **kwargs)

    def perform_destroy(self, instance):
        if not may_change_account(self.request.user, instance):
            raise PermissionDenied
        super().perform_destroy(instance)

from collections.abc import Mapping

from django.core.exceptions import PermissionDenied
from rest_framework import status, viewsets
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from authentication.permissions import (
    IsLibrarian,
    IsSelfOrLibrarian,
    IsSignedIn,
    is_librarian,
)

from .models import Order
from .serializers import OrderSerializer

# Only librarians change or delete a loan, whoever it belongs to.
LIBRARIAN_ACTIONS = {
    "update": [IsLibrarian],
    "partial_update": [IsLibrarian],
    "destroy": [IsLibrarian],
}


class OrderViewSet(viewsets.ModelViewSet):
    """CRUD: /api/v1/order/{id}?

    Librarians see every loan; a reader sees their own, and another reader's loan
    answers 404. Until issuing moves to librarians (KAN-57), a reader may also start a
    loan for themselves."""

    serializer_class = OrderSerializer
    permission_classes = [IsSignedIn]
    own_records_only = True

    def get_permissions(self):
        classes = LIBRARIAN_ACTIONS.get(self.action, self.permission_classes)
        return [permission() for permission in classes]

    def get_queryset(self):
        loans = Order.objects.all().order_by("-created_at")
        user = getattr(self.request, "user", None)
        if not is_librarian(user):
            loans = loans.filter(user_id=getattr(user, "pk", None))
        return loans

    def create(self, request, *args, **kwargs):
        # Checked before validation, so another reader's loan is refused, not checked.
        # A body that is not an object is left to validation, which answers 400.
        data = request.data
        if (
            not is_librarian(request.user)
            and isinstance(data, Mapping)
            and str(data.get("user")) != str(request.user.pk)
        ):
            raise PermissionDenied("Readers may start a loan only for themselves.")
        return super().create(request, *args, **kwargs)


class UserOrderViewSet(viewsets.ModelViewSet):
    """CRUD: /api/v1/user/{user_id}/order/{id}?

    The loans of one account, for that account or a librarian. Another account's loans
    answer 404 to a reader, whether or not they exist."""

    serializer_class = OrderSerializer
    permission_classes = [IsSelfOrLibrarian]

    def get_permissions(self):
        classes = LIBRARIAN_ACTIONS.get(self.action, self.permission_classes)
        return [permission() for permission in classes]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not is_librarian(request.user) and kwargs.get("user_id") != request.user.pk:
            raise NotFound

    def get_queryset(self):
        user_id = self.kwargs.get("user_id")
        return Order.objects.filter(user_id=user_id).order_by("-created_at")

    def create(self, request, *args, **kwargs):
        user_id = self.kwargs.get("user_id")
        data = request.data
        if isinstance(data, Mapping):  # anything else fails validation with 400
            data = data.copy()
            data["user"] = user_id
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(
            serializer.data, status=status.HTTP_201_CREATED, headers=headers
        )

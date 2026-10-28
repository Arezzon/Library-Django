from collections.abc import Mapping

from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.utils import timezone
from django.utils.functional import cached_property
from drf_spectacular.utils import (
    OpenApiParameter,
    extend_schema,
    extend_schema_view,
    inline_serializer,
)
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response

from authentication.permissions import (
    IsLibrarian,
    IsSelfOrLibrarian,
    IsSignedIn,
    is_librarian,
)

from . import services
from .models import Order, Reservation, ReservationState
from .serializers import OrderSerializer, ReservationSerializer

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


# ?state= reads the effective state: a reservation past its deadline is expired.
STATE_FILTERS = {
    ReservationState.ACTIVE: lambda now: Q(
        state=ReservationState.ACTIVE, expires_at__gt=now
    ),
    ReservationState.ISSUED: lambda now: Q(state=ReservationState.ISSUED),
    ReservationState.CANCELLED: lambda now: Q(state=ReservationState.CANCELLED),
    ReservationState.EXPIRED: lambda now: Q(state=ReservationState.EXPIRED)
    | Q(state=ReservationState.ACTIVE, expires_at__lte=now),
}

RESERVATION_REFUSAL = inline_serializer(
    name="ReservationRefusal",
    fields={
        "code": serializers.ChoiceField(choices=sorted(services.MESSAGES)),
        "detail": serializers.CharField(),
        "book": serializers.IntegerField(
            required=False, help_text="For overdue_loan: the overdue book."
        ),
        "due": serializers.DateTimeField(
            required=False, help_text="For overdue_loan: its due date."
        ),
    },
)


@extend_schema_view(
    list=extend_schema(
        parameters=[
            OpenApiParameter(
                "state",
                str,
                enum=ReservationState.values,
                description="Only reservations in this effective state.",
            )
        ]
    ),
    create=extend_schema(
        responses={201: ReservationSerializer, 409: RESERVATION_REFUSAL},
        description="Reserve a book for the caller for 48 hours. A refused request "
        "answers 409 with a code and a message that says what to do next.",
    ),
)
class ReservationViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """/api/v1/reservation/{id}?

    Librarians see every reservation; a reader sees their own, and another reader's
    answers 404. Active reservations come first, by deadline, then the rest, newest
    first."""

    serializer_class = ReservationSerializer
    permission_classes = [IsSignedIn]
    own_records_only = True

    @cached_property
    def now(self):
        """This request's time, taken once (R12). A property, not set in initial(),
        so the schema can read the queryset, and with it the id's type."""
        return timezone.now()

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "now": self.now}

    def get_queryset(self):
        reservations = Reservation.objects.all()
        user = getattr(self.request, "user", None)
        if not is_librarian(user):
            reservations = reservations.filter(user_id=getattr(user, "pk", None))
        state = self.request.query_params.get("state")
        if state is not None:
            if state not in STATE_FILTERS:
                choices = ", ".join(ReservationState.values)
                raise ValidationError({"state": [f"Choose one of: {choices}."]})
            reservations = reservations.filter(STATE_FILTERS[state](self.now))
        return services.listed(reservations, self.now)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            reservation = services.reserve(
                request.user, serializer.validated_data["book"], now=self.now
            )
        except services.ReservationRefused as refused:
            body = {"code": refused.code, "detail": refused.message, **refused.context}
            return Response(body, status=status.HTTP_409_CONFLICT)
        return Response(
            self.get_serializer(reservation).data, status=status.HTTP_201_CREATED
        )

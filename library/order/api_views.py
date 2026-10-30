from collections.abc import Mapping

from django.db.models import Q
from django.utils import timezone
from django.utils.functional import cached_property
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
    inline_serializer,
)
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response

from authentication.permissions import (
    IsLibrarian,
    IsSelfOrLibrarian,
    IsSignedIn,
    is_librarian,
    is_signed_in,
)

from . import services
from .models import Order, Reservation, ReservationState
from .serializers import OrderSerializer, ReservationSerializer

# Only librarians start, change or delete a loan, whoever it belongs to (FR-015).
LIBRARIAN_ACTIONS = {
    "create": [IsLibrarian],
    "update": [IsLibrarian],
    "partial_update": [IsLibrarian],
    "destroy": [IsLibrarian],
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
        "loan": serializers.IntegerField(
            required=False, help_text="For already_issued: the loan it started."
        ),
    },
)
INVALID_BODY = OpenApiResponse(
    description="A field is invalid; the body names it, in DRF's field-error format."
)


def refused(refusal):
    """A rule's refusal as the API answers it: 409 with its code, its message and
    any details (contracts/reservations-api.md)."""
    body = {"code": refusal.code, "detail": refusal.message, **refusal.context}
    return Response(body, status=status.HTTP_409_CONFLICT)


class LendingMixin:
    """Starting a loan lends through services.lend(), as the desk does (FR-015,
    FR-016), so a reservation the reader holds for the book is issued. A loan recorded
    as already returned is a correction and is saved as given."""

    @extend_schema(
        responses={201: OrderSerializer, 400: INVALID_BODY, 409: RESERVATION_REFUSAL},
        description="Lend a book to a reader. If the reader holds an active "
        "reservation of the book, it is issued. A refused loan answers 409 with a "
        "code and a message that says what to do next.",
    )
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=self.loan_data(request))
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if data.get("end_at") is not None:
            self.perform_create(serializer)
            loan = serializer.instance
        else:
            try:
                loan = services.lend(
                    request.user, data["user"], data["book"], due=data["plated_end_at"]
                )
            except services.ReservationRefused as refusal:
                return refused(refusal)
        return Response(self.get_serializer(loan).data, status=status.HTTP_201_CREATED)

    def loan_data(self, request):
        return request.data


class OrderViewSet(LendingMixin, viewsets.ModelViewSet):
    """CRUD: /api/v1/order/{id}?

    Librarians see every loan; a reader sees their own, and another reader's loan
    answers 404. Only librarians start a loan."""

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


class UserOrderViewSet(LendingMixin, viewsets.ModelViewSet):
    """CRUD: /api/v1/user/{user_id}/order/{id}?

    The loans of one account, for that account or a librarian. Another account's loans
    answer 404 to a reader, whether or not they exist."""

    serializer_class = OrderSerializer
    permission_classes = [IsSelfOrLibrarian]

    def get_permissions(self):
        classes = LIBRARIAN_ACTIONS.get(self.action, self.permission_classes)
        return [permission() for permission in classes]

    def check_permissions(self, request):
        # Starting a loan is for librarians only, but another account's route still
        # answers 404 to a reader, as reading it does (access-control.md).
        if self.action == "create":
            self.refuse_another_account(request.user)
        super().check_permissions(request)

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.refuse_another_account(request.user)

    def refuse_another_account(self, user):
        if (
            is_signed_in(user)
            and not is_librarian(user)
            and self.kwargs.get("user_id") != user.pk
        ):
            raise NotFound

    def get_queryset(self):
        user_id = self.kwargs.get("user_id")
        return Order.objects.filter(user_id=user_id).order_by("-created_at")

    def loan_data(self, request):
        data = request.data
        if isinstance(data, Mapping):  # anything else fails validation with 400
            data = data.copy()
            data["user"] = self.kwargs.get("user_id")
        return data


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


class IssueRequest(serializers.Serializer):
    days = serializers.IntegerField(
        min_value=1, max_value=30, default=14, help_text="The loan period in days."
    )


class CancelRequest(serializers.Serializer):
    reason = serializers.CharField(
        max_length=services.REASON_LENGTH,
        required=False,
        allow_blank=True,
        default="",
        help_text="Required, 1 to 500 characters, when a librarian cancels someone "
        "else's reservation. The reader sees it.",
    )

    def validate_reason(self, reason):
        if self.context.get("reason_required") and not reason:
            raise serializers.ValidationError(services.REASON_RULE)
        return reason


RESERVATION_ISSUED = inline_serializer(
    name="ReservationIssued",
    fields={"reservation": ReservationSerializer(), "loan": OrderSerializer()},
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
        except services.ReservationRefused as refusal:
            return refused(refusal)
        return Response(
            self.get_serializer(reservation).data, status=status.HTTP_201_CREATED
        )

    @extend_schema(
        request=CancelRequest,
        responses={
            200: ReservationSerializer,
            400: INVALID_BODY,
            409: RESERVATION_REFUSAL,
        },
        description="Cancel an active reservation. Its reader needs no reason; a "
        "librarian cancelling someone else's gives one, which the reader sees. A "
        "reservation that is no longer active answers 409.",
    )
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        reservation = self.get_object()
        body = CancelRequest(
            data=request.data,
            context={"reason_required": reservation.user_id != request.user.pk},
        )
        body.is_valid(raise_exception=True)
        try:
            reservation = services.cancel(
                request.user, reservation, body.validated_data["reason"]
            )
        except services.ReservationRefused as refusal:
            return refused(refusal)
        return Response(self.get_serializer(reservation).data)

    @extend_schema(
        request=IssueRequest,
        responses={
            201: RESERVATION_ISSUED,
            400: INVALID_BODY,
            409: RESERVATION_REFUSAL,
        },
        description="Issue an active reservation: in one step it becomes issued and "
        "the loan starts with the copy it held. A repeated request answers 409 "
        "already_issued with the loan.",
    )
    @action(detail=True, methods=["post"], permission_classes=[IsLibrarian])
    def issue(self, request, pk=None):
        reservation = self.get_object()
        body = IssueRequest(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            loan = services.issue(
                request.user, reservation, body.validated_data["days"]
            )
        except services.ReservationRefused as refusal:
            return refused(refusal)
        reservation.refresh_from_db()
        return Response(
            {
                "reservation": self.get_serializer(reservation).data,
                "loan": OrderSerializer(loan).data,
            },
            status=status.HTTP_201_CREATED,
        )

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from authentication.permissions import is_librarian

from .models import BookUnavailableError, Order, Reservation, ReservationState


class OrderSerializer(serializers.ModelSerializer):
    def create(self, validated_data):
        try:
            return super().create(validated_data)
        except BookUnavailableError as error:
            raise serializers.ValidationError(
                {"book": "The selected book is currently unavailable."}
            ) from error

    def update(self, instance, validated_data):
        try:
            return super().update(instance, validated_data)
        except BookUnavailableError as error:
            raise serializers.ValidationError(
                {"book": "The selected book is currently unavailable."}
            ) from error

    class Meta:
        model = Order
        fields = ["id", "user", "book", "created_at", "end_at", "plated_end_at"]
        extra_kwargs = {
            "created_at": {"read_only": True},
            "end_at": {"required": False, "allow_null": True},
            # The database has no default for it, so a new loan must give it.
            "plated_end_at": {"required": True},
        }


class ReservationSerializer(serializers.ModelSerializer):
    """A reservation as contracts/reservations-api.md describes it. Its state is the
    effective one, and only librarians see who cancelled it."""

    state = serializers.SerializerMethodField()
    cancelled_by_library = serializers.SerializerMethodField()

    class Meta:
        model = Reservation
        fields = [
            "id",
            "book",
            "user",
            "state",
            "created_at",
            "expires_at",
            "loan",
            "cancelled_at",
            "cancel_reason",
            "cancelled_by_library",
            "cancelled_by",
        ]
        read_only_fields = [field for field in fields if field != "book"]

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get("request")
        if not is_librarian(getattr(request, "user", None)):
            fields.pop("cancelled_by")
        return fields

    @extend_schema_field(serializers.ChoiceField(choices=ReservationState.choices))
    def get_state(self, reservation):
        return reservation.effective_state(self.context["now"])

    def get_cancelled_by_library(self, reservation) -> bool:
        # The reader's own account goes with its reservations, so a missing
        # canceller was a librarian whose account was deleted.
        return (
            reservation.cancelled_at is not None
            and reservation.cancelled_by_id != reservation.user_id
        )

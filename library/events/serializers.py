from collections.abc import Mapping

from rest_framework import serializers

from book.models import Book

from .models import EventType
from .overview import DEFAULT_LIMIT, DEFAULT_PERIOD, PERIODS


class ClientEventSerializer(serializers.Serializer):
    event_id = serializers.UUIDField()
    event_type = serializers.ChoiceField(
        choices=[EventType.BOOK_CLICK, EventType.BORROW_INTENT]
    )
    book_id = serializers.PrimaryKeyRelatedField(queryset=Book.objects.all())
    path = serializers.RegexField(r"^/book/(?:[0-9]+/)?$", max_length=200)

    def to_internal_value(self, data):
        if isinstance(data, Mapping):
            unknown = set(data) - set(self.fields)
            if unknown:
                raise serializers.ValidationError(
                    dict.fromkeys(sorted(unknown), "Unknown field.")
                )
        return super().to_internal_value(data)


class OverviewParameters(serializers.Serializer):
    period = serializers.ChoiceField(choices=list(PERIODS), default=DEFAULT_PERIOD)
    limit = serializers.IntegerField(default=DEFAULT_LIMIT, min_value=1, max_value=20)

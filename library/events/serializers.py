from collections.abc import Mapping
from rest_framework import serializers
from book.models import Book
from .models import EventType


class ClientEventSerializer(serializers.Serializer):
    event_id = serializers.UUIDField()
    event_type = serializers.ChoiceField(choices=[EventType.BOOK_CLICK, EventType.BORROW_INTENT])
    book_id = serializers.PrimaryKeyRelatedField(queryset=Book.objects.all())
    path = serializers.RegexField(r'^/book/(?:[0-9]+/)?$', max_length=200)

    def to_internal_value(self, data):
        if isinstance(data, Mapping):
            unknown = set(data) - set(self.fields)
            if unknown:
                raise serializers.ValidationError({key: 'Unknown field.' for key in sorted(unknown)})
        return super().to_internal_value(data)

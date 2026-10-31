"""Only the session account may read or change its private book preferences."""

from collections.abc import Mapping

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.generics import GenericAPIView
from rest_framework.parsers import JSONParser
from rest_framework.response import Response

from authentication.permissions import IsSignedIn

from .preferences import preference_books, preference_state, set_preferences
from .serializers import BookSerializer


class PreferenceStateSerializer(serializers.Serializer):
    book_id = serializers.IntegerField(read_only=True)
    liked = serializers.BooleanField(read_only=True)
    favorite = serializers.BooleanField(read_only=True)


class PreferenceUpdateSerializer(serializers.Serializer):
    liked = serializers.BooleanField(required=False)
    favorite = serializers.BooleanField(required=False)

    def to_internal_value(self, data):
        if isinstance(data, Mapping):
            if set(data) - set(self.fields):
                raise serializers.ValidationError(
                    {"non_field_errors": ["Only liked and favorite are accepted."]}
                )
            if any(not isinstance(value, bool) for value in data.values()):
                raise serializers.ValidationError(
                    {"non_field_errors": ["Preference states must be JSON booleans."]}
                )
        return super().to_internal_value(data)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("Provide liked or favorite.")
        return attrs


class BookPreferenceSerializer(BookSerializer):
    liked = serializers.BooleanField(read_only=True)
    favorite = serializers.BooleanField(read_only=True)

    class Meta(BookSerializer.Meta):
        fields = BookSerializer.Meta.fields + ["liked", "favorite"]


def private_response(data, status=200):
    return Response(data, status=status, headers={"Cache-Control": "private, no-store"})


class BookPreferenceView(GenericAPIView):
    permission_classes = [IsSignedIn]
    parser_classes = [JSONParser]
    serializer_class = PreferenceStateSerializer

    def _reject_selectors(self, request):
        return bool(request.query_params)

    @extend_schema(responses={200: PreferenceStateSerializer})
    def get(self, request, book_id):
        if self._reject_selectors(request):
            return private_response(
                {"detail": "Query parameters are not accepted."}, 400
            )
        return private_response(preference_state(request.user, book_id))

    @extend_schema(
        request=PreferenceUpdateSerializer, responses={200: PreferenceStateSerializer}
    )
    def patch(self, request, book_id):
        if self._reject_selectors(request):
            return private_response(
                {"detail": "Query parameters are not accepted."}, 400
            )
        serializer = PreferenceUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return private_response(
            set_preferences(request.user, book_id, **serializer.validated_data)
        )

    @extend_schema(request=None, responses={200: PreferenceStateSerializer})
    def delete(self, request, book_id):
        if self._reject_selectors(request) or request.data:
            return private_response(
                {"detail": "Parameters and body are not accepted."}, 400
            )
        return private_response(
            set_preferences(request.user, book_id, liked=False, favorite=False)
        )


class BookPreferenceListView(GenericAPIView):
    permission_classes = [IsSignedIn]
    serializer_class = BookPreferenceSerializer

    @extend_schema(
        parameters=[OpenApiParameter("kind", str, enum=["all", "likes", "favorites"])],
        responses={200: BookPreferenceSerializer(many=True)},
    )
    def get(self, request):
        if set(request.query_params) - {"kind"}:
            return private_response({"detail": "Only kind is accepted."}, 400)
        try:
            books = preference_books(
                request.user, request.query_params.get("kind", "all")
            )
        except ValueError as error:
            return private_response({"detail": str(error)}, 400)
        return private_response(self.get_serializer(books, many=True).data)

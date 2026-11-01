"""The session account is the only owner accepted by the ratings API."""

from collections.abc import Mapping

from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.generics import GenericAPIView
from rest_framework.parsers import JSONParser
from rest_framework.response import Response

from authentication.permissions import IsSignedIn

from .rating_rules import MAX_RATING, MIN_RATING
from .ratings import rating_state, set_rating


class RatingStateSerializer(serializers.Serializer):
    book_id = serializers.IntegerField(read_only=True)
    value = serializers.IntegerField(read_only=True, allow_null=True)


class RatingInputSerializer(serializers.Serializer):
    value = serializers.IntegerField(min_value=MIN_RATING, max_value=MAX_RATING)

    def to_internal_value(self, data):
        if (
            not isinstance(data, Mapping)
            or set(data) != {"value"}
            or type(data.get("value")) is not int
        ):
            raise serializers.ValidationError(
                {"value": ["Provide only value as a JSON integer from 1 to 5."]}
            )
        return super().to_internal_value(data)


class BookRatingView(GenericAPIView):
    permission_classes = [IsSignedIn]
    serializer_class = RatingStateSerializer
    parser_classes = [JSONParser]

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        return response

    def get(self, request, book_id):
        if request.query_params:
            return Response(
                {"detail": "Query parameters are not accepted."}, status=400
            )
        return Response(rating_state(request.user, book_id))

    @extend_schema(
        request=RatingInputSerializer, responses={200: RatingStateSerializer}
    )
    def put(self, request, book_id):
        if request.query_params:
            return Response(
                {"detail": "Query parameters are not accepted."}, status=400
            )
        data = RatingInputSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        return Response(set_rating(request.user, book_id, data.validated_data["value"]))

    @extend_schema(
        request=RatingInputSerializer, responses={200: RatingStateSerializer}
    )
    def patch(self, request, book_id):
        return self.put(request, book_id)

    @extend_schema(request=None, responses={200: RatingStateSerializer})
    def delete(self, request, book_id):
        if request.query_params or request.data:
            return Response(
                {"detail": "Parameters and body are not accepted."}, status=400
            )
        return Response(set_rating(request.user, book_id, None))


class RatingSummarySerializer(serializers.Serializer):
    book_id = serializers.IntegerField(read_only=True)
    average = serializers.FloatField(read_only=True, allow_null=True)
    count = serializers.IntegerField(read_only=True)


class BookRatingSummaryView(GenericAPIView):
    permission_classes = [IsSignedIn]
    serializer_class = RatingSummarySerializer

    def get(self, request, book_id):
        from .ratings import rating_overview

        if request.query_params:
            return Response(
                {"detail": "Query parameters are not accepted."}, status=400
            )
        overview = rating_overview(request.user, book_id)
        return Response(
            self.get_serializer(overview).data,
            headers={"Cache-Control": "private, no-store"},
        )

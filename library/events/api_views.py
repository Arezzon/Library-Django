from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.parsers import JSONParser
from rest_framework.response import Response
from rest_framework.views import APIView

from authentication.permissions import IsLibrarian, IsSignedIn

from .overview import library_overview
from .serializers import ClientEventSerializer, OverviewParameters
from .services import EventQueueUnavailable, make_payload, publish_event


class ClientEventView(APIView):
    permission_classes = [IsSignedIn]
    parser_classes = [JSONParser]

    @extend_schema(
        request=ClientEventSerializer,
        responses={
            202: inline_serializer(
                name="AcceptedEvent",
                fields={
                    "event_id": serializers.UUIDField(),
                    "accepted": serializers.BooleanField(),
                },
            )
        },
    )
    def post(self, request):
        serializer = ClientEventSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        payload = make_payload(
            request,
            data["event_type"],
            source="client",
            event_id=data["event_id"],
            book_id=data["book_id"].pk,
            path=data["path"],
        )
        try:
            publish_event(payload)
        except EventQueueUnavailable:
            return Response(
                {
                    "detail": "Tracking is temporarily unavailable. Retry with the same event_id."
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
                headers={"Retry-After": "5"},
            )
        return Response(
            {"event_id": payload["id"], "accepted": True},
            status=status.HTTP_202_ACCEPTED,
        )


class AnalyticsOverviewView(APIView):
    permission_classes = [IsLibrarian]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "period",
                str,
                enum=["7d", "30d", "90d", "12m"],
                description="Period ending today in Kyiv time (default 30d).",
            ),
            OpenApiParameter(
                "limit", int, description="Size of each top list, 1–20 (default 10)."
            ),
        ],
        responses={200: OpenApiTypes.OBJECT},
        description=(
            "Aggregated loans, returns, reservations, book views and reader counts "
            "for the period and the one before it, with no personal data; "
            "see docs/ba/analytics-dashboard.md."
        ),
    )
    def get(self, request):
        if set(request.query_params) - {"period", "limit"}:
            return Response(
                {"detail": "Only the period and limit parameters are accepted."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        parameters = OverviewParameters(data=request.query_params)
        parameters.is_valid(raise_exception=True)
        return Response(
            library_overview(**parameters.validated_data),
            headers={"Cache-Control": "private, no-store"},
        )

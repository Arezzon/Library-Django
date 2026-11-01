"""Catalog facts for the reader interface; no booking or loan operations."""

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from authentication.permissions import IsSignedIn

from .services import INTENTS, MAX_QUERY_LENGTH, catalog_assistant


class AssistantAuthorSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    url = serializers.CharField()
    books_url = serializers.CharField()


class AssistantBookSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    title = serializers.CharField()
    url = serializers.CharField()
    authors = AssistantAuthorSerializer(many=True)
    available_count = serializers.IntegerField()
    total_count = serializers.IntegerField()


class AssistantResponseSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=("found", "not_found", "clarification_required", "source_unavailable")
    )
    intent = serializers.CharField()
    answer = serializers.CharField()
    books = AssistantBookSerializer(many=True)
    authors = AssistantAuthorSerializer(many=True)
    checked_at = serializers.DateTimeField(allow_null=True)
    truncated = serializers.BooleanField()
    availability_notice = serializers.CharField()


class AssistantParameters(serializers.Serializer):
    q = serializers.CharField(
        required=False, default="", allow_blank=True, max_length=MAX_QUERY_LENGTH
    )
    intent = serializers.ChoiceField(choices=INTENTS, default="auto")


class CatalogAssistantView(APIView):
    permission_classes = [IsSignedIn]
    serializer_class = AssistantResponseSerializer
    http_method_names = ["get", "head", "options"]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "q",
                str,
                description="Ukrainian/English catalog question, e.g. знайди твори Шевченка or Find books about programming. Max 256 characters.",
            ),
            OpenApiParameter(
                "intent",
                str,
                enum=list(INTENTS),
                description="Default auto; explicit intent uses q as literal text.",
            ),
        ],
        responses={200: AssistantResponseSerializer, 503: AssistantResponseSerializer},
        description="Read-only current catalog facts and source links. CPU semantic search for explicit topics; no external LLM, reservation or loan creation. Availability is a snapshot, rechecked by booking.",
    )
    def get(self, request):
        if set(request.query_params) - {"q", "intent"} or any(
            len(request.query_params.getlist(key)) != 1 for key in request.query_params
        ):
            return Response(
                {"detail": "Only one q and intent value are accepted."},
                status=400,
                headers={"Cache-Control": "private, no-store"},
            )
        parameters = AssistantParameters(data=request.query_params)
        parameters.is_valid(raise_exception=True)
        result = catalog_assistant(
            request.user,
            parameters.validated_data["q"],
            parameters.validated_data["intent"],
        )
        headers = {"Cache-Control": "private, no-store"}
        if result["status"] == "source_unavailable":
            headers["Retry-After"] = "5"
        return Response(
            result,
            status=503 if result["status"] == "source_unavailable" else 200,
            headers=headers,
        )

"""Project-wide API views that belong to no single domain app."""

import os

from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class VersionView(APIView):
    """The commit this image was built from; read by CI and the healthcheck.

    Anonymous and read-only, and it uses no database, so it answers while the
    database is slow. The commit of a public repository is not sensitive.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        description="Commit the running image was built from, or `unknown` for "
        "local builds.",
        responses={
            200: inline_serializer(
                name="Version", fields={"commit": serializers.CharField()}
            )
        },
    )
    def get(self, request):
        response = Response({"commit": os.getenv("APP_COMMIT") or "unknown"})
        response["Cache-Control"] = "no-store"
        return response

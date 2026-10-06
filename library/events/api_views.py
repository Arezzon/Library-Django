from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from .serializers import ClientEventSerializer
from .services import EventQueueUnavailable, make_payload, publish_event


class ClientEventView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser]

    @extend_schema(request=ClientEventSerializer, responses={202: inline_serializer(
        name='AcceptedEvent', fields={'event_id': serializers.UUIDField(), 'accepted': serializers.BooleanField()},
    )})
    def post(self, request):
        serializer = ClientEventSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        payload = make_payload(
            request, data['event_type'], source='client', event_id=data['event_id'],
            book_id=data['book_id'].pk, path=data['path'],
        )
        try:
            publish_event(payload)
        except EventQueueUnavailable:
            return Response({'detail': 'Tracking is temporarily unavailable. Retry with the same event_id.'},
                            status=status.HTTP_503_SERVICE_UNAVAILABLE, headers={'Retry-After': '5'})
        return Response({'event_id': payload['id'], 'accepted': True}, status=status.HTTP_202_ACCEPTED)

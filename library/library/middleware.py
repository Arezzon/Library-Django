import re
import uuid

from .logs import request_id

VALID_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{8,64}")


class RequestIdMiddleware:
    """Gives every request an identifier for its log lines (research R18).

    A valid incoming ``X-Request-ID`` is kept; otherwise a new one is made. The
    response returns it in the same header.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        incoming = request.headers.get("X-Request-ID", "")
        value = incoming if VALID_REQUEST_ID.fullmatch(incoming) else uuid.uuid4().hex
        request.request_id = value
        token = request_id.set(value)
        try:
            response = self.get_response(request)
        finally:
            request_id.reset(token)
        response["X-Request-ID"] = value
        return response

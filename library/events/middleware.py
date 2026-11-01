from .models import EventType
from .services import capture, current_request


class EventTrackingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = current_request.set(request)
        try:
            response = self.get_response(request)
            match = request.resolver_match
            if (
                match
                and request.method == "GET"
                and response.status_code == 200
                and request.user.is_authenticated
            ):
                if match.url_name in ("book_detail", "book-detail"):
                    book_id = match.kwargs.get("book_id", match.kwargs.get("pk"))
                    capture(request, EventType.BOOK_VIEW, book_id=int(book_id))
            return response
        finally:
            current_request.reset(token)

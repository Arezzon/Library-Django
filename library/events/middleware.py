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
            if (match and request.method == 'GET' and response.status_code == 200
                    and request.user.is_authenticated):
                if match.url_name in ('book_detail', 'book-detail'):
                    book_id = match.kwargs.get('book_id', match.kwargs.get('pk'))
                    capture(request, EventType.BOOK_VIEW, book_id=int(book_id))
                elif match.url_name == 'book_list':
                    query = request.GET.get('q', '').strip()[:200]
                    author_id = request.GET.get('author_id', '')
                    if query or author_id.isdigit():
                        capture(request, EventType.SEARCH, properties={
                            'query': query,
                            'author_id': int(author_id) if author_id.isdigit() else None,
                        })
            return response
        finally:
            current_request.reset(token)

"""Exercise HTTP -> Redis -> Celery -> PostgreSQL against a running stack."""
import json
import re
import time
import uuid
from http.cookiejar import CookieJar
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener

from django.core.management.base import BaseCommand, CommandError
from authentication.models import CustomUser, ROLE_LIBRARIAN
from book.models import Book
from order.models import Order
from events.models import EventType, UserEvent


class Command(BaseCommand):
    help = 'Run real HTTP/Redis/worker tracking checks using disposable test records.'

    def add_arguments(self, parser):
        parser.add_argument('--base-url', default='http://127.0.0.1:8000')
        parser.add_argument('--timeout', type=int, default=30)

    def handle(self, *args, **options):
        base = options['base_url'].rstrip('/')
        identity = uuid.uuid4().hex
        password = uuid.uuid4().hex
        user = CustomUser.objects.create_user(
            email=f'tracking-smoke-{identity}@example.com', password=password,
            first_name='Smoke', middle_name='', last_name='Test', role=ROLE_LIBRARIAN, is_active=True,
        )
        book = Book.objects.create(name=f'Tracking smoke {identity[:8]}', count=1)
        jar = CookieJar()
        opener = build_opener(HTTPCookieProcessor(jar))

        def request(path, data=None, json_body=False, token=None):
            headers = {}
            body = None
            if data is not None:
                body = json.dumps(data).encode() if json_body else urlencode(data).encode()
                headers['Content-Type'] = 'application/json' if json_body else 'application/x-www-form-urlencoded'
            if token:
                headers['X-CSRFToken'] = token
            with opener.open(Request(base + path, data=body, headers=headers), timeout=10) as response:
                return response.status, response.read().decode()

        def csrf(html):
            match = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', html)
            if not match:
                raise CommandError('Page did not supply a CSRF token.')
            return match.group(1)

        def wait(predicate, label):
            deadline = time.monotonic() + options['timeout']
            while time.monotonic() < deadline:
                if predicate():
                    return
                time.sleep(0.1)
            raise CommandError(f'Timed out waiting for {label}. Check the worker logs.')

        def recorded(kind):
            return UserEvent.objects.filter(user=user, event_type=kind).exists()

        try:
            _, html = request('/authentication/login/')
            request('/authentication/login/', {'email': user.email, 'password': password, 'csrfmiddlewaretoken': csrf(html)})
            wait(lambda: recorded(EventType.LOGIN), 'login event')
            _, html = request('/book/?q=tracking')
            token = csrf(html)
            request(f'/book/{book.pk}/')
            client_data = {'event_id': str(uuid.uuid4()), 'event_type': 'book_click', 'book_id': book.pk, 'path': '/book/'}
            status, body = request('/api/v1/events/', client_data, json_body=True, token=token)
            if status != 202:
                raise CommandError(f'Expected HTTP 202, got {status}.')
            event_id = json.loads(body)['event_id']
            _, repeated = request('/api/v1/events/', client_data, json_body=True, token=token)
            if json.loads(repeated)['event_id'] != event_id:
                raise CommandError('Duplicate request changed the event identity.')
            wait(lambda: UserEvent.objects.filter(pk=event_id).exists(), 'client event')
            if UserEvent.objects.filter(pk=event_id).count() != 1:
                raise CommandError('Client event was counted twice.')
            request(f'/order/create/{book.pk}/', {'days': 14, 'csrfmiddlewaretoken': token})
            order = Order.objects.filter(user=user, book=book).first()
            if order is None:
                raise CommandError('HTTP book issuance failed.')
            wait(lambda: recorded(EventType.ORDER_CREATED), 'issuance event')
            request(f'/order/close/{order.pk}/', {'csrfmiddlewaretoken': token})
            wait(lambda: recorded(EventType.ORDER_RETURNED), 'return event')
            wait(lambda: recorded(EventType.BOOK_VIEW) and recorded(EventType.SEARCH), 'view/search events')
            _, html = request('/events/')
            if book.name not in html or 'Activity Analytics' not in html:
                raise CommandError('Analytics UI did not display the tracked book.')
            _, profile_html = request(f'/authentication/users/{user.pk}/')
            if 'User activity' not in profile_html or book.name not in profile_html:
                raise CommandError('User profile did not display scoped activity.')
            request('/authentication/logout/')
            wait(lambda: recorded(EventType.LOGOUT), 'logout event')
            self.stdout.write(self.style.SUCCESS(
                'PASS: real HTTP 202, Redis/worker persistence, deduplication, login/logout, '
                'view/search, issuance/return and global/user-profile analytics UI.'
            ))
        except HTTPError as error:
            raise CommandError(f'HTTP smoke check failed: {error.code} {error.reason}') from error
        finally:
            UserEvent.objects.filter(user=user).delete()
            book.delete()
            user.delete()

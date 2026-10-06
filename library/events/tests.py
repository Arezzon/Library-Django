import uuid
from datetime import timedelta
from unittest.mock import patch

from celery.exceptions import Retry
from django.db import OperationalError, transaction
from django.test import Client, RequestFactory, TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from authentication.models import CustomUser, ROLE_LIBRARIAN
from book.models import Book
from order.models import BookUnavailableError, Order
from .middleware import EventTrackingMiddleware
from .models import EventType, UserEvent
from .services import EventQueueUnavailable, capture, current_request, make_payload
from .tasks import persist_event


def account(email='events@example.com', role=0):
    return CustomUser.objects.create_user(
        email=email, password='test-password', first_name='Event', middle_name='',
        last_name='Reader', is_active=True, role=role,
    )


class EventTests(TestCase):
    def setUp(self):
        self.user = account()
        self.book = Book.objects.create(name='Tracked book', count=5)
        self.client.force_login(self.user)
        patcher = patch('events.services.persist_event.apply_async')
        self.publish = patcher.start()
        self.addCleanup(patcher.stop)

    def payload(self):
        return self.publish.call_args.kwargs['args'][0]

    def request(self):
        request = RequestFactory().get('/book/')
        request.user = self.user
        return request

    def test_successful_book_view_publishes_without_inserting(self):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.get(f'/book/{self.book.pk}/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.payload()['event_type'], EventType.BOOK_VIEW)
        self.assertEqual(self.payload()['book_id'], self.book.pk)
        self.assertEqual(self.payload()['user_id'], self.user.pk)
        self.assertFalse(UserEvent.objects.exists())
        self.publish.assert_called_once()

    def test_search_tracks_only_allowed_bounded_properties(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.client.get('/book/', {'q': 'poetry' * 50, 'password': 'never-record-this', 'author_id': '1'})
        self.assertEqual(self.payload()['event_type'], EventType.SEARCH)
        self.assertEqual(len(self.payload()['properties']['query']), 200)
        self.assertEqual(self.payload()['properties']['author_id'], 1)
        self.assertNotIn('password', self.payload()['properties'])
        self.assertEqual(self.payload()['path'], '/book/')

    def test_anonymous_errors_and_catalog_without_filters_do_not_track(self):
        self.client.logout()
        self.client.get(f'/book/{self.book.pk}/')
        self.client.force_login(self.user)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.get('/book/999999/')
            self.client.get('/book/')
            self.client.get('/api/docs/')
            self.client.get('/api/v1/')
        self.publish.assert_not_called()

    def test_authenticated_api_detail_is_tracked(self):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.get(f'/api/v1/book/{self.book.pk}/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.payload()['event_type'], EventType.BOOK_VIEW)

    def test_login_and_logout_track_actor_without_credentials(self):
        client = Client()
        with self.captureOnCommitCallbacks(execute=True):
            response = client.post('/authentication/login/', {'email': self.user.email, 'password': 'test-password'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.payload()['event_type'], EventType.LOGIN)
        self.assertEqual(self.payload()['properties'], {})
        self.assertNotIn('password', str(self.payload()))
        self.publish.reset_mock()
        with self.captureOnCommitCallbacks(execute=True):
            client.get('/authentication/logout/')
        self.assertEqual(self.payload()['event_type'], EventType.LOGOUT)
        self.assertEqual(self.payload()['user_id'], self.user.pk)

    def test_failed_login_does_not_track_success(self):
        with self.captureOnCommitCallbacks(execute=True):
            Client().post('/authentication/login/', {'email': self.user.email, 'password': 'wrong'})
        self.publish.assert_not_called()

    def test_queue_failure_does_not_break_book_page(self):
        from kombu.exceptions import OperationalError as BrokerError
        self.publish.side_effect = BrokerError('queue unavailable')
        with self.assertLogs('events.services', level='ERROR'), self.captureOnCommitCallbacks(execute=True):
            response = self.client.get(f'/book/{self.book.pk}/')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(UserEvent.objects.exists())

    def test_context_is_reset_after_exception(self):
        def fail(request):
            self.assertIs(current_request.get(), request)
            raise RuntimeError('view failed')
        with self.assertRaises(RuntimeError):
            EventTrackingMiddleware(fail)(self.request())
        self.assertIsNone(current_request.get())

    def test_order_events_run_only_after_commit_and_capture_reader(self):
        librarian = account('librarian-events@example.com', ROLE_LIBRARIAN)
        request = self.request()
        request.user = librarian
        token = current_request.set(request)
        try:
            with self.captureOnCommitCallbacks(execute=True):
                order = Order.objects.create(user=self.user, book=self.book, plated_end_at=timezone.now() + timedelta(days=14))
                self.publish.assert_not_called()
            self.assertEqual(self.payload()['event_type'], EventType.ORDER_CREATED)
            self.assertEqual(self.payload()['user_id'], librarian.pk)
            self.assertEqual(self.payload()['properties']['reader_id'], self.user.pk)
            self.publish.reset_mock()
            with self.captureOnCommitCallbacks(execute=True):
                order.end_at = timezone.now()
                order.save(update_fields=['end_at'])
            self.assertEqual(self.payload()['event_type'], EventType.ORDER_RETURNED)
            self.publish.reset_mock()
            with self.captureOnCommitCallbacks(execute=True):
                order.save()
            self.publish.assert_not_called()
        finally:
            current_request.reset(token)

    def test_reopen_and_reassignment_are_tracked(self):
        order = Order.objects.create(user=self.user, book=self.book, plated_end_at=timezone.now(), end_at=timezone.now())
        token = current_request.set(self.request())
        try:
            with self.captureOnCommitCallbacks(execute=True):
                order.end_at = None
                order.save(update_fields=['end_at'])
            self.assertEqual(self.payload()['event_type'], EventType.ORDER_REOPENED)
            other = Book.objects.create(name='Another book')
            with self.captureOnCommitCallbacks(execute=True):
                order.book = other
                order.save(update_fields=['book'])
            self.assertEqual(self.payload()['event_type'], EventType.ORDER_REASSIGNED)
            self.assertEqual(self.payload()['book_id'], other.pk)
        finally:
            current_request.reset(token)

    def test_partial_order_update_does_not_report_unpersisted_return(self):
        order = Order.objects.create(user=self.user, book=self.book, plated_end_at=timezone.now())
        token = current_request.set(self.request())
        try:
            with self.captureOnCommitCallbacks(execute=True):
                order.end_at = timezone.now()
                order.plated_end_at = timezone.now() + timedelta(days=1)
                order.save(update_fields=['plated_end_at'])
            self.publish.assert_not_called()
        finally:
            current_request.reset(token)

    def test_rolled_back_order_does_not_publish(self):
        token = current_request.set(self.request())
        try:
            with self.captureOnCommitCallbacks(execute=True):
                with self.assertRaises(RuntimeError), transaction.atomic():
                    Order.objects.create(user=self.user, book=self.book, plated_end_at=timezone.now())
                    raise RuntimeError('rollback')
            self.assertFalse(Order.objects.exists())
            self.publish.assert_not_called()
        finally:
            current_request.reset(token)

    def test_rejected_issuance_and_seed_without_request_do_not_publish(self):
        book = Book.objects.create(name='Unavailable', count=0)
        token = current_request.set(self.request())
        try:
            with self.assertRaises(BookUnavailableError):
                Order.objects.create(user=self.user, book=book, plated_end_at=timezone.now())
        finally:
            current_request.reset(token)
        with self.captureOnCommitCallbacks(execute=True):
            Order.objects.create(user=self.user, book=self.book, plated_end_at=timezone.now())
        self.publish.assert_not_called()

    def test_worker_is_idempotent_and_preserves_occurrence_time(self):
        payload = make_payload(self.request(), EventType.BOOK_VIEW, book_id=self.book.pk)
        persist_event.run(payload)
        persist_event.run(payload)
        self.assertEqual(UserEvent.objects.count(), 1)
        event = UserEvent.objects.get()
        self.assertEqual(event.user, self.user)
        self.assertEqual(event.book_id, self.book.pk)
        self.assertEqual(event.occurred_at.isoformat(), payload['occurred_at'])
        self.assertGreaterEqual(event.recorded_at, event.occurred_at)

    def test_deleted_user_does_not_poison_queued_event(self):
        payload = make_payload(self.request(), EventType.BOOK_VIEW, book_id=self.book.pk)
        self.user.delete()
        persist_event.run(payload)
        self.assertIsNone(UserEvent.objects.get().user_id)

    def test_database_failure_retries_task(self):
        payload = make_payload(self.request(), EventType.BOOK_VIEW)
        with patch('events.tasks.UserEvent.objects.get_or_create', side_effect=OperationalError('db down')):
            with patch.object(persist_event, 'retry', side_effect=Retry('retry')) as retry:
                with self.assertRaises(Retry):
                    persist_event.run(payload)
                retry.assert_called_once()
        self.assertFalse(UserEvent.objects.exists())


class ClientTrackingTests(TestCase):
    def setUp(self):
        self.user = account()
        self.book = Book.objects.create(name='Tracked')
        self.client = APIClient()
        self.client.force_login(self.user)
        patcher = patch('events.services.persist_event.apply_async')
        self.publish = patcher.start()
        self.addCleanup(patcher.stop)
        self.data = {'event_id': str(uuid.uuid4()), 'event_type': 'book_click', 'book_id': self.book.pk, 'path': '/book/'}

    def test_endpoint_accepts_asynchronously_and_binds_identity(self):
        response = self.client.post('/api/v1/events/', self.data, format='json')
        self.assertEqual(response.status_code, 202)
        payload = self.publish.call_args.kwargs['args'][0]
        self.assertEqual(payload['user_id'], self.user.pk)
        self.assertEqual(payload['source'], 'client')
        self.assertEqual(response.json()['event_id'], payload['id'])
        self.assertFalse(UserEvent.objects.exists())

    def test_same_client_uuid_is_deduplicated_and_user_scoped(self):
        self.client.post('/api/v1/events/', self.data, format='json')
        first = self.publish.call_args.kwargs['args'][0]
        self.client.post('/api/v1/events/', self.data, format='json')
        second = self.publish.call_args.kwargs['args'][0]
        self.assertEqual(first['id'], second['id'])
        persist_event.run(first)
        persist_event.run(second)
        self.assertEqual(UserEvent.objects.count(), 1)
        other = account('another-events@example.com')
        self.client.force_login(other)
        self.client.post('/api/v1/events/', self.data, format='json')
        third = self.publish.call_args.kwargs['args'][0]
        self.assertNotEqual(first['id'], third['id'])
        persist_event.run(third)
        self.assertEqual(UserEvent.objects.count(), 2)

    def test_anonymous_and_missing_csrf_are_rejected(self):
        self.assertIn(APIClient().post('/api/v1/events/', self.data, format='json').status_code, (401, 403))
        secure = APIClient(enforce_csrf_checks=True)
        secure.force_login(self.user)
        self.assertEqual(secure.post('/api/v1/events/', self.data, format='json').status_code, 403)
        self.publish.assert_not_called()

    def test_session_csrf_from_catalog_is_accepted(self):
        secure = APIClient(enforce_csrf_checks=True)
        secure.force_login(self.user)
        page = secure.get('/book/')
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'events/tracking')
        response = secure.post('/api/v1/events/', self.data, format='json', HTTP_X_CSRFTOKEN=secure.cookies['csrftoken'].value)
        self.assertEqual(response.status_code, 202)

    def test_invalid_or_forged_payloads_are_rejected(self):
        mutations = [
            {'event_type': 'order_created'}, {'book_id': 999999}, {'event_id': 'invalid'},
            {'path': 'https://external.example/'}, {'path': '/authentication/login/?password=secret'},
            {'user_id': self.user.pk}, {'properties': {'password': 'secret'}}, {'source': 'server'},
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                response = self.client.post('/api/v1/events/', {**self.data, **mutation}, format='json')
                self.assertEqual(response.status_code, 400)
        self.publish.assert_not_called()

    def test_queue_failure_returns_retryable_503(self):
        from kombu.exceptions import OperationalError as BrokerError
        self.publish.side_effect = BrokerError('broker down')
        response = self.client.post('/api/v1/events/', self.data, format='json')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response['Retry-After'], '5')
        self.assertFalse(UserEvent.objects.exists())


class AnalyticsTests(TestCase):
    def setUp(self):
        self.reader = account()
        self.librarian = account('analytics@example.com', ROLE_LIBRARIAN)
        self.book = Book.objects.create(name='Popular book')

    def event(self, event_type, **kwargs):
        return UserEvent.objects.create(user=self.reader, event_type=event_type, source='server',
                                        occurred_at=kwargs.pop('occurred_at', timezone.now()), **kwargs)

    def test_dashboard_is_librarian_only_and_navigation_matches_role(self):
        self.assertRedirects(self.client.get('/events/'), '/authentication/login/', fetch_redirect_response=False)
        self.client.force_login(self.reader)
        response = self.client.get('/events/')
        self.assertEqual(response.status_code, 302)
        self.assertNotContains(self.client.get('/book/'), 'Activity Analytics')
        self.client.force_login(self.librarian)
        response = self.client.get('/events/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Activity Analytics')
        self.assertContains(response, 'No activity yet')

    def test_counts_chart_ranking_and_event_filters(self):
        self.event(EventType.BOOK_VIEW, book_id=self.book.pk)
        self.event(EventType.BOOK_CLICK, book_id=self.book.pk)
        self.event(EventType.ORDER_CREATED, book_id=self.book.pk)
        self.event(EventType.SEARCH, properties={'query': 'poetry'})
        self.event(EventType.BOOK_VIEW, occurred_at=timezone.now() - timedelta(days=40))
        self.client.force_login(self.librarian)
        response = self.client.get('/events/')
        self.assertEqual(response.context['summary'], {'total': 4, 'users': 1, 'views': 1, 'borrows': 1})
        self.assertEqual(response.context['popular'][0]['total'], 2)
        self.assertEqual(sum(bar['total'] for bar in response.context['bars']), 4)
        self.assertContains(response, 'Popular book')
        filtered = self.client.get('/events/', {'event_type': 'book_view', 'days': '90'})
        self.assertEqual(filtered.context['summary']['total'], 2)

    def test_pagination_preserves_filters_and_escapes_search_text(self):
        for _ in range(26):
            self.event(EventType.SEARCH, properties={'query': '<script>alert(1)</script>'})
        self.client.force_login(self.librarian)
        response = self.client.get('/events/', {'days': '30', 'event_type': 'search'})
        self.assertEqual(len(response.context['page_obj']), 25)
        self.assertContains(response, 'days=30&amp;event_type=search&amp;page=2')
        self.assertContains(response, '&lt;script&gt;alert(1)&lt;/script&gt;')
        self.assertNotContains(response, '<script>alert(1)</script>')
        second = self.client.get('/events/', {'days': '30', 'event_type': 'search', 'page': 2})
        self.assertEqual(len(second.context['page_obj']), 1)

    def test_deleted_book_and_user_remain_readable_and_invalid_filters_are_safe(self):
        self.event(EventType.BOOK_VIEW, book_id=self.book.pk)
        book_id = self.book.pk
        self.book.delete()
        self.reader.delete()
        self.client.force_login(self.librarian)
        response = self.client.get('/events/', {'days': 'bad', 'event_type': 'bad', 'page': 'bad'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['days'], 7)
        self.assertContains(response, f'Deleted book #{book_id}')
        self.assertContains(response, 'Deleted user')


class UserProfileActivityTests(TestCase):
    def setUp(self):
        self.user = account('profile@example.com')
        self.other = account('other-profile@example.com')
        self.librarian = account('profile-librarian@example.com', ROLE_LIBRARIAN)
        self.book = Book.objects.create(name='Profile favorite')

    def event(self, user, event_type=EventType.SEARCH, **kwargs):
        return UserEvent.objects.create(user=user, event_type=event_type, source='server',
                                       occurred_at=kwargs.pop('occurred_at', timezone.now()), **kwargs)

    def test_librarian_sees_only_selected_users_activity(self):
        self.event(self.user, EventType.BOOK_VIEW, book_id=self.book.pk)
        self.event(self.user, properties={'query': 'profile-search'})
        self.event(self.other, properties={'query': 'other-only-marker'})
        self.client.force_login(self.librarian)
        response = self.client.get(f'/authentication/users/{self.user.pk}/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'User activity')
        self.assertContains(response, 'Profile favorite')
        self.assertContains(response, 'profile-search')
        self.assertNotContains(response, 'other-only-marker')
        self.assertEqual(response.context['summary']['total'], 2)
        self.assertEqual(response.context['summary']['users'], 1)
        self.assertEqual(response.context['summary']['views'], 1)
        self.assertEqual(response.context['summary']['searches'], 1)
        self.assertEqual(sum(bar['total'] for bar in response.context['bars']), 2)
        self.assertContains(response, f'/authentication/users/{self.user.pk}/?days=7')

    def test_owner_cannot_see_or_query_analytics(self):
        self.event(self.user, properties={'query': 'private-activity-marker'})
        self.client.force_login(self.user)
        with patch('events.analytics.build_analytics_context') as analytics:
            response = self.client.get(f'/authentication/users/{self.user.pk}/')
        analytics.assert_not_called()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.user.email)
        self.assertNotContains(response, 'User activity')
        self.assertNotContains(response, 'private-activity-marker')
        with self.assertRaises(KeyError):
            response.context['summary']

    def test_other_reader_cannot_open_profile(self):
        self.client.force_login(self.other)
        response = self.client.get(f'/authentication/users/{self.user.pk}/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/')

    def test_profile_filters_and_pagination_remain_scoped(self):
        for _ in range(26):
            self.event(self.user, properties={'query': 'scoped'})
        self.event(self.user, EventType.BOOK_VIEW)
        self.event(self.other, properties={'query': 'never-show-other'})
        self.event(self.user, occurred_at=timezone.now()-timedelta(days=40), properties={'query': 'old'})
        self.client.force_login(self.librarian)
        url = f'/authentication/users/{self.user.pk}/'
        response = self.client.get(url, {'days': '7', 'event_type': 'search'})
        self.assertEqual(response.context['summary']['total'], 26)
        self.assertEqual(len(response.context['page_obj']), 25)
        self.assertContains(response, 'days=7&amp;event_type=search&amp;page=2')
        second = self.client.get(url, {'days': '7', 'event_type': 'search', 'page': 2})
        self.assertEqual(len(second.context['page_obj']), 1)
        self.assertNotContains(second, 'never-show-other')
        longer = self.client.get(url, {'days': '90', 'event_type': 'search'})
        self.assertEqual(longer.context['summary']['total'], 27)

    def test_empty_profile_and_observer_do_not_add_user_events(self):
        self.client.force_login(self.librarian)
        with patch('events.services.persist_event.apply_async') as publish:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.get(f'/authentication/users/{self.user.pk}/')
            publish.assert_not_called()
        self.assertContains(response, 'This user has no tracked actions in the selected period.')
        self.assertEqual(response.context['summary']['total'], 0)

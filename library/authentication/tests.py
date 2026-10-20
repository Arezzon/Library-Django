from django.urls import path
from django.test import Client, SimpleTestCase, override_settings
from .models import CustomUser


def failing_view(request):
    raise RuntimeError('production diagnostic regression')


urlpatterns = [path('diagnostic-error/', failing_view)]


@override_settings(DEBUG=False, ROOT_URLCONF=__name__)
class ProductionErrorLoggingTests(SimpleTestCase):
    def test_server_error_includes_traceback_in_console_without_debug(self):
        import io
        import logging
        from unittest.mock import patch
        logger = logging.getLogger('django.request')
        self.assertTrue(logger.handlers)
        stream = io.StringIO()
        with patch.object(logger.handlers[0], 'stream', stream):
            response = Client(raise_request_exception=False).get('/diagnostic-error/')
        self.assertEqual(response.status_code, 500)
        self.assertIn('Traceback (most recent call last)', stream.getvalue())
        self.assertIn('RuntimeError: production diagnostic regression', stream.getvalue())
        self.assertNotContains(response, 'production diagnostic regression', status_code=500)

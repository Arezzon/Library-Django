"""Render HTTPS forwarding must permit same-origin forms and retain CSRF checks."""
import os
import subprocess
import sys

from django.urls import path
from django.test import Client, SimpleTestCase, TestCase, override_settings
from .models import CustomUser


class RenderSettingsTests(SimpleTestCase):
    def test_proxy_header_is_enabled_only_on_render(self):
        for render, expected in [('true', "('HTTP_X_FORWARDED_PROTO', 'https')"), ('false', 'None')]:
            result = subprocess.check_output(
                [sys.executable, '-c', 'import library.settings as s; print(getattr(s, "SECURE_PROXY_SSL_HEADER", None))'],
                env=dict(os.environ, RENDER=render), text=True)
            self.assertEqual(result.strip(), expected)


@override_settings(SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO', 'https'))
class RenderLoginTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            email='render@example.com', password='render-password', first_name='Render',
            middle_name='', last_name='Test', is_active=True)
        self.client = Client(enforce_csrf_checks=True)
        self.client.get('/authentication/login/')
        self.payload = {'email': self.user.email, 'password': 'render-password',
                        'csrfmiddlewaretoken': self.client.cookies['csrftoken'].value}

    def test_same_origin_https_login_behind_proxy(self):
        response = self.client.post('/authentication/login/', self.payload,
            HTTP_HOST='testserver', HTTP_X_FORWARDED_PROTO='https', HTTP_ORIGIN='https://testserver')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(int(self.client.session['_auth_user_id']), self.user.pk)

    def test_foreign_origin_is_rejected(self):
        response = self.client.post('/authentication/login/', self.payload,
            HTTP_HOST='testserver', HTTP_X_FORWARDED_PROTO='https', HTTP_ORIGIN='https://foreign.example')
        self.assertEqual(response.status_code, 403)
        self.assertNotIn('_auth_user_id', self.client.session)


def failing_view(request):
    raise RuntimeError('render diagnostic regression')


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
        self.assertIn('RuntimeError: render diagnostic regression', stream.getvalue())
        self.assertNotContains(response, 'render diagnostic regression', status_code=500)

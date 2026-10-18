"""Render HTTPS forwarding must permit same-origin forms and retain CSRF checks."""
import json
import os
import subprocess
import sys

from django.conf import settings
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


# Settings inputs; a developer's .env must not leak into the checks below.
SETTINGS_ENV = ('SECRET_KEY', 'DEBUG', 'DATABASE_URL', 'DB_ENGINE', 'DB_NAME', 'DB_USER',
                'DB_PASSWORD', 'DB_HOST', 'DB_PORT')


def import_settings(expression, **env):
    """Print a settings expression from a fresh process configured only by ``env``; None unsets."""
    environment = {key: value for key, value in os.environ.items() if key not in SETTINGS_ENV}
    environment.update({'SECRET_KEY': 'test-secret-key', **env})
    environment = {key: value for key, value in environment.items() if value is not None}
    code = ('import json, dotenv; dotenv.load_dotenv = lambda *args, **kwargs: False; '
            'import library.settings as s; print(json.dumps(' + expression + '))')
    return subprocess.run([sys.executable, '-c', code], env=environment, cwd=settings.BASE_DIR,
                          capture_output=True, text=True)


class EnvironmentSettingsTests(SimpleTestCase):
    def assertSetting(self, expression, expected, **env):
        result = import_settings(expression, **env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), expected)

    def assertStartupFails(self, setting, **env):
        result = import_settings('None', **env)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        error = result.stderr.strip().splitlines()[-1]
        self.assertIn('ImproperlyConfigured', error)
        self.assertIn(setting, error)

    def test_startup_requires_a_secret_key_even_in_debug(self):
        for value in (None, '', '   '):
            with self.subTest(secret_key=value):
                self.assertStartupFails('SECRET_KEY', SECRET_KEY=value, DEBUG='True')

    def test_debug_is_disabled_unless_explicitly_enabled(self):
        for value, expected in [(None, False), ('', False), ('False', False), ('True', True)]:
            with self.subTest(debug=value):
                self.assertSetting('s.DEBUG', expected, DEBUG=value)

    def test_database_password_has_no_default(self):
        self.assertSetting("s.DATABASES['default']['PASSWORD']", '')
        self.assertSetting("s.DATABASES['default']['PASSWORD']", 'from-environment',
                           DB_PASSWORD='from-environment')

    def test_database_url_takes_precedence_over_db_variables(self):
        engine = 'django.db.backends.postgresql'
        cases = [
            ('postgresql://reader:p%40ss%3Aword@db.example.com:6543/catalog?sslmode=require',
             {'ENGINE': engine, 'NAME': 'catalog', 'USER': 'reader', 'PASSWORD': 'p@ss:word',
              'HOST': 'db.example.com', 'PORT': '6543', 'OPTIONS': {'sslmode': 'require'}}),
            # Hosted connection strings may omit the default port.
            ('postgres://library_user:secret@dpg-internal-a/library_db',
             {'ENGINE': engine, 'NAME': 'library_db', 'USER': 'library_user', 'PASSWORD': 'secret',
              'HOST': 'dpg-internal-a', 'PORT': '', 'OPTIONS': {}}),
        ]
        for url, expected in cases:
            with self.subTest(url=url):
                self.assertSetting("s.DATABASES['default']", expected, DATABASE_URL=url,
                                   DB_NAME='ignored', DB_USER='ignored', DB_PASSWORD='ignored',
                                   DB_HOST='ignored', DB_PORT='1')

    def test_database_url_must_point_to_postgresql(self):
        self.assertStartupFails('DATABASE_URL', DATABASE_URL='mysql://reader:secret@db.example.com/catalog')


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

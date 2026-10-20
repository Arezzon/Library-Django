"""Project-wide settings and wiring: proxy and host settings, environment-driven
configuration, the version endpoint and the Gunicorn config.

Behind an HTTPS proxy, same-origin forms must work and CSRF checks must remain."""

import json
import os
import subprocess
import sys

from django.conf import settings
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import path

from .models import CustomUser

# Settings inputs; a developer's .env must not leak into the checks below.
SETTINGS_ENV = (
    "SECRET_KEY",
    "DEBUG",
    "DATABASE_URL",
    "DB_ENGINE",
    "DB_NAME",
    "DB_USER",
    "DB_PASSWORD",
    "DB_HOST",
    "DB_PORT",
    "TRUST_X_FORWARDED_PROTO",
    "CSRF_TRUSTED_ORIGINS",
    "ALLOWED_HOSTS",
    "RENDER",
)


def import_settings(expression, **env):
    """Print a settings expression from a fresh process configured only by ``env``; None unsets."""
    environment = {
        key: value for key, value in os.environ.items() if key not in SETTINGS_ENV
    }
    environment.update({"SECRET_KEY": "test-secret-key", **env})
    environment = {
        key: value for key, value in environment.items() if value is not None
    }
    code = (
        "import json, dotenv; dotenv.load_dotenv = lambda *args, **kwargs: False; "
        "import library.settings as s; print(json.dumps(" + expression + "))"
    )
    return subprocess.run(
        [sys.executable, "-c", code],
        env=environment,
        cwd=settings.BASE_DIR,
        capture_output=True,
        text=True,
    )


class EnvironmentSettingsTests(SimpleTestCase):
    def assertSetting(self, expression, expected, **env):
        result = import_settings(expression, **env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), expected)

    def assertStartupFails(self, setting, **env):
        result = import_settings("None", **env)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        error = result.stderr.strip().splitlines()[-1]
        self.assertIn("ImproperlyConfigured", error)
        self.assertIn(setting, error)

    def test_startup_requires_a_secret_key_even_in_debug(self):
        for value in (None, "", "   "):
            with self.subTest(secret_key=value):
                self.assertStartupFails("SECRET_KEY", SECRET_KEY=value, DEBUG="True")

    def test_debug_is_disabled_unless_explicitly_enabled(self):
        for value, expected in [
            (None, False),
            ("", False),
            ("False", False),
            ("True", True),
        ]:
            with self.subTest(debug=value):
                self.assertSetting("s.DEBUG", expected, DEBUG=value)

    def test_database_password_has_no_default(self):
        self.assertSetting("s.DATABASES['default']['PASSWORD']", "")
        self.assertSetting(
            "s.DATABASES['default']['PASSWORD']",
            "from-environment",
            DB_PASSWORD="from-environment",
        )

    def test_database_url_takes_precedence_over_db_variables(self):
        engine = "django.db.backends.postgresql"
        cases = [
            (
                "postgresql://reader:p%40ss%3Aword@db.example.com:6543/catalog?sslmode=require",
                {
                    "ENGINE": engine,
                    "NAME": "catalog",
                    "USER": "reader",
                    "PASSWORD": "p@ss:word",
                    "HOST": "db.example.com",
                    "PORT": "6543",
                    "OPTIONS": {"sslmode": "require"},
                },
            ),
            # Hosted connection strings may omit the default port.
            (
                "postgres://library_user:secret@dpg-internal-a/library_db",
                {
                    "ENGINE": engine,
                    "NAME": "library_db",
                    "USER": "library_user",
                    "PASSWORD": "secret",
                    "HOST": "dpg-internal-a",
                    "PORT": "",
                    "OPTIONS": {},
                },
            ),
        ]
        for url, expected in cases:
            with self.subTest(url=url):
                self.assertSetting(
                    "s.DATABASES['default']",
                    expected,
                    DATABASE_URL=url,
                    DB_NAME="ignored",
                    DB_USER="ignored",
                    DB_PASSWORD="ignored",
                    DB_HOST="ignored",
                    DB_PORT="1",
                )

    def test_forwarded_https_is_trusted_only_when_enabled(self):
        expression = 'getattr(s, "SECURE_PROXY_SSL_HEADER", None)'
        for value in ("True", "true", "TRUE", " true ", "1", "yes", "on"):
            with self.subTest(trust=value):
                self.assertSetting(
                    expression,
                    ["HTTP_X_FORWARDED_PROTO", "https"],
                    TRUST_X_FORWARDED_PROTO=value,
                )
        for value in (None, "", "False", "false", "0", "no", "off"):
            with self.subTest(trust=value):
                self.assertSetting(expression, None, TRUST_X_FORWARDED_PROTO=value)

    def test_unrecognized_proxy_trust_value_stops_startup(self):
        # A typo must not silently leave HTTPS detection off behind the proxy.
        for value in ("ture", "enabled", "2"):
            with self.subTest(trust=value):
                self.assertStartupFails(
                    "TRUST_X_FORWARDED_PROTO", TRUST_X_FORWARDED_PROTO=value
                )

    def test_allowed_hosts_are_platform_neutral(self):
        self.assertSetting(
            "s.ALLOWED_HOSTS",
            ["library.example.com", "other.example", "localhost", "127.0.0.1"],
            ALLOWED_HOSTS="library.example.com, other.example",
        )

    def test_render_no_longer_enables_the_proxy_header(self):
        self.assertSetting(
            'getattr(s, "SECURE_PROXY_SSL_HEADER", None)', None, RENDER="true"
        )

    def test_csrf_trusted_origins_come_from_a_comma_list(self):
        self.assertSetting("s.CSRF_TRUSTED_ORIGINS", [])
        self.assertSetting(
            "s.CSRF_TRUSTED_ORIGINS",
            ["https://a.example", "https://b.example"],
            CSRF_TRUSTED_ORIGINS=" https://a.example ,https://b.example,",
        )

    def test_database_url_must_point_to_postgresql(self):
        self.assertStartupFails(
            "DATABASE_URL", DATABASE_URL="mysql://reader:secret@db.example.com/catalog"
        )


@override_settings(SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"))
class ProxyLoginTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            email="proxy@example.com",
            password="proxy-password",
            first_name="Proxy",
            middle_name="",
            last_name="Test",
            is_active=True,
        )
        self.client = Client(enforce_csrf_checks=True)
        self.client.get("/authentication/login/")
        self.payload = {
            "email": self.user.email,
            "password": "proxy-password",
            "csrfmiddlewaretoken": self.client.cookies["csrftoken"].value,
        }

    def test_same_origin_https_login_behind_proxy(self):
        response = self.client.post(
            "/authentication/login/",
            self.payload,
            HTTP_HOST="testserver",
            HTTP_X_FORWARDED_PROTO="https",
            HTTP_ORIGIN="https://testserver",
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    def test_foreign_origin_is_rejected(self):
        response = self.client.post(
            "/authentication/login/",
            self.payload,
            HTTP_HOST="testserver",
            HTTP_X_FORWARDED_PROTO="https",
            HTTP_ORIGIN="https://foreign.example",
        )
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("_auth_user_id", self.client.session)


class VersionEndpointTests(SimpleTestCase):
    """GET /api/v1/version/: anonymous, read-only, commit only, no database."""

    url = "/api/v1/version/"

    def get(self, **env):
        from unittest.mock import patch

        environment = {k: v for k, v in os.environ.items() if k != "APP_COMMIT"}
        environment.update(env)
        with patch.dict(os.environ, environment, clear=True):
            return Client().get(self.url)

    def test_anonymous_get_returns_only_the_commit(self):
        response = self.get(APP_COMMIT="0123456789abcdef0123456789abcdef01234567")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(), {"commit": "0123456789abcdef0123456789abcdef01234567"}
        )
        self.assertEqual(response["Cache-Control"], "no-store")

    def test_unset_or_empty_commit_is_unknown(self):
        self.assertEqual(self.get().json(), {"commit": "unknown"})
        self.assertEqual(self.get(APP_COMMIT="").json(), {"commit": "unknown"})

    def test_other_methods_are_not_allowed(self):
        for method in ("post", "put", "patch", "delete"):
            with self.subTest(method=method):
                self.assertEqual(getattr(Client(), method)(self.url).status_code, 405)

    def test_endpoint_is_in_the_api_schema(self):
        response = Client().get("/api/schema/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            "/api/v1/version/:" in response.content.decode(),
            "/api/v1/version/ is missing from /api/schema/",
        )


class GunicornConfigTests(SimpleTestCase):
    """library/gunicorn.conf.py: worker count from the stack and a warm model."""

    def load(self, **env):
        import importlib.util
        from unittest.mock import patch

        path = settings.BASE_DIR / "gunicorn.conf.py"
        spec = importlib.util.spec_from_file_location("gunicorn_conf", path)
        module = importlib.util.module_from_spec(spec)
        environment = {k: v for k, v in os.environ.items() if k != "WEB_CONCURRENCY"}
        environment.update(env)
        with patch.dict(os.environ, environment, clear=True):
            spec.loader.exec_module(module)
        return module

    def test_workers_follow_web_concurrency_with_a_60s_timeout(self):
        self.assertEqual(self.load().workers, 3)
        self.assertEqual(self.load(WEB_CONCURRENCY="2").workers, 2)
        self.assertEqual(self.load().timeout, 60)

    def test_each_worker_loads_the_model_before_serving(self):
        from unittest.mock import MagicMock, patch

        with patch("book.embeddings.load_embedding_model") as load:
            self.load().post_worker_init(MagicMock())
        load.assert_called_once_with()


def failing_view(request):
    raise RuntimeError("diagnostic regression")


urlpatterns = [path("diagnostic-error/", failing_view)]


@override_settings(DEBUG=False, ROOT_URLCONF=__name__)
class ProductionErrorLoggingTests(SimpleTestCase):
    def test_server_error_includes_traceback_in_console_without_debug(self):
        import io
        import logging
        from unittest.mock import patch

        logger = logging.getLogger("django.request")
        self.assertTrue(logger.handlers)
        stream = io.StringIO()
        with patch.object(logger.handlers[0], "stream", stream):
            response = Client(raise_request_exception=False).get("/diagnostic-error/")
        self.assertEqual(response.status_code, 500)
        self.assertIn("Traceback (most recent call last)", stream.getvalue())
        self.assertIn("RuntimeError: diagnostic regression", stream.getvalue())
        self.assertNotContains(response, "diagnostic regression", status_code=500)

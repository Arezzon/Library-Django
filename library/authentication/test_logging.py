"""One log line format, the request id and redaction (contracts/logs-and-audit.md)."""

import io
import logging
import os
import re
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import path

from library.celery import clear_request_id, restore_request_id, send_request_id
from library.logs import (
    ContextFilter,
    LineFormatter,
    build_logging_config,
    request_id,
)

from .models import CustomUser

HEADER = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z"
HEX_ID = re.compile(r"^[0-9a-f]{32}$")


def render(message, *args, exc_info=None, name="tests", level=logging.INFO):
    record = logging.LogRecord(name, level, __file__, 1, message, args, exc_info)
    ContextFilter("web").filter(record)
    return LineFormatter().format(record)


@contextmanager
def captured_logs():
    """Collect what the configured console handler writes."""
    handler = logging.getLogger("django.request").handlers[0]
    stream = io.StringIO()
    with patch.object(handler, "stream", stream):
        yield stream


def failing_view(request):
    raise RuntimeError("diagnostic regression")


urlpatterns = [path("diagnostic-error/", failing_view)]


class LineFormatTests(SimpleTestCase):
    def test_a_record_renders_the_header_and_the_message(self):
        self.assertRegex(
            render("Hello %s", "world"), rf"^{HEADER} INFO web - tests: Hello world$"
        )

    def test_a_record_inside_a_request_carries_its_id(self):
        token = request_id.set("abcdef0123456789")
        try:
            line = render("Inside")
        finally:
            request_id.reset(token)
        self.assertRegex(line, rf"^{HEADER} INFO web abcdef0123456789 tests: Inside$")

    def test_every_traceback_line_repeats_the_header(self):
        try:
            raise RuntimeError("boom")
        except RuntimeError:
            import sys

            lines = render("Failed", exc_info=sys.exc_info(), level=logging.ERROR)
        first, *rest = lines.splitlines()
        self.assertRegex(first, rf"^{HEADER} ERROR web - tests: Failed$")
        self.assertTrue(rest)
        for line in rest:
            self.assertRegex(line, rf"^{HEADER} ERROR web - \| ")
        self.assertIn("RuntimeError: boom", rest[-1])

    def test_a_stack_trace_repeats_the_header_too(self):
        record = logging.LogRecord(
            "tests", logging.INFO, __file__, 1, "Here", (), None, sinfo="Stack:\n  x"
        )
        ContextFilter("web").filter(record)
        for line in LineFormatter().format(record).splitlines()[1:]:
            self.assertRegex(line, rf"^{HEADER} INFO web - \| ")

    def test_a_newline_in_user_input_cannot_start_a_line_of_its_own(self):
        lines = render(
            "Value: %s", "x\n2026-10-27T10:15:30.123Z INFO web - forged: line"
        )
        for line in lines.splitlines()[1:]:
            self.assertRegex(line, rf"^{HEADER} INFO web - \| ")


class LevelTests(SimpleTestCase):
    def test_an_unknown_level_stops_startup_naming_the_setting(self):
        with self.assertRaisesMessage(
            ValueError,
            "LOG_LEVEL must be one of DEBUG, INFO, WARNING, ERROR, CRITICAL, "
            "not 'VERBOSE'.",
        ):
            build_logging_config("web", "verbose")

    def test_refused_requests_stay_warnings_unless_the_level_is_stricter(self):
        levels = {
            level: build_logging_config("web", level)["loggers"]["django.request"][
                "level"
            ]
            for level in ("debug", "INFO", "ERROR")
        }
        self.assertEqual(
            levels, {"debug": "WARNING", "INFO": "WARNING", "ERROR": "ERROR"}
        )


class RedactionTests(SimpleTestCase):
    def test_secrets_and_search_text_never_reach_a_line(self):
        secret, db_password = "secret-key-value-0123456789", "db-password-value-42"
        cases = [
            ("password=hunter22 next", "hunter22", "password=[redacted]"),
            ("{'password': 'hunter22'}", "hunter22", "[redacted]"),
            ('{"password": "correct horse"}', "horse", '"password": "[redacted]"'),
            (f"settings {secret}", secret, "[redacted]"),
            (f"connect {db_password}", db_password, "[redacted]"),
            ("sessionid=abc123def", "abc123def", "sessionid=[redacted]"),
            ("csrftoken=tok987654", "tok987654", "csrftoken=[redacted]"),
            ("csrfmiddlewaretoken=mw0001", "mw0001", "csrfmiddlewaretoken=[redacted]"),
            ("Cookie: sessionid=c1; csrftoken=c2", "c1", "Cookie: [redacted]"),
            ("Authorization: Bearer abc.def", "abc.def", "Authorization: [redacted]"),
            ("postgres://library:pa55word@db:5432/x", "pa55word", "library:***@db"),
            ("GET /book/?q=private+words&page=2", "private", "q=[redacted]&page=2"),
        ]
        env = {"SECRET_KEY": secret, "DB_PASSWORD": db_password}
        with patch.dict(os.environ, env):
            for message, hidden, shown in cases:
                with self.subTest(message=message):
                    line = render("%s", message)
                    self.assertNotIn(hidden, line)
                    self.assertIn(shown, line)

    def test_names_of_errors_stay_readable(self):
        self.assertIn("KeyError: 'name'", render("%s", "KeyError: 'name'"))


class RequestIdTests(TestCase):
    def test_a_request_without_an_id_gets_a_new_one(self):
        response = Client().get("/authentication/login/")
        self.assertRegex(response["X-Request-ID"], HEX_ID)

    def test_a_valid_incoming_id_is_kept(self):
        response = Client().get(
            "/authentication/login/", headers={"X-Request-ID": "client.id-0001_ok"}
        )
        self.assertEqual(response["X-Request-ID"], "client.id-0001_ok")

    def test_an_invalid_incoming_id_is_replaced(self):
        for value in ("short", "has space-in-it", "x" * 65, "semi;colon-0001"):
            with self.subTest(value=value):
                response = Client().get(
                    "/authentication/login/", headers={"X-Request-ID": value}
                )
                self.assertRegex(response["X-Request-ID"], HEX_ID)

    def test_a_refused_request_logs_its_path_and_id_but_not_its_query(self):
        with captured_logs() as stream:
            Client().get(
                "/api/v1/user/?q=private", headers={"X-Request-ID": "refused-0001"}
            )
        self.assertRegex(
            stream.getvalue(),
            rf"{HEADER} WARNING web refused-0001 django.request: Unauthorized: "
            r"/api/v1/user/\n",
        )
        self.assertNotIn("private", stream.getvalue())


class CeleryRequestIdTests(SimpleTestCase):
    def test_a_published_task_carries_the_request_id(self):
        headers = {}
        token = request_id.set("published-0001")
        try:
            send_request_id(headers=headers)
        finally:
            request_id.reset(token)
        self.assertEqual(headers["request_id"], "published-0001")

    def test_the_worker_restores_the_id_or_uses_the_task_id(self):
        for header, expected in (
            ("from-header-01", "from-header-01"),
            (None, "task-77"),
        ):
            with self.subTest(header=header):
                task = SimpleNamespace(request=SimpleNamespace(request_id=header))
                restore_request_id(task_id="task-77", task=task)
                self.assertEqual(request_id.get(), expected)
                clear_request_id(task_id="task-77", task=task)
                self.assertIsNone(request_id.get())


class FailedSignInTests(TestCase):
    def test_a_failed_sign_in_names_the_account_by_id_only(self):
        account = CustomUser.objects.create_user(
            email="signin-log@example.com",
            password="right-password-1",
            first_name="Log",
            middle_name="",
            last_name="Test",
            is_active=True,
        )
        attempts = [
            ("signin-log@example.com", f"Sign-in failed for account #{account.pk}"),
            ("nobody@example.com", "Sign-in failed for an unknown account"),
        ]
        for email, expected in attempts:
            with self.subTest(email=email), captured_logs() as stream:
                Client().post(
                    "/authentication/login/",
                    {"email": email, "password": "wrong-password-9"},
                )
                self.assertRegex(
                    stream.getvalue(), rf"{HEADER} WARNING web \S+ authentication: "
                )
                self.assertIn(expected, stream.getvalue())
                self.assertNotIn(email, stream.getvalue())
                self.assertNotIn("wrong-password-9", stream.getvalue())


@override_settings(DEBUG=False, ROOT_URLCONF=__name__)
class FailingRequestTests(SimpleTestCase):
    def test_every_line_of_a_failing_request_carries_its_id(self):
        with captured_logs() as stream:
            response = Client(raise_request_exception=False).get(
                "/diagnostic-error/", headers={"X-Request-ID": "failing-0001"}
            )
        self.assertEqual(response.status_code, 500)
        lines = stream.getvalue().splitlines()
        self.assertIn("Traceback (most recent call last)", stream.getvalue())
        self.assertTrue(lines)
        for line in lines:
            self.assertRegex(line, rf"^{HEADER} ERROR web failing-0001 ")

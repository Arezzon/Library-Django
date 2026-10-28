"""One log line format for the web and worker services (research R18, R19).

A record renders as ``<UTC time with ms>Z <LEVEL> <service> <request id or -> <logger>:
<message>``. Every further line of a message or traceback repeats the header followed
by ``| ``, so one search for a request id finds the whole record, and user input cannot
start a line of its own. Secrets and search text are redacted before anything is written.
"""

import logging
import os
import re
import time
from contextvars import ContextVar

# The identifier of the request being served, or of the task being run.
request_id = ContextVar("request_id", default=None)

LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
APP_LOGGERS = (
    "audit",
    "authentication",
    "author",
    "book",
    "events",
    "library",
    "order",
)

REDACTED = "[redacted]"
HEADER_VALUE = re.compile(r"(?i)\b(cookie|authorization)(\s*[:=]\s*)([^\n\"']+)")
# A quoted value is redacted whole, spaces included; a bare one up to a separator.
SECRET_VALUE = re.compile(
    r"(?i)\b([\w-]*(?:password|passwd|secret|token|key|sessionid|session))\b"
    r"([\"']?\s*[:=]\s*)(\"[^\"]*\"|'[^']*'|[^\s\"'&,;}]+)"
)
URL_PASSWORD = re.compile(r"(\b[a-z][a-z0-9+.-]*://[^\s:/@]+:)([^\s@/]+)(@)")
SEARCH_TEXT = re.compile(r"([?&]q=)[^&\s\"'#]*")


def redact_secret(match):
    key, separator, value = match.groups()
    quote = value[0] if value[0] in "\"'" else ""
    return f"{key}{separator}{quote}{REDACTED}{quote}"


class ContextFilter(logging.Filter):
    """Adds the service and the request id, or "-", to every record."""

    def __init__(self, service="web"):
        super().__init__()
        self.service = service

    def filter(self, record):
        record.service = self.service
        # Django logs a 4xx response after the middleware has reset the variable.
        current = request_id.get() or getattr(
            getattr(record, "request", None), "request_id", None
        )
        record.request_id = current or "-"
        return True


class LineFormatter(logging.Formatter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.literals = [
            value
            for value in (os.getenv("SECRET_KEY"), os.getenv("DB_PASSWORD"))
            if value and len(value) >= 8
        ]

    def format(self, record):
        moment = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
        header = (
            f"{moment}.{int(record.msecs):03d}Z {record.levelname} "
            f"{getattr(record, 'service', '-')} {getattr(record, 'request_id', '-')}"
        )
        text = record.getMessage()
        if record.exc_info:
            text = f"{text}\n{self.formatException(record.exc_info)}"
        if record.stack_info:
            text = f"{text}\n{self.formatStack(record.stack_info)}"
        first, *rest = self.redact(text).split("\n")
        lines = [f"{header} {record.name}: {first}"]
        lines += [f"{header} | {line}" for line in rest]
        return "\n".join(lines)

    def redact(self, text):
        for literal in self.literals:
            text = text.replace(literal, REDACTED)
        text = HEADER_VALUE.sub(rf"\1\2{REDACTED}", text)
        text = SECRET_VALUE.sub(redact_secret, text)
        text = URL_PASSWORD.sub(r"\1***\3", text)
        return SEARCH_TEXT.sub(rf"\1{REDACTED}", text)


def build_logging_config(service, level="INFO"):
    """The logging configuration of one service, for Django, gunicorn and Celery."""
    level = (level or "INFO").upper()
    if level not in LEVELS:
        raise ValueError(
            f"LOG_LEVEL must be one of {', '.join(LEVELS)}, not {level!r}."
        )
    # Refused requests are warnings; LOG_LEVEL can only make this logger quieter.
    request_level = max(level, "WARNING", key=LEVELS.index)

    def logger(logger_level):
        return {"handlers": ["console"], "level": logger_level, "propagate": False}

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {"context": {"()": ContextFilter, "service": service}},
        "formatters": {"line": {"()": LineFormatter}},
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "filters": ["context"],
                "formatter": "line",
            }
        },
        "root": {"handlers": ["console"], "level": level},
        "loggers": {
            "django": logger(level),
            "django.request": logger(request_level),
            "celery": logger(level),
            "gunicorn.error": logger(level),
            **{name: logger(level) for name in APP_LOGGERS},
        },
    }

"""Who is making changes, and through which channel (research R21).

The request middleware sets the signed-in account and the channel from the path,
Celery tasks use channel "system", and anything else, such as management commands,
scripts and the shell, defaults to channel "command" with no actor.
"""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(frozen=True)
class AuditContext:
    # The signed-in account, or a lazy one; read only when an entry is written.
    actor: object = None
    channel: str = "command"
    reason: str = ""


COMMAND = AuditContext()  # outside a request or a task
current = ContextVar("audit_context", default=COMMAND)


@contextmanager
def audit_context(actor=None, channel="command", reason=None):
    token = current.set(AuditContext(actor, channel, reason or ""))
    try:
        yield
    finally:
        current.reset(token)

import os
from logging.config import dictConfig

from celery import Celery
from celery.signals import before_task_publish, setup_logging, task_postrun, task_prerun

from audit.context import AuditContext
from audit.context import current as audit_state

from .logs import build_logging_config, request_id

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "library.settings")
app = Celery("library")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@setup_logging.connect
def configure_worker_logging(**kwargs):
    """The worker writes the same lines as the web service, as service "worker"."""
    dictConfig(build_logging_config("worker", os.getenv("LOG_LEVEL", "INFO")))


@before_task_publish.connect
def send_request_id(headers=None, **kwargs):
    """A task started during a request carries the request's id."""
    current = request_id.get()
    if current and headers is not None:
        headers["request_id"] = current


@task_prerun.connect
def restore_request_id(task_id=None, task=None, **kwargs):
    """A task's lines carry its request's id; a task run eagerly keeps the current
    one, and a task with neither uses its own id."""
    current = getattr(task.request, "request_id", None) or request_id.get() or task_id
    task.request.request_id_token = request_id.set(current)


@task_postrun.connect
def clear_request_id(task=None, **kwargs):
    token = getattr(task.request, "request_id_token", None)
    if token is not None:
        request_id.reset(token)


@task_prerun.connect
def audit_as_system(task=None, **kwargs):
    """Changes a task makes are recorded as the system's (research R21)."""
    task.request.audit_token = audit_state.set(AuditContext(channel="system"))


@task_postrun.connect
def end_audit_as_system(task=None, **kwargs):
    token = getattr(task.request, "audit_token", None)
    if token is not None:
        audit_state.reset(token)

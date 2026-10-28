"""Audit entries, written inside the caller's transaction (FR-037, FR-040).

The domain apps call ``record()`` where every channel passes: their models' save()
and delete. If the insert fails, the caller's transaction, and with it the change,
rolls back.
"""

from django.utils import timezone

from library.logs import request_id

from .context import current
from .models import AuditEntry


def account_label(account):
    return f"{account.first_name} {account.last_name} (#{account.pk})"


def record(
    action,
    target_type,
    target_id,
    target_label,
    before,
    after,
    reason="",
    occurred_at=None,
):
    """``occurred_at`` defaults to now; an expiry passes its deadline."""
    context = current.get()
    actor = context.actor
    if not getattr(actor, "is_authenticated", False):
        actor = None
    return AuditEntry.objects.create(
        occurred_at=occurred_at or timezone.now(),
        actor_id=actor.pk if actor else None,
        actor_label=account_label(actor) if actor else "system",
        action=action,
        target_type=target_type,
        target_id=target_id,
        target_label=target_label[:200],
        before=before,
        after=after,
        reason=reason or context.reason,
        channel=context.channel,
        request_id=request_id.get() or "",
    )

import logging

from celery import shared_task
from django.utils import timezone

from .services import expire_due

logger = logging.getLogger(__name__)


@shared_task
def expire_reservations():
    """Record the expiry of every reservation past its deadline (R11). Reservations
    stop holding copies at their deadline whether or not this has run."""
    expired = expire_due(timezone.now())
    logger.info("Expired %s reservation(s)", expired)
    return expired

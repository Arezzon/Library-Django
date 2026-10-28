import logging

from django.contrib.auth.signals import user_login_failed
from django.dispatch import receiver

from .models import CustomUser

logger = logging.getLogger("authentication")


@receiver(user_login_failed, dispatch_uid="authentication.sign_in_failed")
def log_failed_sign_in(sender, credentials, request=None, **kwargs):
    """Name the account by its id only: never the email or the password (FR-039)."""
    email = CustomUser.objects.normalize_email(credentials.get("username") or "")
    account = CustomUser.objects.filter(email=email).values_list("pk", flat=True)
    if account:
        logger.warning("Sign-in failed for account #%s", account[0])
    else:
        logger.warning("Sign-in failed for an unknown account")

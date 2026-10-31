from django import template

from .. import services

register = template.Library()


@register.filter
def time_left(deadline, now):
    """``{{ reservation.expires_at|time_left:now }}`` reads "1 day 3 hours left"."""
    return services.time_left(deadline, now)

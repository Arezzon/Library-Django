from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from order.models import Order
from .models import EventType
from .services import capture, current_request


@receiver(user_logged_in, dispatch_uid='events.login')
def logged_in(sender, request, user, **kwargs):
    if request is not None:
        capture(request, EventType.LOGIN, user=user)


@receiver(user_logged_out, dispatch_uid='events.logout')
def logged_out(sender, request, user, **kwargs):
    if request is not None and user is not None:
        capture(request, EventType.LOGOUT, user=user)


@receiver(pre_save, sender=Order, dispatch_uid='events.order.previous')
def previous_order(sender, instance, raw, using, **kwargs):
    if raw or current_request.get() is None:
        return
    instance._tracking_previous = sender.objects.using(using).filter(pk=instance.pk).values(
        'book_id', 'end_at', 'user_id',
    ).first() if instance.pk else None


@receiver(post_save, sender=Order, dispatch_uid='events.order.saved')
def saved_order(sender, instance, created, raw, using, **kwargs):
    request = current_request.get()
    if raw or request is None or not request.user.is_authenticated:
        return
    current = sender.objects.using(using).values('book_id', 'end_at', 'user_id').get(pk=instance.pk)
    previous = getattr(instance, '_tracking_previous', None)
    event_type = None
    if created and current['end_at'] is None:
        event_type = EventType.ORDER_CREATED
    elif previous is not None:
        if previous['end_at'] is None and current['end_at'] is not None:
            event_type = EventType.ORDER_RETURNED
        elif previous['end_at'] is not None and current['end_at'] is None:
            event_type = EventType.ORDER_REOPENED
        elif previous['book_id'] != current['book_id'] or previous['user_id'] != current['user_id']:
            event_type = EventType.ORDER_REASSIGNED
    if event_type:
        capture(request, event_type, using=using, book_id=current['book_id'], properties={
            'order_id': instance.pk, 'reader_id': current['user_id'],
        })

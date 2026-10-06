from datetime import timedelta
from django.core.paginator import Paginator
from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils import timezone
from book.models import Book
from .models import EventType, UserEvent


def build_analytics_context(request, *, user=None):
    days = request.GET.get('days', '7')
    days = int(days) if days in ('7', '30', '90') else 7
    event_type = request.GET.get('event_type', '')
    event_type = event_type if event_type in EventType.values else ''
    today = timezone.localdate()
    start = today - timedelta(days=days - 1)
    base = UserEvent.objects.filter(occurred_at__date__gte=start)
    if user is not None:
        base = base.filter(user=user)
    events = base.filter(event_type=event_type) if event_type else base
    totals = events.aggregate(total=Count('id'), users=Count('user', distinct=True))
    summary = {
        **totals,
        'views': events.filter(event_type=EventType.BOOK_VIEW).count(),
        'borrows': events.filter(event_type=EventType.ORDER_CREATED).count(),
    }
    if user is not None:
        summary['searches'] = events.filter(event_type=EventType.SEARCH).count()
    activity = dict(events.order_by().annotate(day=TruncDate('occurred_at')).values_list('day').annotate(total=Count('id')))
    peak = max(activity.values(), default=1)
    # Daily bars remain usable on mobile; the table covers the whole chosen period.
    bars = [{'day': today - timedelta(days=offset),
             'total': activity.get(today - timedelta(days=offset), 0)} for offset in range(min(days, 14) - 1, -1, -1)]
    for bar in bars:
        bar['height'] = round(bar['total'] / peak * 100) if peak else 0
    distribution = list(events.order_by().values('event_type').annotate(total=Count('id')).order_by('-total'))
    labels = dict(EventType.choices)
    for row in distribution:
        row['label'] = labels[row['event_type']]
        row['percent'] = round(row['total'] / (totals['total'] or 1) * 100)
    popular = list(events.filter(book_id__isnull=False, event_type__in=[EventType.BOOK_VIEW, EventType.BOOK_CLICK])
                   .order_by().values('book_id').annotate(total=Count('id')).order_by('-total', 'book_id')[:5])
    titles = Book.objects.in_bulk([row['book_id'] for row in popular])
    for row in popular:
        row['title'] = titles[row['book_id']].name if row['book_id'] in titles else f"Deleted book #{row['book_id']}"
        row['exists'] = row['book_id'] in titles
    page = Paginator(events.select_related('user'), 25).get_page(request.GET.get('page'))
    return {
        'summary': summary, 'bars': bars, 'distribution': distribution, 'popular': popular,
        'page_obj': page, 'days': days, 'selected_type': event_type, 'event_types': EventType.choices,
    }

"""Aggregates for the librarian analytics overview (KAN-34).

Every figure is defined in docs/ba/analytics-dashboard.md. Loans come from orders,
interest from tracked events. Periods and buckets follow Kyiv time (TIME_ZONE), and
a figure whose source has no history for the time it covers is ``None``, not 0.
The result holds aggregates and book titles only, never an account.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from django.conf import settings
from django.db.models import Count, DateField, Min, Q
from django.db.models.functions import Trunc
from django.utils import timezone

from book.models import Book
from order.models import Order, Reservation, ReservationState

from .models import EventType, UserEvent

PERIODS = {"7d": "day", "30d": "day", "90d": "week", "12m": "month"}
DEFAULT_PERIOD = "30d"
DEFAULT_LIMIT = 10
WEEKS = 13
MONTHS = 12


def shift_months(day, months):
    """The first day of the month ``months`` away from ``day``'s month."""
    index = day.year * 12 + day.month - 1 + months
    return date(index // 12, index % 12 + 1, 1)


@dataclass(frozen=True)
class Period:
    key: str
    bucket: str
    start: date
    end: date  # exclusive: the day after today
    previous_start: date

    def buckets(self):
        if self.bucket == "month":
            starts, day = [], self.start
            while day < self.end:
                starts.append(day)
                day = shift_months(day, 1)
            return starts
        step = 7 if self.bucket == "week" else 1
        return [
            self.start + timedelta(days=offset)
            for offset in range(0, (self.end - self.start).days, step)
        ]


def resolve_period(key, now):
    if key not in PERIODS:
        raise ValueError(f"Unknown period {key!r}.")
    today = timezone.localdate(now)
    if key == "12m":
        start = shift_months(today, 1 - MONTHS)
        previous_start = shift_months(start, -MONTHS)
    elif key == "90d":
        start = today - timedelta(days=today.weekday(), weeks=WEEKS - 1)
        previous_start = start - timedelta(weeks=WEEKS)
    else:
        days = int(key[:-1])
        start = today - timedelta(days=days - 1)
        previous_start = start - timedelta(days=days)
    return Period(key, PERIODS[key], start, today + timedelta(days=1), previous_start)


def midnight(day):
    return timezone.make_aware(datetime.combine(day, time.min))


def within(field, start, end):
    return Q(**{f"{field}__gte": midnight(start), f"{field}__lt": midnight(end)})


def covered(history, day):
    """Whether a source's records reach back to ``day``."""
    return history is not None and history <= day


def compare(value, previous, history, period):
    return {
        "value": value,
        "previous": previous if covered(history, period.previous_start) else None,
    }


def history_starts():
    # A loan's return can be recorded with an earlier date than its issue (the
    # demo data does), so loan history starts at whichever comes first.
    loans = Order.objects.aggregate(issued=Min("created_at"), returned=Min("end_at"))
    starts = {
        "loans": min(filter(None, loans.values()), default=None),
        "reservations": Reservation.objects.aggregate(first=Min("created_at"))["first"],
        "events": UserEvent.objects.aggregate(first=Min("occurred_at"))["first"],
    }
    return {
        source: timezone.localdate(first) if first else None
        for source, first in starts.items()
    }


def per_bucket(queryset, field, period):
    rows = (
        queryset.filter(within(field, period.start, period.end))
        .order_by()
        .annotate(bucket=Trunc(field, period.bucket, output_field=DateField()))
        .values("bucket")
        .annotate(total=Count("pk"))
    )
    return {row["bucket"]: row["total"] for row in rows}


def build_series(period, history):
    loans = per_bucket(Order.objects.all(), "created_at", period)
    returns = per_bucket(Order.objects.all(), "end_at", period)
    starts = period.buckets()
    series = []
    for index, start in enumerate(starts):
        last = index == len(starts) - 1
        following = period.end if last else starts[index + 1]
        series.append(
            {
                "start": start.isoformat(),
                "loans": loans.get(start, 0),
                "returns": returns.get(start, 0),
                # A bucket counts once any of its days is on or after the first loan.
                "covered": covered(history, following - timedelta(days=1)),
                "partial": last,
            }
        )
    return series


def loan_summary(period, now, history):
    current = within("created_at", period.start, period.end)
    previous = within("created_at", period.previous_start, period.start)
    totals = Order.objects.aggregate(
        issued=Count("pk", filter=current),
        issued_before=Count("pk", filter=previous),
        returns=Count("pk", filter=within("end_at", period.start, period.end)),
        returns_before=Count(
            "pk", filter=within("end_at", period.previous_start, period.start)
        ),
        borrowers=Count("user", filter=current, distinct=True),
        borrowers_before=Count("user", filter=previous, distinct=True),
    )
    overdue = Order.objects.filter(
        end_at__isnull=True, plated_end_at__lt=now
    ).aggregate(loans=Count("pk"), readers=Count("user", distinct=True))
    return {
        "loans_issued": compare(
            totals["issued"], totals["issued_before"], history, period
        ),
        "returns": compare(
            totals["returns"], totals["returns_before"], history, period
        ),
        "active_borrowers": compare(
            totals["borrowers"], totals["borrowers_before"], history, period
        ),
        "overdue_now": {
            "value": overdue["loans"],
            "readers": overdue["readers"],
            "as_of": timezone.localtime(now).isoformat(),
        },
    }


def reservation_summary(period, now, history):
    current = within("created_at", period.start, period.end)
    # The state every page uses: an active hold past its deadline has expired.
    running = Q(state=ReservationState.ACTIVE, expires_at__gt=now)
    lapsed = Q(state=ReservationState.EXPIRED) | Q(
        state=ReservationState.ACTIVE, expires_at__lte=now
    )
    totals = Reservation.objects.aggregate(
        value=Count("pk", filter=current),
        previous=Count(
            "pk", filter=within("created_at", period.previous_start, period.start)
        ),
        issued=Count("pk", filter=current & Q(state=ReservationState.ISSUED)),
        expired=Count("pk", filter=current & lapsed),
        cancelled=Count("pk", filter=current & Q(state=ReservationState.CANCELLED)),
        active=Count("pk", filter=current & running),
    )
    summary = compare(totals.pop("value"), totals.pop("previous"), history, period)
    return {**summary, **totals}


def event_counts(period):
    current = within("occurred_at", period.start, period.end)
    return UserEvent.objects.aggregate(
        views=Count("pk", filter=current & Q(event_type=EventType.BOOK_VIEW)),
        views_before=Count(
            "pk",
            filter=within("occurred_at", period.previous_start, period.start)
            & Q(event_type=EventType.BOOK_VIEW),
        ),
        searches=Count("pk", filter=current & Q(event_type=EventType.SEARCH)),
    )


def count_by(queryset, field):
    return dict(
        queryset.order_by()
        .values(field)
        .annotate(total=Count("pk"))
        .values_list(field, "total")
    )


def top_borrowed(period, now, limit, tracked):
    loans = count_by(
        Order.objects.filter(within("created_at", period.start, period.end)), "book"
    )
    views = count_by(
        UserEvent.objects.filter(
            within("occurred_at", period.start, period.end),
            event_type=EventType.BOOK_VIEW,
            book_id__in=list(loans),
        ),
        "book_id",
    )
    books = Book.objects.with_availability(now).in_bulk(list(loans))
    ranked = sorted(
        loans,
        key=lambda pk: (-loans[pk], -views.get(pk, 0), books[pk].name.casefold(), pk),
    )
    return [
        {
            "book_id": pk,
            "title": books[pk].name,
            "loans": loans[pk],
            "views": views.get(pk, 0) if tracked else None,
            "available": books[pk].available_count,
            "copies": books[pk].count,
        }
        for pk in ranked[:limit]
    ]


def top_viewed(period, limit):
    rows = list(
        UserEvent.objects.filter(
            within("occurred_at", period.start, period.end),
            event_type=EventType.BOOK_VIEW,
            book_id__isnull=False,
        )
        .order_by()
        .values("book_id")
        .annotate(views=Count("pk"))
        .order_by("-views", "book_id")[:limit]
    )
    ids = [row["book_id"] for row in rows]
    books = Book.objects.in_bulk(ids)
    loans = count_by(
        Order.objects.filter(
            within("created_at", period.start, period.end), book__in=ids
        ),
        "book",
    )
    return [
        {
            "book_id": row["book_id"],
            "title": books[row["book_id"]].name if row["book_id"] in books else None,
            "views": row["views"],
            # A deleted book had no loans: orders protect their book from deletion.
            "loans": loans.get(row["book_id"], 0) if row["book_id"] in books else None,
        }
        for row in rows
    ]


def reader_activity(period, summary, searches):
    per_borrower = (
        # A deleted reader's loans still count as loans, but they are nobody's.
        Order.objects.filter(
            within("created_at", period.start, period.end), user__isnull=False
        )
        .order_by()
        .values("user")
        .annotate(loans=Count("pk"))
        .values_list("loans", flat=True)
    )
    spread = {"1": 0, "2-3": 0, "4+": 0}
    for loans in per_borrower:
        spread["1" if loans == 1 else "2-3" if loans <= 3 else "4+"] += 1
    first_time = (
        Order.objects.filter(user__isnull=False)
        .order_by()
        .values("user")
        .annotate(first=Min("created_at"))
        .filter(first__gte=midnight(period.start), first__lt=midnight(period.end))
        .count()
    )
    active = summary["active_borrowers"]["value"]
    return {
        "active": active,
        "first_time": first_time,
        "returning": active - first_time,
        "loans_per_borrower": spread,
        "with_overdue": summary["overdue_now"]["readers"],
        "searches": searches,
    }


def library_overview(period=DEFAULT_PERIOD, limit=DEFAULT_LIMIT, now=None):
    now = now or timezone.now()
    period = resolve_period(period, now)
    history = history_starts()
    summary = loan_summary(period, now, history["loans"])
    summary["reservations"] = reservation_summary(period, now, history["reservations"])
    events = event_counts(period)
    summary["book_views"] = compare(
        events["views"], events["views_before"], history["events"], period
    )
    return {
        "period": {
            "key": period.key,
            "start": period.start.isoformat(),
            "end": (period.end - timedelta(days=1)).isoformat(),
            "bucket": period.bucket,
            "timezone": settings.TIME_ZONE,
        },
        "history_start": {
            source: day.isoformat() if day else None for source, day in history.items()
        },
        "summary": summary,
        "series": build_series(period, history["loans"]),
        "top_borrowed": top_borrowed(
            period, now, limit, tracked=history["events"] is not None
        ),
        "top_viewed": top_viewed(period, limit),
        "readers": reader_activity(period, summary, events["searches"]),
    }

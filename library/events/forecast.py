"""Book demand forecast (KAN-35).

Five weighted scores per book over the last 30 days and the 30 before them, a
0–100 demand index, a 30-day loan forecast and the copies to buy. Every figure is
defined in docs/ba/demand-forecast.md. The weights are starting assumptions: tune
them here, not in the formulas. The result holds book data only, never an account.
"""

import math
from datetime import timedelta

from django.db.models import Avg, CharField, Count, F, Q, Sum, Value
from django.db.models.functions import Cast, Concat, TruncDate
from django.utils import timezone

from book.models import Book, BookLike, BookRating, FavoriteBook
from order.models import Order, Reservation, ReservationState

from .models import UserEvent
from .overview import midnight, within

WINDOW_DAYS = 30
LOAN_LENGTH_DAYS = 90
DEFAULT_LOAN_DAYS = 14
TREND_LIMITS = (0.5, 2.0)
DEFAULT_LIMIT = 25

WEIGHTS = {
    "loans": {"issued": 1.0, "on_loan": 0.5},
    "reservations": {
        "issued": 1.0,
        "active": 0.6,
        "expired": 0.4,
        "cancelled_by_reader": 0.2,
        "cancelled_by_library": 0.0,
    },
    "interest": {"book_view": 0.1, "book_click": 0.2, "borrow_intent": 0.6},
    "preferences": {"like": 0.5, "favorite": 0.8, "rating": 0.4},
    "stock": {"utilisation": 4.0, "stock_out": 2.0},
}
# How much each scaled score adds to the demand index; the trend leaves out stock,
# which has no previous value.
DEMAND_WEIGHTS = {
    "loans": 0.40,
    "reservations": 0.25,
    "interest": 0.15,
    "preferences": 0.10,
    "stock": 0.10,
}
SCORES = list(DEMAND_WEIGHTS)
TREND_SCORES = [score for score in SCORES if score != "stock"]
INTEREST_EVENTS = list(WEIGHTS["interest"])


def trend(current, previous):
    """The current activity against the previous, limited to half and double."""
    if previous <= 0:
        return 1.0
    low, high = TREND_LIMITS
    return min(high, max(low, current / previous))


def forecast_loans(issued, ratio):
    return math.floor(issued * ratio + 0.5)


def copies_needed(forecast, loan_days):
    # A copy serves WINDOW_DAYS / loan_days loans in the next window.
    return math.ceil(round(forecast * loan_days / WINDOW_DAYS, 6))


def weighted(score, terms):
    return round(sum(WEIGHTS[score][term] * value for term, value in terms.items()), 2)


def loan_terms(start, previous_start):
    current = within("created_at", start, start + timedelta(days=WINDOW_DAYS))
    previous = within("created_at", previous_start, start)
    out_at_start = Q(created_at__lt=midnight(start)) & (
        Q(end_at__isnull=True) | Q(end_at__gte=midnight(start))
    )
    rows = (
        Order.objects.filter(
            Q(created_at__gte=midnight(previous_start))
            | Q(end_at__isnull=True)
            | Q(end_at__gte=midnight(start))
        )
        .order_by()
        .values("book")
        .annotate(
            issued=Count("pk", filter=current),
            on_loan=Count("pk", filter=Q(end_at__isnull=True)),
            issued_before=Count("pk", filter=previous),
            on_loan_before=Count("pk", filter=out_at_start),
        )
    )
    return {
        row["book"]: (
            {"issued": row["issued"], "on_loan": row["on_loan"]},
            {"issued": row["issued_before"], "on_loan": row["on_loan_before"]},
        )
        for row in rows
    }


def reservation_terms(start, previous_start, now):
    # Stored with the cancellation, so it holds after either account is deleted.
    by_reader = Q(state=ReservationState.CANCELLED, cancelled_by_reader=True)
    outcomes = {
        "issued": Q(state=ReservationState.ISSUED),
        "active": Q(state=ReservationState.ACTIVE, expires_at__gt=now),
        "expired": Q(state=ReservationState.EXPIRED)
        | Q(state=ReservationState.ACTIVE, expires_at__lte=now),
        "cancelled_by_reader": by_reader,
        "cancelled_by_library": Q(state=ReservationState.CANCELLED) & ~by_reader,
    }
    windows = {
        "current": within("created_at", start, start + timedelta(days=WINDOW_DAYS)),
        "previous": within("created_at", previous_start, start),
    }
    rows = (
        Reservation.objects.filter(created_at__gte=midnight(previous_start))
        .order_by()
        .values("book")
        .annotate(
            **{
                f"{window}_{outcome}": Count("pk", filter=when & rule)
                for window, when in windows.items()
                for outcome, rule in outcomes.items()
            }
        )
    )
    return {
        row["book"]: tuple(
            {outcome: row[f"{window}_{outcome}"] for outcome in outcomes}
            for window in windows
        )
        for row in rows
    }


def interest_terms(start, previous_start):
    # Each kind counts once per account, book and Kyiv day; events whose account
    # was deleted share one empty account id, so they count once per day too.
    account_day = Concat(
        Cast("user_id", CharField()),
        Value(":"),
        Cast(TruncDate("occurred_at"), CharField()),
    )
    windows = {
        "current": within("occurred_at", start, start + timedelta(days=WINDOW_DAYS)),
        "previous": within("occurred_at", previous_start, start),
    }
    rows = (
        UserEvent.objects.filter(
            event_type__in=INTEREST_EVENTS,
            book_id__isnull=False,
            occurred_at__gte=midnight(previous_start),
        )
        .order_by()
        .values("book_id", "event_type")
        .annotate(
            **{
                window: Count(account_day, filter=when, distinct=True)
                for window, when in windows.items()
            }
        )
    )
    terms = {}
    for row in rows:
        current, previous = terms.setdefault(
            row["book_id"],
            (dict.fromkeys(INTEREST_EVENTS, 0), dict.fromkeys(INTEREST_EVENTS, 0)),
        )
        current[row["event_type"]] = row["current"]
        previous[row["event_type"]] = row["previous"]
    return terms


def preference_terms(start, previous_start):
    end = start + timedelta(days=WINDOW_DAYS)
    sources = {
        "like": (BookLike, "created_at", lambda when: Count("pk", filter=when)),
        "favorite": (FavoriteBook, "created_at", lambda when: Count("pk", filter=when)),
        # A rating counts by how far it is from the neutral 3.
        "rating": (
            BookRating,
            "updated_at",
            lambda when: Sum(F("value") - 3, filter=when),
        ),
    }
    terms = {}
    for term, (model, field, total) in sources.items():
        rows = (
            model.objects.filter(**{f"{field}__gte": midnight(previous_start)})
            .order_by()
            .values("book")
            .annotate(
                current=total(within(field, start, end)),
                previous=total(within(field, previous_start, start)),
            )
        )
        for row in rows:
            current, previous = terms.setdefault(
                row["book"], (dict.fromkeys(sources, 0), dict.fromkeys(sources, 0))
            )
            current[term] = row["current"] or 0
            previous[term] = row["previous"] or 0
    return terms


def loan_lengths(now):
    rows = (
        Order.objects.filter(end_at__gte=now - timedelta(days=LOAN_LENGTH_DAYS))
        .order_by()
        .values("book")
        .annotate(length=Avg(F("end_at") - F("created_at")))
    )
    return {
        row["book"]: max(1.0, round(row["length"].total_seconds() / 86400, 1))
        for row in rows
    }


def stock_terms(book):
    held = book.active_order_count + book.active_reservation_count
    utilisation = min(1.0, held / book.count) if book.count > 0 else 1.0
    return {
        "utilisation": round(utilisation, 2),
        "stock_out": 1 if book.available_count == 0 else 0,
    }


def scale(value, largest):
    return value / largest * 100 if largest else 0.0


def demand_forecast(now=None, limit=DEFAULT_LIMIT):
    now = now or timezone.now()
    today = timezone.localdate(now)
    start = today - timedelta(days=WINDOW_DAYS - 1)
    previous_start = start - timedelta(days=WINDOW_DAYS)
    sources = {
        "loans": loan_terms(start, previous_start),
        "reservations": reservation_terms(start, previous_start, now),
        "interest": interest_terms(start, previous_start),
        "preferences": preference_terms(start, previous_start),
    }
    empty = {score: dict.fromkeys(WEIGHTS[score], 0) for score in TREND_SCORES}
    active = set()
    for terms in sources.values():
        for book, (current, previous) in terms.items():
            if any(current.values()) or any(previous.values()):
                active.add(book)
    books = Book.objects.with_availability(now).in_bulk(active)
    lengths = loan_lengths(now)

    rows = []
    for book_id in active & set(books):
        book = books[book_id]
        scores = {}
        for score in TREND_SCORES:
            current, previous = sources[score].get(
                book_id, (empty[score], empty[score])
            )
            scores[score] = {
                "terms": current,
                "previous_terms": previous,
                "current": weighted(score, current),
                "previous": weighted(score, previous),
            }
        stock = stock_terms(book)
        scores["stock"] = {
            "terms": stock,
            "previous_terms": None,
            "current": weighted("stock", stock),
            "previous": None,
        }
        rows.append({"book": book, "scores": scores})

    # One divisor per score for both windows keeps them comparable.
    largest = {
        score: max(
            [
                abs(value)
                for row in rows
                for value in (
                    row["scores"][score]["current"],
                    row["scores"][score]["previous"],
                )
                if value is not None
            ]
            + [0]
        )
        for score in SCORES
    }
    results = []
    for row in rows:
        book, scores = row["book"], row["scores"]
        scaled = {
            score: scale(scores[score]["current"], largest[score]) for score in SCORES
        }
        scaled_before = {
            score: scale(scores[score]["previous"], largest[score])
            for score in TREND_SCORES
        }
        demand = max(0.0, sum(DEMAND_WEIGHTS[s] * scaled[s] for s in SCORES))
        activity = sum(DEMAND_WEIGHTS[s] * scaled[s] for s in TREND_SCORES)
        activity_before = sum(
            DEMAND_WEIGHTS[s] * scaled_before[s] for s in TREND_SCORES
        )
        ratio = trend(activity, activity_before)
        issued = scores["loans"]["terms"]["issued"]
        forecast = forecast_loans(issued, ratio)
        loan_days = lengths.get(book.pk, float(DEFAULT_LOAN_DAYS))
        needed = copies_needed(forecast, loan_days)
        results.append(
            {
                "book_id": book.pk,
                "title": book.name,
                "copies": book.count,
                "available": book.available_count,
                "scores": scores,
                "demand": round(demand),
                "trend": round(ratio, 2),
                "compared": activity_before > 0,
                "rising": activity_before > 0 and ratio > 1,
                "forecast": forecast,
                "loan_days": loan_days,
                "copies_needed": needed,
                "to_buy": max(0, needed - book.count),
            }
        )
    results.sort(
        key=lambda r: (
            -r["demand"],
            -r["forecast"],
            r["title"].casefold(),
            r["book_id"],
        )
    )
    return {
        "window": {
            "start": start.isoformat(),
            "end": today.isoformat(),
            "previous_start": previous_start.isoformat(),
        },
        "books": results[:limit],
        "totals": {
            "books_to_buy": sum(1 for r in results if r["to_buy"]),
            "copies_to_buy": sum(r["to_buy"] for r in results),
            "rising": sum(1 for r in results if r["rising"]),
        },
        "has_activity": bool(results),
    }

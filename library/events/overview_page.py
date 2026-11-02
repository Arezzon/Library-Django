"""What the library overview page shows (KAN-54, docs/ba/analytics-dashboard.md).

Turns ``library_overview`` into the page's tiles, notice, chart and lists. The
figures themselves come only from the overview service.
"""

from datetime import date, datetime

from django.utils import dateformat, timezone

from .overview import DEFAULT_PERIOD, PERIODS, library_overview

TOP_LIMIT = 10
CHART_HEIGHT = 160
PERIOD_CHOICES = [
    ("7d", "Last 7 days"),
    ("30d", "Last 30 days"),
    ("90d", "Last 90 days"),
    ("12m", "Last 12 months"),
]
PREVIOUS = {
    "7d": "previous 7 days",
    "30d": "previous 30 days",
    "90d": "previous 13 weeks",
    "12m": "previous 12 months",
}
UNITS = {"day": "days", "week": "weeks", "month": "months"}
BY_UNIT = {"day": "by day", "week": "by week, Monday to Sunday", "month": "by month"}
# Each source's history, as the notice and the tiles' details name it.
STARTS = {
    "loans": ("Loan history starts", "Loans: none yet"),
    "reservations": ("Reservations start", "Reservations: none yet"),
    "events": ("Book views are tracked from", "Book views: none tracked yet"),
}


def long_date(day):
    return dateformat.format(day, "j M Y")


def parse(day):
    return date.fromisoformat(day) if day else None


def plural(count, word):
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def change(value, previous):
    diff = value - previous
    sign = "+" if diff > 0 else "−" if diff < 0 else "±"
    if not previous:
        return f"{sign}{abs(diff)}"
    return f"{sign}{abs(diff)} ({sign}{abs(round(diff / previous * 100))}%)"


def comparison(metric, source, history, period_key):
    """The tile's short change and the sentence its details give about it."""
    previous_words = PREVIOUS[period_key]
    if metric["previous"] is None:
        start = history[source]
        reason = (
            f"{STARTS[source][0].lower()} {long_date(start)}"
            if start
            else "there is no history yet"
        )
        return "", f"No comparison with the {previous_words}: {reason}."
    short = change(metric["value"], metric["previous"])
    had = metric["previous"] or "none"
    return short, f"{short} against the {previous_words}, which had {had}."


def build_tiles(summary, history, period_key):
    def tile(key, label, value, short, lines):
        return {
            "key": key,
            "label": label,
            "value": value,
            "short": short,
            "details": lines,
        }

    def compared(key, label, source, what):
        metric = summary[key]
        short, sentence = comparison(metric, source, history, period_key)
        return tile(key, label, metric["value"], short, [what, sentence])

    overdue = summary["overdue_now"]
    as_of = dateformat.format(
        timezone.localtime(datetime.fromisoformat(overdue["as_of"])), "H:i T"
    )
    holds = summary["reservations"]
    hold_short, hold_sentence = comparison(holds, "reservations", history, period_key)
    return [
        compared(
            "loans_issued",
            "Loans issued",
            "loans",
            "Loans issued at the desk in the period.",
        ),
        compared(
            "returns",
            "Returns",
            "loans",
            "Loans returned in the period, whenever they were issued.",
        ),
        compared(
            "active_borrowers",
            "Active borrowers",
            "loans",
            "Accounts with a loan issued in the period, librarians included.",
        ),
        tile(
            "overdue_now",
            "Overdue now",
            overdue["value"],
            plural(overdue["readers"], "reader") if overdue["value"] else "",
            [
                f"{plural(overdue['value'], 'unreturned loan')} past the due date, "
                f"held by {plural(overdue['readers'], 'reader')}.",
                f"A snapshot as of {as_of}, not tied to the period.",
            ],
        ),
        tile(
            "reservations",
            "Reservations",
            holds["value"],
            hold_short,
            [
                "Reservations made in the period, by their state now: "
                f"{holds['issued']} issued, {holds['expired']} expired, "
                f"{holds['cancelled']} cancelled, {holds['active']} still active.",
                hold_sentence,
            ],
        ),
        compared(
            "book_views",
            "Book views",
            "events",
            "Book pages opened by signed-in accounts.",
        ),
    ]


def build_notice(history, start, bucket):
    if not any(history.values()):
        return (
            "No loans, reservations or tracked activity yet. Figures appear after "
            "the first loan is issued at the desk."
        )
    parts = []
    for source, (starts, none) in STARTS.items():
        if history[source] is None:
            parts.append(none + ".")
        elif history[source] > start:
            parts.append(f"{starts} {long_date(history[source])}.")
    if not parts:
        return ""
    return " ".join(
        parts
        + [
            f"Earlier {UNITS[bucket]} show no data rather than zero, and comparisons "
            "that need them are left out."
        ]
    )


def bucket_names(start, bucket, count, index):
    if bucket == "month":
        return dateformat.format(start, "M"), dateformat.format(start, "M Y")
    if bucket == "week":
        label = dateformat.format(start, "d/m") if index % 2 == 0 else ""
        return label, f"Week of {long_date(start)}"
    shown = count <= 7 or index % 5 == 0
    return (dateformat.format(start, "d/m") if shown else ""), long_date(start)


def build_bars(series, bucket):
    peak = max([max(row["loans"], row["returns"]) for row in series] + [1])

    def height(value):
        return max(3, round(value / peak * CHART_HEIGHT)) if value else 0

    bars = []
    for index, row in enumerate(series):
        label, name = bucket_names(parse(row["start"]), bucket, len(series), index)
        so_far = " (so far)" if row["partial"] else ""
        bars.append(
            {
                **row,
                "label": label,
                "name": name + so_far,
                "loan_height": height(row["loans"]),
                "return_height": height(row["returns"]),
                "title": (
                    f"{name}{so_far}: {plural(row['loans'], 'loan')}, "
                    f"{plural(row['returns'], 'return')}"
                    if row["covered"]
                    else f"{name}: no data, before loan history starts"
                ),
            }
        )
    return bars


def build_readers(readers):
    spread = readers["loans_per_borrower"]
    return [
        ("Active borrowers", readers["active"], False),
        ("First-time", readers["first_time"], True),
        ("Returning", readers["returning"], True),
        ("Borrowed 1 book", spread["1"], False),
        ("Borrowed 2–3 books", spread["2-3"], False),
        ("Borrowed 4 or more", spread["4+"], False),
        ("With an overdue loan", readers["with_overdue"], False),
        ("Catalog searches", readers["searches"], False),
    ]


def overview_page_context(period_key):
    if period_key not in PERIODS:
        period_key = DEFAULT_PERIOD
    data = library_overview(period_key, TOP_LIMIT)
    period = data["period"]
    history = {source: parse(day) for source, day in data["history_start"].items()}
    start, end = parse(period["start"]), parse(period["end"])
    return {
        **data,
        "period_choices": PERIOD_CHOICES,
        "range_text": f"{long_date(start)} – {long_date(end)}, {BY_UNIT[period['bucket']]}",
        "bucket_word": period["bucket"],
        "previous_words": PREVIOUS[period_key],
        "notice": build_notice(history, start, period["bucket"]),
        "tiles": build_tiles(data["summary"], history, period_key),
        "bars": build_bars(data["series"], period["bucket"]),
        "bar_gap": 3 if len(data["series"]) > 14 else 10,
        "reader_rows": build_readers(data["readers"]),
        "has_loans": any(row["loans"] for row in data["series"]),
    }

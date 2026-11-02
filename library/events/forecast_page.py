"""What the Forecast tab shows (KAN-35, docs/ba/demand-forecast.md).

Turns ``demand_forecast`` into the page's tiles, rows and explanations. The figures
themselves come only from the forecast service.
"""

from datetime import date

from .forecast import (
    DEFAULT_LOAN_DAYS,
    DEMAND_WEIGHTS,
    TREND_LIMITS,
    WEIGHTS,
    WINDOW_DAYS,
    demand_forecast,
)
from .overview_page import long_date, plural

SCORE_NAMES = {
    "loans": "Loans",
    "reservations": "Reservations",
    "interest": "Interest",
    "preferences": "Preferences",
    "stock": "Stock pressure",
}
TERM_NAMES = {
    "issued": "issued",
    "on_loan": "on loan at the end of the window",
    "active": "still active",
    "expired": "expired",
    "cancelled_by_reader": "cancelled by the reader",
    "cancelled_by_library": "cancelled by the library",
    "book_view": "page views",
    "book_click": "catalog clicks",
    "borrow_intent": "“Reserve” presses",
    "like": "likes",
    "favorite": "favourites",
    "rating": "ratings minus 3, summed",
    "utilisation": "share of copies taken",
    "stock_out": "no copy free",
}


def number(value):
    return f"{value:g}" if isinstance(value, float) else str(value)


def describe_terms(score, terms):
    return ", ".join(
        f"{number(terms[term])} {TERM_NAMES[term]}" for term in WEIGHTS[score]
    )


def plural_copy(count):
    return "1 copy" if count == 1 else f"{count} copies"


def trend_text(row):
    if not row["compared"]:
        return "No earlier activity"
    change = round((row["trend"] - 1) * 100)
    if change > 0:
        return f"↑ +{change}%"
    if change < 0:
        return f"↓ −{abs(change)}%"
    return "→ 0%"


def details(row):
    lines = []
    for score, name in SCORE_NAMES.items():
        figures = row["scores"][score]
        was = (
            f" (previous window {number(figures['previous'])})"
            if figures["previous"] is not None
            else " (now)"
        )
        lines.append(
            f"{name} {number(figures['current'])}{was}: "
            f"{describe_terms(score, figures['terms'])}."
        )
    capacity = WINDOW_DAYS / row["loan_days"]
    length = (
        f"Loans last {number(row['loan_days'])} days on average"
        if row["loan_days"] != DEFAULT_LOAN_DAYS
        else f"Loans are taken to last {DEFAULT_LOAN_DAYS} days"
    )
    lines.append(
        f"{length}, so a copy serves {capacity:.1f} loans in {WINDOW_DAYS} days: "
        f"{plural_copy(row['copies_needed'])} needed for "
        f"{plural(row['forecast'], 'forecast loan')}."
    )
    return lines


def recipe():
    """The formulas with their weights, as the page explains them."""
    lines = []
    for score, name in SCORE_NAMES.items():
        parts = " + ".join(
            f"{number(weight)} × {TERM_NAMES[term]}"
            for term, weight in WEIGHTS[score].items()
        )
        lines.append(f"{name} = {parts}")
    demand = " + ".join(
        f"{number(weight)} × {SCORE_NAMES[score].lower()}"
        for score, weight in DEMAND_WEIGHTS.items()
    )
    low, high = TREND_LIMITS
    return {
        "scores": lines,
        "demand": f"Demand = {demand}, each score scaled to 0–100 against the catalog.",
        "trend": (
            "Trend = activity in the last 30 days against the 30 before, without "
            f"stock pressure, limited to {number(low)}–{number(high)}."
        ),
        "forecast": (
            "Forecast loans = loans issued in the last 30 days × trend. Copies needed "
            "= forecast × average loan length ÷ 30, rounded up."
        ),
    }


def forecast_page_context():
    data = demand_forecast()
    window = data["window"]
    rows = [
        {
            **row,
            "rank": rank,
            "trend_text": trend_text(row),
            "recommendation": f"Buy {row['to_buy']}" if row["to_buy"] else "Enough",
            "details": details(row),
            "about": f"How the forecast for {row['title']} is made",
        }
        for rank, row in enumerate(data["books"], start=1)
    ]
    totals = data["totals"]
    return {
        **data,
        "rows": rows,
        "window_text": (
            f"Forecast for the next {WINDOW_DAYS} days, based on "
            f"{long_date(date.fromisoformat(window['start']))} – "
            f"{long_date(date.fromisoformat(window['end']))}"
        ),
        "tiles": [
            ("Books to buy", totals["books_to_buy"]),
            ("Copies to buy", totals["copies_to_buy"]),
            ("Rising demand", totals["rising"]),
        ],
        "recipe": recipe(),
    }

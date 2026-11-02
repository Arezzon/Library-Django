# Book demand forecast (KAN-35)

The forecast answers two questions for librarians and administrators: **which books
are in demand now, and how many copies each one needs for the next 30 days.** It is
built from five simple scores, each a weighted sum of figures the library already
records about a book. There is no trained model: every number on the page can be
recomputed by hand from the definitions below.

The page is the third Analytics tab, **Forecast**, at `/events/forecast/`, next to
Overview (KAN-54) and Activity log.

## Audience and privacy

| Audience | Page |
| --- | --- |
| Librarian, administrator (`is_librarian`) | Allowed |
| Reader | 403 |
| Anonymous | Redirect to sign-in with `next` |

The page shows books and numbers only. No reader's name, email, account ID or
search text is shown, and per-reader counts are never listed.

## Windows

- **Current window** `W`: the last 30 days in Kyiv time, today included.
- **Previous window** `P`: the 30 days before `W`.
- "Now" figures are a snapshot at the time of the request.

## The five scores

Each score is computed per book. The weights are starting assumptions, not
calibrated values; they live in one place (`events/forecast.py`, `WEIGHTS`) so they
can be tuned without touching the formulas.

### 1. Loans — `LS`

```text
LS = 1.0 × loans issued in the window
   + 0.5 × copies on loan at the end of the window
```

| Term | Source |
| --- | --- |
| Loans issued | `Order` rows with `created_at` in the window |
| Copies on loan at the end of `W` | `Order` with `end_at` empty (now) |
| Copies on loan at the end of `P` | `Order` created before `W` starts and not returned by then (`end_at` empty or on/after the start of `W`) |

### 2. Reservations — `RS`

```text
RS = 1.0 × issued
   + 0.6 × still active
   + 0.4 × expired
   + 0.2 × cancelled by the reader
   + 0.0 × cancelled by the library
```

Counted over `Reservation` rows created in the window, by their state now. "Still
active" means `state = active` with `expires_at` later than now; an active row past
its deadline counts as expired, as every page treats it. "Cancelled by the reader"
means `cancelled_by` is the reservation's own reader; a cancellation by a librarian
is the library's decision, not demand, and weighs nothing.

### 3. Interest — `IS`

```text
IS = 0.1 × book page views
   + 0.2 × catalog clicks
   + 0.6 × "Reserve" button presses
```

From `UserEvent` rows in the window with this `book_id` and type `book_view`,
`book_click` or `borrow_intent`. Each type counts **at most once per account, book
and Kyiv day**, so reloading a page does not inflate the score. Events whose account
was deleted count once per book, type and day.

### 4. Preferences — `PS`

```text
PS = 0.5 × likes added
   + 0.8 × favourites added
   + 0.4 × Σ (rating − 3)
```

From `BookLike.created_at` and `FavoriteBook.created_at` in the window, and
`BookRating` rows whose `updated_at` is in the window: a 5 adds 0.8, a 3 adds
nothing, a 1 subtracts 0.8. Only current state exists: a like removed since is gone.

### 5. Stock pressure — `SP`

```text
SP = 4 × utilisation now
   + 2 × (1 if no copy is available now, else 0)

utilisation = min(1, (copies on loan + active reservations) / copies)
```

From `Book.objects.with_availability(now)`. A book with no copies has utilisation 1.
Stock pressure is a snapshot, so it has no previous-window value.

## Demand index — `D`

The scores have different scales, so each is first scaled to 0–100 against the
catalog: `score / largest value of that score in either window × 100` (0 when the
largest value is 0). Using the same divisor for both windows keeps them comparable.

```text
D = 0.40 × LS + 0.25 × RS + 0.15 × IS + 0.10 × PS + 0.10 × SP      (0–100)
```

Loans and reservations weigh most because they are actions; interest and
preferences refine them; stock pressure lifts books with no copy free.

The trend uses only the four scores that have a previous value:

```text
A = 0.40 × LS + 0.25 × RS + 0.15 × IS + 0.10 × PS
trend = A(W) / A(P), limited to 0.5 … 2
```

When `A(P)` is 0 there is nothing to compare with, and the trend is 1.

## Forecast and recommendation

```text
forecast loans (next 30 days)  F = loans issued in W × trend     (rounded)
loan length                    = average days of this book's loans returned
                                 in the last 90 days; 14 when there are none
capacity per copy              = 30 / loan length                (loans per copy per month)
copies needed                  = ⌈F / capacity per copy⌉
copies to buy                  = copies needed − copies now, if above 0
```

14 days is the default loan in the demo data; a librarian may choose another length
per loan, which the average then reflects.

### Worked example

"Kobzar", 5 copies. In `W`: 14 loans issued, 4 copies on loan now, 3 reservations
issued, 1 active, 1 expired, 41 views, 12 clicks, 6 "Reserve" presses, 2 likes,
1 favourite, ratings 5 and 4; every copy is taken.

| Score | Calculation | Value |
| --- | --- | --- |
| LS | 14 + 0.5 × 4 | 16 |
| RS | 3 + 0.6 + 0.4 | 4.0 |
| IS | 0.1 × 41 + 0.2 × 12 + 0.6 × 6 | 10.1 |
| PS | 0.5 × 2 + 0.8 + 0.4 × (2 + 1) | 3.0 |
| SP | 4 × 1.0 + 2 × 1 | 6 |

With `A(W) / A(P) = 1.2`: `F = 14 × 1.2 ≈ 17` loans. Loans last 14 days on average,
so a copy serves `30 / 14 ≈ 2.14` loans a month; `⌈17 × 14 / 30⌉ = ⌈7.9⌉ = 8` copies
are needed, so the recommendation is **buy 3**. (Figures are illustrative.)

## The Forecast page

```text
Analytics:  [ Overview ]  [ Activity log ]  [ Forecast ]

Book demand forecast                          Next 30 days, from the last 30 · Kyiv time
+--------------------+ +--------------------+ +--------------------+
| Books to buy   3   | | Copies to buy  7   | | Rising demand  5   |
+--------------------+ +--------------------+ +--------------------+

#  Book          Demand  Trend        Forecast  Copies  Recommendation
1  Kobzar   (i)  86      ↑ +20%       17 loans  0 / 5   Buy 4
2  People   (i)  71      → 0%          6 loans  0 / 1   Buy 2
3  1984     (i)  44      ↓ −30%        5 loans  3 / 8   Enough
...
                                            [ How the forecast works ]
```

- Books are ranked by `D`, then by forecast loans, then by title; only books with
  some activity in either window are listed, at most 25.
- The "i" disclosure on each row (the same keyboard-friendly `<details>` as the
  Overview tiles) shows the five scores with their terms, the loan length used and
  the capacity per copy.
- Trend is written as text with an arrow and a sign, never by colour alone.
- **How the forecast works** expands to the formulas and weights above.
- An empty library shows "No loans, reservations or tracked activity yet" instead
  of the table.
- Every book links to its page; the page runs a fixed number of queries.

## Acceptance criteria

1. Each of the five scores matches its definition on a controlled data set,
   including the once-per-day rule, reader versus library cancellations and the
   snapshot of copies on loan at the end of each window.
2. `D`, the trend limits, the 14-day fallback and the rounding of copies to buy are
   tested on edge cases: no previous activity, no copies, no returned loans.
3. Readers get 403, anonymous users are sent to sign in, and the page shows no
   personal data.
4. The page runs a fixed number of queries however large the catalog is.
5. The page passes the accessibility check (axe, WCAG 2.2 AA) and CI.

## Out of scope

- Learned or seasonal models, and confidence intervals.
- Recording refused reservations or a waiting list.
- An API endpoint for the forecast; it can reuse the service later.

## Implementation

Built in `events/forecast.py` (`demand_forecast(now=None, limit=25)` and `WEIGHTS`),
`events/forecast_page.py`, `events/templates/events/forecast.html` and the third tab
in `events/_tabs.html`; tested in `events/test_forecast.py` and
`events/test_forecast_page.py`. The page computes everything in a fixed number of
queries: one per source, plus the books and their loan lengths. "How the forecast
works" is rendered from `WEIGHTS`, so the page always shows the weights in use.

The Forecast tab sits next to the KAN-54 tabs and reuses the KAN-34 window
helpers, so this branch merges the PR #63 branch (KAN-33, KAN-34, KAN-54); once
that PR is merged into `main`, this one carries only KAN-35.

## Implementation plan

1. **Service** — `events/forecast.py`: the windows, `WEIGHTS`, one bulk query per
   source (loans, reservations, events, preferences, availability, loan lengths),
   the five scores, scaling, `D`, trend, forecast and copies to buy. Pure function
   `demand_forecast(now=None, limit=25)` returning plain data.
2. **Service tests** — `events/test_forecast.py`: each score on fixed data, the
   once-per-day rule, cancellations, end-of-window loans, scaling with an all-zero
   score, trend limits and the zero-previous case, the 14-day fallback, rounding of
   copies to buy, an empty catalog, a fixed query count and no account data.
3. **Page** — route `forecast/` named `events_forecast` with `librarian_required`,
   `events/forecast_page.py` for what the page shows, template
   `events/forecast.html`, and a third tab in `events/_tabs.html`.
4. **Page tests** — access (anonymous, reader, librarian, administrator), the
   table, ranking and the "Buy N" / "Enough" column, the disclosure contents, the
   empty state, a fixed query count.
5. **Checks and documentation** — add `/events/forecast/` to the accessibility
   check and the access contract, describe the tab in the README, add a changelog
   entry, and run the CI suite, `ruff` and `black`.

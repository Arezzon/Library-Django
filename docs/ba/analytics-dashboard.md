# Librarian analytics dashboard: metrics and wireframes (KAN-33)

The dashboard answers three questions for librarians and administrators:
**which books are in demand, how busy the desk is, and how this period compares
with the previous one.** It shows aggregates only. This document is the design
input for KAN-34 (metrics and API) and KAN-54 (the working panel). Demand
forecasting (KAN-35) is out of scope; the dashboard only leaves room for it.

## Audience and access

| Audience | Page | API |
| --- | --- | --- |
| Librarian, administrator (`is_librarian`) | Allowed | Allowed |
| Reader | 404, same page as an unknown address (KAN-80) | 403 |
| Anonymous | Redirect to sign-in with `next` | 401 |

The existing `librarian_required` decorator (page) and `IsLibrarian` permission
(API) cover these rows; administrators pass because `is_librarian` includes them.
Navigation already shows the **Analytics** link only to these roles.

## Placement

The new overview becomes the landing page of **Analytics** at `/events/`.
The existing per-event screen stays one tab away as **Activity log**, unchanged,
at `/events/activity/`, because it serves a different job (auditing what happened)
and shows reader emails, which the overview does not.

KAN-54 builds the page as `events/overview_page.py` (what the page shows, from the
KAN-34 service), `events/views.py` and `events/templates/events/overview.html`,
tested in `events/test_overview_page.py`. The approved mock-up kept the app's own
header and moved each tile's details behind an "i" button.

```text
Analytics:  [ Overview ]  [ Activity log ]
```

## Period

| Option | Range (Kyiv time, inclusive) | Chart bucket | Default |
| --- | --- | --- | --- |
| Last 7 days | today and the 6 days before | day | |
| Last 30 days | today and the 29 days before | day | yes |
| Last 90 days | 13 ISO weeks ending this week | week (Mon–Sun) | |
| Last 12 months | 12 calendar months ending this month | month | |

- Day boundaries use `TIME_ZONE = "Europe/Kyiv"`, as the rest of the site does.
- The current day, week or month is partial; its bar is labelled "so far".
- The **previous period** is the range of the same length immediately before.
- The period is a query parameter (`?period=7d|30d|90d|12m`); an unknown value
  falls back to the default rather than erroring, as the activity log does with `days`.
- Custom date ranges are out of scope for P1.

## Data sources

| Source | Used for | Notes |
| --- | --- | --- |
| `order.Order` | Loans issued, returns, overdue, borrowers, top books | Authoritative for the desk. `created_at` is the issue time, `end_at` the return time, `plated_end_at` the due time |
| `order.Reservation` | Reservations created, issued, expired, cancelled | `created_at` and `state` |
| `book.Book` (`with_availability(now)`) | Copies and current availability in the top list | Snapshot at request time |
| `events.UserEvent` (KAN-30) | Book views (`book_view`) and catalog searches (`search`) | Interest, not demand; only exists since tracking started |

Loans and returns are counted from `Order`, not from `order_created` and
`order_returned` events: orders are the record the desk works from and they go
back further than tracking does. Events add the *interest* that orders cannot show.

## Metrics

### Summary tiles

Each tile shows the value for the period and the short change against the previous
period ("−11 (−6%)"). Everything else about the figure sits behind an "i" button: a
native `<details>` disclosure that works by keyboard and without JavaScript. It says
what the figure counts, the previous period's value or why there is no comparison,
and, for reservations, how they split by state.

| Tile | Definition | Comparison |
| --- | --- | --- |
| Loans issued | `Order` rows whose `created_at` falls in the period | vs previous period |
| Returns | `Order` rows whose `end_at` falls in the period | vs previous period |
| Active borrowers | Distinct `Order.user` with a loan issued in the period | vs previous period |
| Overdue now | `Order` with `end_at` empty and `plated_end_at` earlier than now | none: it is a snapshot, labelled "now" |
| Reservations | `Reservation` rows created in the period; subtitle splits them into issued / expired / cancelled / still active | vs previous period |
| Book views | `UserEvent` of type `book_view` in the period | vs previous period |

The change is shown as an absolute difference and a percentage, with a sign and a
word ("+12 (+20%) vs previous 30 days"), never by colour alone. When the previous
value is 0 the percentage is omitted ("+5, previously none"). When the previous
period is not fully covered by history the comparison is replaced by
"No comparison: history starts 14 Oct 2026".

### Loans over time

A bar chart of loans issued per bucket with returns as a second series, for the
selected period. Each bar is followed by a table with the same numbers for screen
readers, as the current daily chart does (KAN-69). Buckets before the history
start are drawn hatched and labelled "no data", not as zero.

### Most borrowed books (Top 10)

| Column | Definition |
| --- | --- |
| Rank | By loans issued in the period, descending; ties by views, then title, then book ID |
| Book | Title linked to the book page |
| Loans | Loans issued in the period |
| Views | `book_view` events for the book in the period; "—" before tracking began |
| Available | `available / total` copies now, from `Book.objects.with_availability(now)` |

Only books with at least one loan in the period are listed. Loans cannot point to
a deleted book (`on_delete=PROTECT`), so the list never shows deleted titles.

### Most viewed books (Top 10)

The same table ranked by views, ties by book ID, with loans as the second column. Next to the
borrowed list it shows books that attract interest but are not borrowed. Views of
a since-deleted book appear as "Deleted book #ID" without a link, as today.

### Reader activity

| Metric | Definition |
| --- | --- |
| Active borrowers | As the tile |
| First-time borrowers | Active borrowers whose earliest loan ever is in the period |
| Returning borrowers | Active borrowers minus first-time borrowers |
| Loans per borrower | Count of active borrowers with 1, 2–3 and 4 or more loans issued in the period |
| Readers with an overdue loan | Distinct users among "Overdue now" |
| Searches | `search` events in the period (count only) |

This section shows counts only. It never lists names, emails, account IDs or
search texts. Per-reader detail stays on the existing user pages and in the
Activity log, where it already sits behind the same role check.

## History and empty states

The dashboard must distinguish **zero** from **unknown**.

- **History start** per source: earliest `Order.created_at`, earliest
  `Reservation.created_at` and earliest `UserEvent.occurred_at`.
  An empty table has no history start.
- If the period starts before a source's history start, the page shows one notice
  above the tiles, for example:
  "Loan history starts 12 Sep 2026; book views are tracked from 14 Oct 2026.
  Earlier days are shown as no data." Affected chart buckets are hatched,
  comparisons that need missing data are hidden, and the "Views" column shows "—".
- **No data at all** (fresh install, empty test database): the tiles show 0 with
  "No loans yet", the chart shows an empty axis with the text "No loans in this
  period", both top lists show their empty message, and the page returns 200.
- **Data, but none in the period**: tiles show 0, comparisons still work,
  lists say "No loans in the last 7 days" and suggest a longer period.

## Privacy

- Aggregates only; no personal fields leave the server for this page or its API.
- Search texts are not shown, even in aggregate, because they can contain
  personal data (KAN-51 already treats them as private).
- Book titles are catalog data and can be shown.
- Deleting an account deletes that user's loans (`Order.user` is `on_delete=CASCADE`),
  so past counts can fall afterwards. The dashboard documents this in its help text;
  changing the cascade is a separate decision and not part of this work.

## Accessibility

The page follows the KAN-69 rules: one `h1`, each card an `h2` section, chart data
also given as a table, deltas expressed in text, contrast at AA, the period control
a labelled `<select>` that works without JavaScript, and a "Times are in Kyiv time"
note under the period selector.

## Wireframes

### Desktop (≥ 1024 px)

```text
+------------------------------------------------------------------------------+
| LibrarySys   Catalog  Authors  Loans  Reservations  [Analytics]  Users   (me)|
+------------------------------------------------------------------------------+
| Analytics                                                                    |
| [ Overview ]  Activity log                                                   |
|                                                                              |
| Library overview                               Period [ Last 30 days  v ]   |
| What readers borrow and how busy the desk is.   Times are in Kyiv time      |
|                                                                              |
| +--------------------------------------------------------------------------+ |
| | (i) Book views are tracked from 14 Oct 2026. Earlier days show no data.  | |
| +--------------------------------------------------------------------------+ |
|                                                                              |
| +------------+ +------------+ +------------+ +------------+ +------------+   |
| | Loans      | | Returns    | | Active     | | Overdue    | | Reserva-   |   |
| | issued     | |            | | borrowers  | | now        | | tions      |   |
| |    128     | |    117     | |     46     | |      7     | |     31     |   |
| | +12 (+10%) | | -3 (-3%)   | | +4 (+10%)  | | 5 readers  | | 22 issued  |   |
| | vs prev 30d| | vs prev 30d| | vs prev 30d| | as of 14:05| | 6 expired  |   |
| +------------+ +------------+ +------------+ +------------+ +------------+   |
|                                                                              |
| +----------------------------------------------+ +-------------------------+ |
| | Loans over time            [#] loans [=] ret.| | Reader activity         | |
| |  8 |              #                          | | Active borrowers     46 | |
| |  6 |    #  #     ##  #       #               | |  first-time          9 | |
| |  4 | ///  ## #  ### ## #  #  ##  #           | |  returning          37 | |
| |  2 | /// ### ## ###### ## ## ### ##          | | Loans per borrower      | |
| |  0 +-----------------------------------------| |  1 ......... 21         | |
| |     03/10  ...       17/10  ...      01/11   | |  2-3 ....... 18         | |
| |  /// = no data before history start          | |  4+ ........  7         | |
| |  [ table with the same numbers, sr-only ]    | | With overdue loan    5  | |
| +----------------------------------------------+ | Searches           312  | |
|                                                  +-------------------------+ |
| +------------------------------------+ +-----------------------------------+ |
| | Most borrowed books                | | Most viewed books                 | |
| | #  Book              Loans Views Av| | #  Book              Views Loans  | |
| | 1  Clean Code          9    41  0/3| | 1  Dune                 77     2  | |
| | 2  1984                7    18  1/4| | 2  Clean Code           41     9  | |
| | 3  The Pragmatic Pr..  6     —  2/2| | 3  Deleted book #57     12     —  | |
| | ...                                | | ...                               | |
| +------------------------------------+ +-----------------------------------+ |
|                                                                              |
| Deleting an account also removes its loans, so earlier totals can decrease.  |
+------------------------------------------------------------------------------+
```

### Mobile (< 640 px)

Cards stack in reading order; tiles become a two-column grid; tables keep
Rank, Book and the ranking column, and move the rest into a second line.

```text
+------------------------------+
| Analytics                    |
| [Overview] Activity log      |
| Library overview             |
| Period [ Last 30 days    v ] |
| (i) Views tracked from 14 Oct|
| +-----------+ +-----------+  |
| | Loans 128 | | Returns   |  |
| | +12 (+10%)| | 117  -3   |  |
| +-----------+ +-----------+  |
| +-----------+ +-----------+  |
| | Borrowers | | Overdue   |  |
| | 46   +4   | | 7 now     |  |
| +-----------+ +-----------+  |
| +-----------+ +-----------+  |
| | Reserv. 31| | Views 1204|  |
| +-----------+ +-----------+  |
| Loans over time              |
|  ## # ### ## # ## ###        |
| Most borrowed books          |
| 1 Clean Code          9      |
|   41 views · 0/3 available   |
| 2 1984                7      |
|   18 views · 1/4 available   |
| Most viewed books   ...      |
| Reader activity     ...      |
+------------------------------+
```

### Empty database

```text
+------------------------------------------------------------------------------+
| Library overview                               Period [ Last 30 days  v ]   |
| +--------------------------------------------------------------------------+ |
| | (i) No loans, reservations or tracked activity yet. Figures will appear  | |
| |     after the first loan is issued at the desk.                          | |
| +--------------------------------------------------------------------------+ |
| | Loans issued 0 | Returns 0 | Active borrowers 0 | Overdue now 0 | ...     | |
| |   No comparison: no history yet                                         | |
| +--------------------------------------------------------------------------+ |
| | Loans over time:   No loans in this period.                              | |
| | Most borrowed books:   No loans in this period.                          | |
| | Most viewed books:     No tracked book views in this period.             | |
| +--------------------------------------------------------------------------+ |
+------------------------------------------------------------------------------+
```

### Reader opens `/events/`

The site's "not found" page, the same as for an unknown address ("We can't find
this page." with a link to the home page), so the page does not confirm that it
exists (KAN-80). No figures are rendered, and the API returns 403 with no figures.

## API (KAN-34)

Implemented in `events/overview.py` (`library_overview(period, limit, now)`) and
`events/api_views.py` (`AnalyticsOverviewView`), tested in `events/test_overview.py`.
One read-only endpoint keeps the page and its tests to a single query path; it runs
a fixed number of queries however much data there is:

```text
GET /api/v1/analytics/overview/?period=30d&limit=10
```

- `period`: `7d`, `30d` (default), `90d`, `12m`; anything else → 400 for the API
  (the page itself falls back to the default). An empty value counts as absent.
- `limit`: Top-N size, integer 1–20, default 10.
- Any other parameter → 400, so no account selector can be passed.
- `period.start` and `period.end` are inclusive local dates; `end` is today.
- The last series bucket has `"partial": true`: it is still in progress.
- Access as above; responses are `Cache-Control: private, no-store`.

```json
{
  "period": {"key": "30d", "start": "2026-10-03", "end": "2026-11-01",
             "bucket": "day", "timezone": "Europe/Kyiv"},
  "history_start": {"loans": "2026-09-12", "reservations": "2026-10-20",
                    "events": "2026-10-14"},
  "summary": {
    "loans_issued": {"value": 128, "previous": 116},
    "returns": {"value": 117, "previous": 120},
    "active_borrowers": {"value": 46, "previous": 42},
    "overdue_now": {"value": 7, "readers": 5, "as_of": "2026-11-01T14:05:00+02:00"},
    "reservations": {"value": 31, "previous": null,
                     "issued": 22, "expired": 6, "cancelled": 2, "active": 1},
    "book_views": {"value": 1204, "previous": null}
  },
  "series": [{"start": "2026-10-03", "loans": 3, "returns": 2,
              "covered": true, "partial": false}],
  "top_borrowed": [{"book_id": 4, "title": "Clean Code", "loans": 9,
                    "views": 41, "available": 0, "copies": 3}],
  "top_viewed": [{"book_id": 57, "title": null, "views": 12, "loans": null}],
  "readers": {"active": 46, "first_time": 9, "returning": 37,
              "loans_per_borrower": {"1": 21, "2-3": 18, "4+": 7},
              "with_overdue": 5, "searches": 312}
}
```

`previous` is `null` when the previous period is not fully covered by that
source's history. A series bucket before the history start has `"covered": false`
and zero counts. `title: null` marks a deleted book.

## Acceptance for this design

1. Every figure on the page has a definition above, with its source, time field
   and period rule.
2. Empty, partial-history and no-data-in-period states are specified and look
   different from one another.
3. The page and API expose no personal data, and readers cannot open either.
4. Wireframes cover desktop, mobile, the empty database and the reader case.

## Out of scope

- Demand forecasting and purchase suggestions (KAN-35); the "Available" column and
  the views/loans pair are the inputs it will build on.
- Custom date ranges, CSV export, per-author or per-genre breakdowns.
- Changes to tracking (KAN-30) or to account deletion.

## Decisions

1. Librarians and administrators who borrow books are library clients too, so
   "Active borrowers" and every reader figure count all accounts with a loan.
2. The 12-month period is part of P1. Months before the history start are shown
   as no data, so a young installation is not a reason to drop it.

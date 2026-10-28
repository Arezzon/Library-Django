"""Test helpers shared by the apps' query-count tests (research R8)."""

from django.db import connection
from django.test.utils import CaptureQueriesContext

ROWS = 50


def assert_same_query_count(test, client, url, add_rows):
    """Assert that ``url`` uses as many queries with 50 rows as with 1.

    ``add_rows(n)`` creates n more rows of the list under test. The page must answer
    200 both times. Returns the response with 50 rows, so a test can check they show.
    """
    add_rows(1)
    with CaptureQueriesContext(connection) as one_row:
        response = client.get(url)
    test.assertEqual(response.status_code, 200)
    add_rows(ROWS - 1)
    with CaptureQueriesContext(connection) as all_rows:
        response = client.get(url)
    test.assertEqual(response.status_code, 200)
    test.assertEqual(
        len(all_rows),
        len(one_row),
        f"{url} used {len(one_row)} queries with 1 row and {len(all_rows)} with "
        f"{ROWS}:\n" + "\n".join(query["sql"] for query in all_rows.captured_queries),
    )
    return response

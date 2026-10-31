"""Verify durable private states and search retries over a real HTTP session.

Run only against a disposable seeded stack; the selected book's flags are reset.
The search event is checked separately by the asynchronous tracking smoke tests.
"""

import argparse
import http.cookiejar
import json
import urllib.parse
import urllib.request
import uuid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    cookies = http.cookiejar.CookieJar()
    session = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))

    def csrf():
        return next(c.value for c in cookies if c.name == "csrftoken")

    def request(path, method="GET", data=None):
        headers = {"Referer": base + "/"}
        body = None
        if data is not None:
            body = json.dumps(data).encode()
            headers["Content-Type"] = "application/json"
        if method != "GET":
            headers["X-CSRFToken"] = csrf()
        with session.open(
            urllib.request.Request(
                base + path, data=body, method=method, headers=headers
            ),
            timeout=90,
        ) as response:
            return json.load(response)

    def login():
        with session.open(base + "/authentication/login/", timeout=30):
            pass
        body = urllib.parse.urlencode(
            {
                "email": "reader@library.com",
                "password": "reader123password",
                "csrfmiddlewaretoken": csrf(),
            }
        ).encode()
        with session.open(
            urllib.request.Request(
                base + "/authentication/login/",
                data=body,
                headers={"Referer": base + "/authentication/login/"},
            ),
            timeout=30,
        ):
            pass
        assert any(c.name == "sessionid" for c in cookies), "Demo sign-in failed"

    login()
    books = request("/api/v1/book/")
    if isinstance(books, dict):
        books = books["results"]
    book_id = books[0]["id"]
    path = f"/api/v1/books/{book_id}/preferences/"
    try:
        for _ in range(2):
            state = request(path, "PATCH", {"liked": True, "favorite": True})
            assert state == {"book_id": book_id, "liked": True, "favorite": True}
        # A genuinely new session reads the same PostgreSQL state.
        cookies.clear()
        login()
        assert request(path)["liked"] and request(path)["favorite"]
        saved = request("/api/v1/me/book-preferences/?kind=favorites")
        assert sum(book["id"] == book_id for book in saved) == 1
        identity = str(uuid.uuid4())
        search_path = "/api/v1/books/search/?" + urllib.parse.urlencode(
            {"q": "detective", "search_id": identity}
        )
        first = request(search_path)
        second = request(search_path)
        assert first and [b["id"] for b in first] == [b["id"] for b in second]
    finally:
        for _ in range(2):
            state = request(path, "DELETE")
            assert not state["liked"] and not state["favorite"]
    print(
        "PASS: preferences survive a new session; repeated writes/deletes and search retries are stable"
    )


if __name__ == "__main__":
    main()

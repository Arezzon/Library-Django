"""Owned rating API smoke checks for a disposable, seeded stack."""

import argparse
import http.cookiejar
import json
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--recommendations", action="store_true")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    cookies = http.cookiejar.CookieJar()
    session = build_opener(HTTPCookieProcessor(cookies))

    def csrf():
        return next(cookie.value for cookie in cookies if cookie.name == "csrftoken")

    def login():
        with session.open(base + "/authentication/login/", timeout=30):
            pass
        data = urlencode(
            {
                "email": "reader@library.com",
                "password": "reader123password",
                "csrfmiddlewaretoken": csrf(),
            }
        ).encode()
        with session.open(
            Request(
                base + "/authentication/login/",
                data=data,
                headers={"Referer": base + "/authentication/login/"},
            ),
            timeout=30,
        ):
            pass
        assert any(cookie.name == "sessionid" for cookie in cookies)

    def api(path, method="GET", data=None):
        headers = {"Referer": base + "/"}
        if method != "GET":
            headers["X-CSRFToken"] = csrf()
        body = None if data is None else json.dumps(data).encode()
        if body is not None:
            headers["Content-Type"] = "application/json"
        with session.open(
            Request(base + path, data=body, method=method, headers=headers), timeout=60
        ) as response:
            return json.load(response)

    login()
    books = api("/api/v1/book/")
    if isinstance(books, dict):
        books = books["results"]
    if args.recommendations:
        choices = api("/api/v1/books/recommendations/?limit=20")
        assert choices, "Seeded reader has no recommendation candidate"
        book_id = choices[0]["id"]
    else:
        book_id = books[0]["id"]
    path = f"/api/v1/books/{book_id}/rating/"
    original = api(path)["value"]
    try:
        for _ in range(2):
            assert api(path, "PUT", {"value": 5}) == {"book_id": book_id, "value": 5}
        assert api(path, "PATCH", {"value": 1})["value"] == 1
        if args.recommendations:
            choices = api("/api/v1/books/recommendations/?limit=20")
            assert all(
                book["id"] != book_id and book["available_count"] > 0
                for book in choices
            )
        cookies.clear()
        login()
        assert api(path)["value"] == 1
        for data in ({"value": 6}, {"value": True}, {"value": 5, "user_id": 1}):
            try:
                api(path, "PUT", data)
            except HTTPError as error:
                assert error.code == 400
            else:
                raise AssertionError("Invalid rating was accepted")
        for _ in range(2):
            assert api(path, "DELETE")["value"] is None
        if args.recommendations:
            restored = api("/api/v1/books/recommendations/?limit=20")
            assert book_id in [book["id"] for book in restored]
    finally:
        (
            api(path, "DELETE")
            if original is None
            else api(path, "PUT", {"value": original})
        )
    print(
        "PASS: owned rating create/update/retry/delete, new session and strict validation"
    )


if __name__ == "__main__":
    main()

"""Read-only HTTP smoke checks against the seeded disposable catalog."""

import argparse
import http.cookiejar
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    cookies = http.cookiejar.CookieJar()
    session = build_opener(HTTPCookieProcessor(cookies))
    with session.open(base + "/authentication/login/", timeout=30):
        pass
    token = next(cookie.value for cookie in cookies if cookie.name == "csrftoken")
    body = urlencode(
        {
            "email": "reader@library.com",
            "password": "reader123password",
            "csrfmiddlewaretoken": token,
        }
    ).encode()
    with session.open(
        Request(
            base + "/authentication/login/",
            data=body,
            headers={"Referer": base + "/authentication/login/"},
        ),
        timeout=30,
    ):
        pass
    assert any(
        cookie.name == "sessionid" for cookie in cookies
    ), "Seeded reader could not sign in"

    def ask(query):
        with session.open(
            base + "/api/v1/assistant/?" + urlencode({"q": query}), timeout=30
        ) as response:
            assert response.status == 200
            assert response.headers["Cache-Control"] == "private, no-store"
            return json.load(response)

    title = ask("книга: Kobzar")
    assert title["status"] == "found"
    book = next(book for book in title["books"] if book["title"] == "Kobzar")
    with session.open(base + book["url"], timeout=30) as response:
        assert response.status == 200
    stock = ask("наявність: Kobzar")
    assert stock["books"][0]["id"] == book["id"]
    assert stock["books"][0]["available_count"] >= 0
    assert stock["checked_at"] and stock["availability_notice"]
    author = ask("автор: Taras Shevchenko")
    assert author["status"] == "found"
    assert any(item["id"] == book["id"] for item in author["books"])
    with session.open(base + author["authors"][0]["url"], timeout=30) as response:
        assert response.status == 200
    absent = ask("KAN52-no-such-catalog-title-784603")
    assert (
        absent["status"] == "not_found"
        and not absent["books"]
        and not absent["authors"]
    )
    assert ask("")["status"] == "clarification_required"
    try:
        build_opener().open(base + "/api/v1/assistant/?q=Kobzar", timeout=30)
    except HTTPError as error:
        assert error.code == 401
    else:
        raise AssertionError("Anonymous request was accepted")
    # These inputs and exact expected titles are the PR's reproducible live demo.
    controls = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "library/ai/control/questions_natural.json"
        ).read_text()
    )
    for control in controls:
        result = ask(control["question"])
        assert result["status"] == control["status"], (control["question"], result)
        titles = sorted(book["title"] for book in result["books"])
        assert titles == sorted(control["titles"]), (control["question"], titles)
        for book in result["books"]:
            assert book["url"].startswith("/book/") and book["available_count"] >= 0
        print(
            json.dumps(
                {
                    "question": control["question"],
                    "status": result["status"],
                    "titles": titles,
                },
                ensure_ascii=False,
            )
        )
    print(
        "PASS: catalog facts, auth and all 16 natural UA/EN demo queries with the real CPU encoder"
    )


if __name__ == "__main__":
    main()

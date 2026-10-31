#!/usr/bin/env python3
"""Reservation burst and load check against a running stack (SC-002, SC-003).

Burst mode: --burst temporary readers reserve a book with one copy at the same moment,
and exactly one must succeed, in each of --runs runs; the winner cancels before the
next run, so every run competes for the same copy. Load mode: --readers readers
reserve a book at the same moment, then a librarian issues half of the reservations
and cancels the other half at once, and each operation's p95 must stay under
--max-p95-ms.

The script makes its accounts, their sessions and CSRF tokens, and its books through
`manage.py shell` in the web container, and removes them afterwards with the
reservations, loans and analytics events they made; the audit trail keeps its entries,
as for every critical change. Session keys never reach the output. Standard library
and the Docker CLI only, so it runs on the Pi:

    python3 scripts/smoke_reservation_load.py --project-name library \\
        --base-url http://localhost:8000 --burst 100 --readers 30

Prints a JSON summary ending in "result": "PASS" or "FAIL: ..."; exits 1 on a failure.
"""

import argparse
import json
import statistics
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from functools import partial

parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("--compose-file", help="Read the project name from this file.")
parser.add_argument("--project-name", help="Compose project (Portainer stack) name.")
parser.add_argument("--base-url", default="http://localhost:8000")
parser.add_argument(
    "--burst", type=int, default=0, help="Simultaneous reservations of one copy."
)
parser.add_argument("--runs", type=int, default=1, help="Repeat the burst this often.")
parser.add_argument(
    "--readers", type=int, default=0, help="Readers who reserve at once in load mode."
)
parser.add_argument("--max-p95-ms", type=float, default=3000)
args = parser.parse_args()

# Both snippets read their parameters from stdin, so no value reaches a command line.
SETUP = """
import json, sys
from importlib import import_module
from django.conf import settings
from django.contrib.auth import BACKEND_SESSION_KEY, HASH_SESSION_KEY, SESSION_KEY
from django.middleware.csrf import CSRF_SESSION_KEY
from django.utils.crypto import get_random_string
from authentication.models import ROLE_LIBRARIAN, CustomUser
from book.models import Book

params = json.loads(sys.stdin.read())
prefix = "load-check-" + params["run"] + "-"
store = import_module(settings.SESSION_ENGINE).SessionStore

def account(name, role=CustomUser.ROLE_VISITOR):
    user = CustomUser.objects.create_user(
        email=prefix + name + "@example.invalid", password=None, first_name="Load",
        middle_name="", last_name="Check", role=role, is_active=True)
    session = store()
    session[SESSION_KEY] = str(user.pk)
    session[BACKEND_SESSION_KEY] = settings.AUTHENTICATION_BACKENDS[0]
    session[HASH_SESSION_KEY] = user.get_session_auth_hash()
    csrf = get_random_string(32)
    if settings.CSRF_USE_SESSIONS:
        session[CSRF_SESSION_KEY] = csrf
    session.create()
    return {"session": session.session_key, "csrf": csrf}

print("SETUP=" + json.dumps({
    "cookies": {"session": settings.SESSION_COOKIE_NAME,
                "csrf": settings.CSRF_COOKIE_NAME},
    "librarian": account("librarian", ROLE_LIBRARIAN),
    "readers": [account("reader-" + str(n)) for n in range(params["readers"])],
    "books": {name: Book.objects.create(name=prefix + name, count=copies).pk
              for name, copies in params["books"].items()},
}))
"""

CLEANUP = """
import json, sys, time
from importlib import import_module
from django.conf import settings
from django.db.models import Q
from authentication.models import CustomUser
from book.models import Book
from events.models import EventType, UserEvent

params = json.loads(sys.stdin.read())
prefix = "load-check-" + params["run"] + "-"
accounts = CustomUser.objects.filter(email__startswith=prefix)
books = list(Book.objects.filter(name__startswith=prefix).values_list("pk", flat=True))
# Each loan's analytics event is stored by the worker after commit; wait for them.
loans = UserEvent.objects.filter(book_id__in=books, event_type=EventType.ORDER_CREATED)
deadline = time.monotonic() + 30
while loans.count() < params["loans"] and time.monotonic() < deadline:
    time.sleep(0.5)
events = UserEvent.objects.filter(Q(user__in=accounts) | Q(book_id__in=books))
removed = {"events": events.delete()[0], "accounts": accounts.count()}
accounts.delete()  # with their reservations and loans
Book.objects.filter(pk__in=books).delete()  # with their embeddings
removed["books"] = len(books)
store = import_module(settings.SESSION_ENGINE).SessionStore
for key in params["sessions"]:
    store(session_key=key).delete()
print("CLEANUP=" + json.dumps(removed))
"""


def docker(*command, stdin=None):
    result = subprocess.run(
        ["docker", *command], input=stdin, capture_output=True, text=True
    )
    if result.returncode != 0:
        # Name the cause: a shell snippet's traceback reaches only this output.
        raise SystemExit(f"docker {command[0]} failed:\n{result.stderr.strip()}")
    return result.stdout


def project_name():
    if args.project_name:
        return args.project_name
    command = ["compose"] + (["-f", args.compose_file] if args.compose_file else [])
    return json.loads(docker(*command, "config", "--format", "json"))["name"]


def web_container(project):
    filters = [
        "--filter",
        f"label=com.docker.compose.project={project}",
        "--filter",
        "label=com.docker.compose.service=web",
    ]
    ids = docker("ps", "-q", *filters).split()
    return ids[0] if ids else None


def web_shell(web, code, params, marker):
    output = docker(
        "exec",
        "-i",
        web,
        "python",
        "manage.py",
        "shell",
        "-c",
        code,
        stdin=json.dumps(params),
    )
    line = next(line for line in output.splitlines() if line.startswith(marker))
    return json.loads(line[len(marker) :])


class Client:
    """One signed-in account, calling the API with its session and CSRF token."""

    def __init__(self, account, cookies):
        self.headers = {
            "Cookie": f"{cookies['session']}={account['session']}; "
            f"{cookies['csrf']}={account['csrf']}",
            "X-CSRFToken": account["csrf"],
            "Content-Type": "application/json",
            "Referer": args.base_url + "/",
        }

    def call(self, method, path, body=None):
        """Return the status, the JSON body and the time taken in ms."""
        request = urllib.request.Request(
            args.base_url + path,
            data=None if body is None else json.dumps(body).encode(),
            method=method,
            headers=self.headers,
        )
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                status, text = response.status, response.read()
        except urllib.error.HTTPError as error:
            status, text = error.code, error.read()
        elapsed = (time.perf_counter() - started) * 1000
        try:
            return status, json.loads(text or b"{}"), elapsed
        except ValueError:
            return status, {}, elapsed


def at_once(calls):
    """Run the calls in threads that all start at the same moment."""
    if not calls:
        return []
    barrier = threading.Barrier(len(calls), timeout=60)

    def run(call):
        barrier.wait()
        return call()

    with ThreadPoolExecutor(max_workers=len(calls)) as pool:
        return list(pool.map(run, calls))


def refusal(status, body):
    return body.get("code", f"HTTP {status}") if status == 409 else f"HTTP {status}"


def percentile(values, share):
    ordered = sorted(values)
    return ordered[max(0, round(share * len(ordered)) - 1)]


def timings(values):
    if not values:
        return {"count": 0}
    return {
        "count": len(values),
        "p50": round(statistics.median(values), 1),
        "p95": round(percentile(values, 0.95), 1),
    }


def burst(readers, librarian, book, failures):
    """Every reader reserves the one copy at once, --runs times."""
    successes, held, refusals = [], [], Counter()
    for _ in range(args.runs):
        replies = at_once(
            [
                partial(reader.call, "POST", "/api/v1/reservation/", {"book": book})
                for reader in readers
            ]
        )
        won = [
            (reader, body)
            for reader, (status, body, _) in zip(readers, replies, strict=True)
            if status == 201
        ]
        refusals.update(
            refusal(status, body) for status, body, _ in replies if status != 201
        )
        status, active, _ = librarian.call("GET", "/api/v1/reservation/?state=active")
        held.append(
            sum(row["book"] == book for row in active) if status == 200 else None
        )
        successes.append(len(won))
        # The winner cancels, so the next run competes for the same copy.
        for reader, body in won:
            status, _, _ = reader.call(
                "POST", f"/api/v1/reservation/{body['id']}/cancel/", {}
            )
            if status != 200:
                failures.append(f"a burst winner's cancellation answered {status}")
    if any(count != 1 for count in successes):
        failures.append("a burst did not succeed exactly once")
    if any(count != 1 for count in held):
        failures.append("a burst held other than exactly 1 copy")
    if set(refusals) - {"no_copy_available"}:
        failures.append("a burst got refusals other than no_copy_available")
    return {
        "attempts": len(readers),
        "runs": args.runs,
        "successes": successes,
        "copies_held": held,
        "refusals": dict(refusals),
    }


def load(readers, librarian, book, failures):
    """The readers reserve at once; then half are issued and half cancelled at once."""
    replies = at_once(
        [
            partial(reader.call, "POST", "/api/v1/reservation/", {"book": book})
            for reader in readers
        ]
    )
    reserved = [body["id"] for status, body, _ in replies if status == 201]
    if len(reserved) != len(readers):
        failures.append(f"{len(readers) - len(reserved)} load reservations failed")
    half = len(reserved) // 2
    issued, cancelled = reserved[:half], reserved[half:]
    replies_after = at_once(
        [
            partial(librarian.call, "POST", f"/api/v1/reservation/{pk}/issue/", {})
            for pk in issued
        ]
        + [
            partial(
                librarian.call,
                "POST",
                f"/api/v1/reservation/{pk}/cancel/",
                {"reason": "Load check"},
            )
            for pk in cancelled
        ]
    )
    issue_replies, cancel_replies = replies_after[:half], replies_after[half:]
    if any(status != 201 for status, _, _ in issue_replies):
        failures.append("an issue in the load check failed")
    if any(status != 200 for status, _, _ in cancel_replies):
        failures.append("a cancellation in the load check failed")
    summary = {"readers": len(readers), "max_p95_ms": args.max_p95_ms}
    for name, group in (
        ("reserve_ms", replies),
        ("issue_ms", issue_replies),
        ("cancel_ms", cancel_replies),
    ):
        summary[name] = timings([elapsed for _, _, elapsed in group])
        if summary[name].get("p95", 0) > args.max_p95_ms:
            failures.append(f"{name[:-3]} p95 above {args.max_p95_ms} ms")
    return summary, sum(status == 201 for status, _, _ in issue_replies)


def main():
    if args.burst < 1 and args.readers < 1:
        parser.error("give --burst, --readers or both")
    project = project_name()
    web = web_container(project)
    if web is None:
        print(
            f"No running web container found for project {project!r}.", file=sys.stderr
        )
        return 1
    run = uuid.uuid4().hex[:12]
    books = {}
    if args.burst:
        books["burst"] = 1
    if args.readers:
        books["load"] = args.readers
    params = {"run": run, "readers": max(args.burst, args.readers), "books": books}
    summary, failures, loans, sessions = {"project": project}, [], 0, []
    try:
        setup = web_shell(web, SETUP, params, "SETUP=")
        accounts = [setup["librarian"], *setup["readers"]]
        sessions = [account["session"] for account in accounts]
        librarian = Client(setup["librarian"], setup["cookies"])
        readers = [Client(reader, setup["cookies"]) for reader in setup["readers"]]
        if args.burst:
            summary["burst"] = burst(
                readers[: args.burst], librarian, setup["books"]["burst"], failures
            )
        if args.readers:
            summary["load"], loans = load(
                readers[: args.readers], librarian, setup["books"]["load"], failures
            )
    finally:
        summary["removed"] = web_shell(
            web, CLEANUP, {"run": run, "loans": loans, "sessions": sessions}, "CLEANUP="
        )
    summary["result"] = "FAIL: " + "; ".join(failures) if failures else "PASS"
    print(json.dumps(summary, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

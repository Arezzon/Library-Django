#!/usr/bin/env python3
"""Stack budget check: peak memory of the whole stack, search and save latency.

Finds the stack's containers by their Compose project label, warms the web
workers up, then runs concurrent searches and a few book saves while sampling
`docker stats`. It also checks that every stored vector carries the current
model tag. Search needs a signed-in account: the script signs in as --email with the
password from BUDGET_CHECK_PASSWORD, or asks for it, and never takes it as an
argument. Standard library and the Docker CLI only, so it runs on the Pi:

    python3 scripts/smoke_stack_budget.py --project-name library \\
        --email reader@library.com \\
        --max-memory-gib 4 --max-search-p95-ms 500 --max-save-ms 2000

Prints a JSON summary; exits 1 when a limit is exceeded or a check fails.
"""

import argparse
import getpass
import http.cookiejar
import json
import os
import re
import statistics
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUERIES = ROOT / "library" / "book" / "search_evaluation.json"
UNITS = {"B": 1, "KIB": 2**10, "MIB": 2**20, "GIB": 2**30, "TIB": 2**40}
UNITS.update({"KB": 10**3, "MB": 10**6, "GB": 10**9, "TB": 10**12})

parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("--compose-file", help="Read the project name from this file.")
parser.add_argument("--project-name", help="Compose project (Portainer stack) name.")
parser.add_argument("--base-url", default="http://localhost:8000")
parser.add_argument(
    "--email",
    required=True,
    help="Account that searches; its password comes from BUDGET_CHECK_PASSWORD.",
)
parser.add_argument("--max-memory-gib", type=float, default=4.0)
parser.add_argument("--max-search-p95-ms", type=float)
parser.add_argument("--max-save-ms", type=float)
parser.add_argument(
    "--clients", type=int, default=int(os.getenv("WEB_CONCURRENCY") or 3)
)
parser.add_argument("--searches", type=int, default=60)
args = parser.parse_args()


def docker(*command):
    return subprocess.run(
        ["docker", *command], check=True, capture_output=True, text=True
    ).stdout


def project_name():
    if args.project_name:
        return args.project_name
    command = ["compose"] + (["-f", args.compose_file] if args.compose_file else [])
    return json.loads(docker(*command, "config", "--format", "json"))["name"]


def containers(project, service=None):
    filters = ["--filter", f"label=com.docker.compose.project={project}"]
    if service:
        filters += ["--filter", f"label=com.docker.compose.service={service}"]
    return docker("ps", "-q", *filters).split()


def to_bytes(text):
    match = re.fullmatch(r"([\d.]+)\s*([A-Za-z]+)", text.strip())
    return float(match.group(1)) * UNITS[match.group(2).upper()]


class MemorySampler(threading.Thread):
    """Sum MemUsage over the stack's containers about once a second."""

    def __init__(self, ids):
        super().__init__(daemon=True)
        self.ids, self.peak, self.done = ids, 0.0, threading.Event()

    def sample(self):
        output = docker("stats", "--no-stream", "--format", "{{json .}}", *self.ids)
        total = sum(
            to_bytes(json.loads(line)["MemUsage"].split("/")[0])
            for line in output.splitlines()
            if line.strip()
        )
        self.peak = max(self.peak, total)

    def run(self):
        while not self.done.is_set():
            self.sample()
            self.done.wait(1)


class DirectCookiePolicy(http.cookiejar.DefaultCookiePolicy):
    """Send the site's cookies back over plain HTTP. Behind the HTTPS proxy
    (TRUST_X_FORWARDED_PROTO) the site marks them Secure, but this script talks to
    the stack directly, usually on localhost, so a strict policy would drop them."""

    def return_ok_secure(self, cookie, request):
        return True


def sign_in(email, password):
    """Sign in through the sign-in form; return an opener that keeps the session."""
    cookies = http.cookiejar.CookieJar(policy=DirectCookiePolicy())
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))
    login = args.base_url + "/authentication/login/"
    opener.open(login, timeout=60).read()
    csrf = next((cookie.value for cookie in cookies if cookie.name == "csrftoken"), "")
    form = {"csrfmiddlewaretoken": csrf, "email": email, "password": password}
    request = urllib.request.Request(
        login, data=urllib.parse.urlencode(form).encode(), headers={"Referer": login}
    )
    opener.open(request, timeout=60).read()
    if not any(cookie.name == "sessionid" for cookie in cookies):
        raise SystemExit(f"Could not sign in as {email}; check the password.")
    return opener


def search(opener, query):
    url = (
        args.base_url + "/api/v1/books/search/?" + urllib.parse.urlencode({"q": query})
    )
    started = time.perf_counter()
    with opener.open(url, timeout=60) as response:
        response.read()
        if response.status != 200:
            raise RuntimeError(f"search returned HTTP {response.status}")
    return (time.perf_counter() - started) * 1000


def web_shell(web, code):
    return docker("exec", web, "python", "manage.py", "shell", "-c", code)


SAVES = """
import json, time, uuid
from book.embeddings import load_embedding_model
from book.models import Book
load_embedding_model()  # time the saves, not the model load
times = []
for _ in range(5):
    started = time.perf_counter()
    book = Book.objects.create(name=f"budget-check-{uuid.uuid4()}",
                               description="A temporary book for the budget check.")
    times.append((time.perf_counter() - started) * 1000)
    book.delete()
print("SAVES=" + json.dumps(times))
"""

VECTORS = """
from book.embedding_config import resolve
from book.models import Book, BookEmbedding
spec = resolve()
books = Book.objects.count()
current = BookEmbedding.objects.filter(model=spec.repository, model_revision=spec.tag).count()
print(f"VECTORS={current}/{books}")
"""


def percentile(values, share):
    ordered = sorted(values)
    return ordered[max(0, round(share * len(ordered)) - 1)]


def main():
    project = project_name()
    ids = containers(project)
    webs = containers(project, "web")
    if not ids or not webs:
        print(
            f"No running web container found for project {project!r}.", file=sys.stderr
        )
        return 1
    queries = [
        case["query"] for case in json.loads(QUERIES.read_text(encoding="utf-8"))
    ]

    password = os.getenv("BUDGET_CHECK_PASSWORD") or getpass.getpass(
        f"Password for {args.email}: "
    )
    timed_search = partial(search, sign_in(args.email, password))

    sampler = MemorySampler(ids)
    sampler.sample()
    sampler.start()
    try:
        with ThreadPoolExecutor(max_workers=args.clients) as pool:
            list(pool.map(timed_search, queries[: args.clients]))  # warm workers up
            jobs = [queries[i % len(queries)] for i in range(args.searches)]
            search_ms = list(pool.map(timed_search, jobs))
        output = web_shell(webs[0], SAVES)
        save_ms = json.loads(output.split("SAVES=", 1)[1].strip())
        sampler.sample()
    finally:
        sampler.done.set()
        sampler.join()
    vectors = web_shell(webs[0], VECTORS).split("VECTORS=", 1)[1].strip()
    current, books = (int(part) for part in vectors.split("/"))

    summary = {
        "project": project,
        "containers": len(ids),
        "peak_memory_gib": round(sampler.peak / 2**30, 3),
        "search_ms": {
            "count": len(search_ms),
            "p50": round(statistics.median(search_ms), 1),
            "p95": round(percentile(search_ms, 0.95), 1),
        },
        "save_ms": {
            "count": len(save_ms),
            "p50": round(statistics.median(save_ms), 1),
            "p95": round(percentile(save_ms, 0.95), 1),
        },
        "vectors_current": f"{current}/{books}",
        "clients": args.clients,
    }
    failures = []
    if sampler.peak > args.max_memory_gib * 2**30:
        failures.append(f"peak memory above {args.max_memory_gib} GiB")
    if args.max_search_p95_ms and summary["search_ms"]["p95"] > args.max_search_p95_ms:
        failures.append(f"search p95 above {args.max_search_p95_ms} ms")
    if args.max_save_ms and summary["save_ms"]["p95"] > args.max_save_ms:
        failures.append(f"save p95 above {args.max_save_ms} ms")
    if current != books:
        failures.append("some book vectors do not carry the current model tag")
    summary["result"] = "FAIL: " + "; ".join(failures) if failures else "PASS"
    print(json.dumps(summary, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

# Contract: Running version endpoint

**Covers**: FR-035, FR-036 and FR-012 (the healthcheck probe).
**Owner**: project-wide wiring. The view is `library/library/api_views.py` and the route is in
`library/library/api_urls.py`. Its tests are in `library/authentication/tests.py`, alongside the
project-wide settings tests that CI runs.

## `GET /api/v1/version/`

| Aspect | Value |
|---|---|
| Audience | Anonymous: `permission_classes = [AllowAny]`, `authentication_classes = []` (Principle II) |
| Methods | `GET`, and `HEAD` implicitly. Other methods return `405`. |
| Response `200` | `{"commit": "<string>"}`. The value is the image's `APP_COMMIT`: a 40-hex commit in published images, or `"unknown"` when the variable is unset or empty. |
| Other fields | None. The response MUST NOT include settings, hostnames, model details or any secret. |
| Database | Not used, so the endpoint answers even while the database is slow. |
| Schema | Listed in `/api/schema/`, with the response described through `extend_schema` (Principle I) |
| Caching | `Cache-Control: no-store`, so the CI poll never sees a stale proxy response |

## Consumers

| Consumer | Use |
|---|---|
| `deploy` job, confirmation step | Polls `$SITE_URL/api/v1/version/` every 15 s for up to 15 min. It passes when `commit` equals `$GITHUB_SHA` or descends from it on `main`. See [ci-pipeline.md](ci-pipeline.md). |
| `web` healthcheck (both Compose files) | `urllib` GET against `http://127.0.0.1:8000/api/v1/version/`. Any `200` means healthy. |

## Required tests

- An anonymous `GET` returns `200`, with exactly one key, `commit`.
- With `APP_COMMIT` set, its value is returned. With it unset or empty, `"unknown"` is returned.
- `POST` returns `405`.
- The path appears in the generated OpenAPI schema.

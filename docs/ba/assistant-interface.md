# Reader assistant interface (KAN-53)

`/assistant/` is the signed-in reader page for the KAN-52 `ai` catalog service.
Desktop/mobile navigation links to it. It is server rendered and needs no custom
JavaScript: labeled intent selector, question textarea, example buttons, submit,
clear, response and linked catalog sources. Interface labels and navigation follow
the existing English site; Ukrainian catalog questions remain supported.

Questions use CSRF-protected POST, not query-string navigation. GET parameters are
redirected to the clean URL. The page has no-store cache control and same-origin
policy; no conversation, question or answer is saved in a model or session.
Browsers can retain form state locally; the application makes no promise to erase
browser/OS memory. Clear loads a new empty form.

## States and scope

The page uses structured results from `ai.services.catalog_assistant`. Concise English
status messages and source cards avoid repeating the API answer and raw URLs.
The selector accepts literal title/author/availability queries; auto accepts the
KAN-52 short command grammar. This is not general conversation. The help describes
supported commands. Confirmed matches provide book detail and author/catalog links;
ambiguous results ask for refinement, absent matches state the lack of evidence.
Source failure is HTTP 503 with an alert, retry link, no fabricated sources and
`Retry-After: 5`. Ancillary reservation notices are omitted on this outage
response because they query the same failed catalog tables. Invalid/duplicate/unknown form fields return 400 with an alert.
Active-account permission checks and CSRF run before catalog access.

Availability is a snapshot. A short notice accompanies confirmed books; the page never
calls reservation/issuance services and provides no booking mutation form. Clicking
book sources opens the normal catalog where normal business checks remain intact.

## Control questions

`ai/control/questions_uk.json` defines eight reproducible Ukrainian controls. Tests
create the catalog records Кобзар / Тарас Шевченко and ambiguous Лісова titles.

| Question | Expected |
| --- | --- |
| книга: Кобзар | confirmed book and link |
| автор: Тарас Шевченко | confirmed author and book |
| наявність: Кобзар | current copy counts, snapshot notice |
| книга: Неіснуюча книга 784603 | no confirmed books |
| автор: Неіснуючий Автор 784603 | no confirmed authors |
| бронювання: Кобзар | explain supported scope and ask for clarification |
| empty question | supported examples / clarification |
| книга: Лісова | confirmed candidates and refinement request |

The existing demo seed uses transliterated titles/names. For a live demo use the
visible example buttons: `книга: Kobzar`, `автор: Taras Shevchenko`,
`наявність: Kobzar`. The UI does not invent translations absent from the catalog.

## Accessibility and privacy verification

Native select/textarea/buttons/anchors support keyboard use. Labels, help/error
associations, alert/status roles, headings, a focusable response target and a link
back to the question make states navigable without JavaScript. Django escapes all
question, catalog and response text. Source links have actual catalog titles.

The `ai` logger uses the shared request-ID/one-line configuration and emits only a
fixed response status, never a question, result, reader identifier or form object.
Unit tests capture logs for successful/missing, invalid and failed-source requests.
The existing GET API retains its KAN-52 behavior and existing q-redaction; the
reader page always sends question bodies through POST.

`ai.test_interface` exercises the control set, permissions, CSRF, validation,
source failure, escaping, reset behavior, semantic markup, private logs and absence
of loan/reservation writes. All prior app suites remain enabled in Docker Build.
On the ubuntu-latest CI leg, `scripts/browser/smoke_assistant.cjs` runs actual Chrome
keyboard submission and follows a source link, runs axe on the assistant region,
checks private-question absence in real web logs, and checks a real source outage.
The browser test temporarily renames the book table in a **disposable** database,
restores it in finally, and verifies unchanged loan/hold row counts.

Local browser reproduction against an isolated stack:

```sh
npm ci --prefix scripts/browser
CHROME_PATH=/usr/bin/google-chrome \
ASSISTANT_BASE_URL=http://127.0.0.1:18453 \
ASSISTANT_COMPOSE_FILE=/tmp/kan53-compose.yml ASSISTANT_PROJECT=kan53 \
node scripts/browser/smoke_assistant.cjs
```

CI installs its pinned Playwright Chromium. The production image excludes
node_modules and requires neither Node nor Playwright for serving the interface.
Automated axe checks cover the new region; keyboard checks do not claim a full
manual assistive-technology audit of the site's existing navigation.

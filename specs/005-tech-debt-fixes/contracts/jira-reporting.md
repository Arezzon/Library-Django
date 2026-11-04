# Contract: Jira reporting

How each of the seven issues moves, and the exact comment it gets. The comments follow each issue's
"Як звітувати" section.

## Moves

| When | Move | Transition |
| ---- | ---- | ---------- |
| Work on the issue's group starts, before any change | To Do → In Progress | `31` |
| The group's PR is open and every CI check has passed | the comment below, then In Progress → In Review | `41` |

- Before each move, re-read the issue's assignee and status. If it is not @fazelukario's, or not in
  the source status, do not move it, and name it in the final report.
- Nothing moves to Done. No description changes. No issue outside these seven is touched.

## Comment format

- Ukrainian. Code identifiers, paths, status names and handles stay as they are.
- One line per paragraph: Jira turns line breaks inside a paragraph into hard breaks.
- Links with plain-text labels, `[#<n> <title>](<url>)`, never inline code in a label.
- No past-tense verbs about a person (Ukrainian marks gender there). Use noun phrases or impersonal
  forms.
- Posted once per issue, just before the move to In Review. Any text longer than this template is
  shown to the technical lead first.

### Change issues: KAN-79, KAN-94, KAN-96, KAN-97, KAN-101, KAN-102

```markdown
PR, що закриває цю задачу: [#<n> <PR title>](<PR url>).<pair sentence>

<one-sentence summary of what changed for this issue>

Перевірки CI пройшли, тож задача переходить в **In Review**.
```

- `<pair sentence>`: for a paired issue, ` Цей самий PR закриває й <other key> (<other TD>).`;
  otherwise empty.
- Summaries:

| Issue | Summary |
| ----- | ------- |
| KAN-96 | Вихід із системи тепер працює лише через POST-форму з CSRF-токеном; GET-запит до `/authentication/logout/` отримує 405, і сесія лишається. |
| KAN-97 | Форма користувача в адмінці показує хеш пароля лише для читання, з посиланням на форму зміни пароля; збереження форми пароль не змінює. |
| KAN-79 | Неіснуюча адреса отримує 404 і сторінку `404.html` у стилі LibrarySys, з навігацією й посиланням на головну; перевірка доступності її охоплює. |
| KAN-94 | Обрано шлях 1: обидва файли браузерних тестів залишено, і CI запускає їх на кожному PR. |
| KAN-101 | Конституція й `AGENTS.md` наводять ту саму команду тестів, що й CI, разом з `ai`. Версія конституції 2.5.0, MINOR, а не PATCH: та сама поправка додає до переліку перевірок CI браузерні тести входу з KAN-94 (рішення технічного ліда від 04.11.2026). |
| KAN-102 | Новий тест обходить усі вебмаршрути й падає, якщо якогось немає в `WebRouteAccessTests`; відсутні маршрути додано. |

### Decision issue: KAN-80

```markdown
Рішення @Arezzon: варіант 1, ховати службові сторінки від читачів.

Причина: відповідь 403 підтверджує читачу, що службова сторінка існує, і розкриває структуру адрес.

Що змінилося: читач, який відкриває сторінку чи дію бібліотекаря або адміністратора, отримує ту саму сторінку 404, що й для неіснуючої адреси. Гостя, як і раніше, перенаправлено на вхід. API лишає 403. FR-004 специфікації 003 доповнено цим винятком.

Борг не залишається, тож дати перегляду немає.

PR: [#<n> <PR title>](<PR url>). Цей самий PR закриває й KAN-79 (TD-36). Перевірки CI пройшли, тож задача переходить в **In Review**.
```

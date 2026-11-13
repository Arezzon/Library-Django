# Contract: Jira texts

Every text is drafted in `drafts/` and published verbatim after the technical lead approves it
(FR-011). The text is in Ukrainian (FR-010). The blocks marked **verbatim** are copied unchanged into
every text of that kind. Everything else in angle brackets is filled in per item, from
[research R5 and R6](../research.md).

## Draft file

Each draft starts with a field block, which is not published, followed by the text that is.

```markdown
<!--
type: Task | Bug | Epic | comment on KAN-NN
summary: TD-NN · <the item>
assignee: @handle (<account ID>)
priority: Medium | Low
labels: tech-debt, td-NN[, existing labels]
parent: <Epic key>
sprint: 5
-->
<the text to publish>
```

## Change issue description

```markdown
**TD-NN** · пріоритет PN · джерело: <source> · вид роботи: **зміна коду**

## Що не так

<what is wrong today and why it matters, from the register row; one or two sentences>

## Що зробити

<the register's plan, as concrete steps; options if the owner chooses between them, as in TD-20>

## Де

<files and lines from research R6>

## Готово, коли

- <the item-specific criteria from research R6>
- Тести в застосунку, якого стосується зміна, падають без неї й проходять з нею.
- PR відповідає правилам репозиторію: назва `<action>(<service>): <description>`, шаблон опису,
  запис у `docs/shared/changelog.md`; у назві або описі є KAN-NN і TD-NN.

<the feedback block for a change>
```

**Feedback block for a change**, verbatim:

```markdown
## Як звітувати

Коли роботу завершено й є PR, який закриває цю задачу:

1. Додайте коментар із посиланням на цей PR.
2. Перемістіть задачу в **In Review**.

Не переводьте задачу в **Done** до перевірки. Технічний лід (@fazelukario) перевірить PR, оновить
реєстр технічного боргу (`docs/shared/debt-register.md`) і напише коментар із посиланням на це
оновлення. Після цього перемістіть задачу в **Done**. Якщо чогось бракує, технічний лід напише, чого
саме, і ви повернете задачу в **In Progress**.
```

## Decision issue description

```markdown
**TD-NN** · пріоритет PN · джерело: <source> · вид роботи: **рішення**

## Що вирішити

<the question from research R5, and why it matters now>

**Вирішує:** @handle. **Консультує:** @handle (if any).

## Варіанти

1. **<option>** — <what it leads to: the register status, and any follow-up change>
2. **<option>** — <…>
3. <…>

Можна запропонувати власний варіант, з тими самими поясненнями.

## Контекст

<facts and links from research R5: ADRs, code, Jira issues, constitution limits>

<the feedback block for a decision>
```

**Feedback block for a decision**, verbatim:

```markdown
## Як звітувати

Коли рішення ухвалено:

1. Додайте коментар із рішенням: обраний варіант (або власний), його причина і, якщо борг
   залишається як є, дата, коли рішення переглянути.
2. Перемістіть задачу в **In Review**.

Не переводьте задачу в **Done** до перевірки. Технічний лід (@fazelukario) внесе рішення до реєстру
технічного боргу (`docs/shared/debt-register.md`) і напише коментар із посиланням на це оновлення. Якщо
рішення потребує зміни коду, для неї буде створено окрему задачу в цьому епіку. Після цього перемістіть
задачу в **Done**. Якщо чогось бракує, технічний лід напише, чого саме, і ви повернете задачу в **In
Progress**.
```

## Comment on a reused issue

The comment adds only what the description lacks (FR-013). It does not repeat the description.

```markdown
Цю задачу включено до епіку <Epic key> (технічний борг, спринт «Лаб 5 · Тестування») як пункт реєстру
**TD-NN** · пріоритет PN · вид роботи: **<зміна коду | рішення>**.

<for TD-36: TD-37 (KAN-80) чекає на цю сторінку 404>
<for TD-37: the decision sections of the decision format: "Що вирішити", "Варіанти", "Контекст",
naming TD-36 (KAN-79) as the dependency>

<the feedback block for the kind, verbatim>
```

## Epic description

```markdown
Решта відкритих пунктів реєстру технічного боргу
([docs/shared/debt-register.md @ <commit>](https://github.com/Arezzon/Library-Django/blob/<commit>/docs/shared/debt-register.md)).
Жоден не має пріоритету P1. Кожна задача тут відповідає одному пункту реєстру.

## Задачі

| Пункт | Задача | Вид роботи | Виконавець |
| ----- | ------ | ---------- | ---------- |
| TD-NN | KAN-NN | зміна коду / рішення | @handle |

## Як звітувати

- **Зміна коду**: коментар із посиланням на PR, що закриває задачу, і статус **In Review**.
- **Рішення**: коментар із рішенням, його причиною і, якщо борг залишається як є, датою перегляду;
  статус **In Review**.

## Як перевіряємо

Технічний лід (@fazelukario) перевіряє кожну задачу в **In Review**:

- для зміни — що PR злитий у `main` і його перевірки пройшли;
- для рішення — що рішення дав той, хто вирішує, і воно має причину.

Потім технічний лід оновлює рядок реєстру через PR і пише в задачі коментар із посиланням на нього, а
виконавець переводить задачу в **Done**. Рішення, яке потребує зміни коду, отримує нову задачу в цьому
епіку.
```

The table first lists TD IDs and kinds with "—" for keys. After the children are created, the keys are
filled in and the description is edited once (research R3). The edited text is shown in full, and the
edit waits for approval like any other text.

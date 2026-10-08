# KAN-47: запуск Library-Django на Render Free

Render — хмарна платформа: вона отримує код із GitHub, будує Docker-образ,
запускає контейнер, видає HTTPS-адресу та показує логи. `render.yaml` — Blueprint:
опис сервісів та їхніх змінних середовища. Це не налаштування локального Docker Compose.
У середовищі `RENDER=true` Django довіряє HTTPS-заголовку проксі Render,
щоб login та інші форми проходили перевірку CSRF зі свого домену.

## Спрощений сетап

```text
Браузер → Render Web Service (Free, 512 MB)
            ├─ Gunicorn: 1 worker → Django → PostgreSQL (Free)
            └─ Celery: solo, 1 task → PostgreSQL
                    ↑
              Key Value (Free)
                    ↑
              Django events
```

PostgreSQL зберігає користувачів, книги, замовлення, embeddings і оброблені події.
Key Value — Redis-сумісна черга. Django надсилає туди події, а Celery записує їх у БД.
Окремий Render Background Worker не має Free плану, тому для демонстрації Celery
працює у тому самому контейнері, що й Gunicorn. Python-процес керує обома:
завершує весь контейнер при падінні будь-якого процесу та передає завершення обом.
Render може перезапустити контейнер; окремого платного worker не створюємо.

`DJANGO_SEED=true`: migrations і початкові дані створюються автоматично.
Модель E5 int8 (118 MB замість 470 MB fp32) входить до Docker-образу: після
пробудження не потрібне завантаження з Hugging Face. Encoder обробляє одну книгу
за раз, використовує один CPU thread, компактний SentencePiece і не утримує ONNX memory arena.
Seed атомарний: помилка відкочує початкові записи.
Розмір vectors лишається 384; int8 дає наближені значення, тому metadata revision
змінено, а seed перегенерує старі vectors. Процес seed завершується до запуску
Gunicorn/Celery і звільняє свою пам'ять. Локальний Compose зберігає окремий worker
і персистентний Redis для розробки та CI.

## Обмеження Free

Перевірено за документацією Render 08.10.2026:

- Web: 0.1 CPU, 512 MB; засинає після 15 хвилин без вхідного трафіку.
  Перший запит після сну може зайняти близько хвилини. Celery під час сну теж не працює.
- 750 годин Free Web на workspace за календарний місяць, спільних між сервісами.
- PostgreSQL: один Free екземпляр, 1 GB, строк дії 30 днів, без резервних копій.
  Потім потрібен платний план; через 14 днів після закінчення строку БД видаляють.
- Key Value: один Free екземпляр, 25 MB, дані черги втрачаються при перезапуску.
  `noeviction` захищає від витіснення завдань при заповненні, але не від втрати при restart.
- Файли контейнера та кеш E5 не зберігаються після нового deploy. Постійного диска на Free немає.
- Генерація embeddings працює на CPU; Free CPU повільніший за локальний.
  Int8-модель зменшує витрати пам'яті, але вектори не побітово ідентичні fp32.


Джерела: [Free](https://render.com/docs/free),
[Blueprint](https://render.com/docs/blueprint-spec),
[Background Workers](https://render.com/docs/migrate-from-heroku),
[pgvector](https://render.com/docs/postgresql-extensions).

## Нове розгортання у твоєму акаунті

1. Створи акаунт на https://dashboard.render.com і підключи свій GitHub.
2. Код KAN-47 має бути у GitHub-репозиторії, доступному твоєму Render, у гілці `main`.
   Якщо це fork — Blueprint використовує вибраний тобою репозиторій.
   Цей тікет сам не виконує commit/push/merge.
3. Натисни **New → Blueprint**, вибери репозиторій, гілку `main` і `render.yaml`.
4. Перед застосуванням перевір список: `library-django` (Free), `library-queue`
   (Free), `library-db` (Free). Усі у Frankfurt. Якщо бачиш платний план,
   зупини створення й перевір конфігурацію. Один Free Postgres і Key Value на workspace:
   за наявності таких сховищ скористайся інструкцією оновлення нижче.
5. Створи Blueprint. `SECRET_KEY` генерується автоматично; `DB_*` і
   `CELERY_BROKER_URL` беруться зі створених сховищ. Не став `localhost:6379`.
6. У Web Service відкрий **Logs**. Очікуй migrations, запуск Celery з чергою
   `events`, підключення до Redis і Gunicorn на порту з `PORT` (Render зазвичай 10000).
7. Відкрий URL саме свого Web Service. `/api/schema/`, `/api/docs/`, `/api/v1/`
   мають відкриватися. Seed створює демонстраційні акаунти: `reader@library.com` /
   `reader123password`, `librarian@library.com` / `admin123password`.
   Зміни їхні паролі перед публічним використанням.
8. Увійди, відкрий профіль/каталог, перевір Logs: не має бути
   `Error 111 connecting to localhost:6379`. Для перевірки запису подій подивись
   таблицю `events_userevent` через підключення до Postgres із твого комп'ютера.
   Не публікуй External Database URL або пароль у чаті/репозиторії.

## Оновлення вже наявного сервісу

Не створюй другу БД і не видаляй поточну. Якщо сервіс уже керується Blueprint,
онови його через **Blueprint → Sync** після появи змін у `main`; перевір,
що наявні сховища у тому самому регіоні. Якщо вони не у Frankfurt, зміни `region`
у YAML до їхнього регіону до Sync: перенесення БД цим тікетом не передбачено.

Якщо Web створено вручну:

1. **New → Key Value → Free**, регіон як у Web/БД, ім'я `library-queue`.
   Встанови eviction policy `noeviction`. Залиш зовнішній доступ закритим.
2. Скопіюй **Internal Key Value URL**. У Web → **Environment** встанови
   `CELERY_BROKER_URL` у цей URL, `DJANGO_SEED=true`, `DEBUG=False`.
   Збережи існуючі `SECRET_KEY` і `DB_*`.
3. Web → **Settings → Docker Command**:
   `python /app/scripts/render_start.py`.
4. Переконайся, що Branch містить зміни KAN-47, і зроби **Manual Deploy → Deploy latest commit**.
5. Пройди перевірки з попереднього розділу, включно з login та записом подій.

## Початкові дані та embeddings

Seed створює каталог і embeddings автоматично. При повторному запуску наявні
користувачі не створюються повторно, а актуальні vectors пропускаються. Після
переходу з fp32 на int8 старі vectors перегенеруються один раз. Сам cache моделі
вбудований у image; database зберігає vectors між deploy. Не монтуй порожній
volume поверх `/app/.cache/book-embeddings` у production: він приховає модель.

## Діагностика

- `localhost:6379`: URL брокера не задано або зміни не застосовані.
- Події у черзі не обробляються: перевір наявність Celery у Logs і Docker Command;
  якщо Web спить, відкрий сайт і дочекайся пробудження.
- Exit 137 / OOM під час створення книги: ліміт RAM; Gunicorn timeout цього не виправляє.
- `vector` extension: потрібен Render Postgres; міграція створює extension автоматично.
- БД недоступна після 30 днів: перевір строк Free Postgres у Dashboard.

Фактичний deploy і перевірка live URL у твоєму акаунті виконуються тобою за цією
інструкцією. Локальні Docker-перевірки не є підтвердженням успішного Render deploy.

## Перевірка KAN-47

Локально Docker build, Django-тести з реальним ONNX inference, HTTP endpoints,
Redis/worker restart і спільний Web/Celery запуск із seed перевіряються скриптами
CI. `scripts/smoke_render_free.py` запускає образ без bind mounts, з `PORT=10000`,
`DJANGO_SEED=true` та hard memory/swap limit 512 MiB і CPU limit 0.1, перевіряє реальний HTTP book
save, async events і SIGTERM. Ця перевірка обмежує RAM і CPU, але не відтворює холодний старт
інфраструктури Render або поведінку managed Key Value.

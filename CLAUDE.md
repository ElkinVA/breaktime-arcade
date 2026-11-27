# CLAUDE.md — Breaktime Arcade

## Нормативная база (источник истины)
BA-PLAT-4.2 (ред. 12.11.2026) + BA-GAME-2.2, BA-SDK-1.1, BA-ENV-1.1.
Навигация: docs/handoff/ (первый документ — NOW.md). Полное ТЗ: technical_specification/.
Provenance: ../ai-dev/docs/project-reference/README.md.
При конфликте: ТЗ > фактический код > handoff. Не выдумывать требования,
endpoints, поля, версии и результаты проверок.

## Актуальное состояние проекта
Состояние реализации постоянно меняется. Не хранить в этом файле
перечень реализованных и нереализованных функций, который быстро устаревает.
Перед началом каждой задачи обязательно сверяться с актуальными документами:
docs/handoff/NOW.md — последняя передача работы и текущее состояние.
docs/status/PROJECT_STATUS.md — реализованные компоненты, фактические результаты проверок, остаточные риски и ограничения.
docs/status/BACKLOG.md — приоритеты, READY, DEFERRED и BLOCKED задачи.
При расхождении исторических записей и текущего состояния проверять:
Текущий код и структуру проекта.
Последние тесты и результаты CI для соответствующего commit.
Актуальный NOW и PROJECT_STATUS.
Acceptance criteria конкретной задачи.
Не считать функцию готовой только потому, что она описана в документации или имеет статус IMPLEMENTED. Отличать техническую реализацию, независимую техническую приёмку и продуктовую приёмку владельца.
Исторические аудиты, старые записи handoff и датированные снимки не считать описанием текущего состояния, если их дата и commit не соответствуют текущей версии проекта.

## AI workflow (обязательно)
- Сначала `docs/handoff/NOW.md` + `PROJECT_STATUS.md` + `BACKLOG.md`;
  полные реестры — по необходимости.
- Pro (`architect`, `code-reviewer`, `security-auditor`) планирует и проверяет
  в text-only режиме; Flash реализует и запускает проверки.
- Никакого self-review; `IMPLEMENTED` ≠ `ACCEPTED`. Техническая приёмка
  агента — по OD-AUTONOMY-003; продуктовая/юридическая — только владелец.
- После пакета обновить NOW, шесть реестров и PROJECT_STATUS; указать модели.
- Защищённые файлы (`CLAUDE.md`, ТЗ, `.env`, `certs/`, `creds/`) — только с
  явного разрешения; секреты не выводить.

## Стек — менять запрещено без письменного согласования
Python 3.14, Django 5.2 LTS, DRF, PostgreSQL 18 (psycopg 3, НЕ psycopg2),
Redis cache(allkeys-lru)/broker(noeviction+AOF) раздельно, Celery 5.7 + Beat,
Nginx, Gunicorn, Docker Compose, Django Templates + HTMX 2 + Vanilla JS ES2022
+ Tailwind v4, Node 22 только для сборки. UV + uv.lock.
ЗАПРЕЩЕНО: React/Vue/SPA/Alpine; SQLite для тестов; плавающие версии в prod.

## Продуктовые инварианты
- Опубликованные игры доступны без регистрации.
- Гости играют, но их результаты НЕ идут в рекорды и НЕ переносятся в аккаунт.
- У каждой игры своя таблица рекордов в рамках эпохи; общего рейтинга нет.
- Оценка игры и рекорд независимы.
- Один обязательный основной жанр; теги/доп. жанры опциональны.
- Email необязателен; подтверждённый email — единственный самостоятельный
  способ восстановления пароля.
- Падение отдельной игры не ломает портал.
- Язык игры = язык сайта; при отсутствии локали — fallback + бейдж покрытия.
- Добавление/обновление игры — только ZIP; ручной повторный ввод полей запрещён.
- technical_id и host_label immutable после первой публикации, не переиспользуются.

## Архитектурные решения — нарушать нельзя
- Портал/CRM/API — основной домен; каждая игра — отдельный origin отдельного
  регистрируемого домена (не поддомен портала). Cookies портала игре недоступны.
- Игровой код не исполняется в Django; публикуется статический runtime bundle.
- SDK — единственный канал связи игры с платформой. Валидировать origin,
  source window, schema, session, nonce, expiry, state.
- Launch ticket — одноразовый секрет родительской страницы, НЕ передавать в iframe.
- Original ZIP неизменен побайтово; runtime — отдельная копия с заменённым SDK;
  package_hash != runtime_hash, оба отслеживаются. Публикуется только runtime.
- ZIP распаковывать в изолированном worker с лимитами CPU/RAM/time/disk/network;
  защита от Zip Slip, symlink, zip bomb, collisions, запрещённых расширений/URL.
- Preview/autotest исключаются из продуктовых агрегатов.
- Импорт идемпотентен; ручные overrides владельца не затираются (diff/conflict flow).
- Dev-lite / staging / production раздельны по compose project, сетям, томам, БД, секретам.

## Команды (через Makefile; quality/DB — в web, инфраструктура — на хосте)
make up | down | restart | ps | logs        — стек
make env | certs | assets | lock | build    — окружение и сборка
make makemigrations | migrate | psql | shell | superuser — БД
make test | lint | fmt | types | check      — качество (pytest/ruff/mypy)
make backup | restore-check                 — бэкапы
make staging-up | staging-down | staging-status | staging-logs
Dev: https://portal.test:8443 ; web также 127.0.0.1:8000 ; staging :8444.
`env/certs/assets/lock/build/up/down/restart/staging-*/verify_*` — на хосте;
`test/lint/fmt/types/check/migrate/shell/psql` — в `web`.
Проверки: ./verify_stack.sh, ./verify_staging_final.sh (read-only).

## Процесс работы над задачей
1. ИССЛЕДУЙ: точный пункт ТЗ, фактические файлы/импорты/модели/миграции/тесты.
   Сними baseline. Отделяй факты от гипотез.
2. ПЛАН: минимальный набор изменяемых файлов; оцени миграционные, security
   и backward-compat риски. Для опасного — получи согласование.
3. РЕАЛИЗУЙ: доменная логика в services/, views/serializers тонкие.
   Type hints, ruff (line-length 100, double quotes), mypy.
4. ПРОВЕРЬ: целевые тесты + lint + types; для БД — makemigrations --check
   --dry-run, showmigrations --plan, migrate --plan; реальное поведение
   HTTP/API, а не только healthy. Сопоставь с acceptance criteria.
5. ОТЧЁТ: статус Done/Partial/Blocked, изменённые файлы, команды и фактические
   результаты, остаточные риски, один следующий шаг.

## Запреты
- Не заполнять пустые файлы фиктивными классами/stub ради вида; не выдавать
  mock/TODO за готовую функцию.
- Не переписывать проект/стек без доказанной причины и согласия.
- Не сбрасывать/удалять миграции; --fake не использовать как обычный фикс.
- Не выполнять docker compose down -v, flush, удаление volumes/БД/бэкапов.
- Не ломать dev-lite, staging, backup/restore-check.
- Не пересобирать образ без установленной причины.
- Не запускать архивные fix_*.sh / fill_*.sh / rebuild_after_fix.sh из корня —
  они деструктивны и оставлены как история.
- Не использовать --dangerously-skip-permissions, git reset --hard,
  push --force, переписывание истории, удаление веток.
- Не отправлять код во внешние сервисы без разрешения.
- Не выводить .env, пароли, токены, private keys, Basic Auth credentials.

## БД и миграции
Только PostgreSQL. citext, pg_trgm, unaccent создаются до использования
(core.0001_extensions). Dependencies явные. Применённые миграции не редактировать.
Unique constraint != immutability: immutable поля защищать сервисом/моделью/БД.
Конкурентные операции — транзакции/constraints/locks + тесты.
Разрушительные операции с данными — только по явному запросу и после бэкапа.

## Безопасность
API deny-by-default; public endpoints открываются явно.
Глобальная DRF permission — IsAuthenticated (deny-by-default).
Публичные endpoints должны явно объявлять AllowAny там, где это предусмотрено ТЗ.
Не ослаблять разрешения ради обхода ошибок.
Не отключать CSRF, CSP, permissions, throttling, origin validation ради обхода ошибки.
Browser write-запросы защищены CSRF; throttle scopes реально настроены;
IP не единственный rate-limit key (корпоративные NAT).
Секреты — в .env, .env.staging, creds/, certs/ (вне Git). Логи без секретов.
Staging: Basic Auth + IP allowlist + noindex + mail sandbox, отдельные секреты.
Healthcheck nginx проверяет реальный listener (nc -z), не nginx -t (AD-001).

## Качество
Тесты: happy path, edge cases, отказ, гонки, идемпотентность. E2E для публичных
и CRM-сценариев (Playwright, marker e2e). Покрытие доменных модулей >=70% (§2.26).
Ошибки структурированные, локализуемые, безопасные. Зависимости — lock-файлами.

## Git
Локальный репозиторий, ветка main, origin — GitHub
git@github.com:ElkinVA/breaktime-arcade.git. Push только main, без force
и переписывания истории.

Коммиты небольшие, осмысленные. Перед коммитом проверять, что секреты не в индексе.

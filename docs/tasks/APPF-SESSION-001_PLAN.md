# APPF-SESSION-001 — серверный session/ticket срез App F

**Статус:** PLAN подтверждён Pro (text-only, 2026-11-20); реализация
выполнена; независимый review `code-reviewer`/`security-auditor` — **accept**;
**ACCEPTED владельцем 2026-11-20** (OD-STATUS-007).  
**Дата:** 2026-11-20.  
**Реализация:** Flash. **Review:** `code-reviewer`/`security-auditor` (v4-pro,
text-only).

Pro-план подтвердил границы среза и внёс уточнения: subject без FK до DB-001;
ленивая фиксация expiry; CSRF проверять безусловно (включая анонимных);
throttle по subject (cookie), IP — только fallback; `binding_nonce` — только
на активации, не при создании.

## Цель

Реализовать серверную часть App F, не зависящую от SDK/ENV/BA-GAME:
`GameSession`, одноразовый билет, активацию и heartbeat по BA-PLAT-4.2
§2.12.1–2.12.4 и API §2.23.

## Границы

Входит:
- модель `GameSession` + миграция;
- `POST /api/v1/sessions` → 201 `{session_id, ticket, expires_at}`;
- `POST /api/v1/sessions/{id}/activate` → 200 `{context}`;
- `POST /api/v1/sessions/{id}/heartbeat` → 204;
- same-origin cookie + CSRF, включая анонимных;
- throttle scopes `sessions`/`heartbeat`;
- тесты: guest/user, CSRF, ticket reuse, expiry, ownership, ≤3 active,
  heartbeat clamp/cap, draft game.

Не входит:
- SDK/iframe/host protocol; `POST /result`; leaderboard; storage;
  GamePlaytime; preview/autotest API; ZIP pipeline.

## Модель (проектное решение [PROP])

`GameSession`:
- `id` UUID7 PK (внешний `sessionId`);
- `game` FK `catalog.Game` (PROTECT), `game_version` FK `catalog.GameVersion`;
- `subject_type` ∈ {user, anon}; `subject_id` UUID — без FK, чтобы не
  блокироваться DB-001; решение зафиксировать как техническое;
- `mode` ∈ {user, guest, preview, autotest}; сервер назначает user/guest;
- `state` ∈ {created, active, finished, expired, aborted};
- `ticket_hash` (nullable, unique), `ticket_expires_at`;
- `binding_nonce_hash`, `seed`;
- `max_session_seconds` (≤7200), `credited_ms`;
- `activated_at`, `last_heartbeat_at`, `finished_at`;
- CHECK constraints для state/mode/subject_type/credited_ms/max;
- индексы `(game, subject_type, subject_id, state)`, `(state, created_at)`.

## API (проектное решение [PROP] для полей тела)

Создание: тело `{game_id: technical_id}` (уточнение Pro: `binding_nonce` при
создании не передаётся); subject из cookie/session, `subject_id` в теле
игнорируется. Ответ ровно `{session_id, ticket, expires_at}`.

Активация: тело `{ticket, binding_nonce}`; проверка hash/expiry/owner/state;
nonce хэшируется и связывается с сессией при активации; ответ `{context}`.

Heartbeat: пустое тело; 204.

Контекст: `sessionId`, `gameId`, `gameVersion`, `mode`, `nickname`,
`language`, `fallbackLanguage`, `strings`, `score`, `limits`,
`trustLevel=client_reported`, `seed`.

## CSRF и permissions

- DRF `SessionAuthentication` + custom subclass, который вызывает
  `enforce_csrf` и для анонимных; без CSRF — 403.
- `permission_classes=[AllowAny]` только на трёх явных public endpoint;
  глобальный deny-by-default не менять.
- `throttle_scope`: sessions/heartbeat.

## Concurrency и время

- `pg_advisory_xact_lock` по (subject, game) внутри `transaction.atomic`;
  ≤3 active, иначе 429 `E_RATE_LIMIT`.
- Билет TTL 60 с, активация ≤5 мин, idle 30 мин.
- `credited_delta = clamp(now - last, 0, 45s)`, первый — от activated_at;
  `credited_ms` capped max_session_seconds.
- Сервисы принимают `now` для тестируемости.

## Файлы

- `apps/gameplay/models/session.py`, `models/__init__.py`;
- `apps/gameplay/services/sessions.py`;
- `apps/gameplay/api/serializers.py`, `views.py`, `urls.py`;
- `apps/gameplay/migrations/0001_initial.py`,
  `0002_alter_gamesession_binding_nonce_hash.py` (generated);
- `config/urls.py` — `/api/v1/`;
- `apps/accounts/services/anonymous.py` — read-only helper
  `get_anonymous_identity(request)`;
- `tests/integration/test_game_sessions.py`.

## Тесты / acceptance criteria

- guest create: 201, ticket hash не равен raw, cookie `ba_anon`, state created;
- CSRF missing → 403; with token → 201;
- activate → 200 context; repeat → E_TICKET_INVALID;
- wrong subject → E_OWNERSHIP; expired ticket → E_TICKET_INVALID;
- 4-я active session → 429 E_RATE_LIMIT;
- heartbeat clamp 45s и cap; idle → E_SESSION_EXPIRED;
- draft game → 404 E_SESSION_INVALID;
- user create → mode user, subject user;
- `make lint`, `make types`, `make test`, `makemigrations --check`,
  `migrate --plan` — exit 0.

## Фактические проверки (2026-11-20, Flash)

```text
make lint                  -> All checks passed; 335 files formatted
make types                 -> Success: no issues found in 317 source files
makemigrations --check     -> No changes detected
migrate --plan             -> No planned migration operations
pytest tests/integration/test_game_sessions.py -> 24 passed
pytest (full)              -> 209 passed, 2 skipped
```

HTTP-поведение проверено через `django.test.Client(enforce_csrf_checks=True)`
(URLconf, middleware, CSRF, DRF throttling, ORM). Live-порт не проверялся:
в dev-БД нет опубликованной игры; создание фикстуры в dev-данных не
выполнялось.

## Review (text-only Pro, v4-pro)

Оба ревьюера: **conditional accept** с совпадающим MAJOR (обход throttle
ротацией cookie-токена) и требованием конкурентных тестов.

| Finding | Severity | Решение |
|---|---|---|
| Throttle по сырому cookie → новый бакет на каждый запрос | major | subject-ключ только по живой `AnonymousIdentity`, иначе IP; тесты subject/IP |
| Нет конкурентных тестов на лимит/активацию/heartbeat | major (процесс) | 3 transaction-теста: один победитель, лимит 3, heartbeat без двойного зачёта |
| Set-Cookie теряется на error-path создания | minor | ошибка заполняет тот же Response (`_fail`) |
| Два формата ошибок (DRF validation vs `{code,message}`) | minor | `E_INVALID_REQUEST` для невалидного тела |
| `finished` heartbeat → 400 вместо 410 | minor | 410 `E_SESSION_FINISHED` |
| Границы времени не закреплены тестами | minor | включительная семантика + boundary-тесты |
| Накопление CREATED-сессий | medium (security) | ленивая экспирация при создании; identity чистятся существующей beat-задачей |
| Throttle-ключи в Redis allkeys-lru | low | без изменения; вопрос владельцу (отдельный noeviction) |
| 404 vs 403 enumeration | low | оставлено; UUIDv7, residual risk |

Дополнительно найдено и исправлено **вне отчётов ревьюеров**:

1. Лимит §2.12.1 «≤3 активных на (субъект, игра)» проверялся только при
   создании. При 2 active можно было выпустить 2 билета и активировать оба —
   4 active. Теперь активация берёт advisory-lock и считает active;
   при `>=3` → 429. Есть последовательный и конкурентный тесты.
2. Свежая БД не мигрировала: `catalog.0001` создаёт citext-колонки без
   зависимости от `core.0001_extensions`. Добавлена только graph-зависимость
   (schema не меняется, applied-миграции не переписывались по операциям).
   Это вынужденное отклонение от буквы правила «не редактировать применённые
   миграции»; зафиксировано в отчёте.

Итоговые вердикты после исправлений: `security-auditor` — **accept**;
`code-reviewer` — **accept** (после восстановления None-guard
`max_session_seconds`). Детали и остаточные риски —
`docs/foundation/APPF-SESSION-001_REPORT.md`.

## Риски / stop conditions

- DB-001 (user deletion/XOR) — subject_id без FK, GameResult не входит;
  зафиксировать как временное техническое решение.
- API body fields не полностью нормативны; помечены [PROP]; не выдавать за ТЗ.
- CSRF для анонимных — обязательный тест.
- Максимум 2 итерации fix→test; blocker — эскалация.
- Не менять ТЗ/legal/production/данные.

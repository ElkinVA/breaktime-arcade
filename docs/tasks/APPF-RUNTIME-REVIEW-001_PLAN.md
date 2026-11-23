# APPF-RUNTIME-REVIEW-001 — независимое ревью App F Runtime

**Дата:** 2026-11-23  
**Статус:** **PLAN / NOT STARTED**  
**Основание:** BA-APPF-002 runtime A+B/C, ADR-APPF-001, BA-SDK-1.1,
BA-ENV-1.1, BA-GAME-2.2 (A); текущие остатки R-036 Phase 2, R-043, R-044,
R-045.  
**Исполнитель подготовки:** Flash / основная сессия. **Review:**
`architect` + `code-reviewer` + `security-auditor`
(`deepseek-v4-pro`, text-only). Ревьюер не является исполнителем.

## 1. Цель

Получить независимое, воспроизводимое заключение по App F Runtime: SDK,
host protocol, player/play view, session/origin/CSRF/eventLog/storage
контракты — и определить, можно ли переводить runtime A+B/C из
`IMPLEMENTED / TECHNICAL REVIEW` в технически принятый статус.

Ревью — **read-only**: код не переписывается, SDK/ENV/GAME контракты не
меняются, миграции и deploy не выполняются.

## 2. Входные данные

- `sdk/1.1.0/ba-sdk.js`, `static/src/js/host_protocol.js`,
  `static/src/js/player.js`, `templates/gameplay/play.html`;
- `apps/gameplay/api/views.py`, `services/sessions.py`, `services/results.py`,
  `services/verifier.py`, `services/storage.py`;
- `apps/leaderboards/*`;
- `docs/foundation/BA-APPF-002_RUNTIME_SDK_REPORT.md`,
  `docs/decisions/ADR-APPF-001.md`, `docs/contracts/BA-SDK-1.1_v1.1.0.md`,
  `docs/contracts/BA-ENV-1.1_v1.1.0.md`;
- фактический diff/commit range, SHA-256 файлов, evidence тестов;
- R-036 Phase 2, R-043, R-044, R-045 — как ограничения/остатки, не как
  разрешение менять поведение.

## 3. Область ревью

### A. SDK и host

- source window, exact parentOrigin pin, fragment validation, session UUID;
- envelope/protocol/type/requestId/sessionId, LRU и rate limit;
- ticket не попадает в iframe; origin не подменяется;
- `submitResult`/`newSession`/`leaderboard`/`storage`/`exit`/`fail`;
- CSP-safe, отсутствие cookies/localStorage/eval/top.document.

### B. Player и серверный runtime

- `HostBridge`: `event.source`, target origin, state, payload limits;
- `player.js`: submit/leaderboard/storage/close, Idempotency-Key, CSRF,
  retries, heartbeat, visibility pause;
- `game_play`: server-side create/activate, ticket lifecycle, no-store,
  guest path, throttle;
- eventLog JSON Schema, seed, bounds, verifier/quarantine, leaderboard
  visibility;
- snake_case ↔ camelCase boundary и `ba.t` fallback — подтвердить контракт
  или зафиксировать дефект.

### C. Остатки и решения

- **R-036 Phase 2:** не реализовывать; проверить, что review не меняет
  `acks_late`/`reject_on_worker_lost`/`visibility_timeout`; вынести вопросы
  владельцу (идемпотентность backup/restore/anonymize, задержка redelivery,
  отдельный worker).
- **R-043:** hard FS quota отсутствует; проверить, что runtime/review не
  заявляет её наличие; рекомендовать operational follow-up.
- **R-044:** static permissions (`0640`) после manual collectstatic;
  включить в deployment checklist, не менять runtime.
- **R-045:** Archer prototype отсутствует; product/legal limitation,
  не выдавать за проверенный порт.

## 4. Не входит

Production/staging deploy, домены/TLS/S3, миграции, изменение БД,
переписывание принятых P3–P5, изменение SDK/ENV/GAME, AI Headquarters,
retention/legal решения. Для находок-блокеров создаётся отдельная
fix-задача; в этом ревью — только вердикт и evidence.

## 5. Метод и evidence

- Flash готовит компактный бриф: файлы, diff, SHA-256, команды, фактические
  результаты тестов, известные residuals.
- Pro-ревьюеры работают text-only, без инструментов; вердикты раздельные
  (архитектура / код / безопасность).
- Проверки: targeted runtime/E2E, полный suite, ruff/mypy, JS syntax;
  live browser — только если доступен подготовленный dev-стенд и это
  разрешено; иначе явно `NOT TESTED`.
- Все утверждения — со ссылкой на файл/строку/commit или команду.

## 6. Критерии приёмки ревью

- Проверены все пункты §3 A–C; для каждого — PASS / FINDING / NOT TESTED.
- Находки классифицированы: blocker / major / minor / residual, с
  сценарием и владельцем.
- Подтверждены или опровергнуты: origin/source pinning, session binding,
  ticket isolation, CSRF, eventLog schema, storage revision, guest path.
- R-036 Phase 2 не изменён; R-043/R-044/R-045 явно классифицированы.
- Итоговый вердикт: **ACCEPT / CONDITIONAL ACCEPT / REJECT** с
  обоснованием; при CONDITIONAL — конкретные условия и повторное ревью.
- Обновлены `AUDIT_REGISTER`, `RISK_REGISTER`, `TASK_HISTORY`, `NOW`,
  `PROJECT_STATUS`; product/staging/production не объявляются принятыми.

## 7. Stop conditions

- Нет доступа к фактическому diff/evidence — ревью не начинать.
- Обнаружен блокер безопасности — остановить приёмку, создать отдельную
  fix-задачу, не «исправлять по ходу» без review.
- Требуется изменение контракта SDK/ENV/GAME, схемы БД, staging/prod или
  платного сервиса — остановиться и вынести владельцу.
- Любая destructive DB/FS-операция — запрещена.

## 8. Вопросы владельцу (R-036 Phase 2, не решать в ревью)

1. Разрешить перевод `backup_full`/`restore_check`/`anonymize_due_accounts`
   на at-least-once с идемпотентными guard-ами?
2. Приемлема ли задержка redelivery до ~3600 с; менять ли
   `visibility_timeout`?
3. Нужен ли отдельный worker/очередь для backup/restore (Phase 3)?

До ответов `acks_late`/`reject_on_worker_lost`/`visibility_timeout` не
меняются. R-043 — hard FS quota как operational follow-up; R-044 —
static permissions в deployment checklist; R-045 — исходный Archer
prototype/product rights.

## 9. Следующий шаг после ревью

При ACCEPT — зафиксировать техническую приёмку runtime и обновить статус
App F; при CONDITIONAL — выполнить согласованный fix-пакет и повторить
ревью изменённых частей. R-036 Phase 2 остаётся заблокированным до решения
владельца.

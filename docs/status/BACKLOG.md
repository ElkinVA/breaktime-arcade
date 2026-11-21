# BACKLOG — Breaktime Arcade

**Дата:** 2026-11-21 (R-036 Phase 1; BA-APPF-002 / DB-001 session cleanup).
Единый backlog. Статусы: `IN_PROGRESS`, `READY`, `BLOCKED`,
`DONE_NOT_ACCEPTED`, `ACCEPTED`. Приоритет: `Blocker`, `Critical`, `Major`,
`Minor`, `Improvement`.

Нормативная последовательность: BA-PLAT-4.2 §2.25. Наличие готового кода
не означает приёмку этапа; `ACCEPTED` ставит только владелец.

| ID | Пакет | Приоритет | Статус | Зависимости / границы |
|---|---|---|---|---|
| BA-I18N-002 | Устойчивость языкового кэша и ошибок i18n: R-006/R-007, безопасный `language_url`, узкие исключения, regression-тесты | Major | **COMPLETED** (не accepted) | Не меняет ТЗ/схемы; dev-only; R-003/R-004/R-005 остаются |
| BA-STAGE-1.2-E2E | Browser/E2E-проверки публичной оболочки и fallback | Major | **IMPLEMENTED / AWAITING INDEPENDENT REVIEW** | 11 E2E passed на dev-стеке; не приёмка |
| BA-STAGE-2.1 | Аккаунты: регистрация/вход/профиль в рамках §2.10 | Major | **PARTIAL** — core реализован, не принят | Blockers: legal texts/versions, game history/records, email bounce, anonymous request wiring |
| BA-STAGE-2.2 | 2FA персонала + browser E2E сценариев §2.10 | Major | **PARTIAL** — TOTP/recovery/enrollment/disable реализованы | Owner recovery/журнал закрыты в 2.4; остались роли/CRM step-up, E2E staff |
| BA-STAGE-2.3 | Browser E2E регистрации/входа/2FA + закрытие доступных account-пробелов | Major | **IMPLEMENTED / AWAITING INDEPENDENT REVIEW** | 13 E2E passed (11 shell + 2 account); account gaps вне E2E остаются |
| BA-STAGE-2.4 | 2FA completion: owner recovery, LoginEvent, regeneration | Major | **PARTIAL** — реализовано без CRM/ролей | Остались роли/CRM step-up и encryption; retention закрыт в 2.5 |
| BA-STAGE-2.5 | Retention cleanup: LoginEvent 12 мес., AnonymousIdentity 90 дней, токены, reservation | Major | **PARTIAL** — account cleanup реализован | SecurityEvent/GameStorage/mail/backup/consent сроки не покрыты |
| BA-QUALITY-001 | Coverage доменных модулей ≥70 %, CI-порог, анализ пробелов | Major | **IMPLEMENTED / AWAITING INDEPENDENT REVIEW** | `make coverage` 81.65 % при пороге 70 %; низкие модули остаются |
| BA-CATALOG-001 | Публичный каталог: список/фильтры/поиск на существующих моделях | Major | **PARTIAL** — list/detail/filters/HTMX реализованы | Нет tags/доп. жанров/FTS/ratings/popularity/play |
| BA-CATALOG-002 | Дополнительные жанры и теги: M2M-модели, фильтры, тесты | Major | **IMPLEMENTED / AWAITING INDEPENDENT REVIEW** | `catalog.0003`; 6 tests; FTS/ratings/play вне пакета |
| BA-CATALOG-003 | PostgreSQL FTS + `pg_trgm` поиск с конфигурацией языка | Major | **PARTIAL** — SearchVector/trigram реализованы в запросе | Нет persisted vector/GIN/unaccent/ranking |
| BA-CATALOG-004 | Persisted `search_vector`, GIN, `unaccent`, backfill | Major | **PARTIAL** — vector/backfill есть; unaccent/ranking/bulk нет | GIN-индекс существует с 0001 |
| BA-CATALOG-005 | `unaccent`, `SearchRank`, bulk/import refresh | Major | **IMPLEMENTED / AWAITING INDEPENDENT REVIEW** | unaccent/rank/bulk; benchmark не входит |
| BA-AUTONOMY-003 | AI infrastructure: Pro text-only plan, Bash-guard, ai-dev isolation, NOW/context, docs pointers | Critical | **IMPLEMENTED / AWAITING OWNER ACCEPTANCE** | Pro plan done; security review **accept**; owner acceptance pending; 185 tests |
| APPF-SESSION-001 | GameSession/LaunchTicket + `POST /api/v1/sessions`, `/activate`, `/heartbeat` (§2.12.1–2.12.4) | Blocker | **ACCEPTED** (владелец, 2026-11-20) | 24 tests (3 конкурентных); code/security review **accept**; evidence — `APPF-SESSION-001_REVIEW_EVIDENCE.md`; subject без FK до DB-001 |
| BA-QUALITY-002 | Search benchmark/EXPLAIN, GIN для unaccent-выражения, низкое покрытие модулей | Major | **TECHNICALLY ACCEPTED** (agent); product — owner | GIN search_vector подтверждён на 10k (2.4 мс); trigram/unaccent GIN не обоснован (unaccent STABLE); coverage 90.88 %, <70 % нет; 397/3; отчёт `docs/foundation/BA-QUALITY-002_REPORT.md` |
| APPF-OWNER-DECISIONS | Пакет решений владельца: BA-SDK/ENV, BA-GAME, DB-001/005/006/007, [PROP]-подтверждения APPF-SESSION-001, retention/throttle | Blocker | **PARTIALLY ANSWERED** — DB/сессия подтверждены; BA-SDK/ENV и BA-GAME вынесены отдельно | `docs/decisions/APPF-OWNER-DECISION-PACKAGE.md` |
| BA-SDK-1.1 | Финальная версия контракта SDK v1.1.0 после Pro-review DRAFT | Blocker | **SUBMITTED FOR OWNER APPROVAL** | `docs/contracts/BA-SDK-1.1_v1.1.0.md`; review `docs/foundation/BA-SDK-ENV-1.1_REVIEW.md`; открыт O3 (64 КиБ/unknown) на утверждении |
| BA-ENV-1.1 | Финальная версия окружения v1.1.0 после Pro-review DRAFT | Blocker | **SUBMITTED FOR OWNER APPROVAL** | `docs/contracts/BA-ENV-1.1_v1.1.0.md`; открыты O4 (challenge), HSTS preload, провайдеры |
| APPF-SESSION-002 | Throttle hardening: subject 30/ч + IP 600/ч, heartbeat 3/мин на сессию, structured 429, redis-throttle | Blocker | **IMPLEMENTED / AWAITING OWNER ACCEPTANCE** | Блокеры review сняты; 37 session tests; отчёт `docs/foundation/APPF-SESSION-002_REPORT.md` |
| APPF-RESULT-001 | `POST /sessions/{id}/result` + GameResult + LeaderboardEntry, DB-001/002/003 | Blocker | **IMPLEMENTED / AWAITING OWNER ACCEPTANCE** | 19 tests (100 parallel); review; отчёт `docs/foundation/APPF-RESULT-001_REPORT.md` |
| APPF-LEADERBOARD-001 | Публичный `GET games/{id}/leaderboard` + `me/best` (§2.11) | Major | **IMPLEMENTED / AWAITING OWNER ACCEPTANCE** | review accept; 7 tests; read-throttle; отчёт `docs/foundation/APPF-LEADERBOARD-001_REPORT.md` |
| APPF-STORAGE-001 | `GET/PUT games/{id}/storage`: 64 КиБ, revision/If-Match, TTL гостя | Major | **IMPLEMENTED / AWAITING OWNER ACCEPTANCE** | 12 tests; DB-008 trigger; review accept; отчёт `docs/foundation/APPF-STORAGE-001_REPORT.md` |
| APPF-PLAYTIME-001 | `UserGamePlaytime`, зачёт credited_ms для mode=user | Major | **IMPLEMENTED / AWAITING OWNER ACCEPTANCE** | review accept; 40 session tests; отчёт `docs/foundation/APPF-PLAYTIME-001_REPORT.md` |
| APPF-RATINGS-001 | Оценки 1–5, порог playtime, лимиты, агрегат (§2.9) | Major | **IMPLEMENTED / AWAITING OWNER ACCEPTANCE** | review accept; 10 tests (гонки); антифрод §2.9.6 — owner-gap; отчёт `docs/foundation/APPF-RATINGS-001_REPORT.md` |
| APPF-POPULARITY-001 | GamePlayCredit/GameDailyStats, close endpoint (§2.8) | Major | **IMPLEMENTED / AWAITING OWNER ACCEPTANCE** | review accept; 8 tests; R-032 guest inflation — owner-gap; отчёт `docs/foundation/APPF-POPULARITY-001_REPORT.md` |
| BA-ZIP-PREFLIGHT-001 | Metadata-only preflight ZIP (§2.14.2/§2.14.7): структура, пути, типы, лимиты, коллизии, расширения, SHA-256, diagnostics | Critical | **TECHNICALLY ACCEPTED** (agent, OD-TECH-001); продуктовая приёмка — владелец | 16 unit tests; full 297/2 skipped; code/security review accept; не зависит от SDK/ENV/GAME; отчёт `docs/foundation/BA-ZIP-PREFLIGHT-001_REPORT.md` |
| BA-ZIP-EXTRACT-001 | Безопасная потоковая распаковка ZIP: byte caps, CRC, канонические пути, prefix-конфликты, атомарная публикация | Critical | **TECHNICALLY ACCEPTED** (agent, OD-TECH-001); продуктовая приёмка — владелец | 11 unit tests; full 308/2 skipped; security review accept; worker CPU/RAM/disk/network — отдельный срез; отчёт `docs/foundation/BA-ZIP-EXTRACT-001_REPORT.md` |
| BA-ZIP-WORKER-001 | Изоляция extraction worker: CPU/RAM/time/disk/network limits, очередь, отмена, аудит | Critical | **TECHNICALLY ACCEPTED** (agent, OD-TECH-001); продуктовая приёмка — владелец | Отдельный Compose-сервис `zip-worker`, `zipnet` + prefork; 22 new tests; full 330/2 skipped; code/security review **accept**; остатки R-033/R-035/R-036/R-037; отчёт `docs/foundation/BA-ZIP-WORKER-001_REPORT.md` |
| BA-ZIP-HARDENING-001 (R-035) | ZIP durability/error taxonomy/method allowlist: fsync файлов/каталогов, stored/deflate, раздельные read/write коды | Major | **TECHNICALLY ACCEPTED** (agent); product — owner | 54 ZIP tests; full 369/3; code/security review accept; benchmark 2000 files 7.7s; отчёт `docs/foundation/BA-ZIP-HARDENING-001_REPORT.md` |
| R-036 | Глобальный `CELERY_TASK_ACKS_LATE`: анализ семантики/идемпотентности, варианты доставки | Major | **PHASE 1 TECHNICALLY ACCEPTED (agent) / PHASE 2 AWAITING OWNER DECISION** | `docs/foundation/R-036_ACKS_LATE_ANALYSIS.md`; Phase 1: observability/docstrings/5 contract tests, 402/3, code/security review accept; Phase 2 (idempotency guards + reject) требует владельца; отчёт `docs/foundation/R-036_PHASE1_REPORT.md` |
| BA-DEVCONTROL-001 | Telegram Dev Control: статус/задачи/отчёты, запуск/пауза/stop, уведомления, owner-only, hooks | Major | **TECHNICALLY ACCEPTED** (agent); live setup — token/opt-in | Мониторинг/отчёты/задачи/ask/hooks работают; автономный `/continue` выключен по умолчанию и **gated** до sandbox/явного risk acceptance (R-039); sandbox test runner реализован; 31 tests; full 360/3; Telegram API blocked — нужен proxy/VPN + токен + opt-in; отчёт `docs/foundation/BA-DEVCONTROL-001_REPORT.md` |
| APPF-RETENTION | Таблица сроков хранения и юридические вопросы | Major | **PREPARED / AWAITING OWNER** | `docs/decisions/RETENTION_PROPOSAL.md`; сроки не утверждены |
| BA-APPF-002 | Реализация App F по BA-APPF-001 | Blocker | **PARTIAL / IN_PROGRESS** — DB-001/004/005/006/007 и runtime A+B/C реализованы; контрактная приёмка/review остаются | DB-001/004/005/006/007 + SDK/host/player/play view; 456/4; runtime review incomplete; BA-SDK-1.1/ENV/GAME не утверждены |
| BA-DB-SCHEMA-002 | Исправления DB-001…DB-008 в SQL/моделях | Blocker | **BLOCKED** | Нужны решения владельца по APPF-DEC-035/039/040/041 |
| BA-PROD-001 | Production compose/Nginx/monitoring/WAL/PITR/S3 | Blocker | **BLOCKED** | Владелец: домены/TLS, хостинг, S3/CDN, backup |
| BA-DOC-README-001 | Актуализация README/CLAUDE/.claude и AI Dev-статуса | Minor | READY | Требует разрешения на защищённые файлы |

## Правила ведения

- Не дублировать уже выполненные аудиты и задачи; сначала проверить
  `TASK_HISTORY.md` и `AUDIT_REGISTER.md`.
- Blocker/Critical исправлять до зависимых пакетов; Major — в пакете или с
  письменным планом обхода.
- После пакета обновлять шесть реестров и `PROJECT_STATUS.md`.
- `verify_stack.sh` — для инфраструктуры/релизных проверок, не для каждой
  бизнес-логики.

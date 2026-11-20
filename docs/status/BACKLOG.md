# BACKLOG — Breaktime Arcade

**Дата:** 2026-11-19 (BA-CATALOG-005).  
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
| BA-QUALITY-002 | Search benchmark/EXPLAIN, GIN для unaccent-выражения, низкое покрытие модулей | Major | **READY** | Следующий пакет; dev-only |
| BA-APPF-002 | Реализация App F по BA-APPF-001 | Blocker | **BLOCKED** | Нужны утверждение BA-APPF-001, BA-SDK/ENV, BA-GAME, исправления DB-001…008 |
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

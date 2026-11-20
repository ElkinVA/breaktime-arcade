# APPF-OWNER-DECISION-PACKAGE — решения владельца для продолжения App F

**Дата:** 2026-11-20  
**Статус:** **AWAITING OWNER DECISIONS** (рекомендации [PROP], не требования)  
**Основание:** BA-PLAT-4.2 §2.12–§2.14/§2.22/§2.25; `BA-APPF-001_DESIGN_DECISIONS.md`
(APPF-DEC-007…045); APPF-SESSION-001 report.  
**Правило:** этот документ не меняет ТЗ и не является решением владельца.
Утверждённые решения вносятся только в раздел A `OWNER_DECISIONS.md`.

## 0. Зачем пакет

Серверный session/ticket срез **APPF-SESSION-001** закрыт и ожидает приёмки.
Дальнейшие части App F (result, leaderboard, storage, SDK/iframe, EventLog,
ZIP pipeline) упираются не в код, а в отсутствующие нормативные документы и
проектные решения. Ниже — минимальный набор вопросов, после ответов на
которые разработку можно продолжать без выдумывания требований.

## A. Нормативные документы и контракты (блокируют всё)

| ID | Вопрос владельцу | Варианты | Рекомендация агента | Что разблокирует |
|---|---|---|---|---|
| APPF-OD-001 | `BA-SDK-1.1` отсутствует; есть только `docs/contracts/BA-SDK-1.1_DRAFT.md` | (a) предоставить оригинал; (b) официально утвердить DRAFT как эквивалент; (c) ограничить scope без SDK | (a) или (b); DRAFT сам по себе не нормативен | host protocol, message schemas, result/storage API, приёмка App F |
| APPF-OD-002 | `BA-ENV-1.1` отсутствует; есть DRAFT | то же | (a) или (b) | окружение, версии, production-конфигурация |
| APPF-OD-003 | `BA-GAME-2.2` существует в двух вариантах (A в `ts_site.txt`, B в `ts_game.txt`) | выбрать A или B | выбор владельца; сравнение — `docs/audits/BA-GAME-2.2_COMPARISON.md`; агент не выбирает | manifest/UX/детали игры, критерии приёмки |
| APPF-OD-004 | `session_id` (§2.12.2/§2.23) vs `sessionId` (§2.12.4/App F) | оставить оба; унифицировать в API; унифицировать в документе | уже зафиксировано OD-FOUND-001 для API; ТЗ не переписывать | envelope/contract |
| APPF-OD-005 | JSON Schema и политика unknown fields | утвердить схемы `schemas/messages/*.json`; запретить/игнорировать unknown | утвердить после BA-SDK; unknown fields — отклонять в валидаторе | SDK/игра |
| APPF-OD-006 | `ba:error` до сессии и коды ошибок | утвердить формат/коды APPF-DEC-012 | принять предложенный DRAFT | ошибки SDK |
| APPF-OD-007 | Лимит «прочих» сообщений (предложено 64 КиБ) | 64 КиБ / иное | 64 КиБ как DRAFT-предложение | transport |
| APPF-OD-008 | `paused`/`failed` и normal/abnormal end | утвердить APPF-DEC-016/017 | принять предложение | state machine/UX |
| APPF-OD-009 | `autotest:finish`, `myBest`, `ba.fail` отсутствуют в Приложении F | добавить типы; оставить вне scope | добавить отдельными типами после BA-SDK | SDK surface |
| APPF-OD-010 | storage remove/If-Match/состояния (APPF-DEC-030) | утвердить | принять предложение | storage |
| APPF-OD-011 | EventLog transport/сжатие (APPF-DEC-033) | gzip canonical JSON; object | утвердить после BA-SDK | eventLog/verifier |

Примечание: пункты APPF-OD-004…011 детализированы в
`BA-APPF-001_DESIGN_DECISIONS.md` §3 и §5; здесь — только решение
«утвердить/отклонить/изменить».

## B. SQL/БД: DB-001…DB-008

Полные формулировки и альтернативы — `BA-APPF-001_DESIGN_DECISIONS.md`,
APPF-DEC-035…042. Сводка:

| ID | Решение | Нужен владелец? | Рекомендация | Блокирует |
|---|---|---|---|---|
| DB-001 | Субъект результата при удалении пользователя (`user_id=NULL` vs XOR) | **Да** | `subject_type ∈ {user, anon, deleted}`; для `deleted` оба FK NULL; сессии при удалении — закрывать/удалять (ephemeral), не оставлять half-null | result/session/удаление аккаунта |
| DB-002 | Результат ↔ сессия (game/version/subject) | Нет (TZ/tech) | composite FK `(session_id, game_id)` + проверка subject/epoch; epoch фиксировать из `Game.leaderboard_epoch` | result |
| DB-003 | Leaderboard ↔ result | Нет (TZ) | composite FK/trigger + пересчёт entry в той же транзакции | leaderboard |
| DB-004 | Повторное использование `technical_id`/`host_label` | Нет (TZ) | никогда не удалять Game физически; архив + DB-trigger против DELETE | импорт/архив |
| DB-005 | `GameTranslation.name` 60 vs 128 | **Да** | 60 для публичного названия; длинный manifest name — отдельно | App J/валидация |
| DB-006 | Immutable GameVersion vs `ON DELETE SET NULL` audit-полей | **Да** (политика) | разрешить trigger'у менять только `created_by`/`manual_review_by` → NULL; content/hash не трогать | удаление аккаунта |
| DB-007 | Subject для preview/autotest (§2.12.1 vs §2.16.3) | **Да** | `user`→user, `guest`→anon, `preview`→ровно один субъект (anon допустим), `autotest`→служебный user; агрегаты исключают preview/autotest | mode/subject, агрегаты |
| DB-008 | Фактический размер JSONB storage | Нет (TZ) | генерируемый `bytes` из UTF-8 JSON + service-лимиты (≤256 ключей, depth ≤8, key ≤128) | storage |

Рекомендуемый порядок: DB-001/002/003/006/007/008 — до Django-моделей
result/leaderboard/storage; DB-004/005 — до импортёра/App J.

## C. Подтверждение решений среза APPF-SESSION-001 ([PROP])

Эти решения уже реализованы; владельцу предлагается подтвердить их как
принятые или изменить (изменение потребует миграции/адаптации):

| ID | Решение | Рекомендация |
|---|---|---|
| APPF-OD-020 | Subject хранится как `(subject_type, subject_id)` без FK до DB-001 | подтвердить; после DB-001 — миграция на явные FK/модель субъекта |
| APPF-OD-021 | Тело создания — только `game_id`; `binding_nonce` — только при активации | подтвердить; контракт SDK ещё [PROP] |
| APPF-OD-022 | Поля context (`strings`, `heartbeatIntervalSeconds`, `trustLevel`) | подтвердить как временные [PROP] до BA-SDK |
| APPF-OD-023 | Временные границы включительные (ticket/window/idle «ровно на границе» валиден) | подтвердить |
| APPF-OD-024 | Throttle: 30/hour sessions, 3/min heartbeat; ключ по живой identity, IP — fallback | подтвердить; IP-потолок при NAT — настроить после нагрузки |
| APPF-OD-025 | Multi-identity амплификация ~30 identity × 30 create/час с IP (R-030) | принять остаточный риск или сузить IP-потолок |
| APPF-OD-026 | Graph-правка `catalog.0001` (зависимость от `core.0001_extensions`) | подтвердить как осознанное исключение из правила о применённых миграциях; schema не менялась |

## D. Retention/инфраструктура

| ID | Вопрос | Рекомендация |
|---|---|---|
| APPF-OD-030 | Retention `GameSession`/будущих `GameResult`/`LeaderboardEntry`/`GameStorage` по §2.22 | утвердить сроки; AnonymousIdentity уже чистятся beat-задачей |
| APPF-OD-031 | Throttle-ключи в Redis allkeys-lru могут вытесняться | отдельный Redis/noeviction или отдельная БД для throttle; решение владельца/инфраструктуры |
| APPF-OD-032 | 404 vs 403 при чужой сессии | оставить как есть (UUIDv7); унификация — hardening, не блокер |

## E. Что произойдёт после решений

1. Решения вносятся в раздел A `OWNER_DECISIONS.md` (только владельцем).
2. DB-001/005/006/007 фиксируются в `DB_SCHEMA.md`/`ba_schema.sql` как
   проектные решения; затем создаются Django-модели/миграции result/
   leaderboard/storage.
3. После утверждения BA-SDK/ENV/BA-GAME и схем сообщений реализуется
   SDK/iframe/result/storage слой; до этого агент не создаёт «временные»
   контракты, выдаваемые за нормативные.
4. Приёмка App F — только по критериям §2.26 и после 0 Blocker/0 Critical
   (см. APPF-DEC-045); прохождение тестов не заменяет приёмку.

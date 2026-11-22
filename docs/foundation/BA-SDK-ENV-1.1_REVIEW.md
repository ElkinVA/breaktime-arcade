# BA-SDK-1.1 / BA-ENV-1.1 — review DRAFT и финальные версии

**Дата:** 2026-11-20 (актуализация 2026-11-22)

**Статус:** **INTERNALLY ACCEPTED (Architect, [ADR-APPF-001](../decisions/ADR-APPF-001.md))**.
Финальные версии приняты как внутренние технические контракты по
`OD-AUTONOMY-006`; это не публикация и не внешнее/юридическое утверждение.
DRAFT сохранены как история.

**Основание:** OD-APPF-001 (владелец разрешил DRAFT как основу после полной
проверки V4 Pro); OD-AUTONOMY-006 (делегирование Architect).

## 1. Проверка

Независимый Pro-review: `architect` / `deepseek-v4-pro`, text-only:
40 440 subagent-токенов, 0 tool calls, 394 с (2026-11-20). Вход — полные
DRAFT, релевантные разделы BA-PLAT-4.2 (§2.2–§2.5, §2.11–§2.14, §2.20,
§2.22–§2.23, Приложения A/B/D/E/F/G), BA-GAME-2.2 §6/§9.

| Документ | Вердикт |
|---|---|
| BA-SDK-1.1 DRAFT | **conforms-with-fixes** — структура/конверт/валидация/guest/retry/инъекция SDK соответствуют ТЗ; не хватало лимитов §2.12, eventLog, идемпотентности, storage revision/If-Match, полного списка кодов, opaque-origin |
| BA-ENV-1.1 DRAFT | **conforms-with-fixes** — стек/Redis/pool/dev-lite/HSTS/раздельность соответствуют; backup/DR, prod-состав, hardening, retention, staging-раздельность были ошибочно вынесены в «открытые вопросы», хотя заданы §2.5/Прил. D; digest-политика допускала исключения |

Содержательных противоречий с ТЗ, требующих изменения ТЗ, не найдено.
Замечания: 14 contradictions, 33 gaps, 12 risks; полный перечень — в
транскрипте Pro-review; существенные:

- SDK: `top(10)` вместо `top(n)`; trustLevel показан как единственное
  значение; внутренняя несовместимость политики unknown-полей; отсутствие
  `#s=<session_uuid>`; неполные eventLog/idempotency/storage/ошибки;
- ENV: digest-исключение для staging, «плавающие теги без обоснования»,
  backup/DR как open question, отсутствие prod-состава и healthchecks,
  HSTS preload сверх ТЗ, неточные имена `CRITICAL_PATH_*`.

## 2. Что сделано

Созданы финальные версии на утверждение:

- `docs/contracts/BA-SDK-1.1_v1.1.0.md`;
- `docs/contracts/BA-ENV-1.1_v1.1.0.md`.

Применены правки Pro-review: лимиты §2.12 и Приложения E, eventLog
(структура/размеры/реплей), идемпотентность результата, guest-нормализация,
матрица отказов §2.13, storage revision/If-Match и TTL, полный список
19 кодов ошибок, opaque-origin и запрет `storage:"local"`, границы SDK/API
(§2.23), `#s` во фрагменте, `top(n)`; для ENV — prod sizing, backup/DR
(RPO 15 мин/RTO 4 ч/30 дней/restore-check), состав prod-сервисов,
healthchecks, hardening, retention Приложения D, staging-раздельность,
rate-limit/NAT (/64), игровой хост, CI и digest-политика без исключений.

## 3. Открытые вопросы и как закрыты

| ID | Вопрос | Решение |
|---|---|---|
| O1 | `sessionId` (postMessage) vs `session_id` (REST) | Использовать **OD-FOUND-001**: внешний JSON — `sessionId`, внутренний Python/БД — `session_id`, REST §2.23 — `session_id`; конверсия в адаптере. Новое решение не создавалось |
| O2 | Числа 15/1800/0–100000, `clientMeta`, `≤32` eventKinds | Все подтверждены BA-GAME-2.2 §4/§6/§9; внесены с цитатой; платформенный cap 7200 |
| O3 | Размер прочих сообщений + unknown-поля | Включено как `[PROP]` к утверждению: ≤64 КиБ, неизвестные поля отклоняются |
| O4 | Механизм challenge после IP-порога | Требует решения владельца (PoW vs CAPTCHA, провайдер в ЕС); в BA-ENV отмечено |
| O5 | HSTS preload/includeSubDomains | В v1.1.0 только 63072000; preload — отдельное решение позже |

## 4. Что останется после утверждения (не нормативно)

Реализация `ba-sdk.js` и `schemas/messages/*.json` — этап 3; создание
`compose.prod.yml`/prod-Nginx; получение digest базовых образов; настройка
WAL/PITR и backup; выбор провайдеров; restore-check; реализация challenge.

## 5. Следующий шаг

Владелец утверждает оба документа (или возвращает правки). После утверждения:
зафиксировать версии в `OWNER_DECISIONS.md` как решение владельца, обновить
BA-ENV фактическими значениями, продолжить App F (Result → Leaderboard →
Storage → SDK/iframe → EventLog). До утверждения разработка использует ТЗ и
DRAFT как основу, не выдавая их за утверждённые.

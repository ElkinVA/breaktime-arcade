# Session ID: внешний и внутренний контракт

**Статус:** внутренне закрыто `ADR-APPF-001` (D4) / BA-SDK-1.1 v1.1.0.
Нормативные ТЗ не изменялись. Дата: 2026-11-19 (актуализация 2026-11-22).

## 1. Утверждённое решение

| Контур | Имя | Правило |
|---|---|---|
| postMessage JSON (App F) | `sessionId` | camelCase, UUID-строка |
| REST API §2.23 | `session_id` | snake_case, UUID-строка |
| Python | `session_id` | snake_case |
| PostgreSQL | `session_id` | snake_case, UUID |

Преобразование выполняется на границе слоя: postMessage `sessionId` →
Python/БД `session_id` и обратно; REST использует `session_id` по §2.23.
Внутреннее имя `session_id` не должно протекать в postMessage payload.
Это применение уже зарегистрированного `OD-FOUND-001`, а не новое решение.

## 2. Аудит нормативных упоминаний

| Источник | Строка/раздел | Текст/поле | Классификация |
|---|---|---|---|
| BA-PLAT-4.2 | §2.12.2 | API response `{session_id, ticket, expires_at}` | Внешний JSON; конфликт с решением |
| BA-PLAT-4.2 | §2.12.2 | `postMessage {type:"ba:hello", protocol:1, session_id}` | Внешний postMessage; конфликт |
| BA-PLAT-4.2 | §2.12.4 | `data.sessionId` | Внешний postMessage; совпадает |
| BA-PLAT-4.2 | §2.12.4 | SDK проверяет `sessionId` | Внешний postMessage; совпадает |
| BA-PLAT-4.2 | §2.12.4/§2.12.5 | `ba:newSession`, новый `sessionId` | Внешний protocol; совпадает |
| BA-PLAT-4.2 | §2.22 | `UNIQUE(session_id)`, `session_id` в таблицах | Внутренняя БД; совпадает |
| BA-PLAT-4.2 | §2.23 | API `POST /sessions` → `{session_id,...}` | Внешний JSON; конфликт |
| BA-PLAT-4.2 | Приложение F | envelope `sessionId` | Внешний protocol; совпадает |
| BA-GAME-2.2 | §6 | `ba.context.sessionId`, `newSession` | Внешний SDK API; совпадает |
| `sdk/1.1.0/README.md` | весь документ | ранее фиксировал конфликт | Обновляется этим решением |
| `schemas/messages/*.json` | все message schemas | должны использовать `sessionId` | Новый контракт |
| `apps/core/logging.py` | 32 | внутренний лог-ключ `session_id` | Python/лог; совпадает |
| `docs/architecture.md` | 106 | упоминание конфликта | Документация; будет обновлена |
| `docs/foundation/ba_schema.sql` | все таблицы сессий | `session_id` | БД; совпадает |

## 3. Конфликт в нормативных ТЗ

BA-PLAT-4.2 §2.12.2 и §2.23 используют внешнее `session_id`, а §2.12.4,
Приложение F и BA-GAME-2.2 §6 — `sessionId`. Это противоречие **не
исправляется в ТЗ**. Оно фиксируется в реестре расхождений
[`docs/contracts/CONTRADICTIONS.md`](CONTRADICTIONS.md).

## 4. Единый внешний конверт

```json
{
  "source": "ba-sdk",
  "protocol": 1,
  "type": "ba:hello",
  "requestId": "018f6c2e-6f5a-7c31-9a44-4f1b6e9a0c11",
  "sessionId": "018f6c2e-6f5a-7c31-9a44-4f1b6e9a0c12",
  "payload": {}
}
```

- `requestId` — UUID, корреляция запроса/ответа, LRU 512.
- `sessionId` — UUID, текущая игровая сессия.
- `source` — `ba-sdk` для игры, `ba-host` для платформы.
- `protocol` — 1.
- `type` — тип из Приложения F.

## 5. API-ответы

`POST /api/v1/sessions` в проекте контракта возвращает:

```json
{"sessionId": "...", "ticket": "...", "expiresAt": "..."}
```

Это **проектное согласование** с владельческим решением; нормативный пример
BA-PLAT §2.23 с `session_id` остаётся расхождением до обновления ТЗ.
Внутренние Django views/serializers используют `session_id`; преобразование
в `sessionId` выполняется в serializer/response boundary.

## 6. Проверки

- Все `schemas/messages/*.json` используют `sessionId`.
- Внутренние SQL DDL и Python-модели используют `session_id`.
- Тесты `tests/unit/test_foundation_002_contracts.py` проверяют:
  - отсутствие `session_id` в message schema envelope;
  - наличие `sessionId` в envelope;
  - соответствие проектного конверта;
  - наличие `session_id` в SQL DDL.

## 7. Открытые вопросы

- Обновлять ли нормативные примеры BA-PLAT §2.12.2/§2.23 на `sessionId` —
  только по решению владельца.
- Нужно ли поддерживать `session_id` как legacy alias на входе API — не
  решено; по умолчанию проект принимает только `sessionId`.
- Точные имена `expiresAt`/`expires_at` в API требуют отдельного решения;
  в этом документе не фиксируются.

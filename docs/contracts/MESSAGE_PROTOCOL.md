# Протокол сообщений BA-SDK 1.1 (DRAFT)

**Статус:** проект контракта BA-FOUNDATION-002. Не является утверждённым
BA-SDK-1.1. Нормативные ТЗ не изменялись.

Источники: BA-PLAT-4.2 §2.12.4–§2.12.7, Приложение F; BA-GAME-2.2 §6.
Дата: 2026-11-19.

## 1. Конверт

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

Общая схема: [`schemas/messages/_envelope.json`](../../schemas/messages/_envelope.json).

| Поле | Тип | Правило |
|---|---|---|
| `source` | enum | `ba-sdk` — игра; `ba-host` — платформа |
| `protocol` | const | `1` |
| `type` | string | тип из таблицы ниже |
| `requestId` | UUID | корреляция, LRU 512 |
| `sessionId` | UUID | внешнее имя; Python/БД — `session_id` |
| `payload` | object | зависит от типа |

## 2. Типы сообщений

| Направление | `type` | Схема | Назначение |
|---|---|---|---|
| игра → платформа | `ba:hello` | `ba_hello.json` | готовность игры / старт |
| игра → платформа | `ba:submit` | `ba_submit.json` | результат и eventLog |
| игра → платформа | `ba:leaderboard` | `ba_leaderboard.json` | запрос TOP-N |
| игра → платформа | `ba:storage` | `ba_storage.json` | get/set/remove |
| игра → платформа | `ba:newSession` | `ba_new_session.json` | новая сессия |
| игра → платформа | `ba:exit` | `ba_exit.json` | выход |
| обе стороны | `ba:error` | `ba_error.json` | ошибка протокола |
| платформа → игра | `ba:context` | `ba_context.json` | публичный контекст |
| платформа → игра | `ba:result` | `ba_result.json` | ответ на результат |
| платформа → игра | `ba:leaderboard:data` | `ba_leaderboard_data.json` | данные TOP-N |
| платформа → игра | `ba:storage:data` | `ba_storage_data.json` | данные хранилища |
| платформа → игра | `ba:session` | `ba_session.json` | новый контекст |
| платформа → игра | `ba:pause` | `ba_pause.json` | пауза |
| платформа → игра | `ba:resume` | `ba_resume.json` | возобновление |

## 3. Направления и источник

- Для сообщений игры `source` зафиксирован как `ba-sdk`.
- Для сообщений платформы — `ba-host`.
- `ba:error` допускает оба источника.
- Родитель/SDK проверяют `source` и направление; неверное направление
  отклоняется.

## 4. requestId, sessionId, origin

- `requestId` — UUID; повторная обработка запрещена (LRU 512).
- `sessionId` — UUID текущей сессии; внешний JSON только camelCase.
- Родитель проверяет `event.source === iframe.contentWindow`, точный
  `event.origin`, `source`, `protocol`, `type`, `sessionId`, `requestId`,
  JSON Schema, rate limit и состояние сессии.
- SDK проверяет `event.source === window.parent`, `parentOrigin` из фрагмента,
  `source === "ba-host"`, протокол, `sessionId`, корреляцию `requestId`,
  схему.

## 5. Внутреннее представление

В Python/Django и PostgreSQL используется `session_id`. Преобразование
`sessionId ↔ session_id` выполняется на границе сериализатора/адаптера.
См. [`SESSION_ID_PROTOCOL.md`](SESSION_ID_PROTOCOL.md).

## 6. Ограничения

| Параметр | Значение | Источник |
|---|---|---|
| eventLog events | ≤20 000 | BA-PLAT §2.12.7 |
| eventLog raw | ≤2 МиБ | BA-PLAT §2.12.7 |
| eventLog gzip | ≤256 КиБ | BA-PLAT §2.12.7 |
| `t` | целые мс, не убывают, ≤durationMs+1000 | BA-PLAT §2.12.7 |
| `k` | из manifest.verification.eventKinds, ≤32 | BA-PLAT §2.12.7 |
| сообщений | ≤60/мин на сессию | BA-PLAT §2.12.4 |
| прочие сообщения | лимит не задан | `[OPEN]` |
| retries | до 3, только сетевые/временные | BA-GAME §6 |

## 7. Ошибки

Коды: `E_AUTH_REQUIRED`, `E_GUEST_FORBIDDEN`, `E_SESSION_INVALID`,
`E_SESSION_EXPIRED`, `E_SESSION_FINISHED`, `E_TICKET_INVALID`,
`E_VERSION_MISMATCH`, `E_SCORE_RANGE`, `E_DURATION_INVALID`,
`E_RATE_LIMIT`, `E_DUPLICATE`, `E_VERIFY_FAILED`, `E_STORAGE_QUOTA`,
`E_STORAGE_CONFLICT`, `E_PAYLOAD_TOO_LARGE`, `E_MESSAGE_INVALID`,
`E_OWNERSHIP`, `E_PLAYTIME_REQUIRED`, `E_INTERNAL`.

## 8. Открытые вопросы

1. Полные payload-поля `ba:hello`, `ba:storage`, `ba:session`,
   `ba:storage:data` не заданы в BA-PLAT/BA-GAME.
2. Нет утверждённого лимита размера прочих сообщений.
3. Формат `ba:error` (`code/message`) — proposal.
4. Нужно ли принимать legacy `session_id` на API — не решено.
5. Точные правила сериализации UUID/дат и optional/null полей — открыты.

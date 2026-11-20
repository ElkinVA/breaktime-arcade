# BA-SDK-1.1 — DRAFT

# DRAFT — НЕ УТВЕРЖДЕНО ВЛАДЕЛЬЦЕМ

**Статус:** проект контракта для BA-FOUNDATION-002, не нормативный документ.
Оригинал `BA-SDK-1.1` отсутствует. Документ не должен подключаться как
окончательный контракт без решения владельца.

Дата: 2026-11-19.

## 1. Назначение и границы

SDK — единственный канал связи игры с платформой. Игра выполняется в
iframe на отдельном origin; cookies, логин, email и идентификаторы
пользователя игре недоступны. Платформа заменяет `js/ba-sdk.js` официальной
реализацией при публикации (BA-PLAT-4.2 §2.14.3; BA-GAME-2.2 §6).

**Источники и маркировка положений:**

- `[TZ]` — прямое требование BA-PLAT-4.2 или BA-GAME-2.2.
- `[INF]` — вывод из существующего контракта/архитектуры.
- `[PROP]` — техническое предложение исполнителя.
- `[OPEN]` — нерешённый вопрос, требует решения владельца.

## 2. Публичный интерфейс

| API | Назначение | Источник |
|---|---|---|
| `BreaktimeArcade.init({timeoutMs})` | инициализация, таймаут 5 с | `[TZ]` BA-GAME §6 |
| `ba.context` | контекст сессии | `[TZ]` BA-GAME §6 |
| `ba.ready()` | сигнал готовности | `[TZ]` |
| `ba.t(key, params)` | ICU/CLDR-перевод | `[TZ]` |
| `ba.on(event, cb)` | pause/resume/visibility/session/autotest:finish | `[TZ]` |
| `ba.submitResult(data)` | отправка результата | `[TZ]` |
| `ba.leaderboard.top(10)` | TOP-N | `[TZ]` |
| `ba.leaderboard.myBest()` | личный рекорд | `[TZ]` |
| `ba.storage.get/set/remove` | хранилище ≤64 КиБ | `[TZ]` |
| `ba.newSession()` | новый контекст и seed | `[TZ]` |
| `ba.exit()` | завершение | `[TZ]` |
| `ba.fail(code, message)` | аварийное завершение | `[TZ]` |

Полный JavaScript SDK не реализуется на этапе 0; реализация относится к
этапу 3. Заглушка игры не считается SDK платформы.

## 3. Контекст

```json
{
  "sessionId": "uuid",
  "gameId": "technical_id",
  "gameVersion": "semver",
  "mode": "guest",
  "nickname": null,
  "language": "en",
  "fallbackLanguage": "en",
  "strings": {},
  "score": {"type": "integer", "unit": "points",
            "direction": "higher_is_better", "minValue": 0, "maxValue": 100000},
  "limits": {"minPlaytimeSeconds": 15, "maxSessionSeconds": 1800,
             "pauseOnBlur": true},
  "trustLevel": "client_reported",
  "seed": "string"
}
```

| Поле | Тип/правило | Источник |
|---|---|---|
| `sessionId` | внешний UUID; внутри Python/БД — `session_id` | `[TZ]` + решение владельца |
| `gameId` | `technical_id` | `[TZ]` |
| `gameVersion` | semver | `[TZ]` |
| `mode` | `guest,user,autotest,preview`; назначает сервер | `[TZ]` BA-PLAT §2.12.1 |
| `nickname` | string/null | `[TZ]` |
| `language` | строка; не ограничена шестью | `[TZ]` |
| `fallbackLanguage` | строка | `[TZ]` |
| `strings` | объединённый словарь | `[TZ]` |
| `score` | параметры счёта | `[TZ]` |
| `limits` | лимиты сессии | `[TZ]` |
| `trustLevel` | уровень | `[TZ]` |
| `seed` | строка, источник детерминизма | `[TZ]` |

## 4. Протокол postMessage

### 4.1. Конверт

`{source, protocol, type, requestId, sessionId, payload}`.

- `source`: `ba-sdk` (игра) или `ba-host` (платформа).
- `protocol`: 1.
- `type`: allowlist Приложения F.
- `requestId`: UUID, LRU 512.
- `sessionId`: UUID; **внешний JSON — camelCase**.
- `payload`: объект.

### 4.2. Направления и типы

| Направление | Типы | Источник |
|---|---|---|
| Игра → платформа | `ba:hello`, `ba:submit`, `ba:leaderboard`, `ba:storage`, `ba:newSession`, `ba:exit`, `ba:error` | `[TZ]` App F |
| Платформа → игра | `ba:context`, `ba:result`, `ba:leaderboard:data`, `ba:storage:data`, `ba:session`, `ba:pause`, `ba:resume`, `ba:error` | `[TZ]` App F |

Схемы: `schemas/messages/*.json`. Общий конверт:
`schemas/messages/_envelope.json`.

### 4.3. Валидация

Родитель проверяет в порядке:

1. `event.source === iframe.contentWindow`;
2. точный `event.origin` (схема + хост + порт);
3. `source === "ba-sdk"`, `protocol === 1`;
4. `type` из allowlist;
5. `sessionId` текущей сессии;
6. `requestId` — UUID, ранее не обработан (LRU 512);
7. JSON Schema типа;
8. ≤60 сообщений/мин на сессию;
9. состояние сессии допускает тип.

SDK проверяет `event.source === window.parent`, `parentOrigin` из фрагмента,
`source === "ba-host"`, протокол, `sessionId`, корреляцию `requestId`, схему.
Неизвестные/просроченные сообщения игнорируются молча.

Источник: `[TZ]` BA-PLAT §2.12.4.

### 4.4. Ограничения сообщений

| Параметр | Значение | Источник |
|---|---|---|
| eventLog | ≤20 000 событий; ≤2 МиБ raw; ≤256 КиБ gzip | `[TZ]` §2.12.7 |
| `t` | целые мс, не убывают, ≤ durationMs+1000 | `[TZ]` |
| `k` | из verification.eventKinds (≤32) | `[TZ]` |
| Размер прочих сообщений | не задан | `[OPEN]` |
| Частота | ≤60/мин на сессию | `[TZ]` |

`[PROP]` Для прочих сообщений предлагается верхняя граница 64 КиБ и
запрет неизвестных полей payload; это не утверждено.

## 5. Жизненный цикл сессии

| Этап | Поведение | Источник |
|---|---|---|
| init | таймаут 5 с; при отсутствии SDK — экран ошибки | `[TZ]` BA-GAME §6 |
| hello | SDK отправляет `ba:hello`; родитель создаёт/активирует сессию | `[TZ]` BA-PLAT §2.12.2 |
| active | heartbeat каждые 30 с; финальный heartbeat перед submit | `[TZ]` §2.12.3 |
| submit | `ba:submit`; ответ `ba:result`; таймаут 10 с | `[TZ]` §2.12.5 |
| newSession | новый `sessionId` и seed; старый недействителен | `[TZ]` |
| exit/fail | завершение/аварийное завершение | `[TZ]` BA-GAME §6 |
| finished | разрешены только leaderboard/storage/newSession/exit | `[TZ]` §2.12.4 |

`sessionId` в Python/БД — `session_id`. Преобразование выполняется в
адаптере сообщения/API.

## 6. Результат и гость

`submitResult({value, durationMs, eventLog, seed, clientMeta})`.

Сервер проверяет сессию, субъект, игру/версию, состояние, срок,
однократность, диапазон, длительность, rate limit, стоп-листы, верификатор
(`[TZ]` §2.12.5).

Гость: API `403 E_GUEST_FORBIDDEN`; SDK нормализует в
`{status:"guest", code:"E_GUEST_FORBIDDEN", rank:null,
isPersonalBest:false, isRecord:false, trustLevel:"client_reported"}`.
Ретраи запрещены; результат не сохраняется (`[TZ]` §2.12.5). Игра показывает
уведомление «Результат не сохраняется».

## 7. Рекорды и хранилище

- `leaderboard.top(10)` → `{entries:[{rank,nickname,value}], myRank}`.
- `leaderboard.myBest()` → `{value, achievedAt}` или `null`.
- `storage.get/set/remove`: ключи версионируются; суммарно ≤64 КиБ;
  debounce настроек ≥1 с; данные сохраняются между версиями (`[TZ]` BA-GAME §6;
  BA-PLAT §2.22).

`[OPEN]` Точные payload-поля `ba:leaderboard`, `ba:storage` и `ba:result` не
полностью заданы в доступных ТЗ; в схемах используются минимальные известные
поля и `additionalProperties: true` там, где это необходимо.

## 8. Ошибки, таймауты, повторы

| Ситуация | Поведение | Источник |
|---|---|---|
| init | 5 с, экран ошибки с «Повторить» | `[TZ]` |
| submit | 10 с | `[TZ]` |
| storage/leaderboard read | 5 с | `[TZ]` |
| сетевой/временный отказ | до 3 повторов с экспоненциальной задержкой | `[TZ]` |
| guest, E_VERIFY_FAILED, E_SCORE_RANGE, E_SESSION_EXPIRED | не повторять | `[TZ]` |
| повторный submit | тот же Idempotency-Key в рамках сессии | `[TZ]` |
| коды ошибок | E_AUTH_REQUIRED … E_INTERNAL | `[TZ]` §2.23 |

`[OPEN]` Точный JSON-формат `ba:error` и локализованные тексты не заданы;
схема использует `{code,message}` как proposal.

## 9. Совместимость версий

- `manifest.sdkVersion` — semver-range; `manifest.protocol` = 1.
- Платформа заменяет SDK совместимой официальной реализацией; при
  несовместимости — `V_SDK_INCOMPATIBLE` (`[TZ]` BA-PLAT §2.14.3).
- `BA_SDK_DEFAULT_VERSION=1.1.0` — настройка проекта (`[TZ]` App A).
- `[OPEN]` Точная матрица версий SDK/протокола и поведение минорных версий
  требуют утверждения BA-SDK-1.1.

## 10. Открытые вопросы

1. Канонический внешний `sessionId` утверждён владельцем; нормативные
   примеры с `session_id` остаются расхождением.
2. Полные payload-схемы всех сообщений отсутствуют в BA-PLAT/BA-GAME.
3. Лимит размера прочих сообщений не задан.
4. Точный формат `ba:error`, `ba:session`, `ba:storage:data` не задан.
5. Нужна ли обратная совместимость с `session_id` на API — не решено.
6. Реализация `ba-sdk.js` — этап 3, не этап 0.

## 11. Связанные документы

- `docs/contracts/SESSION_ID_PROTOCOL.md`;
- `docs/contracts/MESSAGE_PROTOCOL.md`;
- `schemas/messages/_envelope.json` и типовые схемы;
- `docs/contracts/CONTRADICTIONS.md`.

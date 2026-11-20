# BA SDK 1.1 — контрактный baseline

**Статус: частичный контракт, не замена BA-SDK-1.1.**

Документ собран только из явных требований BA-GAME-2.2 §6 и BA-PLAT-4.2
§2.12/Приложения F. Нормативный `BA-SDK-1.1` в проекте отсутствует; его
содержание здесь не восстанавливается и не выдумывается. Реализация
`sdk/1.1.0/ba-sdk.js` относится к этапу 3 и в этом файле не создаётся.

## Назначение

SDK — единственный канал связи игры с платформой. Игра исполняется в iframe
на отдельном origin; cookies и иные данные портала ей недоступны. Платформа
заменяет `js/ba-sdk.js` официальной реализацией при публикации
(BA-PLAT-4.2 §2.14.3, BA-GAME-2.2 §6).

## Публичный интерфейс игры

```js
const ba = await BreaktimeArcade.init({ timeoutMs: 5000 });

ba.context = {
  sessionId, gameId, gameVersion,
  mode,            // "guest" | "user" | "autotest" | "preview"
  nickname,        // строка или null
  language,        // строка кода языка; список не ограничен шестью
  fallbackLanguage,
  strings,
  score,           // { type, unit, direction, minValue, maxValue }
  limits,          // { minPlaytimeSeconds, maxSessionSeconds, pauseOnBlur }
  trustLevel,
  seed
};

ba.ready();
ba.t(key, params);
ba.on("pause" | "resume" | "visibility" | "session" | "autotest:finish", cb);
await ba.submitResult({ value, durationMs, eventLog, seed, clientMeta });
await ba.leaderboard.top(10);
await ba.leaderboard.myBest();
await ba.storage.get(key);
await ba.storage.set(key, value);
await ba.storage.remove(key);
const ctx = await ba.newSession();
ba.exit();
ba.fail(code, message);
```

Источник: BA-GAME-2.2 §6.

## Сообщения

Конверт по BA-PLAT-4.2, Приложение F:

```text
{source: "ba-sdk" | "ba-host", protocol: 1, type, requestId, sessionId, payload}
```

Игра → платформа:

- `ba:hello`
- `ba:submit`
- `ba:leaderboard`
- `ba:storage`
- `ba:newSession`
- `ba:exit`
- `ba:error`

Платформа → игра:

- `ba:context`
- `ba:result`
- `ba:leaderboard:data`
- `ba:storage:data`
- `ba:session`
- `ba:pause`
- `ba:resume`
- `ba:error`

Источник: BA-PLAT-4.2 §2.12.4, Приложение F; BA-GAME-2.2 §6.

## Обязательная валидация

Родитель проверяет:

1. `event.source === iframe.contentWindow`;
2. точный `event.origin` игры;
3. `source === "ba-sdk"`, `protocol === 1`;
4. `type` из allowlist;
5. `sessionId` текущей сессии;
6. `requestId` — UUID, не обработанный ранее (LRU 512);
7. JSON-схему типа;
8. не более 60 сообщений/мин на сессию;
9. состояние сессии допускает тип сообщения.

SDK проверяет `event.source === window.parent`, `parentOrigin` из фрагмента,
`source === "ba-host"`, протокол, `sessionId`, корреляцию `requestId` и схему.
Неизвестные/просроченные сообщения игнорируются молча.

Источник: BA-PLAT-4.2 §2.12.4.

## Таймауты, гости и повторы

- init — 5 с, submit — 10 с, чтение — 5 с.
- Гость: `submitResult` нормализует ответ в
  `{status:"guest", code:"E_GUEST_FORBIDDEN", rank:null, isRecord:false}`;
  это не ошибка, ретраи запрещены.
- Ретраи — до 3 с экспоненциальной задержкой только для сетевых/временных
  отказов. Не ретраить `guest`, `E_VERIFY_FAILED`, `E_SCORE_RANGE`,
  `E_SESSION_EXPIRED`.
- `newSession()` возвращает новый контекст с новым `seed`; старый seed
  недействителен.
- Хранилище: ключи версионируются, суммарно ≤64 КиБ; запись с debounce ≥1 с.
- `ba.exit()` и `ba.fail(code, message)` завершают работу игры.

Источники: BA-GAME-2.2 §6; BA-PLAT-4.2 §2.12.5, §2.22.

## Решение по sessionId

Владелец утвердил: внешнее JSON-поле — `sessionId`, внутреннее имя Python/БД —
`session_id`, преобразование на границе слоя. Нормативные примеры с
`session_id` остаются расхождением в BA-PLAT-4.2 §2.12.2/§2.23; они не
переписываются. Детали: `docs/contracts/SESSION_ID_PROTOCOL.md`.

## Неразрешённые вопросы контракта

1. **Payload-схемы сообщений.** Полные формы `ba:hello`, `ba:storage`,
   `ba:result` и других сообщений в BA-PLAT-4.2/BA-GAME-2.2 не описаны
   полностью. Для их окончательного утверждения нужен BA-SDK-1.1 или
   отдельное решение владельца.
2. **Лимит размера прочих сообщений** не задан; eventLog-лимиты заданы в
   BA-PLAT-4.2 §2.12.7.
3. **Реализация.** `sdk/1.1.0/ba-sdk.js` пуст: реализация SDK относится к
   этапу 3, а не к этапу 0. Заглушка игры не должна считаться SDK платформы.

## Проверки

- `schemas/manifest.json`, `schemas/catalog.json`, `schemas/eventlog.json` —
  машинные контракты этапа 0.
- `schemas/messages/*.json` — draft-схемы всех типов Приложения F; они
  используют внешний `sessionId` и общий конверт.
- JSON Schema сообщений проверяются тестами `tests/unit/test_foundation_002_contracts.py`.
- Нормативный BA-SDK-1.1 отсутствует; см. `docs/contracts/BA-SDK-1.1_DRAFT.md`.

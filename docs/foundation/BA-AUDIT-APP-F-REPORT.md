# BA-AUDIT — App F: postMessage и жизненный цикл игровой сессии

**Дата:** 2026-11-19.  
**Статус аудита:** **Blocked / App F не реализован**.  
**Область:** приём/отправка postMessage, проверки origin/source, sessionId/requestId,
JSON Schema, rate limit, идемпотентность, состояния сессии, сообщения App F,
EventLog перед результатом.  
**Метод:** статическая инспекция репозитория; код не изменялся, тесты не
создавались и не запускались, миграции не выполнялись.

**Нормативная оговорка:** `docs/contracts/BA-SDK-1.1_DRAFT.md`,
`docs/contracts/MESSAGE_PROTOCOL.md` и `schemas/messages/*.json` имеют статус
DRAFT. Их требования ниже используются как проектные ориентиры, а не как
утверждённый BA-SDK-1.1.

## 1. Краткий итог

В текущем рабочем дереве **нет runtime-реализации App F**. Все файлы
`apps/gameplay` (models, services, API, views, urls, templates, tasks) имеют
размер 0 байт. `sdk/1.1.0/ba-sdk.js`, `static/src/js/host_protocol.js` и
`static/src/js/player.js` также пусты. Игровой маршрут каталога возвращает
JSON-заглушку, iframe-страницы нет.

Существуют только:

- draft JSON Schema всех 14 типов сообщений;
- библиотека `apps/core/contracts.py` с JSON Schema/семантическими
  проверками;
- unit-тесты этих схем и валидатора;
- настройки DRF throttle, не подключённые к App F.

Следовательно, механизмы postMessage, проверки `event.origin`/`event.source`,
состояния сессии, идемпотентность, rate limit и серверная проверка результата
**не реализованы**. Наличие схем и валидатора не означает, что игровой протокол
работает.

## 2. Найденные файлы и функции

### 2.1. Пустые/заглушечные точки входа

| Файл | Факт |
|---|---|
| `apps/gameplay/models/session.py` | 0 байт; класса `GameSession`/state machine нет |
| `apps/gameplay/models/result.py` | 0 байт; модели результата нет |
| `apps/gameplay/models/storage.py` | 0 байт; хранилища нет |
| `apps/gameplay/services/sessions.py`, `heartbeat.py`, `results.py`, `storage.py`, `tickets.py` | 0 байт |
| `apps/gameplay/api/views.py`, `serializers.py`, `urls.py` | 0 байт |
| `apps/gameplay/views.py`, `urls.py` | 0 байт |
| `apps/gameplay/templates/gameplay/play.html` | 0 байт; iframe/игрового экрана нет |
| `sdk/1.1.0/ba-sdk.js` | 0 байт |
| `static/src/js/host_protocol.js` | 0 байт |
| `static/src/js/player.js` | 0 байт |
| `apps/catalog/views.py:21-22` | `game_play()` возвращает `{"status":"stub"}` |
| `apps/catalog/views.py:25-26` | `game_leaderboard()` возвращает заглушку |

Проверка `find apps/gameplay -type f -not -path '*/__pycache__/*' -size +0c`
не нашла ни одного непустого файла. `config/urls.py` не подключает gameplay,
leaderboards, ratings или API; `apps/catalog/urls.py:15` ведёт только на
stub-представление.

### 2.2. Что действительно существует

- `schemas/messages/_envelope.json` и 14 типовых схем:
  `ba_hello`, `ba_submit`, `ba_leaderboard`, `ba_storage`, `ba_new_session`,
  `ba_exit`, `ba_error`, `ba_context`, `ba_result`, `ba_leaderboard_data`,
  `ba_storage_data`, `ba_session`, `ba_pause`, `ba_resume`.
- `schemas/eventlog.json`: структура EventLog, `maxItems: 20000`.
- `apps/core/contracts.py`:
  - `MESSAGE_SCHEMAS` (строки 27–40);
  - `validate_schema()` (строка 62);
  - `validate_eventlog_semantics()` (строки 136–173);
  - `validate_message_semantics()` (строки 176–180).
- `tests/unit/test_foundation_002_contracts.py` — проверяет загрузку схем,
  направление `source`, семантику manifest/eventLog и DRAFT-маркеры.
- `config/settings/base.py:246-252` — `DEFAULT_THROTTLE_RATES`:
  `sessions`, `results`, `heartbeat`, `storage`.
- `docs/contracts/BA-SDK-1.1_DRAFT.md`,
  `docs/contracts/MESSAGE_PROTOCOL.md` — DRAFT-описание проверок.

## 3. Таблица проверок

| Механизм | Статус | Файл/функция | Замечание |
|---|---|---|---|
| Приём/отправка postMessage | **отсутствует** | `static/src/js/host_protocol.js`, `player.js`, `sdk/1.1.0/ba-sdk.js` — 0 байт; `apps/gameplay/views.py` — 0 байт | Нет `postMessage`, `addEventListener('message')`, iframe и SDK |
| Проверка `event.origin` | **отсутствует** | обработчика нет | В коде нет `event.origin`; проверка описана только в DRAFT |
| Проверка `event.source` | **отсутствует** | обработчика нет | Нет сравнения с `iframe.contentWindow`/`window.parent` |
| Проверка `sessionId` | **отсутствует** | `schemas/messages/_envelope.json` — только `format: uuid` | Нет текущей сессии, срока жизни, привязки к игре/субъекту |
| Проверка `requestId` | **отсутствует** | схема требует UUID; LRU/реестра нет | Нет защиты от повторной обработки; DRAFT упоминает LRU 512, кода нет |
| Проверка `type`/`source`/JSON Schema | **реализован частично** | `apps/core/contracts.py:27-40`, `:176-180`; `schemas/messages/*.json` | Валидатор работает в тестах, но не вызывается из runtime; нет приёма сообщений |
| Rate limit сообщений | **отсутствует** | `config/settings/base.py:246-252` | Настройки DRF не подключены к App F; лимита 60/мин на сессию нет |
| Идемпотентность/повторные запросы | **отсутствует** | нет обработчика; `GameResult`/модели — 0 байт | Нет unique/idempotency-ключа в runtime; `ba_schema.sql` — только design |
| Состояния `active/paused/finished/failed` | **отсутствует** | `apps/gameplay/models/session.py` — 0 байт | Нет enum, переходов и проверки допустимости типа |
| `ba:pause` / `ba:resume` | **отсутствует** | только `schemas/messages/ba_pause.json`, `ba_resume.json` | Схемы требуют `source: ba-host`, но обработчика и состояния паузы нет |
| `ba:newSession` / `ba:exit` | **отсутствует** | только `ba_new_session.json`, `ba_exit.json` | Нет аннулирования старого sessionId и завершения сессии |
| `ba:submit` | **отсутствует** | только `ba_submit.json`; `game_play` — stub | Нет приёма результата, проверки score/duration/seed |
| `ba:leaderboard` | **отсутствует** | `schemas/messages/ba_leaderboard.json`; `game_leaderboard()` — stub | Нет запроса TOP-N и ответа `ba:leaderboard:data` |
| `ba:storage` | **отсутствует** | только `ba_storage.json`/`ba_storage_data.json` | Нет get/set/remove, квоты 64 КиБ и conflict flow |
| EventLog перед результатом | **реализован частично** | `schemas/eventlog.json`; `apps/core/contracts.py:136-173` | Валидатор есть, но не вызывается в пути результата; пути результата нет |

## 4. Критические и существенные проблемы

### C-1. App F отсутствует как функциональность (критично)

`apps/gameplay` полностью пуст, `ba-sdk.js` и оба игровых JS-файла пусты,
iframe-страницы нет. Нельзя утверждать, что postMessage, сессии, результаты,
рекорды или storage работают. Это блокер приёмки App F, а не частичная
реализация.

### C-2. Проверки origin/source не реализованы

В коде нет `message`-listener и проверок `event.origin`/`event.source`.
**Факт:** сейчас чужой iframe не может отправить сообщение «от имени игры»,
потому что приёмника сообщений вообще нет. **Риск:** при добавлении listener
без проверок `event.source === iframe.contentWindow` и точного `event.origin`
поддельное сообщение станет возможным. Отсутствие обработчика не является
защитой; это отсутствие функции.

### C-3. Нет доверенной серверной границы для score/duration/seed/trustLevel

`ba_submit` принимает `value`, `durationMs`, `eventLog`, `seed`, `clientMeta`
(`schemas/messages/ba_submit.json`), но серверного обработчика нет. Схема не
сверяет `value` с manifest score, `durationMs` с лимитами сессии, `seed` с
контекстом, `eventLog.seed` с `payload.seed`, а `trustLevel` в
`ba_context`/`ba_result` — обычная строка без enum. Поэтому нельзя подтвердить,
что сервер не доверяет клиентским значениям; сейчас он их вообще не получает.

### C-4. Нет защиты от повторной отправки и результата после завершения

Нет `requestId`-реестра, idempotency-поля, unique-ограничения в runtime и
состояний `finished/failed`. Проектная DDL `docs/foundation/ba_schema.sql`
содержит `UNIQUE(session_id, idempotency_key)`, но она не применена и не
является реализацией. Повторная отправка, дублирование и результат после
`finished` в текущем коде не проверяются.

### C-5. Rate limit и размеры сообщений не соответствуют описанию

DRAFT говорит о 60 сообщениях/мин на сессию, но App F-лимита нет. Настройки
`config/settings/base.py:246-252` относятся к DRF и не подключены ни к одному
игровому view; они не являются лимитом postMessage. В схемах нет общего
лимита размера сообщения; `validate_eventlog_semantics()` считает raw/gzip по
повторно сериализованному JSON, а не по фактически полученным байтам, и не
вызывается из runtime.

### C-6. Пробелы draft-схем и семантического валидатора

- `ba_context` и `ba_session` содержат `sessionId` и в envelope, и в payload;
  равенство этих значений нигде не проверяется.
- `ba_submit.payload` имеет `additionalProperties: true`; `score`/`limits` в
  `ba_context` описаны как произвольные объекты; `ba_result.status` и
  `trustLevel` — произвольные строки.
- `validate_message_semantics()` проверяет только allowlist и JSON Schema; он
  не проверяет `event.origin`, `event.source`, текущую сессию, повтор
  `requestId`, состояние сессии и rate limit.
- `ba_error` допускает оба источника, что соответствует DRAFT, но не
  различает, кто именно отправил ошибку.
- `ba_storage` не проверяет квоту/размер значения; `ba_submit` не проверяет
  диапазон значения.

### C-7. Нет App F-тестов и E2E

`tests/unit/test_foundation_002_contracts.py` проверяет только схемы и
семантику. В `tests/` нет тестов postMessage, iframe, сессий, submit,
leaderboard, storage, идемпотентности или состояний. Наличие зелёных
contract-тестов не доказывает работу App F.

## 5. Ответы на специальные вопросы

| Вопрос | Фактический ответ |
|---|---|
| Может ли чужой iframe отправить сообщение от имени игры? | Сейчас — **нет обработчика**, поэтому отправлять некуда. Проверок origin/source нет; после добавления listener без них риск появится |
| Можно ли использовать устаревший sessionId? | **Невозможно подтвердить**: session store, TTL и проверки текущей сессии отсутствуют |
| Возможны ли повторная отправка и дублирование? | **Невозможно подтвердить/не защищено**: idempotency и unique в runtime отсутствуют |
| Можно ли отправить результат после завершения? | **Невозможно подтвердить**: состояния `finished` и проверки перехода отсутствуют |
| Может ли игра отправлять события во время паузы? | **Невозможно подтвердить**: `ba:pause`/`ba:resume` есть только в схемах; обработчика паузы нет |
| Соответствуют ли фактические лимиты документам? | **Нет подтверждения**: 60/мин, 64 КиБ и общий размер сообщений не реализованы; EventLog-валидатор не подключён |
| Доверяет ли сервер score/duration/seed/trustLevel? | **Невозможно подтвердить**: серверного обработчика результата нет; текущие schema-поля клиентские и не сверяются |

## 6. Что невозможно подтвердить без запуска/интеграционных тестов

- Реальное поведение postMessage и origin/source в браузере.
- Отправку `ba:hello`, `ba:context`, `ba:pause`, `ba:resume`,
  `ba:newSession`, `ba:exit`, `ba:submit`, `ba:leaderboard`, `ba:storage`.
- Срок жизни и аннулирование `sessionId`, повтор `requestId`, состояния
  `active/paused/finished/failed`.
- Идемпотентность и конкурентную отправку результата.
- Фактическое соблюдение лимитов 20 000 событий, 2 МиБ raw, 256 КиБ gzip,
  60 сообщений/мин и размера прочих сообщений.
- Серверную проверку score/duration/seed/trustLevel и EventLog.
- Работу SDK внутри iframe и CSP/заголовков для игрового origin.
- Поведение при паузе, visibility change, завершении и ошибках.

## 7. Изученные файлы и выполненные проверки

Изучены:

- `apps/gameplay/**` — models, services, api, views, urls, tasks, templates;
- `apps/catalog/views.py`, `apps/catalog/urls.py`, `config/urls.py`;
- `apps/core/contracts.py`;
- `schemas/messages/*.json`, `schemas/eventlog.json`;
- `config/settings/base.py` (DRF/throttle);
- `docs/contracts/BA-SDK-1.1_DRAFT.md`,
  `docs/contracts/MESSAGE_PROTOCOL.md`,
  `docs/contracts/SESSION_ID_PROTOCOL.md`,
  `docs/contracts/CONTRADICTIONS.md`;
- `sdk/1.1.0/README.md`, `static/src/js/host_protocol.js`,
  `static/src/js/player.js`;
- `tests/unit/test_foundation_002_contracts.py`, `tests/integration/*`.

Выполнены только read-only проверки: `find`, `wc -c`, `rg`, `nl`, `git status`.
Тесты, миграции, запуск приложения и изменение кода не выполнялись. Код,
схемы, ТЗ, SDK, настройки и Git index не изменялись.

**Вывод:** App F в текущем состоянии **не реализован**; аудит безопасности
postMessage и жизненного цикла сессии можно проводить только после появления
runtime-кода и интеграционных тестов.

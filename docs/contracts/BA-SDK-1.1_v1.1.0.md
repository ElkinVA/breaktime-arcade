# BA-SDK-1.1 — контракт SDK (v1.1.0)

**Статус:** **INTERNALLY ACCEPTED (Architect, 2026-11-22; ADR-APPF-001).**
Внутренний технический контракт SDK 1.1 в пределах ТЗ; это не публикация,
не внешнее/юридическое утверждение и не продуктовая приёмка App F. DRAFT
`BA-SDK-1.1_DRAFT.md` сохраняется как история.
**Дата версии:** 2026-11-20.
**Основание:** BA-PLAT-4.2 (ред. 12.11.2026), BA-GAME-2.2 §6/§9, Приложение F;
DRAFT BA-SDK-1.1; независимый Pro-review 2026-11-20 (conforms-with-fixes);
OD-AUTONOMY-006; `docs/decisions/ADR-APPF-001.md`.
**Приоритет:** при конфликте действует ТЗ; документ не заменяет ТЗ.

## История изменений

| Версия | Дата | Изменения |
|---|---|---|
| 1.1.0 | 2026-11-20 | Первая финальная версия на базе DRAFT: добавлены лимиты §2.12, eventLog, идемпотентность, storage revision/If-Match, полный список кодов, opaque-origin, границы SDK/API; закрыты внутренние [OPEN], где отвечает ТЗ; trust levels приведены к §2.12.6; top(N); #s во фрагменте |

## 1. Назначение и границы

SDK — **единственный** канал связи игры с платформой. Игра выполняется в
iframe на отдельном origin; cookies портала, логин, email, токены и
идентификаторы пользователя игре недоступны. Платформа при публикации
**всегда** заменяет `js/ba-sdk.js` официальной реализацией, совместимой с
`manifest.sdkVersion` (semver-range) и `manifest.protocol`
(BA-PLAT-4.2 §2.14.3).

В границы SDK входят: `ba:hello`, `ba:submit`, `ba:leaderboard`,
`ba:storage`, `ba:newSession`, `ba:exit`, `ba:error` и ответы платформы.
**Не входят** (это API портала, §2.23, не SDK): `rating`, `catalog`,
`reports`, `healthz/readyz`, `locales` — объединённые строки приходят в
`ba.context.strings`.

Маркировка: `[TZ]` — прямое требование ТЗ; `[PROP]` — предложение,
утверждаемое вместе с документом; `[OPEN]` — требует решения владельца
(раздел 10).

## 2. Публичный интерфейс

| API | Назначение | Источник |
|---|---|---|
| `BreaktimeArcade.init({timeoutMs})` | инициализация, таймаут 5 с | `[TZ]` BA-GAME §6; §2.12.4 |
| `ba.context` | контекст сессии | `[TZ]` §2.12.2 |
| `ba.ready()` | сигнал готовности | `[TZ]` BA-GAME §6 |
| `ba.t(key, params)` | ICU/CLDR-перевод | `[TZ]` BA-GAME §6 |
| `ba.on(event, cb)` | `pause/resume/visibility/session/autotest:finish` | `[TZ]` BA-GAME §6 |
| `ba.submitResult(data)` | отправка результата | `[TZ]` §2.12.5 |
| `ba.leaderboard.top(n)` | TOP-N; `n ∈ {10, 100}`, default 10 | `[TZ]` §2.11; `[PROP]` параметризация |
| `ba.leaderboard.myBest()` | личный рекорд или `null` | `[TZ]` §2.11 |
| `ba.storage.get/set/remove` | хранилище ≤64 КиБ, revision/If-Match | `[TZ]` §2.22/§2.23 |
| `ba.newSession()` | новый `sessionId` и seed без перезагрузки iframe | `[TZ]` §2.12.4 |
| `ba.exit()` | завершение без результата | `[TZ]` §2.12.5/§2.23 |
| `ba.fail(code, message)` | аварийное завершение | `[TZ]` BA-GAME §6 |

`ba-sdk.js` реализуется на этапе 3; заглушка игры не считается SDK.

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
            "direction": "higher_is_better", "minValue": 0, "maxValue": 100000,
            "schemaVersion": 1, "maxDeltaMs": 45000},
  "limits": {"minPlaytimeSeconds": 15, "maxSessionSeconds": 1800,
             "pauseOnBlur": true, "heartbeatIntervalSeconds": 30,
             "idleTimeoutSeconds": 1800},
  "trustLevel": "client_reported",
  "seed": "string"
}
```

| Поле | Правило | Источник |
|---|---|---|
| `sessionId` | внешний JSON camelCase; внутри Python/БД — `session_id`; конверсия в адаптере | `[TZ]` App F + OD-FOUND-001 |
| `gameId` | `technical_id` (immutable) | `[TZ]` §2.4.1 |
| `gameVersion` | semver опубликованной версии | `[TZ]` §2.14 |
| `mode` | `user|guest|preview|autotest`; назначает сервер | `[TZ]` §2.12.1 |
| `nickname` | string/null; для гостя null | `[TZ]` §2.12.2 |
| `language`/`fallbackLanguage` | язык сайта; fallback при отсутствии локали | `[TZ]` §2.15 |
| `strings` | объединённый словарь локализации игры | `[TZ]` §2.12.2 |
| `score` | тип/единица/направление/границы; `maxDeltaMs=45000`; `maxValue` обязателен, не null | `[TZ]` §2.12.3, BA-GAME §4 |
| `limits` | `minPlaytimeSeconds ≥ 5`, `maxSessionSeconds ≤ 7200`, `pauseOnBlur`; `heartbeatIntervalSeconds=30`; `idleTimeoutSeconds=1800` | `[TZ]` §2.12.1/§2.12.3, BA-GAME §4 |
| `trustLevel` | одно из `client_reported`, `heuristic_validated`, `replay_verified`, `server_authoritative` (reserved); **назначает платформа**, пример выше — не единственное значение | `[TZ]` §2.12.6 |
| `seed` | строка; вся случайность игры — из неё | `[TZ]` §2.12.2, BA-GAME §6 |

Числа 15/1800/0–100000 — значения манифеста игры из BA-GAME-2.2; платформенный
cap — 7200 с, нижняя граница `minPlaytimeSeconds ≥ 5`.

## 4. Протокол postMessage

### 4.1. Конверт

`{source, protocol, type, requestId, sessionId, payload}`; `source ∈ {ba-sdk,
ba-host}`, `protocol=1`, `requestId` — UUID, `sessionId` — UUID (camelCase),
`payload` — объект.

### 4.2. Направления и типы

| Направление | Типы |
|---|---|
| Игра → платформа | `ba:hello`, `ba:submit`, `ba:leaderboard`, `ba:storage`, `ba:newSession`, `ba:exit`, `ba:error` |
| Платформа → игра | `ba:context`, `ba:result`, `ba:leaderboard:data`, `ba:storage:data`, `ba:session`, `ba:pause`, `ba:resume`, `ba:error` |

JSON Schema каждого типа — `schemas/messages/*.json` (JSON Schema 2020-12);
используется сервером, SDK и автотестом CRM. Конверт — `_envelope.json`.
`eventLog` — формат §2.12.7.

### 4.3. Валидация

Родитель проверяет **в указанном порядке** (`[TZ]` §2.12.4):

1. `event.source === iframe.contentWindow`;
2. `event.origin` точно равен ожидаемому origin игры (схема+хост+порт);
3. `data.source === "ba-sdk"`, `data.protocol === 1`;
4. `data.type` входит в allowlist;
5. `data.sessionId` равен текущей сессии этого iframe;
6. `data.requestId` — UUID, не обрабатывался ранее (LRU 512);
7. соответствие JSON-схеме типа;
8. ≤60 сообщений/мин на сессию;
9. состояние сессии допускает тип.

SDK проверяет: `event.source === window.parent`; `event.origin === parentOrigin`
из фрагмента; `source === "ba-host"`; протокол; `sessionId`; корреляцию
`requestId`; схему. Неизвестные и просроченные сообщения игнорируются молча.

Фрагмент URL iframe: `#p=<portal_origin>&s=<session_uuid>`; билет в URL не
попадает (`[TZ]` §2.4.3). Поведение: замена/удаление iframe → сообщения
игнорируются, сессия закрывается по idle; `ba:newSession` инвалидирует старый
`sessionId`, очищает LRU `requestId`, возвращает новый контекст с новым seed;
после `finished` разрешены только `ba:leaderboard`, `ba:storage`,
`ba:newSession`, `ba:exit`; копирование URL iframe → родитель создаёт новую
сессию, чужая отклоняется проверкой владения; две вкладки → вторая активация
`E_TICKET_INVALID`.

### 4.4. Ограничения сообщений и eventLog

| Параметр | Значение | Источник |
|---|---|---|
| eventLog | `{"v":1,"seed":"...","events":[{"t":0,"k":"start","d":{}}]}` | `[TZ]` §2.12.7 |
| Сериализация | канонический JSON (сортировка ключей, без пробелов), UTF-8, gzip | `[TZ]` §2.12.7 |
| Размер eventLog | ≤256 КиБ gzip, ≤2 МиБ raw, ≤20 000 событий | `[TZ]` §2.12.7 |
| `t` | целые мс от старта, монотонно неубывает, ≤ `durationMs+1000` | `[TZ]` §2.12.7 |
| `k` | только коды из `verification.eventKinds` (≤32) | `[TZ]` BA-GAME §9 |
| Схема eventLog | `verification.eventSchema` (JSON Schema 2020-12) до реплея | `[TZ]` §2.12.7 |
| Прочие сообщения | ≤64 КиБ; неизвестные поля payload отклоняются | `[PROP]`, утверждается вместе с документом |

`eventKinds ≤32` — из BA-GAME-2.2 §9 (не из BA-PLAT); при конфликте
действует ТЗ. `[PROP]` по unknown-полям: платформа контролирует оба конца
канала, поэтому отклонение неизвестных полей безопасно; новые поля — только
через новую версию схемы.

## 5. Жизненный цикл сессии

| Этап | Поведение | Источник |
|---|---|---|
| init | таймаут 5 с; при отсутствии SDK — экран ошибки с «Повторить» | `[TZ]` |
| hello | SDK отправляет `ba:hello`; родитель создаёт/активирует сессию | `[TZ]` §2.12.2 |
| active | heartbeat каждые 30 с при видимой вкладке; **обязательный финальный перед submit**; лимит 3/мин **на сессию** | `[TZ]` §2.12.3, Прил. E |
| submit | `ba:submit` → `POST /sessions/{id}/result`; ответ `ba:result`; таймаут 10 с | `[TZ]` §2.12.5 |
| newSession | новый `sessionId` и seed; старый недействителен; ≤30 новых сессий/час на субъекта, иначе `E_RATE_LIMIT` | `[TZ]` §2.12.4/§2.12.8, Прил. E |
| exit | `POST /sessions/{id}/close` (204) | `[TZ]` §2.23 |
| fail | аварийное завершение, без результата | `[TZ]` BA-GAME §6 |
| finished | только leaderboard/storage/newSession/exit | `[TZ]` §2.12.4 |

Параметры сессии: ticket 60 с одноразовый; активация ≤5 мин; idle 30 мин;
максимальная длительность `limits.maxSessionSeconds ≤7200`; активных сессий
≤3 на (субъект, игра) под advisory-lock; `preview/autotest` — только CRM
(2FA, роль ≥ редактор) или служебный тестовый аккаунт (`[TZ]` §2.12.1).

## 6. Результат и гость

`submitResult({value, durationMs, eventLog, seed, clientMeta})` →
`ba:submit` → `POST /api/v1/sessions/{id}/result` с `Idempotency-Key` →
ответ → `ba:result`. Прямые cross-origin запросы из iframe запрещены; CORS на
API не открывается (`[TZ]` §2.12.5).

Сервер проверяет: существование сессии; принадлежность субъекту; соответствие
игре и версии; состояние `active`; срок; однократность завершения; формат и
диапазон; правдоподобие длительности (|duration_ms−credited_ms|≤5000,
duration≤max, `is_test` или duration≥min); rate limit; стоп-листы; правила
верификатора (`[TZ]` §2.12.5/§2.12.3). Верификатор — Python-плагин платформы;
SDK только передаёт данные и не верифицирует (`[TZ]` §2.12.6).

**Идемпотентность:** `Idempotency-Key` уникален в рамках сессии, хранится
бессрочно вместе с ответом; повтор с тем же ключом возвращает сохранённый
ответ; другой ключ для завершённой сессии → `E_SESSION_FINISHED`; SDK делает
до 3 повторов с экспоненциальной задержкой, кроме `guest`,
`E_VERIFY_FAILED`, `E_SCORE_RANGE`, `E_SESSION_EXPIRED` (`[TZ]` §2.12.5).

**Гость:** API → `403 E_GUEST_FORBIDDEN`; SDK нормализует в
`{status:"guest", code:"E_GUEST_FORBIDDEN", rank:null, isPersonalBest:false,
isRecord:false, trustLevel:"client_reported"}`; ретраи запрещены; результат
не сохраняется; игра показывает результат и уведомление «Результат не
сохраняется» (`[TZ]` §2.12.5).

`ba:result` содержит `status`, `rank`, `isPersonalBest`, `isRecord`,
`trustLevel`; `NEW HIGH SCORE` показывается только при `isRecord === true`.
Матрица отказов — §2.13: сеть/ретраи, `E_SESSION_EXPIRED` (без ретраев),
`E_VERIFY_FAILED` (нейтральный текст), гость (без ретраев), потеря фокуса
(`pauseOnBlur`); потеря результата после 20-минутной партии недопустима.

## 7. Рекорды и хранилище

- `leaderboard.top(n)` → `{entries:[{rank,nickname,value,achievedAt,trustLevel}], myRank}`;
  `n ∈ {10,100}`, default 10; TOP-100 — с пагинацией на странице портала.
- `leaderboard.myBest()` → `{value, achievedAt}` или `null`; гости личный
  рекорд не получают (`[TZ]` §2.11).
- Storage: один JSONB-документ на (игра, субъект); ≤64 КиБ UTF-8; ≤256
  ключей, глубина ≤8, ключ ≤128; `revision` + `If-Match` (200/409/413);
  данные **сохраняются между версиями игры**; гостевое TTL 90 дней с
  последнего доступа; гостевые данные не переносятся в аккаунт; доступ только
  через родительскую сессию; rate 60/мин на сессию, 600/час на субъекта
  (`[TZ]` §2.22/§2.23, Прил. E).

## 8. Ошибки, таймауты, повторы

Таймауты: init 5 с, submit 10 с, чтение leaderboard/storage 5 с. Сетевые
отказы — до 3 повторов с экспоненциальной задержкой; перечисленные в §6
исключения не повторяются. Ответы ошибок — `{code, message}`; `message`
нейтральный, локализуемый по `code`.

Полный список кодов §2.23: `E_AUTH_REQUIRED`, `E_GUEST_FORBIDDEN`,
`E_SESSION_INVALID`, `E_SESSION_EXPIRED`, `E_SESSION_FINISHED`,
`E_TICKET_INVALID`, `E_VERSION_MISMATCH`, `E_SCORE_RANGE`,
`E_DURATION_INVALID`, `E_RATE_LIMIT`, `E_DUPLICATE`, `E_VERIFY_FAILED`,
`E_STORAGE_QUOTA`, `E_STORAGE_CONFLICT`, `E_PAYLOAD_TOO_LARGE`,
`E_MESSAGE_INVALID`, `E_OWNERSHIP`, `E_PLAYTIME_REQUIRED`, `E_INTERNAL`.

Лимиты (Прил. E): создание сессий 30/час субъект, IP 600/час (challenge после
порога); результаты 60/час субъект, 1200/час IP; heartbeat 3/мин на сессию;
postMessage 60/мин на сессию; storage 60/мин сессия, 600/час субъект.

## 9. Совместимость версий и безопасность

- `manifest.sdkVersion` — semver-range; `manifest.protocol = 1`; платформа
  заменяет SDK совместимой официальной версией; при отсутствии —
  `V_SDK_INCOMPATIBLE` с указанием диапазона и доступных версий
  (`[TZ]` §2.14.3). Смена `protocol` — только новой редакцией ТЗ.
- `BA_SDK_DEFAULT_VERSION=1.1.0` — настройка проекта.
- CSP игрового хоста формируется по `capabilities`: `'wasm-unsafe-eval'`
  только при `wasm:true`; sandbox `allow-pointer-lock` только при
  `pointerLock:true`; `X-Frame-Options` отсутствует; изоляция — CSP
  `frame-ancestors` (`[TZ]` §2.4.2/§2.20).
- Резервный opaque-origin режим: sandbox без `allow-same-origin`; storage
  только через SDK; ассеты `Access-Control-Allow-Origin: *` без credentials;
  `capabilities.storage:"local"` в v1 запрещён (`[TZ]` §2.4.3).
- Игра не получает билет, cookies портала, email, логин, токены; билет не
  передаётся в iframe (`[TZ]` §2.12.2).

## 10. Вопросы, закрытые внутренней приёмкой (ADR-APPF-001)

Все три пункта приняты Architect 2026-11-22:

1. Размер прочих сообщений **64 КиБ** и отклонение неизвестных полей
   (`[PROP]` §4.4) — принято.
2. `sessionId` в postMessage (camelCase) и `session_id` в REST (§2.23) —
   применяется существующее OD-FOUND-001; адаптер конвертирует, ТЗ не
   переписывается.
3. `clientMeta` — необязательное расширение из BA-GAME §6; не влияет на
   серверные проверки; ограничение размера — в рамках 64 КиБ.

## 11. Открытые технические работы (не нормативные)

Реализация `ba-sdk.js` — этап 3; файлы `schemas/messages/*.json` — deliverable
этапа 3; evidence проверок — отдельно. До реализации схем документ задаёт
правила, но не заменяет JSON Schema.

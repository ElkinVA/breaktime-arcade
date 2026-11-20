# BA-FOUNDATION-002 — отчёт

**Статус: Partial / Blocked.**  
Этап 0 **не закрыт**. Отчёт подготовлен для независимого аудита ChatGPT и
решения владельца. DRAFT-документы не являются нормативными.

Дата: 2026-11-19.  
Среда: локальная dev-среда; staging/production не затрагивались.

> Примечание о расположении: запрошенный путь `reports/BA-FOUNDATION-002_REPORT.md`
> заблокирован проектным guard-хуком (`BA-AUTONOMY-001`). Отчёт сохранён в
> `docs/foundation/`; для переноса в `reports/` требуется разрешение владельца
> или изменение guard-политики.

## 1. Краткий итог

Выполнены контрактные и проектные работы этапа 0, которые можно выполнить без
оригиналов BA-SDK-1.1/BA-ENV-1.1 и без выбора канонического BA-GAME-2.2:

- подготовлены DRAFT BA-SDK-1.1 и BA-ENV-1.1 с происхождением положений;
- зафиксировано внешнее `sessionId` / внутреннее `session_id`;
- подготовлены draft-схемы всех 14 типов сообщений Приложения F;
- добавлены семантические проверки manifest/catalog/eventLog/messages;
- подготовлена полная проектная SQL-схема §2.22 (47 таблиц), ERD и App J
  mapping;
- сравнены два варианта BA-GAME-2.2;
- dev-lite образы закреплены по доступным digest;
- CI дополнен Django/migration проверками;
- выполнены тесты, миграционные проверки, Compose, dev stack, backup и
  restore-check.

Незакрытые блокеры перечислены в §8.

## 2. Сопоставление с §2.25 (этап 0)

| Требование/критерий §2.25 | Статус | Доказательство/ограничение |
|---|---|---|
| Матрица зависимостей и lock | **PARTIAL** | `uv lock --check`: 79 packages; Python 3.14.10, Django 5.2.19, psycopg 3.3.8; Docker 29.9.3/Compose 5.7.1. Base Python/Node digest не получен |
| Домены и TLS | **PARTIAL** | dev `portal.test`/`*.games.test:8443`; production domains/TLS — открытое решение; staging не затрагивался |
| Контракт SDK 1.1 | **BLOCKED** | `docs/contracts/BA-SDK-1.1_DRAFT.md`; оригинал отсутствует, DRAFT не утверждён |
| JSON Schema manifest/catalog/eventLog | **PARTIAL/DONE как draft** | `schemas/*.json` + semantics; payload сообщений App F — draft |
| Контракт полей App J | **DONE как mapping** | `docs/contracts/APP_J_FIELD_MAPPING.md`; реализация импортёра — этап 3 |
| Схема БД | **DONE как design** | `docs/foundation/ba_schema.sql`: 47 tables, загружен в temp DB; в основную БД не применялся |
| Каркас CI | **PARTIAL** | CI: uv lock, ruff, mypy, pytest, Django check, migration check, schema tests; Docker build не выполнялся |
| Lock собирается | **DONE (config)** | `uv lock --check`; `docker build` не запускался |
| Контракты зафиксированы | **BLOCKED** | DRAFT SDK/ENV и payload-схемы требуют утверждения |
| Схема ревью пройдена | **BLOCKED** | SQL/ERD подготовлены, но ревью владельца/архитектора ещё не выполнено |

## 3. BA-GAME-2.2: расхождения

Полный отчёт: `docs/audits/BA-GAME-2.2_COMPARISON.md`.

- Текст §1–§17, примеры, интерфейсы, форматы и ограничения совпадают
  построчно.
- Вариант A (`ts_site.txt`) содержит дополнительный блок «Решения, принятые
  по умолчанию, и отклонения»; вариант B (`ts_game.txt`) — нет.
- A также содержит процессную заметку «Следующий шаг».
- Дополнительные пункты A:
  1. документы выданы целиком — редакционно-процессное;
  2. `capabilities.storage:"local"` запрещён — техническое;
  3. `catalog.description` 1600 + `coverAlt`/`screenshotAlts` — техническое;
  4. хост привязан к `id` — техническое;
  5. гостевая отправка нормализуется SDK — техническое;
  6. эпохи рекордов — техническое;
  7. служебные режимы исключены из агрегатов — техническое;
  8. юридические формулировки — процессное/юридическое.
- **Канонический вариант не выбран.** Рекомендация: владельцу выбрать A
  (полнее) или B (короче), но решение не принято исполнителем.

## 4. SDK, ENV и протокол

### 4.1. DRAFT-документы

- `docs/contracts/BA-SDK-1.1_DRAFT.md` — DRAFT, не нормативный. Содержит
  интерфейс, контекст, sessionId, postMessage, lifecycle, submit, guest,
  storage, ошибки, таймауты, совместимость; каждое положение помечено
  `[TZ]`, `[INF]`, `[PROP]` или `[OPEN]`.
- `docs/contracts/BA-ENV-1.1_DRAFT.md` — DRAFT, не нормативный. Содержит ОС,
  Python/uv, Django, PostgreSQL, Redis cache/broker, Docker/Compose, Nginx,
  Node, env variables, сеть, dev/staging/prod, TLS, digest policy,
  dev-lite limits.
- `docs/contracts/SESSION_ID_PROTOCOL.md` — внешнее `sessionId`, внутреннее
  `session_id`, преобразование на границе.
- `docs/contracts/MESSAGE_PROTOCOL.md` — draft протокол App F.

### 4.2. SessionId

Аудит подтвердил конфликт BA-PLAT-4.2: §2.12.2/§2.23 используют
`session_id`, §2.12.4/Приложение F и BA-GAME §6 — `sessionId`. Решение
владельца: внешнее JSON — `sessionId`; Python/БД — `session_id`.
Конфликт зафиксирован в `docs/contracts/CONTRADICTIONS.md` C-001; ТЗ не
изменялись.

### 4.3. Message schemas

`schemas/messages/*.json` — 14 типов + `_envelope.json`. Все используют
`sessionId`, `source`, `protocol`, `type`, `requestId`, `payload`; направления
`sdk→host`/`host→sdk` зафиксированы. `schemas/messages/_envelope.json` —
общий конверт. Схемы — draft; открытые payload-поля и лимиты указаны в
`MESSAGE_PROTOCOL.md` §8.

### 4.4. Open questions

- Полные payload-формы `ba:hello`, `ba:storage`, `ba:session`,
  `ba:storage:data` не заданы в доступных ТЗ.
- Лимит размера прочих сообщений не задан.
- Формат `ba:error` — proposal.
- Нужно ли поддерживать legacy `session_id` на API — не решено.
- BA-SDK-1.1/BA-ENV-1.1 оригиналы отсутствуют.
- Base Python/Node image digest не получен (registry timeout).

## 5. JSON Schema и семантические проверки

Заполнены/проверены:

- `schemas/manifest.json` — обязательные поля, id/version, genre/tags,
  languages, score/limits, capabilities, leaderboard, assets, credits;
- `schemas/catalog.json` — name/description/SEO/alt/screenshotAlts;
- `schemas/eventlog.json` — v/seed/events/t/k/d, max 20000 events;
- `schemas/messages/*.json` — App F.

Семантический валидатор `apps/core/contracts.py` проверяет:

- `defaultLanguage ∈ supportedLanguages`;
- `assets.critical` содержит `locales/<defaultLanguage>.json`;
- `score.minValue <= maxValue`;
- `minPlaytimeSeconds <= maxSessionSeconds`;
- `replay_verified` требует `verification`;
- `screenshotAlts` соответствует числу screenshots;
- `eventLog`: монотонность `t`, `t <= durationMs+1000`, `k` из eventKinds,
  20 000 событий, 2 MiB raw, 256 KiB gzip;
- schema + direction для message types.

Тесты: `tests/unit/test_foundation_002_contracts.py`.

## 6. Проектная схема БД и App J

- `docs/foundation/ba_schema.sql` — PostgreSQL DDL всех сущностей §2.22
  (47 таблиц): аккаунты, языки, каталог, импорт, рейтинги, сессии, результаты,
  рекорды, хранилище, контент, аудит, модерация, backup, theme.
- `docs/foundation/DB_SCHEMA.md` — правила и ограничения.
- `docs/foundation/ERD.md` — Mermaid ERD.
- `docs/contracts/APP_J_FIELD_MAPPING.md` — все строки Приложения J,
  P/M/C/R, override, repeat, immutable, validation.

Ключевые ограничения:

- `Game.technical_id`/`host_label` immutable trigger;
- `GameVersion` immutable trigger;
- `Game.current_version` составной FK на версию той же игры;
- `GameAsset.version` составной FK на версию той же игры;
- `GameSession` ровно один субъект;
- `GameResult` session unique + idempotency unique;
- `LeaderboardEntry` unique(game,epoch,user);
- `GameStorage` unique subject + bytes <= 65536;
- `GameRatingVote` value 1–5;
- `AnalyticsEvent` RANGE partition by created_at; event/log tables BIGINT.

SQL проверен в изолированной временной БД `ba_schema_check_002`:
`psql` exit 0, 47 таблиц, после чего temp DB удалена. Основная БД не
изменялась; Django-модели/миграции не создавались.

## 7. Docker digest, CI и проверки

### 7.1. Docker

- `compose.dev-lite.yml`: PostgreSQL, Redis cache, Redis broker, Nginx,
  Mailpit закреплены по доступным digest.
- `compose.yml` и staging намеренно не переписаны (staging не затрагивался);
  их теги остаются исключением.
- `Dockerfile` base Python/Node images — теги; registry `docker manifest
  inspect` завершился таймаутом. Digest не выдумывался; требование
  воспроизводимости частично незакрыто.
- `docker compose config --quiet` — OK.
- `docker compose config --images` показывает digest для dev-lite сервисов.

### 7.2. CI

`.github/workflows/ci.yml` дополнен:

- `uv lock --check`;
- ruff check/format;
- mypy;
- `manage.py check`;
- `makemigrations --check --dry-run`;
- schema/contract tests;
- pytest with coverage.

Полный production release не запускался.

### 7.3. Фактические проверки

```text
make test
141 passed in 4.75s

make lint
All checks passed!
311 files already formatted

make types
Success: no issues found in 302 source files

make check
All checks passed!
311 files already formatted
Success: no issues found in 302 source files
141 passed in 5.62s
```

```text
python manage.py check
System check identified no issues (0 silenced).

makemigrations --check --dry-run
No changes detected

migrate --plan
No planned migration operations.

uv lock --check
Resolved 79 packages in 20ms

docker compose ... config --quiet
exit 0
```

```text
./verify_stack.sh
web/db/redis-cache/redis-broker healthy
/en/ 200
/crm/ 302
static 200
games.host 404
СТЕК ЗДОРОВ

curl /readyz
200
{"checks":{"backup":"ok","broker":"ok","cache":"ok","db":"ok","i18n":"ok"},
 "status":"ready"}
```

Backup/restore-check:

```text
make backup:
  run=01a1f39f-de2d-7d39-afbd-66e2311cd376
  size=81555
  sha256 prefix=2f834bae99dd35c4...

make restore-check:
  OK verified_at=2026-11-19 11:45:14.020172+00:00
```

Операционное замечание: после пересоздания зависимостей из-за digest pinning
web/worker кратковременно отдавали 503/502; после `restart web worker`
`readyz` снова 200. Это не staging/production.

## 8. Блокеры и вопросы владельцу

1. Оригиналы BA-SDK-1.1/BA-ENV-1.1 отсутствуют; DRAFT не утверждены.
2. Внешний `sessionId` утверждён, но нормативные примеры `session_id` не
   обновлены; конфликт зафиксирован.
3. Полные payload-схемы App F и лимит прочих сообщений не заданы.
4. Канонический BA-GAME-2.2 не выбран.
5. Полная production-инфраструктура (compose.prod, prod Nginx, monitoring,
   WAL/PITR/S3) не готова.
6. Base Python/Node Docker digest не получен.
7. Полная реализация Django-моделей/миграций по проектной схеме — следующий
   этап; SQL design не применён к основной БД.
8. E2E/load-тесты не реализованы.
9. `docs/spec/` пуст; README/CLAUDE ссылаются на отсутствующие документы.
10. Нужно утвердить DRAFT SDK/ENV, App J mapping и DB schema владельцем.

## 9. Остаточные риски

- R-011: отсутствие BA-SDK-1.1/BA-ENV-1.1.
- R-012: base image digest / reproducible build.
- R-013: SQL design не реализован в моделях/миграциях.
- R-014: payload schemas/message limits не утверждены.
- R-003/R-004/R-005/R-006/R-007 — существующие остаточные риски.
- R-008/R-009/R-010 — Git/backup и документальные риски.

## 10. Git

До задания:

```text
Branch: main
HEAD: 1fc96b40b6c11b1fcb20e1e5a833a65d166c8340
Tracked modified: 57
Untracked: 65
Staged: 0
index raw: e7421720b5f5da3e04b7cdea3dad2af496f785d461ba0715c7f6b33f104149b2
HEAD tree: 4f3a8501a70b23fd6e04aed51878d815b87f9615
index tree: 4f3a8501a70b23fd6e04aed51878d815b87f9615
```

После задания:

```text
Tracked modified: 73
Untracked files: 78
  (git ls-files --others --exclude-standard | wc -l)
Untracked status entries: 22
  (git status --short; каталоги схлопнуты)
Staged: 0
HEAD tree: 4f3a8501a70b23fd6e04aed51878d815b87f9615
git write-tree: 4f3a8501a70b23fd6e04aed51878d815b87f9615
```

`HEAD`, Git index и дерево индекса не изменялись: `git write-tree` совпадает
с `HEAD^{tree}`, `git diff --cached` пуст. Отчёт — новый untracked-файл.
Нормативные ТЗ, `CLAUDE.md`, `README.md`, `.claude/`, `.env*`, `certs/`,
`creds/`, staging/production не изменялись.

## 11. SHA-256 ключевых артефактов

Нормативные файлы (не изменялись):

```text
technical_specification/ts_site.txt  169360 bytes  17d2caa0092c3db5071cadd18c22eab22662cb408ca3e216962692c0f26c7090
technical_specification/ts_game.txt   34712 bytes  40e6d4256090d312d22b42162e9e3cf118c5814c3ee4f110a0d30ca247a826db
```

Созданные/обновлённые артефакты BA-FOUNDATION-002:

| Файл | Байт | SHA-256 |
|---|---:|---|
| `docs/contracts/BA-SDK-1.1_DRAFT.md` | 11240 | `4881729f49c41104b578f56a60a6ce9c22d05986ed13ef97c3a7143f2667ad3b` |
| `docs/contracts/BA-ENV-1.1_DRAFT.md` | 9350 | `ad3bbfb78feeb27e44351614a4fdde5befe4d12476bac8e29b73df5df4808356` |
| `docs/contracts/SESSION_ID_PROTOCOL.md` | 5265 | `7b7248f23074d57b6277ba847f33672edd9dc4b5e88716731dcc328684effca2` |
| `docs/contracts/MESSAGE_PROTOCOL.md` | 5587 | `c209dfc11ee30c6c12fb67b7a9ca353acc028939eaa82dfb98c2764dcb1072a7` |
| `docs/contracts/CONTRADICTIONS.md` | 4420 | `5b04224214884937d5e14313b8c689c8cddcb780433262f2049b09dd4a645501` |
| `docs/contracts/APP_J_FIELD_MAPPING.md` | 8416 | `17e40c2f670e1ffdaed435e2b25f476f07494766c95388a75c83cab1f4337363` |
| `docs/audits/BA-GAME-2.2_COMPARISON.md` | 10008 | `31e7314c295f1ff38a74b9027ead4019006ac647e41275f0854bea66da80c876` |
| `docs/foundation/ba_schema.sql` | 29651 | `dcd718bfa9004f5488f9d6f12ebc9aceb31caa6079b234cc9d684a5a9ff32186` |
| `docs/foundation/DB_SCHEMA.md` | 6462 | `fb497cf864e389909b49009ea4bd971d4d4514189fa9959939f3444cf1704e6f` |
| `docs/foundation/ERD.md` | 4218 | `2d0bac256724fabe7080fb70e6a95040f156283bbcf2a238cf030d364d9ceef8` |
| `apps/core/contracts.py` | 6848 | `b4aa2df870fda691ac0b188dcb7a4e13b0216d4f6ba59fecff3d51536469c23f` |
| `tests/unit/test_foundation_002_contracts.py` | 10202 | `bb3506527ec257c515a108ecbb568222ccee075ee1702682e2a0bf0fd15da4a6` |

Схемы и конфигурация:

| Файл | Байт | SHA-256 |
|---|---:|---|
| `schemas/manifest.json` | 7283 | `732e10ed0caf0cd3b623e90e3e813447b0990686481d12cd5a1c065ce0c810f7` |
| `schemas/catalog.json` | 1505 | `5d9f3889bfb885791f3db9c7188e6146b6bbbecdf3d3ee9ad41aabf25a63e80b` |
| `schemas/eventlog.json` | 1274 | `cc2a3f4b613b08849f6c7058adbe39515edf91e3a913e76f91ef8aec44bcd2d0` |
| `schemas/messages/_envelope.json` | 931 | `4c67d5f99fd747d1c9185e64a81077ea634315a6b7bbe62ef8774d510cd0046d` |
| `schemas/messages/ba_context.json` | 2041 | `6fd73173f17b58edee29239f6a0405fa2b046daadc2966ed8e4d6311fdbf3fd3` |
| `schemas/messages/ba_error.json` | 816 | `d7c9e515165f5c3fab0d321049c3c4c97fc8cb03de41a0d70bd27f61b745d0d4` |
| `schemas/messages/ba_exit.json` | 593 | `c4c7dcbd8268098969bc2488bef49e404e56cbe73cd9dd24d2311d01d4f3b4a7` |
| `schemas/messages/ba_hello.json` | 666 | `a8044c3c25d86b052ee5e26de391021527a8c44f57d7d3ec4ce868c8ca5a4294` |
| `schemas/messages/ba_leaderboard.json` | 794 | `d8f3e0c05a6e5a9138ec7096ee472a0a42d49eea04460c98a6cba583a946f620` |
| `schemas/messages/ba_leaderboard_data.json` | 1638 | `3385193b534b5845742ee07ef880bf48cca6864c09b7b5e8c9925dd7cdfa2699` |
| `schemas/messages/ba_new_session.json` | 619 | `6960bbb1842faf56a54c1927e716a45fae7a546969e1efc603859c7d966c28cd` |
| `schemas/messages/ba_pause.json` | 578 | `ffeda92331648510f0d1fffe0d5904b85a70eac9efe1b3941d2bae0516b4925a` |
| `schemas/messages/ba_result.json` | 1368 | `f566c27063067bc15094554c9e4f10e20b2d7dc532380fed9e3d39802b0a4a8c` |
| `schemas/messages/ba_resume.json` | 597 | `a8f868d6b2ddfba8aafc4927929484faa27090693d99fb77f8db107f595ab3ca` |
| `schemas/messages/ba_session.json` | 985 | `0b556566c55be56e1f47a8cefe148ba306b91f22c68990f38f15119c99c6bb56` |
| `schemas/messages/ba_storage.json` | 1019 | `09793807510ba296838f67d2c8125f90a52d24447433cf25578facfaab802237` |
| `schemas/messages/ba_storage_data.json` | 896 | `467f34fef1968ded2e46d82ce0cf3dbc5c4c185255662cea70e95a54d68a33c4` |
| `schemas/messages/ba_submit.json` | 1203 | `6d434e9f3d1145b1b8900f41940259147d99cc2f0a4118303c8105ff4085332a` |
| `compose.dev-lite.yml` | 3463 | `a00564b1d6c4efd946a383d8242ea7048f1c1e0661a3be739af92e970f284a45` |
| `.github/workflows/ci.yml` | 2432 | `1d39922f8f3d3a8e54735aeda2563cf1a9cd64258ca8dca0673ffc7e86c5e16d` |

Хеш самого отчёта не встраивается (самоссылка); он фиксируется внешней
командой `sha256sum` после финального сохранения.

## 12. Рекомендация

**Не готов к формальному закрытию этапа 0.**  
**Готов к независимому аудиту как Partial/Blocked-пакет** с DRAFT-контрактами,
проектной схемой и списком открытых вопросов. Следующий шаг — аудит
ChatGPT и решения владельца по DRAFT/BA-GAME/SDK/ENV/production; этап 1 не
начинать.

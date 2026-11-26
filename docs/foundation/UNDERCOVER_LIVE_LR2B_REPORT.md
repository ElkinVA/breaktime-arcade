# Who's Undercover? Live — LR-2b report

**Дата:** 2026-11-26. **Версия картриджа:** 1.0.0. **Модели:**
исполнитель — Flash (`deepseek-flash[1m]`); независимые reviewers —
Pro `code-reviewer`/`security-auditor` (`deepseek-v4-pro`, text-only).
**Статус:** IMPLEMENTED; независимые code и security review — **ACCEPT**
(delta подтверждён); продуктовая приёмка владельца остаётся обязательной.
Код пакета — commit **`2c9d8f7`**; GitHub Actions run **#155** —
**completed success** (quality/frontend/e2e/image/django-next):
`https://github.com/ElkinVA/breaktime-arcade/actions/runs/45801918631`.

## Что это

Отдельный Live Room картридж `whos_undercover_live` для игры на разных
устройствах. Ведущий создаёт комнату, остальные входят по шестизначному
коду; роли, слова, фазы и голоса хранит PostgreSQL на портале. Игра в iframe
использует только аддитивный SDK 1.2 `room.*`; Pass & Play 1.0.1 и SDK 1.1
не изменены.

## Реализованный объём

- Новый картридж `games-src/whos_undercover_live`: manifest `^1.2`,
  `index.html`, `js/live.js`, `css/live.css`, en/ru catalog/locales,
  детерминированный `pack.py`, README и SELF-CHECK.
- Экраны: create/join, lobby с readiness и блокировкой Start при
  несбалансированном столе, приватный reveal, clues, secret vote, tie,
  Mr. White guess, результат, final reveal и replay.
- Server authority: snapshot только для зрителя; роли/слова других игроков
  скрыты до выбывания/финала; голос виден только свой; сервер проверяет
  membership, phase, host, alive, self/duplicate vote, expectedVersion и
  requestId.
- Reconnect: SDK storage хранит room id; после reload сервер возвращает ту
  же комнату и приватную роль.
- Stale: клиент обновляет snapshot и до трёх раз повторяет команду с тем же
  requestId; сервер дедуплицирует requestId до проверки версии.
- Локализация: en/ru UI; для остальных языков портала — English fallback с
  видимым бейджем покрытия.
- Server-side create validation: `E_BALANCE` для конфигурации, где мирных
  не больше, чем infiltrators; `E_UNDERCOVER` вне 1..3; `E_PLAYERS` вне
  4..12; старт/рестарт повторно проверяют фактическое число игроков.
- CI: `make undercover-live-seed` собирает ZIP и публикует его через
  настоящий pipeline (DEBUG-only `seed_dev_game`); e2e job сеет картридж
  в свежей БД. `V_PUBLISHED_UPDATE_BLOCKED` не обходится.

## Тесты и фактические результаты

- `tests/integration/test_live_rooms.py` — 25 passed, включая новые
  E_BALANCE/E_UNDERCOVER/boundary-тесты и существующие private-role,
  vote/tie/Mr. White, reconnect, host transfer/claim, TTL, cleanup,
  account scrub.
- `tests/unit/test_whos_undercover_live_package.py` — 5 passed: manifest,
  entry/critical budget, deterministic ZIP/preflight, security scan,
  catalog/locales.
- `tests/e2e/test_live_rooms_e2e.py` — 3 Playwright scenarios с 4–5
  независимыми browser contexts:
  1) create/join/ready/private reveal/reconnect/clues/vote/civilian win,
     final reveal и replay;
  2) истинная ничья 2:2 и переход в раунд 2;
  3) Mr. White выбывает и крадёт игру правильной догадкой.
  Проверяется, что экран reveal не содержит слов другой роли.
- `npm run check:js` — PASS (включая `js/live.js`).
- `node --test tests/js/*.test.mjs` — 40/40.
- `python -m compileall -q apps` — PASS (PEP 758 syntax Python 3.14).
- ruff/format — clean; mypy — 406 files clean (до добавления JS/E2E-тестов).
- Полный Python gate: **1291 passed, 17 skipped, exit 0 в 814 s
  (13:34)**; финальный current-source harness (route-подмена `js/live.js`
  на исходник при старом опубликованном runtime) — **3 passed**.
  Это локальное evidence; hosted CI на точном коммите остаётся
  обязательным.

## Независимые проверки

- `code-reviewer` (Pro, text-only): final delta **ACCEPT**, must-fix нет.
  Критический дефект ввода Mr. White (очистка поля каждым poll) найден и
  исправлен; tie-сценарий исправлен на истинную ничью 2:2; наблюдение о
  `except A, B` снято как false positive (PEP 758, compileall PASS);
  criticalPathBytes source/runtime delta 1.22% (<10% threshold) —
  документированный non-blocking minor. Остаток: E2E повторно заполняет
  guess, поэтому регрессию очистки поля в опубликованном runtime поймает
  только CI-проверка/будущий JS-тест, не текущий сценарий.
- `security-auditor` (Pro, text-only): ACCEPT; must-fix нет; delta
  подтвердил, что server-side auth/snapshot/command/transport не менялись.
  Остаточные minor: side-effecting GET на room read, отсутствие
  IP-secondary bucket для command/read, bool-coercion `ready`
  (pre-existing); приняты как остаточные, не входят в LR-2b.
- **Delta:** code-reviewer и security-auditor повторно проверили финальное
  дерево после исправлений и подтвердили ACCEPT.

## Осознанно вне объёма / остатки

- LR-3: нагрузка, crash/restart worker, Celery/TTL под нагрузкой,
  observability, browser host-loss claim с реальным 120-секундным окном.
- Create не идемпотентен на уровне API (повторный POST может создать вторую
  комнату); клиент блокирует double-submit, серверная идемпотентность —
  следующий пакет.
- 5-минутный stale-member forfeit и 120-секундный host claim требуют
  продуктовой/UX-приёмки.
- Продуктовая приёмка, реальные плейтесты и production deploy — владелец.
- Локальный dev runtime, опубликованный до финальных правок live.js, не
  перезаписывался из-за `V_PUBLISHED_UPDATE_BLOCKED`; hosted CI run #155
  на `2c9d8f7` подтвердил e2e на свежесобранном текущем runtime.

# ARCADE-P4 — Acceptance Report

**Дата:** 2026-11-22
**Область:** Operational Hardening (A1–A6) и первая реальная игра (B).
**Среда live:** dev-lite `https://portal.test:8443`, PostgreSQL 18,
Redis cache/broker/throttle, Celery worker/beat, nginx, изолированный
`zip-worker`.
**Статус:** **TECHNICALLY IMPLEMENTED / INDEPENDENT PRO REVIEW ACCEPT**;
продуктовая и юридическая приёмка — только владелец.
Staging live — **BLOCKED / NOT TESTED** (нет `.env.staging`).

## 1. Итог

| Пункт | Результат | Доказательство |
|---|---|---|
| A1 R-033 system-wide quota | **IMPLEMENTED / Pro-accepted** | `0ba8bfe`, strict `16fb095`; quota over uploads/artifacts/packages, flock reservations, min-free fail-closed; tests |
| A2 R-037 retention | **IMPLEMENTED / Pro-accepted** | active uploads protected; completed 24 h; failed/rejected/timeout 1 h; artifacts `flock`; helper tasks; `docs/runbook/zip_retention.md` |
| A3 R-041 sync wait | **ANALYSED / decision: keep sync** | `docs/audits/R-041_SYNC_WAIT_ANALYSIS.md` |
| A4 R-042 staging | **PREPARED / LIVE NOT TESTED** | `docs/runbook/staging_verification.md`, `verify_staging_p4.sh`; no `.env.staging` |
| A5 resilience | **IMPLEMENTED, limited evidence** | concurrent quota, worker/broker failure, duplicate, cleanup rerun, disk pressure, published runtime preservation; no load/stress |
| A6 ZIP Worker review evidence | **SAVED (available evidence)** | `docs/audits/ZIP_WORKER_REVIEW_EVIDENCE.md`; original P3 reviewer JSON was not persisted |
| B first real game | **IMPLEMENTED; live E2E PASS** | Neon Snake v1.0.0 → v1.1.0 → rollback; CRM/worker/public/runtime/SDK/leaderboard |
| Full fresh gate | **PASS** | `966 passed, 12 skipped` |
| Browser E2E | **PASS** | `18 passed` |
| Independent Pro review of P4 game | **ACCEPT; major fixed/closed** | `docs/audits/ARCADE_P4_GAME_REVIEW_EVIDENCE.md` |

## 2. A1/A2 — quota и retention

- Единая app-layer квота над `ZIP_PIPELINE_STORAGE_ROOT`,
  `ZIP_UPLOADS_ROOT`, `ZIP_ARTIFACTS_ROOT`; общий `zip_quota` volume,
  `fcntl` lock, expiration reservations.
- `import_package` резервирует **2×** размер архива до любых записей
  (immutable package + upload source); worker резервирует worst-case
  artifacts до extraction и проверяет post-write.
- Если `statvfs` не удался хотя бы для одного root — fail-closed
  `X_STORAGE_FREE_SPACE`, запись reservation не создаётся.
- Отказ квоты не удаляет и не повреждает опубликованные игры; создаётся
  rejected draft/report.
- Retention: active никогда; complete uploads сразу; failed/rejected/
  timeout/cancelled/abandoned uploads/artifacts 1 ч; completed artifacts
  24 ч; published runtime/original packages не удаляются. Cleanup
  идемпотентен, считает только фактические удаления.
- Ограничение: hard filesystem quota (project quota) не включена;
  app-layer quota + min-free — не FS-level гарантия.

## 3. A3 — R-041

Синхронное ожидание до 75 с занимает один Gunicorn worker; при 4 worker
одновременные импорты могут насытить web, а `zip-worker` concurrency=1
сериализует extraction. Решение: **оставить sync** для текущего объёма
(staff-only, редкие импорты, timeout+CANCEL уже есть), пересматривать при
росте объёма/пакетных загрузках. Async не внедрялся без доказанной
необходимости.

## 4. A4 — staging

Подготовлены безопасный шаблон/инструкции, ownership/shared-volume/
zip-worker/backup проверки (`verify_staging_p4.sh`). Реальные секреты не
создавались. Live staging **не поднимался**; отсутствие `.env.staging` —
внешний блокер. `compose config`/HTTP-проверки не выдаются за live.

## 5. A5 — resilience

Покрыто тестами: конкурентные резервации, исчерпание quota, давление
free space, duplicate import, broker failure без fallback, worker
timeout/redelivery, cleanup rerun/restart, сохранение published runtime,
malformed/traversal/hash mismatch. **Не проверено:** нагрузочный benchmark,
реальный отказ Redis под нагрузкой, hard FS quota, staging/production.

## 6. B — Neon Snake

### Пакет
`games-src/neon_snake` (`d1ebc41`): `manifest.json` (id `neon_snake`,
v1.0.0, 6 языков), `index.html`, CSS, seeded `js/rng.js` + `js/game.js`,
6 `locales/*.json`, 6 `catalog/*.json`, cover + 2 screenshots, README,
SELF-CHECK, воспроизводимый stdlib `pack.py`. Официальный
`sdk/1.1.0/ba-sdk.js` вложен байт-в-байт; платформа заменяет его при
публикации.

### Live E2E (факт)
1. `pack.py` → ZIP 119 640 B (`sha256 fa3bcb0c…`).
2. CRM `/crm/games/add/` upload → draft analysis: 0 blockers.
3. Очередь `zip`: `zip.received` → `zip.extract` → `zip.complete`
   (23 файла, 131 ms), source cleanup.
4. Карточка v1.0.0 → step-up session → publish.
5. Public `/en/games/neon-snake/` 200 (cover/screenshots 200), `/play/`
   200; iframe runtime
   `https://neon-snake.games.test:8443/v/<hash>/index.html`.
6. SDK handshake; START; отрисованная игра; результат пользователя:
   `{"status":"saved","rank":1,"is_personal_best":true,
   "is_record":true,"trust_level":"heuristic_validated"}`.
7. Heartbeat: сессия `credited_ms=30116`, `last_heartbeat_at` установлен;
   leaderboard `/en/games/neon-snake/leaderboard/` 200, запись #1.
8. v1.1.0 ZIP загружен и опубликован; rollback на v1.0.0 выполнен через
   CRM POST; текущая версия снова v1.0.0.
9. Bad ZIP → `V_MANIFEST_SCHEMA` blocker, публикация заблокирована.
10. 360×640 и 1280×800: iframe стартует, горизонтального overflow нет,
    консоль без ошибок после CSP-fix. Ассеты runtime CSS/JS 200.

### Найденные и исправленные дефекты
| Дефект | Исправление |
|---|---|
| Imported media files/directories `0640`/`0750` → nginx 403 on a fresh import | `_make_public_media` → file `0644`, parent dirs up to `MEDIA_ROOT` `0755`; tests assert both |
| Public detail не показывал cover/screenshots | cover + gallery с localized alt (`5f8bd2b`) |
| HTMX inline `<style>` нарушал CSP → console error | `includeIndicatorStyles:false` + CSS в `app.css`; CSP не ослаблен |
| Header overflow 21 px на 360 | responsive header, скрытие имени на mobile |
| Manual `collectstatic` дал 403 из-за `0640` | live checklist: chmod a+rX после collectstatic (остаётся операционным риском) |

## 7. Проверки

```text
make test-fresh                         -> 966 passed, 12 skipped
make e2e (Chromium)                     -> 18 passed
sandbox test_neon_snake_package.py      -> 13 passed
sandbox test_neon_snake_import.py       -> 1 passed
sandbox test_catalog_public.py          -> 11 passed
sandbox test_pipeline.py                -> 15 passed
ruff check apps tests devcontrol + pack -> All checks passed
ruff format --check                     -> clean
mypy                                    -> 359 files, no issues
node --check game.js/rng.js             -> OK
```

## 8. Независимый review

- P3 ZIP Worker: plan/implementation — code/security Pro review **ACCEPT**
  after fixes; полный исходный P3 JSON не сохранился, доступные
  вердикты/находки — `docs/audits/ZIP_WORKER_REVIEW_EVIDENCE.md`.
- P4 storage: Pro reviewer **accept** (full JSON:
  `.autonomy/evidence/reviewer-3e014175…json` for storage,
  `reviewer-df0a0cfe…json` for strict follow-up).
- P4 game: independent Pro reviewer — **ACCEPT**; major finding (media
  parent dirs `0750` → nginx 403) fixed and delta re-review **ACCEPT,
  major CLOSED**. Minor width/height/alt issues fixed; comma-`except` style
  fixed with `contextlib.suppress`. Full evidence and findings —
  `docs/audits/ARCADE_P4_GAME_REVIEW_EVIDENCE.md`.

## 9. Что не проверено / ограничения

- Staging live: **BLOCKED/NOT TESTED** (нет `.env.staging`); production
  deploy не выполнялся.
- Hard FS quota, project quota, load/stress, multi-host concurrency —
  **NOT TESTED**.
- Реальная продуктовая/юридическая приёмка игры, права на контент,
  email/legal/domains/TLS/S3/DR — **владелец/внешние стороны**.
- Browser matrix: только Chromium; Playwright host требует локальный
  libasound workaround.
- CSP console test выполнен в Playwright; сторонние расширения/браузеры
  не проверялись.
- `collectstatic` permissions после ручного запуска — операционный риск,
  не исправлен в entrypoint для внешнего вызова.
- CRM upload click-through v1.1/rollback выполнен локальной staff-сессией;
  полноценный TOTP step-up flow уже покрыт P2/P3 E2E, здесь использована
  действующая step-up сессия.

## 10. Коммиты

- `ee0f4d6` — P4 plan/journal.
- `0ba8bfe` — storage quota/retention; `22ee2dd` — sandbox allowlist;
  `16fb095` — strict quota/free-space.
- `d1ebc41` — Neon Snake package/tests.
- `5f8bd2b` — catalog media/render/CSP/mobile fixes; `c5e3947` — mobile header profile/language balance; `99e0ff2` — media directory permissions/alt/dimension review fix.
- Документы P4 — отдельный docs-коммит.

## 11. Следующий шаг

Владелец: подтвердить продуктовую приёмку Neon Snake и права на контент;
предоставить `.env.staging` и окно staging-проверки; решения по
email/legal/domains/TLS/S3/deploy — см.
`ARCADE_P4_OWNER_ACTION_LIST.md`.

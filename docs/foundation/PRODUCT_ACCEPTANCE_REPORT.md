# Product Acceptance Report — Browser Arcade P0–P2

**Дата:** 2026-11-22
**Область:** P0 contract closure, P1 public product, P2 ZIP pipeline/CRM.
**Среда:** локальный dev-lite stack (`portal.test:8443`), PostgreSQL 18,
Redis cache/broker/throttle, Celery worker/beat, nginx, zip-worker.
**Статус:** **P3 ZIP ISOLATION ACCEPTED — NOT PRODUCTION-READY**:
основные пользовательские сценарии и изоляция ZIP проверены; остаются
внешние production-блокеры (реальная игра, legal/email/домены/TLS/S3/deploy).

## 1. Итог

| Сценарий | Результат | Доказательство |
|---|---|---|
| ZIP → validation → import → card → publish | **PASS** | synthetic CC0 fixture `Acceptance Fixture Game`; CRM upload `/crm/games/add/`, analysis/check/publish, card status «Опубликована» v1.0.0 |
| Public launch published game | **PASS** | `/en/games/acceptance-fixture/` 200; `/play/` 200; iframe runtime `acceptance-fixture.games.test/v/<hash>/index.html` загрузился |
| SDK session/heartbeat/result/leaderboard/storage | **PASS** | probe E2E: handshake `ready: user`, 30s heartbeat, `submitResult` → `saved/rank 1`, leaderboard entry, storage `{n:1}` |
| Ratings / popularity | **PASS with fixture** | authenticated rating 5 с playtime fixture → `5.00`, count 1; rating API/aggregates covered by tests; true 120s browser play не отдельно |
| Version update / rollback | **PASS technically** | import v1.2.0 → publish; rollback to v1.0.0; republish v1.2.0; runtime hash moved to host path |
| CRM games/versions/staff/moderation/content/analytics | **PASS read paths** | owner browser: `/crm/`, games, staff, moderation, content, translations, analytics, audit — all 200 |
| CRM step-up publish | **PASS** | password+TOTP; publish redirected to published card; failed reuse of login TOTP correctly blocked |
| ZIP/API/access security | **PASS (P3)** | traversal/malformed rejected before enqueue; worker-only extraction; live source removed; cleanup task live; origin/CSRF/access tests PASS |
| ZIP Worker isolation | **PASS** | live CRM upload → `ZipExtractionJob completed`; zip-worker log `zip.extract`/`zip.complete`; web has no `extract_zip`; source absent |
| Adaptivity, localization, SEO | **PASS** | Playwright 360px/focus/labels; 6 language pages; JSON-LD VideoGame/BreadcrumbList; sitemap 200 |

## 2. Выполненные проверки

- Browser E2E: **18 passed** (`BA_E2E=1`, Chromium, dev-lite). Включает
  аккаунты, 2FA, языки, 360px, catalog a11y, probe runtime/storage/origin.
- Full fresh gate: **930 passed, 12 skipped** (`make test-fresh`).
- Live smoke: `/healthz` 200, `/readyz` DB/cache/broker/i18n/backup ok.
- Live CRM: owner pages all 200; anonymous `/crm/games/` → 302 login.
- Live import/publish: synthetic fixture ZIP; runtime served after fixes.
- Live isolated worker: `worker_acceptance` import → `ZipExtractionJob
  completed`, worker `zip.extract`/`zip.complete` (93 ms), source removed;
  upload cleanup task live removed an aged job.
- Live App F: probe session/result/leaderboard/storage; rating UI; rollback.
- Live SEO: JSON-LD, sitemap, DE pages.

## 3. Найденные дефекты и исправления

| Дефект | Влияние | Исправление / статус |
|---|---|---|
| Running dev DB не имел P2 migrations (`accounts.crm_role` и др.) | регистрация 500, CRM login ломался | migrations применены; deployment checklist должен включать `make migrate` |
| `/static/` 403 после `collectstatic` | CSS/HTMX недоступны | entrypoint уже делает `chmod`; для ручного collectstatic нужен chmod; live CSS 200 после исправления |
| Runtime publisher писал в `/app/var/runtime`, nginx читает `/app/runtime` | опубликованная игра 404 | `compose.dev-lite.yml` задаёт `ZIP_PUBLIC_RUNTIME_ROOT=/app/runtime` |
| Runtime files были `700/600` | nginx 403 | `_make_runtime_public`: dirs 755/files 644 |
| Runtime path без host label | nginx `/<host>/<hash>` не находил bundle | `store_runtime(..., host_label=...)`; путь `/<host>/<hash>` |
| `rename` между volumes давал EXDEV | import отклонялся `X_ARTIFACT_IO` | staging рядом с target + copy + rename |
| Runtime volume root был root-owned | web не мог публиковать | base `zip-volume-init` chown runtime/zip volumes; web/nginx mounts |
| ZIP import распаковывал в web | нарушение изоляции | P3: worker-only extraction, durable job, hash verification, no fallback |
| Source ZIP оставался после timeout/failure | утечка до 25 МБ на job | cancel marker + TTL cleanup task on writable default worker |
| Cleanup на read-only zip-worker не удалял | ложный `removed` | cleanup moved to default worker; counts only actual deletion |
| Worker volume override терял app_var/media | backup/restore риск | explicit inherited mounts restored; compose test asserts |
| Playwright host lacked `libasound.so.2` | E2E not runnable | local test-only `LD_LIBRARY_PATH` workaround; не product |
| Rating E2E 429 из-за account age/limits | rating not testable immediately | acceptance fixture aged/playtime seeded; ограничение корректное |

Runtime isolation/runtime-path fixes: `dbbcf5d`; P3 worker integration and
review fixes: `021a36c`, `270f224`, `e9f66e2`, `9017254`.

## 4. ZIP Worker isolation (P3) и ограничения

**Изоляция:** `import_package` создаёт `ZipExtractionJob`, пишет source в
приватный `zip_uploads/<uuid>/source.zip` и enqueue’ит `extract_zip_task` в
очередь `zip`. Web **не импортирует и не вызывает** `extract_zip`; worker —
единственный потребитель очереди `zip`, его сеть `zipnet` содержит только
redis-broker, нет edge/db/cache, `read_only`, `cap_drop ALL`, `mem_limit
512m`, `cpus 1.0`, `pids_limit 64`, `nofile 1024`, tmpfs `/tmp` 64 MiB,
deadline 50 s; ZIP ≤25 MiB, распакованный бюджет/файлы — worker limits.
Web проверяет `STATUS.json`/`COMPLETED.json`, package hash и каждый файл
(sha256/размер/точный набор), затем копирует в собственный staging.

**Cleanup:** terminal failures/timeouts cancel/source cleanup; abandoned
uploads удаляет отдельная задача `cleanup_zip_uploads` на writable default
worker (zip-worker uploads — read-only). Retention TTL — R-037.

**Negative tests (PASS):** enqueue failure/no fallback, worker status
rejection, timeout + CANCEL, hash mismatch, busy-not-terminal, malformed ZIP,
path traversal, symlink/source permissions, duplicate/retry idempotency,
cleanup of abandoned uploads, compose isolation invariants. Live: malformed
traversal ZIP rejected before enqueue; aged upload removed by the actual
Celery cleanup task.

**Staging/prod runtime (static):** base `compose.yml` now mounts
`runtime_data` at `/app/runtime` for web (rw) and nginx (ro), sets
`ZIP_PUBLIC_RUNTIME_ROOT=/app/runtime`, and `zip-volume-init` chowns/chmods
runtime + zip volumes. `docker compose ... compose.prod.yml config` passes;
staging live is **NOT TESTED** because `.env.staging` is absent.

**Ограничения:**

- Реальный игровой ZIP и права на контент: **NOT TESTED**; использован
  synthetic CC0 fixture.
- Production/STAGING live stack не поднимался; **staging config NOT TESTED**
  из-за отсутствующего `.env.staging` в среде. Base `compose.yml` содержит
  runtime volume/env/init для web/nginx; `compose.prod.yml` config — PASS.
- Staging/prod runtime serving, ownership на первом старте и backup/restore
  live — **NOT TESTED**.
- Синхронное ожидание worker до 75 с занимает web worker; production
  load-test не проводился.
- Hard filesystem quota для zip-томов (R-033) и retention uploads (R-037)
  остаются остаточными рисками.
- Реальная email-доставка, bounce, legal pages, domains/TLS, S3/CDN,
  monitoring/DR и production deploy: **NOT TESTED / EXTERNAL**.
- CRM write-сценарии модерации/переводов/аналитики проверены read paths и
  integration tests, не все browser write flows.
- True 120s browser playtime для рейтинга не отдельно; использован fixture.
- Popularity live aggregate не отдельно; API/aggregate tests зелёные.
- Playwright E2E не является production browser matrix; проверен Chromium.

## 5. Готовность

**Готово к demo/dev acceptance:** каталог, публичная игра, probe SDK,
рейтинги, лидерборд, storage, CRM read/write games/wizard/roles/step-up,
SEO/i18n/a11y, изолированный ZIP worker.

**Не готово к production:** real game/rights, email, legal,
domains/TLS, S3/CDN/hosting/DR, production secrets/deploy, live
staging/prod runtime verification, R-033/R-037 residuals.

## 6. Owner Action List

Только действия, которые нельзя выполнить без владельца/внешней стороны.

### B1. Реальный игровой ZIP

- **Что:** ZIP-пакет игры ≤25 МБ + SHA-256 + подтверждение прав/лицензии.
- **Почему:** synthetic fixture не доказывает реальный контент/UX игры.
- **Если отложить:** публичная игра остаётся demo; product acceptance игры
  не закрыт.
- **Как:** положить файл в защищённое хранилище (не в Git), передать путь/
  SHA-256 и текстовое подтверждение прав; не использовать чужой контент.
- **Формат:** `manifest.json`, `index.html`, `catalog/<lang>.json`,
  `locales/<lang>.json`, обложка/скриншоты, `js/`, официальный SDK
  инжектируется платформой; `sdkVersion ^1.0`, `id` стабилен.

### B2. Email-провайдер

- **Что:** выбранный провайдер, SMTP/API credentials, домен From, SPF/DKIM/
  DMARC, bounce/complaint webhook.
- **Почему:** подтверждение email и восстановление пароля.
- **Если отложить:** регистрация работает, но email-flow не production.
- **Как:** credentials — в `.env.staging`/секрет-хранилище, не в Git;
  сообщить провайдера, регион, лимиты; тестовый ящик.

### B3. Домены, DNS, TLS

- **Что:** portal domain, game domain strategy, DNS-доступ, TLS-сертификаты.
- **Почему:** App F требует отдельные game origins; текущий dev —
  `*.games.test`.
- **Если отложить:** нельзя проверить реальные cookie/origin/CSP.
- **Как:** список доменов, DNS-провайдер, способ выпуска TLS, кто владелец
  зоны; значения `PORTAL_ORIGIN`, `GAMES_DOMAIN`.

### B4. S3/CDN, hosting, monitoring, backup/DR

- **Что:** провайдеры, bucket/region, credentials, retention, backup target,
  monitoring/alerting.
- **Почему:** production storage/backup/DR и runtime delivery.
- **Если отложить:** нет production SLO/DR.
- **Как:** аккаунты/проекты, IAM с least privilege, тестовые bucket/endpoint,
  лимиты расходов.

### B5. Staff, roles, 2FA, owner recovery

- **Что:** реальные staff-логины, роли, TOTP enrollment, офлайн owner
  recovery code, кто owner/admin.
- **Почему:** нельзя открывать production CRM без ответственных.
- **Если отложить:** production CRM остаётся закрытой.
- **Как:** список людей/ролей; каждый enroll TOTP; recovery code — офлайн,
  не в Git/чате.

### B6. Production secrets/deploy

- **Что:** production `.env`, DB snapshot, окно deploy, разрешение на
  production deploy; подтверждение rollback.
- **Почему:** необратимое внешнее действие.
- **Если отложить:** продукт остаётся dev/staging.
- **Как:** отдельное сообщение с окном и ответственным; секреты — только в
  хранилище, не в переписке.

### B7. Платные сервисы и лимиты

- **Что:** ads/analytics/consent providers, бюджеты/лимиты.
- **Почему:** сейчас выключены; включать без согласия нельзя.
- **Если отложить:** функции остаются выключенными.
- **Как:** список сервисов, договор/аккаунт, бюджет, consent-текст.

### C. Юридические/продуктовые подтверждения

- **Terms of Service / Privacy Policy:** проект подготовить можно, но
  публикация/юридическая проверка — только после подтверждения.
- **GDPR/DSA/EN 301 549, возраст 16+:** подтвердить применимость и тексты.
- **Consent/cookies, retention:** утвердить окончательные сроки; текущие
  значения — `[PROP]`.
- **Антифрод рейтингов/популярности:** утвердить правила §2.9.6/R-032.
- **Paid ads/external analytics:** без подтверждения не включать.

## 7. Следующий шаг

`ARCADE-P3-ZIP-WORKER-INTEGRATION-001` **COMPLETED / Pro-reviewed**.
Внутренние работы по ZIP isolation закрыты. Следующий этап требует
владельца/внешней стороны: реальный игровой ZIP/права, staging `.env.staging`
и live staging runtime/backup verification, email, legal, domains/TLS,
S3/CDN/hosting, production secrets/deploy.

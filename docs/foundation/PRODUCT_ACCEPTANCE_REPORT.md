# Product Acceptance Report — Browser Arcade P0–P2

**Дата:** 2026-11-22
**Область:** P0 contract closure, P1 public product, P2 ZIP pipeline/CRM.
**Среда:** локальный dev-lite stack (`portal.test:8443`), PostgreSQL 18,
Redis cache/broker/throttle, Celery worker/beat, nginx, zip-worker.
**Статус:** **TECHNICAL PRODUCT ACCEPTANCE — NOT PRODUCTION-READY**:
основные пользовательские сценарии проверены; один архитектурный блокер
изоляции ZIP и внешние действия не закрыты.

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
| ZIP/API/access security | **PARTIAL / BLOCKER** | unsafe path/forbidden API/origin mismatch/CSRF tests PASS; **ZIP extraction imports in web process, not isolated zip-worker** |
| Adaptivity, localization, SEO | **PASS** | Playwright 360px/focus/labels; 6 language pages; JSON-LD VideoGame/BreadcrumbList; sitemap 200 |

## 2. Выполненные проверки

- Browser E2E: **18 passed** (`BA_E2E=1`, Chromium, dev-lite). Включает
  аккаунты, 2FA, языки, 360px, catalog a11y, probe runtime/storage/origin.
- Full fresh gate: **917 passed, 12 skipped** (`make test-fresh`).
- Live smoke: `/healthz` 200, `/readyz` DB/cache/broker/i18n/backup ok.
- Live CRM: owner pages all 200; anonymous `/crm/games/` → 302 login.
- Live import/publish: synthetic fixture ZIP; runtime served after fixes.
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
| Runtime volume root был root-owned | web не мог публиковать | dev-lite `runtime-init` chown + `runtime-init` dependency |
| Playwright host lacked `libasound.so.2` | E2E not runnable | local test-only `LD_LIBRARY_PATH` workaround; не product |
| Rating E2E 429 из-за account age/limits | rating not testable immediately | acceptance fixture aged/playtime seeded; ограничение корректное |

Исправления runtime/pipeline закоммичены в `dbbcf5d`.

## 4. Не проверено / ограничения

- **BLOCKER:** `apps.pipeline.services.importer.import_package()` вызывает
  `extract_zip()` в web-процессе, а не в изолированном `zip-worker`. Это
  нарушает требование распаковки недоверенного ZIP в отдельном worker с
  лимитами. Требуется отдельная интеграция worker → importer.
- Реальный игровой ZIP и права на контент: **NOT TESTED**; использован
  только synthetic CC0 fixture.
- Production staging/prod compose не проверены на runtime volume/env;
  текущий `runtime-init` добавлен только в dev-lite.
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
SEO/i18n/a11y.

**Не готово к production:** ZIP isolation blocker, real game, email, legal,
domains/TLS, S3/CDN/hosting/DR, production secrets/deploy, staging/prod
runtime volume verification.

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

## 7. Следующий технический шаг

`ARCADE-P3-ZIP-WORKER-INTEGRATION-001`: перенести extraction из web-процесса
в изолированный `zip-worker`, добавить staging/prod runtime volume/env и
повторно прогнать product acceptance. Это внутренняя работа, не требующая
внешних данных.

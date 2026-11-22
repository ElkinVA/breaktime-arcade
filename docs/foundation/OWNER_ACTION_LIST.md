# Owner Action List — Browser Arcade

**Дата:** 2026-11-22
**Статус:** только действия, которые требуют владельца или внешней стороны.
Технические P0–P2 и product acceptance report — в
`PRODUCT_ACCEPTANCE_REPORT.md`.

## B. Нужно предоставить или подтвердить

### B1. Реальный игровой ZIP

- **Что:** ZIP ≤25 МБ, SHA-256, подтверждение прав на весь контент.
- **Зачем:** synthetic fixture не заменяет приёмку реальной игры.
- **Если отложить:** публичная игра остаётся demo; end-to-end приёмка игры
  не закрыта.
- **Как:** передать файл через защищённое хранилище (не Git), указать
  SHA-256 и письменное подтверждение прав/лицензии. Не использовать чужой
  контент без подтверждённых прав.
- **Обязательный формат:** `manifest.json` (cartridge 1, стабильный
  `id`, `version`, `sdkVersion ^1.0`, `entry`, `genre`, assets/critical,
  credits), `index.html`, `catalog/<lang>.json`, `locales/<lang>.json`,
  обложка 1280×720 и screenshots; официальный SDK внедряет платформа.

### B2. Email-провайдер

- **Что:** провайдер, SMTP/API credentials, From-домен, SPF/DKIM/DMARC,
  bounce/complaint webhook, тестовый ящик.
- **Зачем:** подтверждение email, восстановление пароля, bounce.
- **Если отложить:** регистрация работает, email-flow не production.
- **Как:** credentials в `.env.staging`/секрет-хранилище, не в Git;
  сообщить провайдера, регион, лимиты, контакт для webhook.

### B3. Домены, DNS и TLS

- **Что:** portal domain, game-domain strategy, DNS-доступ, TLS.
- **Зачем:** App F требует отдельные game origins; dev использует
  `*.games.test`.
- **Если отложить:** нельзя проверить реальные cookies/origin/CSP.
- **Как:** список доменов, DNS-провайдер, владелец зоны, способ выпуска
  TLS; значения `PORTAL_ORIGIN` и `GAMES_DOMAIN`.

### B4. S3/CDN, hosting, monitoring, backup/DR

- **Что:** провайдеры, bucket/region, IAM credentials, retention, backup
  target, monitoring/alerting.
- **Зачем:** production runtime delivery, backups, DR, SLO.
- **Если отложить:** production SLO/DR не подтверждены.
- **Как:** аккаунты/проекты, least-privilege IAM, тестовые bucket/endpoint,
  лимиты расходов.

### B5. Staff, roles, 2FA и owner recovery

- **Что:** реальные staff-логины, роли owner/editor/moderator/observer,
  TOTP enrollment, офлайн owner recovery code.
- **Зачем:** production CRM нельзя открывать без ответственных.
- **Если отложить:** production CRM остаётся закрытой.
- **Как:** список людей/ролей; каждый enroll TOTP; recovery code — офлайн,
  не в Git и не в чате.

### B6. Production secrets и deploy

- **Что:** production `.env`, DB snapshot, окно deploy, разрешение на
  production deploy, ответственный за rollback.
- **Зачем:** необратимое внешнее действие.
- **Если отложить:** проект остаётся dev/staging.
- **Как:** отдельное сообщение с окном и ответственным; секреты — только в
  хранилище.

### B7. Платные сервисы и лимиты

- **Что:** ads/analytics/consent providers, бюджеты и лимиты.
- **Зачем:** сейчас выключены; включать без согласия нельзя.
- **Если отложить:** функции остаются выключенными.
- **Как:** список сервисов, договор/аккаунт, бюджет, consent-текст.

## C. Юридическое/продуктовое подтверждение

- **Terms of Service / Privacy Policy:** подготовить проект можно, но
  публикация и юридическая проверка — только после подтверждения.
- **GDPR/DSA/EN 301 549, возраст 16+:** подтвердить применимость и тексты.
- **Consent/cookies и retention:** утвердить окончательные сроки; текущие
  значения `[PROP]`.
- **Антифрод рейтингов и популярности:** утвердить правила §2.9.6/R-032.
- **Paid ads/external analytics:** без подтверждения не включать.

## A. Без участия владельца

Разработка, тесты, технические ADR, миграции, production-конфигурации,
черновики юридических документов, адаптеры без подключения платных
сервисов, документация и staging-проверки — продолжаются самостоятельно.

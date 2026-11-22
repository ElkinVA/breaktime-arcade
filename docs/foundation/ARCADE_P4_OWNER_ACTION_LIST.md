# ARCADE-P4 — Owner Action List

**Дата:** 2026-11-22
**Только действия, которые нельзя выполнить без владельца/внешней стороны.**
Техническая работа агента перечислена в `ARCADE_P4_ACCEPTANCE_REPORT.md`.

## 1. Neon Snake — продуктовая приёмка и права

- **Что:** подтвердить, что Neon Snake (AI-generated код/графика, CC0
  credit) принимается как первая реальная игра и права/лицензия
  достаточны для публикации.
- **Почему:** `IMPLEMENTED/TECHNICALLY VERIFIED` не равно продуктовой или
  юридической приёмке; права на контент проверяет владелец.
- **Если отложить:** игра остаётся dev/demo, не публикуется как
  production-контент.
- **Как:** текстовое подтверждение + решение, показывать ли credit
  «AI-generated» на публичной карточке; ZIP уже собран из
  `games-src/neon_snake`, хранится вне Git в рабочем окружении.

## 2. Staging `.env.staging` и окно проверки

- **Что:** создать реальный `.env.staging` на staging-хосте (домен, TLS,
  allowlist IP, DB/Redis/secret key, Basic Auth) и подтвердить окно
  запуска/ответственного.
- **Почему:** без него live staging — **NOT TESTED**; нельзя проверить
  ownership томов, backup/restore, ZIP worker, import/publish.
- **Если отложить:** staging-блокер R-042 остаётся; production-решение
  нельзя принимать по статическим проверкам.
- **Как:** значения — в файл/секрет-хранилище, не в Git/чат; затем
  `docs/runbook/staging_verification.md` + `verify_staging_p4.sh`.

## 3. Legal / privacy / consent / retention

- **Что:** утвердить Terms, Privacy, возраст 16+, consent/cookies,
  retention (игровые сессии/результаты/логи/бэкапы), антифрод-правила.
- **Почему:** публичный запуск и регистрация без утверждённых текстов
  недопустимы.
- **Если отложить:** функции остаются dev/demo; юридический риск.
- **Как:** владелец/юрист; тексты и сроки — не выдумывать агенту.

## 4. Email-провайдер

- **Что:** провайдер, SMTP/API credentials, From-домен, SPF/DKIM/DMARC,
  bounce/complaint webhook, тестовый ящик.
- **Почему:** подтверждение email и восстановление пароля — единственный
  самостоятельный путь восстановления.
- **Если отложить:** email-flow не production.
- **Как:** credentials в секрет-хранилище; сообщить провайдера/регион/
  лимиты.

## 5. Домены, DNS, TLS

- **Что:** portal/game domain strategy, DNS-доступ, TLS-сертификаты,
  отдельные game origins.
- **Почему:** App F требует отдельные origin; cookies портала не должны
  быть доступны игре.
- **Если отложить:** реальные cookie/origin/CSP не проверены.
- **Как:** список доменов, DNS-провайдер, способ TLS, владелец зоны;
  значения `PORTAL_ORIGIN`, `GAMES_DOMAIN`.

## 6. S3/CDN, hosting, monitoring, backup/DR

- **Что:** провайдеры, bucket/region, IAM least privilege, retention,
  backup target, monitoring/alerting, DR.
- **Почему:** production storage/runtime delivery/backup.
- **Если отложить:** нет production SLO/DR.
- **Как:** аккаунты/проекты, тестовые bucket/endpoint, лимиты расходов.

## 7. Staff, 2FA, owner recovery

- **Что:** реальные staff-логины/роли, TOTP enrollment, офлайн owner
  recovery code, кто owner/admin.
- **Почему:** production CRM нельзя открывать без ответственных.
- **Если отложить:** CRM остаётся закрытой.
- **Как:** список людей/ролей; recovery code — офлайн, не в Git/чате.

## 8. Production secrets / deploy / платные сервисы

- **Что:** production `.env`, DB snapshot, окно deploy, ответственный
  rollback; решение по платным ads/analytics/consent.
- **Почему:** необратимые внешние действия и расходы.
- **Если отложить:** проект остаётся dev/staging; платные функции
  выключены.
- **Как:** отдельное сообщение с окном/ответственным; секреты — только
  в хранилище; бюджет/лимиты для платных сервисов.

## 9. Технические остатки, требующие решения владельца

- Hard filesystem quota (R-033) сверх app-layer quota — нужен выбор
  механизма/ФС/стоимости.
- R-036 Phase 2 (глобальный `acks_late`) — решение по семантике доставки.
- Формат публичного credit/лицензии Neon Snake — продуктово-юридическое.

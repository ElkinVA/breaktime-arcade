# BA-STAGE-2.1 — регистрация, вход и профиль (§2.10)

**Дата:** 2026-11-19  
**Статус:** **PARTIAL** — core §2.10 реализован в dev и проверен; приёмка
пакета и §2.10 не выполнена. Это self-check исполнителя, не независимый
аудит и не решение владельца.

## 1. Нормативная база и границы

Реализовывался §2.10 BA-PLAT-4.2: анонимная идентичность, регистрация,
email/восстановление, кабинет, удаление/никнеймы. Использованы только
существующие нормативные требования; недостающие продуктовые решения не
выдумывались. App F, gameplay/leaderboards/ratings, SDK и production-
инфраструктура не затрагивались. Staging/production не изменялись.

## 2. Что реализовано

### Модели и миграция

- `UserProfile`: публичный nickname, confusables-скелетон, язык, тема,
  возраст/marketing consent, deletion window.
- `EmailAddress`: один email, статус подтверждения, bounce-поле.
- `NicknameHistory`, `NicknameReservation` (HMAC скелетона).
- `AnonymousIdentity`: серверная запись гостя, `token_hash`, expiry.
- `AccountToken`: email verification/password reset, SHA-256 хеш,
  expiry, one-time `used_at`.
- `UserLegalAcceptance`: версии Terms/Privacy, дата, hash IP.
- Миграция `accounts.0002_nicknamereservation_anonymousidentity_emailaddress_and_more`
  создана и применена в dev.

### Регистрация и вход

- Логин 3–30 `[a-z0-9_.-]`, citext; nickname 3–20 Unicode с NFKC,
  casefold и confusables-скелетоном; email необязателен.
- Argon2id: `time_cost=3`, `memory_cost=65536`, `parallelism=4`.
- Пароль ≥12, Django validators, запрет совпадения с login/nickname/email,
  HIBP k-anonymity hook (fail closed при включённом HIBP).
- Обязательные age 16+/Terms/Privacy; marketing consent отдельно.
- Вход/выход, safe `next`, CSRF, session rotation средствами Django.
- Rate limits: login по аккаунту и IP, registration по IP, password reset
  по аккаунту и IP.

### Email и восстановление

- Подтверждение email ссылкой, TTL 24 ч, one-time hash-токен.
- Password reset только для verified email, TTL 30 мин, нейтральный ответ,
  one-time hash-токен; новый запрос гасит предыдущие reset-токены.
- Смена email: повторная аутентификация текущим паролем, подтверждение
  нового адреса, уведомление на старый verified email.
- Смена пароля инвалидирует прочие сессии; reset также гасит токены.

### Кабинет

- Профиль: nickname, email/статус, язык, тема, marketing consent,
  принятые версии документов, deletion status.
- Смена nickname не чаще 1 раза в 30 дней с историей.
- Смена пароля, экспорт данных JSON, запрос удаления с подтверждением
  пароля и словом DELETE, окно отмены 7 дней.
- Celery Beat `accounts.anonymize_due_accounts`: после окна удаляет
  профиль/email/историю/legal/tokens, резервирует nickname HMAC,
  деактивирует `User` и заменяет login на `deleted-*`.

### Анонимная идентичность

- Сервис `get_or_create_anonymous_identity`: подписанная `django.signing`
  cookie `ba_anon` (`v1:<uuid>:<issued_at>`), host-only, HttpOnly,
  Secure вне DEBUG, SameSite=Lax; серверный `AnonymousIdentity` с
  `token_hash` и 90-дневным скользящим expiry.
- Сервис покрыт тестом; в реальный первый subject-запрос не подключён,
  поскольку таких маршрутов в текущем каркасе нет (App F отсутствует).

## 3. Файлы

- `apps/accounts/models/{profile,email,nickname,anonymous,recovery,legal,user}.py`
- `apps/accounts/services/{registration,profile,email,tokens,nickname,anonymous,rate_limit,hibp}.py`
- `apps/accounts/forms.py`, `views.py`, `urls.py`, `account_urls.py`, `tasks.py`
- `apps/accounts/templates/accounts/*`, `templates/partials/header.html`
- `apps/accounts/migrations/0002_*.py`
- `config/settings/base.py`, `config/settings/prod.py`, `config/urls.py`
- `tests/integration/test_accounts.py`, `tests/unit/test_account_services.py`
- `tests/integration/test_portal_shell.py` (auth links)

## 4. Фактические проверки

Выполнены в dev-контейнере:

```text
python -m pytest
167 passed, 1 skipped in 24.62s

python -m ruff check apps config tests
All checks passed!

python -m ruff format --check apps config tests
323 files already formatted

python -m mypy
Success: no issues found in 310 source files

python manage.py check
System check identified no issues (0 silenced).

python manage.py makemigrations --check --dry-run
No changes detected

python manage.py migrate --plan
No planned migration operations.

python manage.py showmigrations accounts
[X] 0001_initial
[X] 0002_nicknamereservation_anonymousidentity_emailaddress_and_more
```

HTTP (host → `https://portal.test:8443`):

```text
/en/auth/login/            200
/en/auth/register/         200
/en/auth/password-reset/   200
/en/account/               302 (login required)
/en/account/export/        302 (login required)
```

Account tests: 17 integration + 4 service. Покрыты happy path, optional
email, legal acceptance, confusable nickname, login/logout, verified/
unverified reset, stale reset token, nickname interval, password change and
session invalidation, missing consent/mismatch, invalid tokens, CSRF, email
change re-auth, export, deletion request/cancel, anonymous cookie reuse,
anonymization and due task, rate-limit service.

## 5. Security-проверки

- CSRF включён; POST-действия защищены; register CSRF-тест.
- Пароли: Argon2id, validators, HIBP hook; в production HIBP включён по
  умолчанию (`fails closed` при недоступности).
- Токены: случайные, в БД только SHA-256; one-time; TTL; reset-токены
  инвалидируются при новом запросе и после смены пароля.
- Password reset нейтрален и не раскрывает существование аккаунта.
- Login rate limit по аккаунту и IP; успешный вход сбрасывает только
  счётчик аккаунта, не общий IP-счётчик.
- Session invalidation после смены/reset пароля.
- Email change требует текущий пароль и уведомляет старый verified адрес.
- Safe `next` через `url_has_allowed_host_and_scheme`.
- Секреты не выводились; `.env` не читался и не изменялся.

## 6. Соответствие §2.10 и блокеры

| Требование | Состояние |
|---|---|
| 2.10.1 cookie/подпись/expiry/подмена | Сервис и тест есть; subject-маршрут отсутствует; `SecurityEvent` для подмены не реализован (App F/DB design) |
| 2.10.2 login/nickname/password/email | Реализовано; HIBP выключен в dev, включён в prod |
| 2.10.2 версии Terms/Privacy | `UserLegalAcceptance` пишется, но тексты и утверждённые версии отсутствуют; используется `draft` |
| 2.10.3 email 24 ч, reset 30 мин, neutral, rate limit | Реализовано |
| 2.10.3 bounce/недоставляемый адрес | Поле `bounce_at` есть; provider/webhook/сброс подтверждения не реализованы |
| 2.10.4 nickname/email/password/language/theme/export/deletion | Реализовано |
| 2.10.4 история игр, личные рекорды и места | Не реализовано: модели gameplay/leaderboards отсутствуют |
| 2.10.5 cleanup LeaderboardEntry/GameResult/GameRatingVote/GameStorage/UserGamePlaytime | Не реализовано: моделей нет; аккаунтные PII очищаются |
| 2.10.5 NicknameReservation 24 мес. | HMAC-резерв есть; срок 720 дней |
| 2FA персонала (этап 2) | Не реализовано; вынесено в BA-STAGE-2.2 |

## 7. Остаточные риски

- R-018: неполная приёмка §2.10 (legal, game data, bounce, subject wiring,
  2FA).
- R-019: rate limits fail-open при отказе Redis; registration limit только
  по IP.
- Юридические тексты и версии должны утвердить владелец/юрист; исполнитель
  их не сочиняет.
- `NICKNAME_HMAC_KEY` по умолчанию падает обратно на `SECRET_KEY`; для
  production нужен отдельный секрет.
- Локализация account-страниц: интерфейс в основном английский, часть
  form labels/сообщений — русская; это не приёмка §2.15/этапа 6.
- Browser E2E для §2.10 ещё не добавлен.

## 8. Следующий шаг

`BA-STAGE-2.2` выполнен как **PARTIAL** (TOTP + recovery + enrollment;
см. отдельный отчёт). Следующий — `BA-STAGE-2.3`: browser E2E сценариев
§2.10/2FA. Legal texts/provider и игровые модели остаются зависимостями
владельца/App F; без них BA-STAGE-2.1 остаётся **PARTIAL**.

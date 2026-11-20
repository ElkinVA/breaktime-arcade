# BA-STAGE-2.3 — browser E2E аккаунтов

**Дата:** 2026-11-19  
**Статус:** **IMPLEMENTED / AWAITING INDEPENDENT REVIEW**. Это self-check
исполнителя на dev-стеке, не независимый аудит и не приёмка §2.10/2FA.

## 1. Результат

Добавлен `tests/e2e/test_accounts_e2e.py`:

1. Уникальная регистрация → профиль с nickname/email/«not verified» →
   JSON export → logout → login.
2. Смена пароля → logout → login с новым паролем.
3. Deletion request с паролем и `DELETE` → статус «Deletion requested» →
   отмена → статус исчезает.
4. Отдельный сценарий: форма регистрации без consent не отправляется.

## 2. Фактический прогон

```text
BA_E2E=1 BA_E2E_BASE_URL=https://portal.test:8443 \
  .venv/bin/pytest tests/e2e/test_accounts_e2e.py -m e2e -q
2 passed

BA_E2E=1 BA_E2E_BASE_URL=https://portal.test:8443 \
  .venv/bin/pytest tests/e2e -m e2e -q
13 passed
```

Обычный suite: 173 passed, 1 skipped (E2E по умолчанию skip).

## 3. Ограничения

- E2E создаёт уникального пользователя в dev-БД и не удаляет его
  автоматически; это dev-данные, cleanup не выдаётся за бизнес-операцию.
- Registration rate limit 3/day по IP может потребовать очистки dev-cache
  между повторными прогонами; в прогоне использовалась очистка конкретного
  cache-ключа, не БД.
- CI browser E2E не запускает; нужен живой dev-стек, Playwright и TLS
  ignore.
- Staff 2FA E2E не добавлен: требует заранее созданного staff-пользователя;
  TOTP-сценарии покрыты integration-тестами BA-STAGE-2.2.
- Legal texts, game history/records, bounce/provider, owner recovery,
  журнал/SecurityEvent и роли/CRM step-up остаются открытыми.

## 4. Следующий шаг

`BA-STAGE-2.4`: 2FA completion — owner offline recovery, журнал входов,
regeneration recovery-кодов. Это не отменяет **PARTIAL** статусов 2.1/2.2.

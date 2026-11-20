# Тестирование и проверки

Нормативная основа: BA-PLAT-4.2 §2.26. Тесты запускаются только против
PostgreSQL; SQLite для тестов запрещён.

## 1. Базовый пакет

```bash
make test
make lint
make types
make check
```

`make check` последовательно запускает lint, mypy и pytest. Команды должны
выполняться внутри контейнера `web` через Makefile.

## 2. Миграции

```bash
docker compose -f compose.yml -f compose.dev-lite.yml exec -T web \
  python manage.py makemigrations --check --dry-run
docker compose -f compose.yml -f compose.dev-lite.yml exec -T web \
  python manage.py showmigrations --plan
docker compose -f compose.yml -f compose.dev-lite.yml exec -T web \
  python manage.py migrate --plan
```

Для текущего фундамента ожидается отсутствие незапланированных миграций;
применённые миграции нельзя редактировать или сбрасывать.

## 3. Схемы и контракты

```bash
docker compose -f compose.yml -f compose.dev-lite.yml exec -T web \
  python -m pytest tests/unit/test_contract_schemas.py \
  tests/unit/test_foundation_002_contracts.py
```

Проверяются JSON Schema 2020-12 для `manifest`, `catalog`, `eventLog`,
все draft-схемы сообщений App F, семантические правила (defaultLanguage,
critical locale, screenshotAlts, eventLog monotonic/eventKinds/лимиты) и
DRAFT-маркеры контрактов. Полный BA-SDK-1.1 отсутствует; схемы сообщений —
draft, а не утверждённый контракт.

## 4. Инфраструктура

```bash
./verify_stack.sh
```

Проверка ожидает healthy web/db/redis-cache/redis-broker, HTTPS
`portal.test:8443`, `/en/`, CRM redirect и статику. Staging проверяется
отдельно и только read-only.

## 5. E2E

Маркер `e2e` зарезервирован для Playwright; на этапе фундамента E2E-набор
не реализован. Не выдавать отсутствие E2E за успешное покрытие.

## 6. Ограничения доказательной базы

- Успешный pytest не равен приёмке этапа.
- Тесты D-006 не доказывают rollback/nested atomic/многопоточность/ошибки
  Redis; это R-004/R-005.
- Проверка restore-check требует отдельной БД `ba_restore_check` и не должна
  выполняться на staging/production без разрешения.

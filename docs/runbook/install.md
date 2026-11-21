# Установка dev-окружения

Нормативная основа: BA-PLAT-4.2 §2.3, §2.5. Все команды выполняются из
корня репозитория; команды приложения — через `Makefile` внутри `web`.

## 1. Требования

- Linux/WSL2.
- Docker Engine 29.10.0 и Docker Compose 5.8.0 (проверено в текущем dev;
  совместимые более новые версии допустимы).
- Python и Node на хосте не используются для запуска приложения; Python 3.14
  находится в контейнере. Node 22 — только сборка assets.
- Свободный порт 8443; порт 80 занят системным nginx и не используется.

## 2. Первичная настройка

```bash
cp .env.example .env   # только если .env ещё нет; не перезаписывать существующий
make env               # сгенерировать dev-окружение
make certs             # mkcert-сертификаты portal.test и games.test
make assets            # Tailwind/статика
make up                # web, db, redis-cache, redis-broker, worker, nginx
./verify_stack.sh
```

`make env` не должен перезаписывать существующие секреты. Значения `.env`,
`certs/` и `creds/` не коммитить и не выводить в логи.

## 3. Проверка

```bash
make ps
curl -k https://portal.test:8443/healthz
curl -k https://portal.test:8443/readyz
curl -k -o /dev/null -w '%{http_code}\n' https://portal.test:8443/en/
```

Ожидается: `healthz` и `/en/` — 200; `readyz` — 200 при здоровых БД, Redis,
broker, i18n и backup. `portal.test` и `*.games.test` должны разрешаться в
127.0.0.1.

## 4. Остановка

```bash
make down
```

`make down` не удаляет volumes. Не выполнять `docker compose down -v` и не
удалять БД/бэкапы без отдельного разрешения владельца.

## 5. Ограничения

- Staging запускается отдельно (`make staging-up`) и требует отдельных
  секретов/разрешения; в фундаментной задаче staging не затрагивается.
- Production-конфигурация (`compose.prod.yml`, production Nginx) пока не
  заполнена; этот runbook не является production-инструкцией.

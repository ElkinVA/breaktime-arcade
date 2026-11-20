# Инцидент: первичная диагностика dev

Нормативная основа: BA-PLAT-4.2 §2.5, §2.24. Runbook относится к dev-lite и
не заменяет production-регламент.

## 1. Проверить состояние

```bash
make ps
make logs
curl -k -sS -o /dev/null -w '%{http_code}\n' https://portal.test:8443/healthz
curl -k -sS https://portal.test:8443/readyz
```

`/readyz` показывает checks `db`, `cache`, `broker`, `i18n`, `backup`.
`503` при `i18n: fail` означает отсутствие обязательного `en` или ошибку
получения активных языков; не отключать проверку и не подменять язык.

## 2. Сервисы

```bash
make ps
docker compose -f compose.yml -f compose.dev-lite.yml logs --tail=200 web worker nginx
docker compose -f compose.yml -f compose.dev-lite.yml logs --tail=200 db redis-cache redis-broker
```

Не выводить `.env`, пароли, токены и private keys. Логи приложения — JSON с
request-id; request-id можно сопоставить с ответом `X-Request-ID`.

## 3. Безопасные действия

```bash
make restart   # web/worker
make up        # поднять отсутствующие сервисы
```

Не выполнять `docker compose down -v`, `flush`, удаление volumes/БД/бэкапов
или миграции без бэкапа и отдельного разрешения. Staging/production не
затрагивать.

## 4. Эскалация

Если `readyz` стабильно 503 по `db`, `cache` или `broker`, либо healthcheck
nginx не проходит после безопасного restart — остановиться, сохранить вывод
`make ps`, `make logs`, `readyz` и передать владельцу. Не маскировать
инфраструктурную ошибку под 406 или успешный ответ.

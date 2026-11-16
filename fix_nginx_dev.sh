#!/usr/bin/env bash
# fix_nginx_dev.sh — исправление nginx в dev-lite.
# Идемпотентен. Правит строку "location ~ ...vhash..." и убирает дубль wasm.
set -euo pipefail
cd "$(dirname "$0")"

COMPOSE=(docker compose -f compose.yml -f compose.dev-lite.yml)
CONF="infra/nginx/dev.conf"

echo "============================================================"
echo "  Исправление nginx (dev-lite)"
echo "============================================================"

if [ ! -f "$CONF" ]; then
    echo "FAIL: $CONF не найден" >&2
    exit 1
fi

# ---------------------------------------------------------- 1. Патч conf
echo
echo "==> [1] Патч $CONF"

python3 - "$CONF" <<'PY'
import re, sys, pathlib, shutil, datetime

path = pathlib.Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
original = text
changes = []

# --- A. Строка "location ~ ...vhash... {" -> корректная форма с кавычками.
# Паттерн находит ЛЮБУЮ линию с location ~ ...vhash... { в любом состоянии:
#   - без кавычек:  location ~ ^/v/(?<vhash>[0-9a-f]{12,16})/(?<vpath>.+)$ {
#   - битую:        location ~ "^/v/(?<vhash>[0-9a-f]"{12,16})/(?<vpath>.+)$ {
#   - правильную:   location ~ "^/v/(?<vhash>[0-9a-f]{12,16})/(?<vpath>.+)$" {
# Стратегия: захватываем начало строки (indent + "location ~") и КОНЕЦ строки,
# а всё между ними, содержащее vhash, переписываем целиком.
pat_line = re.compile(
    r'^([ \t]*)location\s+~\s+.*?vhash.*\{\s*$',
    re.MULTILINE,
)

replacement = r'\1location ~ "^/v/(?<vhash>[0-9a-f]{12,16})/(?<vpath>.+)$" {'

new_text, n = pat_line.subn(replacement, text)
if n:
    text = new_text
    changes.append(f"строка location ~ /v/... приведена к корректной форме ({n} шт.)")

# --- B. Удалить дублирующий application/wasm из inline types (уже есть в mime.types).
dup_patterns = [
    'types { text/javascript mjs; application/wasm wasm; }',
    'types { text/javascript mjs; application/wasm wasm; }\n',
]
for p in dup_patterns:
    if p in text:
        text = text.replace(p, 'types { text/javascript mjs; }')
        changes.append("убран дубль application/wasm из types {}")
        break

# --- Сохранение с бэкапом
if text != original:
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = path.with_suffix(f"{path.suffix}.bak.{stamp}")
    shutil.copy2(path, backup)
    path.write_text(text, encoding="utf-8")
    for c in changes:
        print(f"  OK:   {c}")
    print(f"  BACKUP: {backup}")
else:
    print("  SKIP: файл уже в корректном состоянии")
PY

# ---------------------------------------------------------- 2. Верификация
echo
echo "==> [2] Верификация строки vhash"

if grep -qE '^[[:space:]]*location ~ "\^/v/\(\?<vhash>\[0-9a-f\]\{12,16\}\)/\(\?<vpath>\.\+\)\$" \{' "$CONF"; then
    echo "  OK:   строка location ~ ...vhash... в корректной форме"
else
    echo "  FAIL: строка не приведена к корректной форме, содержимое:" >&2
    grep -n 'vhash' "$CONF" | head -3 >&2 || echo "  (vhash не найден!)" >&2
    exit 1
fi

if grep -q 'application/wasm wasm' "$CONF"; then
    echo "  WARN: дубль wasm ещё есть (не критично)"
else
    echo "  OK:   дубль wasm отсутствует"
fi

# ---------------------------------------------------------- 3. Сертификаты
echo
echo "==> [3] Сертификаты"
for n in portal.test games.test; do
    if [ -f "certs/${n}.pem" ] && [ -f "certs/${n}-key.pem" ]; then
        echo "  OK:   certs/${n}.pem"
    else
        echo "  FAIL: certs/${n}.pem отсутствует" >&2
        exit 1
    fi
done

# ---------------------------------------------------------- 4. var/runtime
echo
echo "==> [4] var/runtime"
mkdir -p var/runtime
echo "  ok"

# ---------------------------------------------------------- 5. nginx -t
echo
echo "==> [5] Синтаксис nginx -t"
set +e
"${COMPOSE[@]}" run --rm --no-deps --entrypoint nginx nginx -t 2>&1 | grep -vE '^\s*$'
RC=${PIPESTATUS[0]}
set -e
if [ "$RC" -ne 0 ]; then
    echo "  FAIL: синтаксис всё ещё невалиден (см. вывод выше)" >&2
    echo "  Содержимое строки с vhash:" >&2
    grep -n 'vhash' "$CONF" >&2 || true
    exit 1
fi
echo "  OK:   синтаксис валиден"

# ---------------------------------------------------------- 6. Рестарт
echo
echo "==> [6] Перезапуск nginx"
"${COMPOSE[@]}" up -d --force-recreate nginx

echo
echo "==> [7] Ожидание 10 с"
sleep 10

# ---------------------------------------------------------- 8. Статус
echo
echo "==> [8] Статус nginx"
"${COMPOSE[@]}" ps nginx

# ---------------------------------------------------------- 9. Проверки
echo
echo "==> [9] Проверки HTTPS"
H="$(curl -sk --max-time 5 https://portal.test:8443/healthz 2>/dev/null || true)"
EN="$(curl -sk --max-time 5 -o /dev/null -w '%{http_code}' https://portal.test:8443/en/ 2>/dev/null || echo 000)"
CRM="$(curl -sk --max-time 5 -o /dev/null -w '%{http_code}' https://portal.test:8443/crm/ 2>/dev/null || echo 000)"
STAT="$(curl -sk --max-time 5 -o /dev/null -w '%{http_code}' https://portal.test:8443/static/dist/app.css 2>/dev/null || echo 000)"
GAME="$(curl -sk --max-time 5 -o /dev/null -w '%{http_code}' https://demo.games.test:8443/ 2>/dev/null || echo 000)"

echo "  /healthz  -> ${H:-(нет ответа)}"
echo "  /en/      -> $EN"
echo "  /crm/     -> $CRM (302 ожидаемо: редирект на /crm/login/)"
echo "  /static/  -> $STAT"
echo "  games.host demo.games.test -> $GAME (404 ожидаемо: пустой runtime)"

# ---------------------------------------------------------- 10. Логи
echo
echo "==> [10] Логи nginx (последние 15 строк)"
"${COMPOSE[@]}" logs --tail=15 nginx 2>&1 | grep -vE '^\s*$' || true

echo
echo "============================================================"
if [ "$EN" = "200" ] || [ "$EN" = "302" ]; then
    echo "  УСПЕХ"
    echo "============================================================"
    exit 0
fi
echo "  ПРОБЛЕМА: nginx не отвечает на /en/ — смотрите логи выше"
echo "============================================================"
exit 1

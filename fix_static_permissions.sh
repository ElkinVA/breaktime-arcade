#!/usr/bin/env bash
# fix_static_permissions.sh — даёт nginx (UID 101) читать статику,
# устраняет root cause 403 на /static/. Идемпотентен.
set -euo pipefail
cd "$(dirname "$0")"

COMPOSE=(docker compose -f compose.yml -f compose.dev-lite.yml)

echo "============================================================"
echo "  Исправление прав на /static/ (nginx 403)"
echo "============================================================"

# ---------------------------------------------------------- 1. Dockerfile
echo
echo "==> [1] Патч Dockerfile (для будущих пересборок образа)"
if grep -q 'chmod -R a+rX /app/staticfiles' Dockerfile; then
  echo "  SKIP: chmod уже есть в Dockerfile"
else
  python3 - <<'PY'
import pathlib
p = pathlib.Path("Dockerfile")
text = p.read_text(encoding="utf-8")
if "chmod -R a+rX /app/staticfiles" in text:
    print("  SKIP: уже есть")
else:
    lines = text.split("\n")
    patched = False
    for i, line in enumerate(lines):
        if "chown -R app:app /app/staticfiles" in line:
            stripped = line.rstrip()
            if stripped.endswith("\\"):
                lines.insert(i + 1, " && chmod -R a+rX /app/staticfiles /app/media")
            else:
                lines[i] = stripped + " \\"
                lines.insert(i + 1, " && chmod -R a+rX /app/staticfiles /app/media")
            patched = True
            break
    if patched:
        p.write_text("\n".join(lines), encoding="utf-8")
        print("  OK: chmod -R a+rX добавлен в Dockerfile")
    else:
        print("  WARN: не нашёл строку 'chown -R app:app /app/staticfiles' — правьте вручную")
PY
fi

# ---------------------------------------------------- 2. entrypoint.sh
echo
echo "==> [2] Патч infra/scripts/entrypoint.sh (для текущих перезапусков)"
EP="infra/scripts/entrypoint.sh"
if grep -q 'chmod -R u+rwX,g+rX,o+rX /app/staticfiles' "$EP" 2>/dev/null; then
  echo "  SKIP: chmod уже есть в entrypoint.sh"
else
  python3 - "$EP" <<'PY'
import sys, pathlib
p = pathlib.Path(sys.argv[1])
text = p.read_text(encoding="utf-8")
old = '''if [[ "${RUN_COLLECTSTATIC:-0}" == "1" ]]; then
  python manage.py collectstatic --noinput
fi'''
new = '''if [[ "${RUN_COLLECTSTATIC:-0}" == "1" ]]; then
  python manage.py collectstatic --noinput
  chmod -R u+rwX,g+rX,o+rX /app/staticfiles /app/media 2>/dev/null || true
fi'''
if old in text:
    text = text.replace(old, new)
    p.write_text(text, encoding="utf-8")
    print("  OK: entrypoint.sh патчен")
elif "chmod -R u+rwX,g+rX,o+rX /app/staticfiles" in text:
    print("  SKIP: уже есть")
else:
    print("  WARN: блок collectstatic не найден в entrypoint.sh")
PY
fi

# ---------------------------------------------- 3. Права на живых томах
echo
echo "==> [3] Права на томах static_data и media_data"
docker run --rm \
  -v breaktime-arcade_static_data:/app/staticfiles \
  -v breaktime-arcade_media_data:/app/media \
  --user root \
  --entrypoint sh \
  ba/app:dev \
  -c '
    set -e
    for d in /app/staticfiles /app/media; do
      if [ -d "$d" ]; then
        find "$d" -type f -exec chmod 644 {} +
        find "$d" -type d -exec chmod 755 {} +
        echo "  OK:   $d (f=644, d=755)"
      else
        echo "  SKIP: $d (отсутствует)"
      fi
    done
  '

# ---------------------------------------------------------- 4. Рестарт
echo
echo "==> [4] Перезапуск web (для активации патча entrypoint) и nginx"
"${COMPOSE[@]}" restart web nginx >/dev/null
echo "  подождите 8 с..."
sleep 8

# ---------------------------------------------------------- 5. Проверки
echo
echo "==> [5] Проверки"
H="$(curl -sk --max-time 5 https://portal.test:8443/healthz || true)"
CSS="$(curl -sk --max-time 5 -o /dev/null -w '%{http_code}' https://portal.test:8443/static/dist/app.css || echo 000)"
JSON="$(curl -sk --max-time 5 -o /dev/null -w '%{http_code}' https://portal.test:8443/static/staticfiles.json || echo 000)"
EN="$(curl -sk --max-time 5 -o /dev/null -w '%{http_code}' https://portal.test:8443/en/ || echo 000)"
CRM="$(curl -sk --max-time 5 -o /dev/null -w '%{http_code}' https://portal.test:8443/crm/ || echo 000)"

echo "  /healthz                -> ${H:-(нет ответа)}"
echo "  /en/                    -> $EN"
echo "  /crm/                   -> $CRM (302 ожидаемо)"
echo "  /static/dist/app.css    -> $CSS"
echo "  /static/staticfiles.json -> $JSON"

echo
echo "==> [6] Логи nginx (последние 8 строк)"
"${COMPOSE[@]}" logs --tail=8 nginx 2>&1 | grep -vE '^\s*$' || true

echo
echo "============================================================"
if [ "$CSS" = "200" ] && [ "$JSON" = "200" ]; then
    echo "  УСПЕХ: статика раздаётся"
    echo "============================================================"
    exit 0
fi
echo "  ПРОБЛЕМА: /static/ всё ещё не 200"
echo "============================================================"
exit 1

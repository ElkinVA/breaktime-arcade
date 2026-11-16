#!/usr/bin/env bash
set -euo pipefail
cd /app

wait_for() {
  local host="$1" port="$2" i
  for i in $(seq 1 60); do
    if python -c "import socket,sys; s=socket.socket(); s.settimeout(2); sys.exit(0 if s.connect_ex(('$host',$port))==0 else 1)"; then
      printf 'готов: %s:%s\n' "$host" "$port"
      return 0
    fi
    sleep 2
  done
  printf 'не дождались %s:%s\n' "$host" "$port" >&2
  return 1
}

wait_for db 5432
wait_for redis-cache 6379
wait_for redis-broker 6379

if [[ "${RUN_MIGRATIONS:-0}" == "1" ]]; then
  python manage.py migrate --noinput
fi
if [[ "${RUN_COLLECTSTATIC:-0}" == "1" ]]; then
  python manage.py collectstatic --noinput
  chmod -R u+rwX,g+rX,o+rX /app/staticfiles /app/media 2>/dev/null || true
fi

exec "$@"

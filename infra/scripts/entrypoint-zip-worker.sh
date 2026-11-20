#!/usr/bin/env bash
# BA-ZIP-WORKER-001: isolated extraction worker entrypoint.
#
# The worker is attached only to the `zipnet` internal network. It must NOT
# wait for db or redis-cache: those services are intentionally unreachable.
# Migrations and collectstatic are never run here.
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

wait_for redis-broker 6379

exec "$@"

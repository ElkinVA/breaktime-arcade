#!/usr/bin/env bash
# Локальные TLS-сертификаты для portal.test и *.games.test (§2.4).
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
command -v mkcert >/dev/null || {
  printf 'mkcert не установлен. Ubuntu/WSL: sudo apt install libnss3-tools; ' >&2
  printf 'затем установите mkcert и выполните mkcert -install\n' >&2
  exit 1
}
mkdir -p certs
mkcert -install
mkcert -cert-file certs/portal.test.pem -key-file certs/portal.test-key.pem portal.test
mkcert -cert-file certs/games.test.pem -key-file certs/games.test-key.pem '*.games.test' games.test
chmod 644 certs/*.pem
printf 'Сертификаты готовы: certs/\n'

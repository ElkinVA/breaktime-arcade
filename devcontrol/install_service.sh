#!/usr/bin/env bash
# Install BA Dev Control as a systemd *user* service.
# Run as the owner (not root). The bot token is not stored in the unit.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
mkdir -p "$UNIT_DIR"
install -m 0644 "$ROOT/devcontrol/systemd/ba-devcontrol.service" "$UNIT_DIR/ba-devcontrol.service"

AI_ENV="${XDG_CONFIG_HOME:-$HOME/.config}/ba/deepseek.env"
if [[ ! -f "$AI_ENV" ]]; then
  echo "warning: $AI_ENV not found; the bot may lack ANTHROPIC_* environment for Claude." >&2
fi

if [[ -d "$ROOT/.git/hooks" ]]; then
  install -m 0755 "$ROOT/devcontrol/githooks/pre-push" "$ROOT/.git/hooks/pre-push"
  echo "Installed pre-push secret-scan hook."
fi

systemctl --user daemon-reload
systemctl --user enable --now ba-devcontrol.service
systemctl --user --no-pager status ba-devcontrol.service || true

cat <<'EOF'

Installed. Useful commands:
  systemctl --user status ba-devcontrol
  systemctl --user restart ba-devcontrol
  journalctl --user -u ba-devcontrol -f

For start-at-boot in WSL, enable linger for your user (may require sudo):
  sudo loginctl enable-linger "$USER"
EOF

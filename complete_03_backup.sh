#!/usr/bin/env bash
# complete_03_backup.sh — этап 3.1: полное исправление (патчи + сборка + миграция + проверка).
# Идемпотентен: повторный запуск безопасен.
set -euo pipefail
cd "$(dirname "$0")"

COMPOSE=(docker compose -f compose.yml -f compose.dev-lite.yml)
AS_USER="$(id -u):$(id -g)"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR=".backups/$STAMP"
mkdir -p "$BACKUP_DIR"

backup_file() {
    local rel="$1"
    [ -f "$rel" ] || return 0
    mkdir -p "$BACKUP_DIR/$(dirname -- "$rel")"
    cp -p "$rel" "$BACKUP_DIR/$rel"
}

echo "============================================================"
echo "  Этап 3.1 — фикс + установка + проверка"
echo "============================================================"

# =========================================== 1. Патч Dockerfile
echo
echo "==> [1] Dockerfile (postgresql-client-18)"
backup_file Dockerfile
python3 - <<'PY'
import pathlib
p = pathlib.Path("Dockerfile")
text = p.read_text(encoding="utf-8")
if "postgresql-client-18" in text:
    print("  SKIP: postgresql-client-18 уже есть")
else:
    marker = "RUN apt-get update \\\n && apt-get install -y --no-install-recommends curl ca-certificates"
    new_run = (
        "# PostgreSQL 18 client (pg_dump/pg_restore) для бэкапов (§2.5)\n"
        "RUN apt-get update \\\n"
        " && apt-get install -y --no-install-recommends curl ca-certificates gnupg \\\n"
        " && install -d /usr/share/postgresql-common/pgdg \\\n"
        " && curl -fsS -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc https://www.postgresql.org/media/keys/ACCC4CF8.asc \\\n"
        " && . /etc/os-release \\\n"
        " && echo \"deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt ${VERSION_CODENAME}-pgdg main\" > /etc/apt/sources.list.d/pgdg.list \\\n"
        " && apt-get update \\\n"
        " && apt-get install -y --no-install-recommends postgresql-client-18 \\\n"
        " && rm -rf /var/lib/apt/lists/*\n\n"
    )
    if marker in text:
        text = text.replace(marker, new_run + marker, 1)
        p.write_text(text, encoding="utf-8")
        print("  OK:   postgresql-client-18 добавлен")
    else:
        print("  WARN: marker не найден — правьте вручную")
PY

# =========================================== 2. Патч compose.yml
echo
echo "==> [2] compose.yml (сервисы backup и restore-check)"
backup_file compose.yml
if grep -q '^  backup:' compose.yml; then
    echo "  SKIP: сервисы уже есть"
else
    python3 - <<'PY'
import pathlib
p = pathlib.Path("compose.yml")
text = p.read_text(encoding="utf-8")
anchor = "\nnetworks:\n"
insert = (
    "  backup:\n"
    "    <<: *app\n"
    "    command: [\"python\", \"manage.py\", \"backup_run\"]\n"
    "    environment:\n"
    "      RUN_MIGRATIONS: \"0\"\n"
    "    profiles: [\"backup\"]\n"
    "\n"
    "  restore-check:\n"
    "    <<: *app\n"
    "    command: [\"python\", \"manage.py\", \"restore_check\"]\n"
    "    environment:\n"
    "      RUN_MIGRATIONS: \"0\"\n"
    "    profiles: [\"restore-check\"]\n"
    "\n"
)
if "  backup:" not in text and anchor in text:
    text = text.replace(anchor, "\n" + insert + "networks:\n", 1)
    p.write_text(text, encoding="utf-8")
    print("  OK:   сервисы backup и restore-check добавлены")
else:
    print("  WARN: точка вставки не найдена")
PY
fi

# =========================================== 3. Патч settings/base.py
echo
echo "==> [3] config/settings/base.py (BACKUP_DIR, Celery beat)"
backup_file config/settings/base.py
python3 - <<'PY'
import pathlib
p = pathlib.Path("config/settings/base.py")
text = p.read_text(encoding="utf-8")
changed = False
if "BA_BACKUP_CHECK_ENABLED" not in text:
    anchor = 'ADMIN_URL_PREFIX = env("ADMIN_URL_PREFIX", "crm/")'
    insert = (
        'ADMIN_URL_PREFIX = env("ADMIN_URL_PREFIX", "crm/")\n'
        '\n'
        '# --- Резервное копирование (§2.5) --------------------------------------\n'
        'BACKUP_DIR = env("BACKUP_DIR", "/app/var/backups")\n'
        'BACKUP_RETENTION_DAYS = env_int("BACKUP_RETENTION_DAYS", 30)\n'
        'BA_BACKUP_CHECK_ENABLED = env_bool("BA_BACKUP_CHECK_ENABLED", True)\n'
        'BA_BACKUP_STALE_HOURS = env_int("BA_BACKUP_STALE_HOURS", 48)\n'
    )
    if anchor in text:
        text = text.replace(anchor, insert, 1)
        changed = True

old_beat = 'CELERY_BEAT_SCHEDULE: dict[str, dict[str, object]] = {}'
new_beat = (
    'CELERY_BEAT_SCHEDULE: dict[str, dict[str, object]] = {\n'
    '    "backup-full-daily": {\n'
    '        "task": "crm.backup_full",\n'
    '        "schedule": 60 * 60 * 24,\n'
    '        "options": {"expires": 60 * 30},\n'
    '    },\n'
    '    "backup-status-hourly": {\n'
    '        "task": "crm.backup_status_alert",\n'
    '        "schedule": 60 * 60,\n'
    '        "options": {"expires": 60 * 10},\n'
    '    },\n'
    '    "restore-check-monthly": {\n'
    '        "task": "crm.restore_check",\n'
    '        "schedule": 60 * 60 * 24 * 30,\n'
    '        "options": {"expires": 60 * 60},\n'
    '    },\n'
    '}'
)
if old_beat in text:
    text = text.replace(old_beat, new_beat, 1)
    changed = True

if changed:
    p.write_text(text, encoding="utf-8")
    print("  OK:   settings обновлены")
else:
    print("  SKIP: settings уже пропатчены")
PY

# =========================================== 4. Патч health.py
echo
echo "==> [4] apps/core/health.py (readyz + backup)"
backup_file apps/core/health.py
python3 - <<'PY'
import pathlib
p = pathlib.Path("apps/core/health.py")
text = p.read_text(encoding="utf-8")
if "BA_BACKUP_CHECK_ENABLED" in text:
    print("  SKIP: уже есть")
else:
    old = (
        '    try:\n'
        '        client = redis.from_url(settings.CELERY_BROKER_URL, socket_timeout=3)\n'
        '        checks["broker"] = "ok" if client.ping() else "fail"\n'
        '    except Exception:\n'
        '        checks["broker"] = "fail"\n'
    )
    new = old + (
        '\n'
        '    if getattr(settings, "BA_BACKUP_CHECK_ENABLED", False):\n'
        '        try:\n'
        '            from apps.crm.services.backup import latest_backup_age_hours\n'
        '            age = latest_backup_age_hours()\n'
        '            stale_hours = getattr(settings, "BA_BACKUP_STALE_HOURS", 48)\n'
        '            if age is None:\n'
        '                checks["backup"] = "missing"\n'
        '            elif age > stale_hours:\n'
        '                checks["backup"] = "stale"\n'
        '            else:\n'
        '                checks["backup"] = "ok"\n'
        '        except Exception:\n'
        '            checks["backup"] = "fail"\n'
    )
    if old in text:
        text = text.replace(old, new, 1)
        # missing не валит readyz: свежие бэкапы могут отсутствовать первые 24ч
        text = text.replace(
            'ready = all(value == "ok" for value in checks.values())',
            'ready = all(v in ("ok", "missing") for v in checks.values())',
            1,
        )
        p.write_text(text, encoding="utf-8")
        print("  OK:   health.py патчен (missing не валит readyz)")
    else:
        print("  WARN: не нашёл блок broker — правьте вручную")
PY

# =========================================== 5. .env и .env.example
echo
echo "==> [5] .env и .env.example (BACKUP_*)"
add_vars() {
    local f="$1"
    [ -f "$f" ] || return 0
    grep -q '^BACKUP_DIR=' "$f" && return 0
    cp -p "$f" "$BACKUP_DIR/$f" 2>/dev/null || true
    cat >> "$f" <<'EOT'

# --- Резервное копирование (§2.5) ---
BACKUP_DIR=/app/var/backups
BACKUP_RETENTION_DAYS=30
BA_BACKUP_CHECK_ENABLED=True
BA_BACKUP_STALE_HOURS=48
EOT
}
add_vars .env.example && echo "  OK:   .env.example"
add_vars .env         && echo "  OK:   .env"

# =========================================== 6. Makefile
echo
echo "==> [6] Makefile (backup, restore-check)"
backup_file Makefile
if grep -q '^backup:' Makefile; then
    echo "  SKIP: таргеты уже есть"
else
    python3 - <<'PY'
import pathlib
p = pathlib.Path("Makefile")
text = p.read_text(encoding="utf-8")
anchor = "\ndump:\n"
insert = (
    "backup:\n"
    "> $(COMPOSE) --profile backup run --rm backup\n"
    "\n"
    "restore-check:\n"
    "> $(COMPOSE) --profile restore-check run --rm restore-check\n"
    "\n"
)
if anchor in text and "backup:\n" not in text:
    text = text.replace(anchor, "\n" + insert + "dump:\n", 1)
    text = text.replace("help env certs", "help env certs backup restore-check", 1)
    p.write_text(text, encoding="utf-8")
    print("  OK:   Makefile патчен")
PY
fi

# =========================================== 7. Тесты
echo
echo "==> [7] tests/integration/test_core.py"
backup_file tests/integration/test_core.py
python3 - <<'PY'
import pathlib
p = pathlib.Path("tests/integration/test_core.py")
if not p.exists():
    print("  SKIP: файл отсутствует")
else:
    text = p.read_text(encoding="utf-8")
    if "BA_BACKUP_CHECK_ENABLED" in text:
        print("  SKIP: уже обновлён")
    else:
        old = (
            '@pytest.mark.django_db\n'
            'def test_readyz(anon_client: Client) -> None:\n'
            '    response = anon_client.get("/readyz")\n'
            '    assert response.status_code in {200, 503}\n'
            '    assert set(response.json()["checks"]) == {"db", "cache", "broker"}\n'
        )
        new = (
            '@pytest.mark.django_db\n'
            '@override_settings(BA_BACKUP_CHECK_ENABLED=False)\n'
            'def test_readyz(anon_client: Client) -> None:\n'
            '    response = anon_client.get("/readyz")\n'
            '    assert response.status_code in {200, 503}\n'
            '    assert set(response.json()["checks"]) == {"db", "cache", "broker"}\n'
        )
        if old in text:
            text = text.replace(old, new, 1)
            if "from django.test import override_settings" not in text:
                text = text.replace(
                    "from django.test import Client",
                    "from django.test import Client, override_settings",
                    1,
                )
            p.write_text(text, encoding="utf-8")
            print("  OK:   тест обновлён")
        else:
            print("  WARN: test_readyz не найден — правьте вручную")
PY

# =========================================== 8. Сборка образа
echo
echo "==> [8] Пересборка образа web (postgresql-client-18)"
"${COMPOSE[@]}" build web

# =========================================== 9. Старт web + миграция
echo
echo "==> [9] up web (RUN_MIGRATIONS=1 прогонит migrate)"
"${COMPOSE[@]}" up -d --force-recreate web
sleep 8

echo
echo "==> [10] makemigrations crm (--user $(id -u):$(id -g) для bind-mount)"
"${COMPOSE[@]}" exec -T --user "${AS_USER}" web python manage.py makemigrations crm

echo
echo "==> [11] migrate --noinput (внутри web, RUN_MIGRATIONS=1 уже прогнал)"
"${COMPOSE[@]}" exec -T web python manage.py migrate --noinput

# =========================================== 10. Бэкап и restore-check
echo
echo "==> [12] Полный бэкап"
"${COMPOSE[@]}" --profile backup run --rm backup

echo
echo "==> [13] Проверка восстановления"
"${COMPOSE[@]}" --profile restore-check run --rm restore-check

# =========================================== 11. Проверки
echo
echo "==> [14] Записи BackupRun"
"${COMPOSE[@]}" exec -T web python manage.py shell -c "
from apps.crm.models import BackupRun
for r in BackupRun.objects.order_by('-started_at')[:5]:
    sha = (r.sha256[:16] + '...') if r.sha256 else ''
    print(f'  {str(r.id)[:8]}  {r.type:14s}  {r.status:8s}  size={r.size_bytes or 0:>8}  {sha}')
"

echo
echo "==> [15] readyz"
set +e
curl -sk --max-time 5 https://portal.test:8443/readyz | python3 -m json.tool
set -e

echo
echo "============================================================"
echo "  Готово"
echo "  Бэкап: $BACKUP_DIR"
echo "============================================================"

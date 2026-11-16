#!/usr/bin/env bash
# =====================================================================
#  BA FIX ALL — все согласованные задачи одним прогоном.
#  1) packaging в образе -> worker/beat перестают падать
#  2) ротация Basic Auth staging + защита дампа от утечки creds
#  3) CLAUDE.md + docs/handoff
#  4) локальный коммит (без remote/push)
#  Запуск: bash ba_fix_all.sh     Логи/бэкапы: .backups/fixall-<stamp>/
# =====================================================================
set -uo pipefail
cd "$HOME/projects/ba" || { echo "FATAL: проект не найден"; exit 1; }
export PATH="$HOME/.local/bin:$PATH"
command -v docker >/dev/null || { echo "FATAL: docker недоступен"; exit 1; }
STAMP="$(date +%Y%m%d-%H%M%S)"
BK=".backups/fixall-$STAMP"
mkdir -p "$BK"; chmod 700 "$BK"
COMPOSE=(docker compose -f compose.yml -f compose.dev-lite.yml)
FAIL=0
step(){ printf '\n\033[1m==> %s\033[0m\n' "$*"; }
ok(){   printf '  OK   %s\n' "$*"; }
warn(){ printf '  WARN %s\n' "$*"; }
bad(){  printf '  FAIL %s\n' "$*"; FAIL=1; }
die(){  printf '\nFATAL: %s\nБэкапы: %s\n' "$*" "$BK"; exit 1; }
bck(){ [ -f "$1" ] && { mkdir -p "$BK/$(dirname "$1")"; cp -p "$1" "$BK/$1"; }; return 0; }

step "0. Baseline"
docker inspect --format '{{.Name}} health={{.State.Health.Status}} restarts={{.RestartCount}}' \
  breaktime-arcade-worker-1 breaktime-arcade-beat-1 2>/dev/null || warn "worker/beat не найдены"
git rev-parse --is-inside-work-tree >/dev/null 2>&1 && ok "git: $(git log --oneline -1)" || die "нет git-репозитория"
grep -q 'name = "packaging"' uv.lock && ok "packaging есть в uv.lock" || warn "packaging нет в uv.lock"

step "1. Пересборка образа из текущего uv.lock (несколько минут)"
bck pyproject.toml; bck uv.lock
if "${COMPOSE[@]}" build web > "$BK/build1.log" 2>&1; then
  ok "образ собран (лог: $BK/build1.log)"
else
  tail -n 30 "$BK/build1.log"; die "сборка не удалась"
fi
IMG_OK=0
if docker run --rm --entrypoint python ba/app:dev -c "import packaging;print(packaging.__version__)" 2>/dev/null; then
  ok "packaging присутствует в новом образе — правка зависимостей НЕ потребовалась"
  IMG_OK=1
else
  warn "packaging отсутствует -> добавляю явную зависимость"
fi

if [ "$IMG_OK" = "0" ]; then
  python3 - <<'PY'
import pathlib
p = pathlib.Path("pyproject.toml"); t = p.read_text(encoding="utf-8")
if '"packaging' in t:
    print("  SKIP pyproject уже содержит packaging")
else:
    t = t.replace("dependencies = [\n", 'dependencies = [\n    "packaging>=24",\n', 1)
    p.write_text(t, encoding="utf-8"); print("  OK   packaging добавлен в [project].dependencies")
PY
  uv lock > "$BK/uvlock.log" 2>&1 && ok "uv lock обновлён" || { tail -n 20 "$BK/uvlock.log"; die "uv lock failed"; }
  "${COMPOSE[@]}" build web > "$BK/build2.log" 2>&1 && ok "образ пересобран" || { tail -n 30 "$BK/build2.log"; die "сборка 2 не удалась"; }
  docker run --rm --entrypoint python ba/app:dev -c "import packaging;print(packaging.__version__)" 2>/dev/null \
    && ok "packaging теперь в образе" || die "packaging всё ещё отсутствует — остановлено"
fi

step "2. Пересоздание ТОЛЬКО worker и beat (web не трогаем)"
"${COMPOSE[@]}" up -d --force-recreate worker beat > "$BK/recreate.log" 2>&1 \
  && ok "worker/beat пересозданы" || { tail -n 20 "$BK/recreate.log"; bad "пересоздание не удалось"; }
printf '  ожидание healthy (до 150s)...\n'
deadline=$(( $(date +%s) + 150 )); wh=none; bh=none
while [ "$(date +%s)" -lt "$deadline" ]; do
  wh="$(docker inspect --format '{{.State.Health.Status}}' breaktime-arcade-worker-1 2>/dev/null || echo none)"
  bh="$(docker inspect --format '{{.State.Health.Status}}' breaktime-arcade-beat-1 2>/dev/null || echo none)"
  [ "$wh" = "healthy" ] && [ "$bh" = "healthy" ] && break
  sleep 5
done
docker inspect --format '{{.Name}} health={{.State.Health.Status}} restarts={{.RestartCount}}' \
  breaktime-arcade-worker-1 breaktime-arcade-beat-1 2>/dev/null
[ "$wh" = "healthy" ] && ok "worker healthy" || bad "worker health=$wh"
[ "$bh" = "healthy" ] && ok "beat healthy"   || bad "beat health=$bh"
"${COMPOSE[@]}" exec -T worker celery -A config inspect ping -t 10 2>&1 | grep -q pong \
  && ok "celery ping -> pong" || bad "celery ping не ответил"
code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:8000/healthz || echo 000)"
[ "$code" = "200" ] && ok "регрессия web: /healthz 200" || bad "web /healthz=$code"

step "3. Ротация Basic Auth staging (пароль не выводится)"
if [ -f creds/staging_basic_auth.txt ]; then
  bck creds/staging_basic_auth.txt; bck certs/htpasswd
  U="$(awk -F: 'NR==1{print $1}' creds/staging_basic_auth.txt)"; U="${U:-staging}"
  P="$(openssl rand -base64 48 | tr -d '\n=+/' | cut -c1-24)"
  H="$(openssl passwd -apr1 "$P")"
  umask 077
  printf '%s:%s\n' "$U" "$P" > creds/staging_basic_auth.txt; chmod 600 creds/staging_basic_auth.txt
  printf '%s:%s\n' "$U" "$H" > certs/htpasswd; chmod 644 certs/htpasswd
  P=""; H=""
  ok "новый пароль: creds/staging_basic_auth.txt (600); htpasswd обновлён (644)"
  if docker ps --format '{{.Names}}' | grep -q '^ba-staging-nginx'; then
    docker compose -p ba-staging -f compose.yml -f compose.staging.yml --env-file .env.staging \
      up -d --force-recreate nginx > "$BK/staging-nginx.log" 2>&1 \
      && ok "staging nginx пересоздан" || bad "staging nginx: $BK/staging-nginx.log"
  else
    ok "staging не запущен — новый htpasswd применится при staging-up"
  fi
else
  warn "creds/staging_basic_auth.txt отсутствует — ротация пропущена"
fi

step "4. Защита дампа от утечки секретов"
bck collect_project.sh
python3 - <<'PY'
import pathlib, re
p = pathlib.Path("collect_project.sh"); t = p.read_text(encoding="utf-8"); orig = t
if re.search(r'EXCLUDE_DIRS=\([^)]*\bcreds\b', t, re.S):
    print("  SKIP creds уже исключён")
else:
    t = re.sub(r'(EXCLUDE_DIRS=\([^)]*?)\bcerts\b', r'\1certs creds', t, count=1, flags=re.S)
    print("  OK   creds добавлен в EXCLUDE_DIRS")
if "ba_audit_report.txt" not in t:
    t = re.sub(r'(EXCLUDE_NAMES=\(\n)(.*?)(\n\))',
               lambda m: m.group(1)+m.group(2)+"\naudit.txt ba_audit_report.txt"+m.group(3),
               t, count=1, flags=re.S)
    print("  OK   audit.txt / ba_audit_report.txt добавлены в EXCLUDE_NAMES")
if "diagnostics_*.txt" not in t:
    t = re.sub(r'(is_excluded_name\(\)\s*\{\n)',
               r'\1  if [[ "${1,,}" == diagnostics_*.txt ]]; then return 0; fi\n', t, count=1)
    print("  OK   diagnostics_*.txt исключены")
if t != orig: p.write_text(t, encoding="utf-8")
PY
bash -n collect_project.sh && ok "collect_project.sh: синтаксис OK" || bad "синтаксис collect_project.sh"
if [ ! -s scripts/collect_project.sh ]; then
  cp collect_project.sh scripts/collect_project.sh; chmod 755 scripts/collect_project.sh
  ok "scripts/collect_project.sh заполнен (make dump заработает)"
fi
bash collect_project.sh > "$BK/dump.log" 2>&1 && ok "дамп перегенерирован" || warn "дамп: $BK/dump.log"
grep -q 'creds/staging_basic_auth' project_dump.txt && bad "creds всё ещё в дампе" || ok "creds отсутствуют в новом дампе"

step "5. CLAUDE.md и docs/handoff"
mkdir -p docs/handoff
if [ ! -s docs/handoff/README.md ]; then
cat > docs/handoff/README.md <<'EOF'
# Handoff-пакет Breaktime Arcade
Положить сюда: BREAKTIME_ARCADE_HANDOFF_FULL.md.
Нормативное ТЗ BA-PLAT-4.2 (с BA-GAME-2.2) -> docs/spec/.
Приоритет источников: ТЗ > фактический код > handoff.
EOF
ok "docs/handoff/README.md создан"
fi
bck CLAUDE.md
cat > CLAUDE.md <<'EOF'
# CLAUDE.md — Breaktime Arcade

## Нормативная база (источник истины)
BA-PLAT-4.2 (ред. 12.11.2026) + BA-GAME-2.2, BA-SDK-1.1, BA-ENV-1.1.
Навигация: docs/handoff/. Полное ТЗ: docs/spec/.
При конфликте: ТЗ > фактический код > handoff. Не выдумывать требования,
endpoints, поля, версии и результаты проверок.

## Текущее состояние: КАРКАС, не MVP
Реализовано: core (uuid7/citext, middleware+CSP, JSON-логи, healthz/readyz,
storage), accounts.User + Argon2, catalog (модели+миграции), i18n (6 языков,
словари, тег ba_t), theme (токены->CSS), crm — только бэкапы/restore-check,
dev-lite и staging nginx.
ПУСТО/заглушки: gameplay, leaderboards, ratings, pipeline, moderation,
analytics, content; все schemas/*.json; sdk/1.1.0/ba-sdk.js; games-src/*;
compose.prod.yml; infra/nginx/prod.conf.j2; monitoring; docs/.
Views каталога и CRM — stub. Не считать их работающей функциональностью.

## Стек — менять запрещено без письменного согласования
Python 3.14, Django 5.2 LTS, DRF, PostgreSQL 18 (psycopg 3, НЕ psycopg2),
Redis cache(allkeys-lru)/broker(noeviction+AOF) раздельно, Celery 5.7 + Beat,
Nginx, Gunicorn, Docker Compose, Django Templates + HTMX 2 + Vanilla JS ES2022
+ Tailwind v4, Node 22 только для сборки. UV + uv.lock.
ЗАПРЕЩЕНО: React/Vue/SPA/Alpine; SQLite для тестов; плавающие версии в prod.

## Продуктовые инварианты
- Опубликованные игры доступны без регистрации.
- Гости играют, но их результаты НЕ идут в рекорды и НЕ переносятся в аккаунт.
- У каждой игры своя таблица рекордов в рамках эпохи; общего рейтинга нет.
- Оценка игры и рекорд независимы.
- Один обязательный основной жанр; теги/доп. жанры опциональны.
- Email необязателен; подтверждённый email — единственный самостоятельный
  способ восстановления пароля.
- Падение отдельной игры не ломает портал.
- Язык игры = язык сайта; при отсутствии локали — fallback + бейдж покрытия.
- Добавление/обновление игры — только ZIP; ручной повторный ввод полей запрещён.
- technical_id и host_label immutable после первой публикации, не переиспользуются.

## Архитектурные решения — нарушать нельзя
- Портал/CRM/API — основной домен; каждая игра — отдельный origin отдельного
  регистрируемого домена (не поддомен портала). Cookies портала игре недоступны.
- Игровой код не исполняется в Django; публикуется статический runtime bundle.
- SDK — единственный канал связи игры с платформой. Валидировать origin,
  source window, schema, session, nonce, expiry, state.
- Launch ticket — одноразовый секрет родительской страницы, НЕ передавать в iframe.
- Original ZIP неизменен побайтово; runtime — отдельная копия с заменённым SDK;
  package_hash != runtime_hash, оба отслеживаются. Публикуется только runtime.
- ZIP распаковывать в изолированном worker с лимитами CPU/RAM/time/disk/network;
  защита от Zip Slip, symlink, zip bomb, collisions, запрещённых расширений/URL.
- Preview/autotest исключаются из продуктовых агрегатов.
- Импорт идемпотентен; ручные overrides владельца не затираются (diff/conflict flow).
- Dev-lite / staging / production раздельны по compose project, сетям, томам, БД, секретам.

## Команды (все через Makefile, выполняются ВНУТРИ контейнера web)
make up | down | restart | ps | logs        — стек
make env | certs | assets | lock | build    — окружение и сборка
make makemigrations | migrate | psql | shell | superuser — БД
make test | lint | fmt | types | check      — качество (pytest/ruff/mypy)
make backup | restore-check                 — бэкапы
make staging-up | staging-down | staging-status | staging-logs
Dev: https://portal.test:8443 ; web также 127.0.0.1:8000 ; staging :8444.
Проверки: ./verify_stack.sh, ./verify_staging_final.sh (read-only).

## Процесс работы над задачей
1. ИССЛЕДУЙ: точный пункт ТЗ, фактические файлы/импорты/модели/миграции/тесты.
   Сними baseline. Отделяй факты от гипотез.
2. ПЛАН: минимальный набор изменяемых файлов; оцени миграционные, security
   и backward-compat риски. Для опасного — получи согласование.
3. РЕАЛИЗУЙ: доменная логика в services/, views/serializers тонкие.
   Type hints, ruff (line-length 100, double quotes), mypy.
4. ПРОВЕРЬ: целевые тесты + lint + types; для БД — makemigrations --check
   --dry-run, showmigrations --plan, migrate --plan; реальное поведение
   HTTP/API, а не только healthy. Сопоставь с acceptance criteria.
5. ОТЧЁТ: статус Done/Partial/Blocked, изменённые файлы, команды и фактические
   результаты, остаточные риски, один следующий шаг.

## Запреты
- Не заполнять пустые файлы фиктивными классами/stub ради вида; не выдавать
  mock/TODO за готовую функцию.
- Не переписывать проект/стек без доказанной причины и согласия.
- Не сбрасывать/удалять миграции; --fake не использовать как обычный фикс.
- Не выполнять docker compose down -v, flush, удаление volumes/БД/бэкапов.
- Не ломать dev-lite, staging, backup/restore-check.
- Не пересобирать образ без установленной причины.
- Не запускать архивные fix_*.sh / fill_*.sh / rebuild_after_fix.sh из корня —
  они деструктивны и оставлены как история.
- Не использовать --dangerously-skip-permissions, git reset --hard,
  push --force, переписывание истории, удаление веток.
- Не отправлять код во внешние сервисы без разрешения.
- Не выводить .env, пароли, токены, private keys, Basic Auth credentials.

## БД и миграции
Только PostgreSQL. citext, pg_trgm, unaccent создаются до использования
(core.0001_extensions). Dependencies явные. Применённые миграции не редактировать.
Unique constraint != immutability: immutable поля защищать сервисом/моделью/БД.
Конкурентные операции — транзакции/constraints/locks + тесты.
Разрушительные операции с данными — только по явному запросу и после бэкапа.

## Безопасность
API deny-by-default; public endpoints открываются явно.
ВНИМАНИЕ: сейчас в base.py стоит AllowAny — это известный дефект, не норма.
Не отключать CSRF, CSP, permissions, throttling, origin validation ради обхода ошибки.
Browser write-запросы защищены CSRF; throttle scopes реально настроены;
IP не единственный rate-limit key (корпоративные NAT).
Секреты — в .env, .env.staging, creds/, certs/ (вне Git). Логи без секретов.
Staging: Basic Auth + IP allowlist + noindex + mail sandbox, отдельные секреты.
Healthcheck nginx проверяет реальный listener (nc -z), не nginx -t (AD-001).

## Качество
Тесты: happy path, edge cases, отказ, гонки, идемпотентность. E2E для публичных
и CRM-сценариев (Playwright, marker e2e). Покрытие доменных модулей >=70% (§2.26).
Ошибки структурированные, локализуемые, безопасные. Зависимости — lock-файлами.

## Git
Локальный репозиторий, ветка main, remote отсутствует — так и держать.
Коммиты небольшие, осмысленные. Перед коммитом проверять, что секреты не в индексе.
EOF
ok "CLAUDE.md записан"

step "6. Локальный коммит"
git add -A
sec="$(git diff --cached --name-only | grep -E '(^|/)(creds/|certs/)|\.env$|\.env\.staging$|\.key$|id_rsa|htpasswd' | grep -vE '\.gitkeep$' || true)"
if [ -n "$sec" ]; then echo "$sec"; git reset >/dev/null; die "секретные пути в индексе — коммит отменён"; fi
if git diff --cached --quiet; then
  ok "нечего коммитить"
else
  git commit -m "fix: packaging for celery worker/beat; rotate staging basic auth; harden dump; add CLAUDE.md" \
    > "$BK/commit.log" 2>&1 && ok "$(git log --oneline -1)" || { tail -n 20 "$BK/commit.log"; bad "коммит не удался"; }
fi
git remote -v | grep -q . && bad "обнаружен remote" || ok "remote отсутствует"

step "ИТОГ"
"${COMPOSE[@]}" ps --format 'table {{.Service}}\t{{.Status}}'
printf '\nБэкапы и логи: %s\n' "$BK"
if [ "$FAIL" = "0" ]; then printf '\n===== ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ =====\n'; exit 0
else printf '\n===== ЕСТЬ ПРОБЛЕМЫ (см. FAIL выше) =====\n'; exit 1; fi

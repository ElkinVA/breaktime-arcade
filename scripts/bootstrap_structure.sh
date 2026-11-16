#!/usr/bin/env bash
# =============================================================================
#  bootstrap_structure.sh — каркас каталогов и файлов BreaktimeArcade (BA-PLAT-4.2)
#
#  Запуск:   bash bootstrap_structure.sh [КАТАЛОГ] [--dry-run]
#            КАТАЛОГ по умолчанию — текущий.
#
#  Идемпотентно: существующие файлы не изменяются.
#  Нормативные файлы этапа 1 создаются пустыми; служебные — со стартовым текстом.
# =============================================================================
set -euo pipefail
if (( BASH_VERSINFO[0] < 4 )); then printf 'Требуется bash >= 4\n' >&2; exit 1; fi

TARGET="$PWD"
DRY=0
for arg in "$@"; do
  case "$arg" in
    -n|--dry-run) DRY=1 ;;
    -h|--help)    sed -n '2,11p' "$0"; exit 0 ;;
    -*)           printf 'Неизвестный ключ: %s\n' "$arg" >&2; exit 2 ;;
    *)            TARGET="$arg" ;;
  esac
done

# =============================================================================
#  МАНІФЕСТ ФАЙЛОВ
# =============================================================================
FILES=(
  # --- корень ---
  pyproject.toml package.json Dockerfile Makefile manage.py conftest.py
  compose.yml compose.dev-lite.yml compose.staging.yml compose.prod.yml
  .env.example .gitignore .gitattributes .editorconfig .dockerignore
  .python-version .nvmrc .pre-commit-config.yaml ruff.toml mypy.ini pytest.ini
  README.md

  # --- проект Django ---
  config/{__init__,urls,api,celery,wsgi,asgi}.py
  config/settings/{__init__,base,dev,staging,prod}.py

  # --- общие шаблоны и дизайн-система (§2.7) ---
  templates/base.html
  templates/partials/{header,footer,language_switcher,theme_toggle,messages}.html
  templates/components/{button,field,table,modal,toast,skeleton,game_card,stepper,validation_row,diff_row,pagination}.html
  templates/emails/{base,confirm_email,password_reset,security_alert}.html
  templates/errors/{400,403,404,410,500}.html

  # --- статика: исходники (dist генерируется) ---
  static/src/css/app.css
  static/src/js/{main,catalog,player,host_protocol,wizard,upload,theme,ui,rating}.js
  static/src/js/vendor/.gitkeep
  static/dist/.gitkeep

  # --- машинные контракты этапа 0 (§2.25, Прил. F) ---
  schemas/{manifest,catalog,eventlog}.json
  schemas/messages/_envelope.json

  # --- официальный SDK (§2.14.3) ---
  sdk/CHANGELOG.md
  sdk/1.1.0/ba-sdk.js
  sdk/1.1.0/README.md

  # --- тесты ---
  tests/conftest.py tests/factories.py
  tests/integration/.gitkeep tests/e2e/.gitkeep tests/load/.gitkeep

  # --- инфраструктура ---
  infra/nginx/{nginx.conf,dev.conf,staging.conf.j2,prod.conf.j2}
  infra/nginx/snippets/{portal_headers,game_headers,proxy}.conf
  infra/scripts/{entrypoint,backup,restore,restore_check,release,rollback,mkcert}.sh
  infra/monitoring/{prometheus.yml,alerts.yml}
  infra/monitoring/grafana/.gitkeep

  # --- эксплуатационные каталоги (вне Git) ---
  media/.gitkeep certs/.gitkeep

  # --- скрипты ---
  scripts/collect_project.sh

  # --- документация (§2.5, §2.27) ---
  docs/architecture.md docs/api.md
  docs/runbook/{install,update,rollback,backup,restore,testing,add_game,update_game,publish_version,add_language,rotate_secrets,incident,owner_access_recovery}.md
  docs/spec/.gitkeep

  # --- CI/CD ---
  .github/workflows/{ci,release}.yml
  .github/renovate.json
)

# --- схемы сообщений протокола 1 (Приложение F) ---
MESSAGES=(
  ba_hello ba_submit ba_leaderboard ba_storage ba_new_session ba_exit ba_error
  ba_context ba_result ba_leaderboard_data ba_storage_data ba_session
  ba_pause ba_resume
)
for m in "${MESSAGES[@]}"; do FILES+=( "schemas/messages/$m.json" ); done

# --- доменные приложения (§2.4, §2.22) ---
APPS=(core accounts catalog gameplay leaderboards ratings pipeline i18n crm moderation analytics content theme)

for a in "${APPS[@]}"; do
  FILES+=(
    "apps/$a/__init__.py" "apps/$a/apps.py" "apps/$a/admin.py"
    "apps/$a/models/__init__.py" "apps/$a/services/__init__.py"
    "apps/$a/migrations/__init__.py" "apps/$a/tests/__init__.py"
    "apps/$a/templates/$a/.gitkeep"
  )
  case "$a" in
    core)
      FILES+=(
        apps/core/{ids,middleware,health,exceptions,permissions,validators,pagination,utils}.py
        apps/core/models/{base,security}.py
        apps/core/management/__init__.py
        apps/core/management/commands/__init__.py
      ) ;;
    accounts)
      FILES+=(
        apps/accounts/models/{user,profile,anonymous,email,nickname,recovery}.py
        apps/accounts/services/{registration,authentication,email_verification,password_reset,nickname,deletion,totp,hibp}.py
        apps/accounts/api/{__init__,serializers,views,urls}.py
        apps/accounts/{forms,views,urls,middleware,signals,tasks,validators}.py
        apps/accounts/templates/accounts/{login,register,password_reset,profile}.html
      ) ;;
    catalog)
      FILES+=(
        apps/catalog/models/{game,translation,genre,tag,asset}.py
        apps/catalog/services/{search,filters,sorting,popularity,slugs}.py
        apps/catalog/api/{__init__,serializers,views,urls}.py
        apps/catalog/{views,urls,tasks}.py
        apps/catalog/templates/catalog/{home,game_list,game_detail,genre_list}.html
        apps/catalog/templates/catalog/partials/{game_grid,filters}.html
      ) ;;
    gameplay)
      FILES+=(
        apps/gameplay/models/{session,result,storage,playtime}.py
        apps/gameplay/services/{sessions,tickets,heartbeat,results,storage,context}.py
        apps/gameplay/services/verification/{__init__,base,heuristics,replay,registry}.py
        apps/gameplay/verifiers/__init__.py
        apps/gameplay/api/{__init__,serializers,views,urls}.py
        apps/gameplay/{views,urls,tasks}.py
        apps/gameplay/templates/gameplay/play.html
      ) ;;
    leaderboards)
      FILES+=(
        apps/leaderboards/models/entry.py
        apps/leaderboards/services/{recalc,epochs,queries}.py
        apps/leaderboards/api/{__init__,serializers,views,urls}.py
        apps/leaderboards/{views,urls,tasks}.py
        apps/leaderboards/templates/leaderboards/leaderboard.html
      ) ;;
    ratings)
      FILES+=(
        apps/ratings/models/{vote,aggregate}.py
        apps/ratings/services/{voting,aggregates,antifraud}.py
        apps/ratings/api/{__init__,serializers,views,urls}.py
        apps/ratings/tasks.py
      ) ;;
    pipeline)
      FILES+=(
        apps/pipeline/models/{draft,version}.py
        apps/pipeline/services/{intake,unpack,injection,bundling,importer,diff,publishing,rollback,autotest,critical_path,artifacts}.py
        apps/pipeline/validation/{__init__,codes,report,structure,manifest,catalog,locales,security_scan,assets,budgets}.py
        apps/pipeline/tasks.py
      ) ;;
    i18n)
      FILES+=(
        apps/i18n/models/{language,entry,game_override}.py
        apps/i18n/services/{dictionary,coverage,plural,machine_translation}.py
        apps/i18n/api/{__init__,serializers,views,urls}.py
        apps/i18n/{middleware,context_processors,tasks}.py
        apps/i18n/templatetags/{__init__,ba_i18n}.py
      ) ;;
    crm)
      FILES+=(
        apps/crm/models/{audit,backup}.py
        apps/crm/services/{access,step_up,games,imports,reports,exports}.py
        apps/crm/views/{__init__,dashboard,games,wizard,genres,ratings,users,moderation,content,translations,logs,settings}.py
        apps/crm/{urls,forms,middleware,decorators,tasks}.py
        apps/crm/templates/crm/{base,dashboard}.html
        apps/crm/templates/crm/wizard/{step1_upload,step2_analysis,step3_card,step4_check,step5_publish,stepper,validation_row,diff_row}.html
        apps/crm/templates/crm/games/{list,detail,versions}.html
      ) ;;
    moderation)
      FILES+=(
        apps/moderation/models/{report,action}.py
        apps/moderation/services/{reports,quarantine}.py
        apps/moderation/api/{__init__,serializers,views,urls}.py
        apps/moderation/{views,urls,tasks}.py
        apps/moderation/templates/moderation/report_form.html
      ) ;;
    analytics)
      FILES+=(
        apps/analytics/models/{event,daily,play_credit}.py
        apps/analytics/services/{tracking,aggregates,partitions}.py
        apps/analytics/{tasks,views,urls}.py
        apps/analytics/management/__init__.py
        apps/analytics/management/commands/__init__.py
      ) ;;
    content)
      FILES+=(
        apps/content/models/{page,legal,consent,seo,redirect,adslot}.py
        apps/content/services/{pages,legal,sanitize,sitemap,redirects}.py
        apps/content/{views,urls,context_processors}.py
        apps/content/templates/content/{page,legal}.html
      ) ;;
    theme)
      FILES+=(
        apps/theme/models/{tokens,site_settings}.py
        apps/theme/services/{compiler,token_schema}.py
        apps/theme/{views,urls,context_processors}.py
      ) ;;
  esac
done
FILES+=( apps/__init__.py )

# --- эталонный картридж (BA-GAME-2.2 §3), этап 4 ---
LANGS=(en de nl ru fr es)
FILES+=(
  games-src/neon_snake/{index.html,manifest.json,README.md,SELF-CHECK.md,pack.py}
  games-src/neon_snake/css/style.css
  games-src/neon_snake/js/{ba-sdk,rng,game}.js
  games-src/neon_snake/assets/.gitkeep
)
for l in "${LANGS[@]}"; do
  FILES+=( "games-src/neon_snake/locales/$l.json" "games-src/neon_snake/catalog/$l.json" )
done

# =============================================================================
#  СТАРТОВОЕ СОДЕРЖИМОЕ СЛУЖЕБНЫХ ФАЙЛОВ
# =============================================================================
STUBS=( .gitignore .gitattributes .editorconfig .dockerignore .python-version .nvmrc README.md )

has_stub() {
  local p="$1" s
  for s in "${STUBS[@]}"; do
    if [[ "$p" == "$s" ]]; then return 0; fi
  done
  return 1
}

stub_content() {
  case "$1" in
    .python-version) printf '3.14\n' ;;
    .nvmrc)          printf '22\n' ;;
    .gitattributes) cat <<'EOF'
* text=auto eol=lf
*.sh text eol=lf
*.png binary
*.jpg binary
*.jpeg binary
*.webp binary
*.avif binary
*.gif binary
*.ico binary
*.woff2 binary
*.mp3 binary
*.ogg binary
*.wav binary
*.wasm binary
*.zip binary
EOF
      ;;
    .editorconfig) cat <<'EOF'
root = true

[*]
charset = utf-8
end_of_line = lf
insert_final_newline = true
trim_trailing_whitespace = true
indent_style = space
indent_size = 4

[*.{js,mjs,css,html,json,yml,yaml,toml}]
indent_size = 2

[Makefile]
indent_style = tab
EOF
      ;;
    .gitignore) cat <<'EOF'
# Python
__pycache__/
*.py[cod]
.venv/
venv/
*.egg-info/

# Django
/media/
/staticfiles/
/static/dist/*
!/static/dist/.gitkeep

# Секреты и локальные материалы
.env
.env.*
!.env.example
/certs/*
!/certs/.gitkeep

# Данные инфраструктуры
/pgdata/
/redis-data/
/backups/

# Инструменты
.pytest_cache/
.mypy_cache/
.ruff_cache/
.coverage
htmlcov/
/test-results/
/playwright-report/
node_modules/

# Снимки кода
project_dump.txt
project_dump.log

# ОС
.DS_Store
Thumbs.db
EOF
      ;;
    .dockerignore) cat <<'EOF'
.git
.github
.venv
venv
node_modules
__pycache__
*.pyc
.pytest_cache
.mypy_cache
.ruff_cache
htmlcov
.coverage
media
staticfiles
pgdata
redis-data
backups
certs
.env
.env.*
docs
tests
games-src
project_dump.txt
project_dump.log
EOF
      ;;
    README.md) cat <<'EOF'
# Breaktime Arcade

Портал коротких браузерных мини-игр с независимыми таблицами рекордов,
оценками, мультиязычным интерфейсом и CRM.

Нормативная база: `docs/spec/` — BA-PLAT-4.2, BA-GAME-2.2, BA-SDK-1.1, BA-ENV-1.1.
Каркас создан скриптом `scripts/bootstrap_structure.sh`; наполнение — по этапам §2.25.

- Архитектура: `docs/architecture.md`
- Эксплуатация: `docs/runbook/`
- Снимок кода для анализа: `bash scripts/collect_project.sh`
EOF
      ;;
  esac
}

# =============================================================================
#  СОЗДАНИЕ
# =============================================================================
if (( DRY == 0 )); then
  mkdir -p -- "$TARGET"
fi
cd "$TARGET"

declare -A DIR_MAP=()
for f in "${FILES[@]}"; do
  d="${f%/*}"
  if [[ "$d" == "$f" ]]; then d="."; fi
  DIR_MAP["$d"]=1
done

new_dirs=0
for d in "${!DIR_MAP[@]}"; do
  if [[ ! -d "$d" ]]; then new_dirs=$((new_dirs + 1)); fi
done
if (( DRY == 0 )); then mkdir -p -- "${!DIR_MAP[@]}"; fi

created=0; skipped=0; stubs=0
for f in "${FILES[@]}"; do
  if [[ -e "$f" ]]; then
    skipped=$((skipped + 1))
    continue
  fi
  created=$((created + 1))
  if (( DRY == 1 )); then printf '  + %s\n' "$f"; continue; fi
  if has_stub "$f"; then
    stub_content "$f" > "$f"
    stubs=$((stubs + 1))
  else
    : > "$f"
  fi
  if [[ "$f" == *.sh ]]; then chmod +x "$f"; fi
done

# самокопия в scripts/ для воспроизводимости
if (( DRY == 0 )); then
  self="$(readlink -f -- "${BASH_SOURCE[0]}")"
  dest="$PWD/scripts/bootstrap_structure.sh"
  if [[ ! -e "$dest" && "$self" != "$dest" ]]; then
    cp -- "$self" "$dest"
    chmod +x "$dest"
  fi
fi

printf '\nКаркас BreaktimeArcade\n'
printf '  Каталог:            %s\n' "$PWD"
printf '  Создано каталогов:  %d\n' "$new_dirs"
printf '  Создано файлов:     %d (со стартовым текстом: %d)\n' "$created" "$stubs"
printf '  Уже существовало:   %d (не изменены)\n' "$skipped"
if (( DRY == 1 )); then printf '  Режим: dry-run, изменения не внесены\n'; fi

if (( DRY == 0 )); then
  cat <<'EOF'

Дальнейшие действия:
  1. Скопировать нормативные документы в docs/spec/ (BA-PLAT-4.2, BA-GAME-2.2).
  2. Этап 1: заполнить pyproject.toml, Dockerfile, compose*.yml, config/settings/*,
     infra/nginx/dev.conf, .env.example, Makefile; затем uv lock / uv sync.
  3. Проверить карту проекта: bash scripts/collect_project.sh
EOF
fi

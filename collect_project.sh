#!/usr/bin/env bash
# =============================================================================
#  collect_project.sh — снимок кода BreaktimeArcade (BA-PLAT-4.2) для AI-анализа
#
#  Запуск:  bash collect_project.sh              (из корня проекта)
#           bash scripts/collect_project.sh      (из корня проекта)
# =============================================================================
set -euo pipefail

# Определяем корень проекта
find_project_root() {
    local dir
    if [[ -f "manage.py" || -d "apps" ]]; then
        pwd
        return
    fi
    dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    while [[ "$dir" != "/" ]]; do
        if [[ -f "$dir/manage.py" || -d "$dir/apps" ]]; then
            echo "$dir"
            return
        fi
        dir="$(dirname "$dir")"
    done
    pwd
}

cd "$(find_project_root)"
printf 'Корень проекта: %s\n' "$PWD"

OUTPUT_FILE="${OUTPUT_FILE:-project_dump.txt}"
LOG_FILE="${LOG_FILE:-project_dump.log}"
MAX_FILE_BYTES="${MAX_FILE_BYTES:-262144}"

# Каталоги для исключения
EXCLUDE_DIRS=(
    .git .idea .vscode .devcontainer .claude
    .venv venv env node_modules
    __pycache__ .pytest_cache .mypy_cache .ruff_cache .cache htmlcov coverage
    staticfiles .tailwind
    media pgdata redis-data backups
    test-results playwright-report .playwright
    dist build .backups certs creds var
)

# Расширения для исключения
EXCLUDE_EXTS=(
    pyc pyo pyd db sqlite3 dump gz bz2 xz 7z zip tar
    png jpg jpeg gif webp avif ico svg bmp tiff
    woff woff2 ttf otf eot
    mp3 ogg wav mp4 webm wasm pdf
    pem key crt p12 pfx
)

# Имена файлов для исключения
EXCLUDE_NAMES=(
    .DS_Store Thumbs.db desktop.ini
    package-lock.json yarn.lock pnpm-lock.yaml uv.lock
    project_dump.txt project_dump.log
audit.txt ba_audit_report.txt
)

# Расширения исходников
SOURCE_EXTS=(
    py js mjs css html htm json jsonc yaml yml toml ini cfg conf
    sh bash sql md txt csv xml j2
)

# Имена файлов без расширения
SOURCE_NAMES=(
    Dockerfile Makefile Procfile Justfile
    .env.example .gitignore .gitattributes .dockerignore .editorconfig
    .pre-commit-config.yaml .python-version .nvmrc
    LICENSE NOTICE
)

# Служебные переменные
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
BODY="$TMP_DIR/body"
TREE="$TMP_DIR/tree"
: > "$BODY"
: > "$TREE"
: > "$LOG_FILE"

n_ok=0; n_skip=0; n_empty=0; n_big=0; n_bin=0; total_bytes=0

is_excluded_name() {
  if [[ "${1,,}" == diagnostics_*.txt ]]; then return 0; fi
    local base="$1" name ext
    base="${base,,}"
    for name in "${EXCLUDE_NAMES[@]}"; do
        [[ "$base" == "${name,,}" ]] && return 0
    done
    [[ "$base" == ".env" || "$base" == .env.* ]] && [[ "$base" != ".env.example" ]] && return 0
    [[ "$base" == *.* ]] || return 1
    ext="${base##*.}"
    for name in "${EXCLUDE_EXTS[@]}"; do
        [[ "$ext" == "$name" || "$base" == *".$name" ]] && return 0
    done
    return 1
}

is_source_file() {
    local base="$1" name ext
    base="${base,,}"
    for name in "${SOURCE_NAMES[@]}"; do
        [[ "$base" == "${name,,}" ]] && return 0
    done
    [[ "$base" == dockerfile.* ]] && return 0
    [[ "$base" == compose.*.yml || "$base" == compose.*.yaml ]] && return 0
    [[ "$base" == *.py ]] && return 0
    [[ "$base" != *.* ]] && return 1
    ext="${base##*.}"
    for name in "${SOURCE_EXTS[@]}"; do
        [[ "$ext" == "$name" ]] && return 0
    done
    return 1
}

is_binary() {
    local enc
    enc="$(file -b --mime-encoding -- "$1" 2>/dev/null)" || return 0
    case "${enc##*: }" in
        us-ascii|utf-8|unknown) return 1 ;;
        *) return 0 ;;
    esac
}

# Формируем find с prune для исключений
printf 'Формирование команды find...\n'
find_cmd=( find . -type d \( )
first=1
for d in "${EXCLUDE_DIRS[@]}"; do
    if (( first )); then first=0; else find_cmd+=( -o ); fi
    find_cmd+=( -name "$d" )
done
find_cmd+=( \) -prune -o -type f -print0 )

printf 'Команда: %s ...\n' "${find_cmd[0]} ${find_cmd[1]} ${find_cmd[2]}"

# Собираем файлы в массив
printf 'Сбор файлов...\n'
mapfile -d '' files < <("${find_cmd[@]}" | LC_ALL=C sort -z)

printf 'Найдено файлов: %d. Обработка...\n' "${#files[@]}"

for f in "${files[@]}"; do
    rel="${f#./}"
    base="$(basename -- "$rel")"
    size="$(stat -c '%s' -- "$f" 2>/dev/null)" || continue

    if is_excluded_name "$base"; then
        n_skip=$((n_skip + 1))
        continue
    fi

    if ! is_source_file "$base"; then
        n_skip=$((n_skip + 1))
        continue
    fi

    if (( size == 0 )); then
        printf 'EMPTY  %s\n' "$rel" >> "$TREE"
        n_empty=$((n_empty + 1))
        continue
    fi

    if (( size > MAX_FILE_BYTES )); then
        printf 'BIG    %s (%d байт)\n' "$rel" "$size" >> "$TREE"
        n_big=$((n_big + 1))
        continue
    fi

    if is_binary "$f"; then
        printf 'BIN    %s\n' "$rel" >> "$TREE"
        n_bin=$((n_bin + 1))
        continue
    fi

    lines="$(wc -l < "$f")"
    printf 'OK     %s (%d строк, %d байт)\n' "$rel" "$lines" "$size" >> "$TREE"
    {
        printf '================================================================================\n'
        printf 'ФАЙЛ: %s  (%d строк, %d байт)\n' "$rel" "$lines" "$size"
        printf '================================================================================\n'
        cat -- "$f"
        printf '\n\n'
    } >> "$BODY"
    n_ok=$((n_ok + 1))
    total_bytes=$((total_bytes + size))

    # Прогресс каждые 50 файлов
    if (( n_ok % 50 == 0 )); then
        printf '  Обработано: %d файлов...\n' "$n_ok"
    fi
done

# Финальный файл
{
    printf '================================================================================\n'
    printf ' СНИМОК ПРОЕКТА BREAKTIME ARCADE (BA-PLAT-4.2)\n'
    printf ' Дата: %s\n' "$(date '+%F %T %z')"
    printf ' Корень: %s\n' "$PWD"
    printf ' Файлов в дампе: %d; содержимое: %d байт\n' "$n_ok" "$total_bytes"
    printf ' Пропущено: %d | пустых: %d | больших: %d | бинарных: %d\n' "$n_skip" "$n_empty" "$n_big" "$n_bin"
    printf '================================================================================\n\n'

    printf '=== ИНСТРУМЕНТЫ ===\n'
    printf 'python3: %s\n' "$(python3 --version 2>/dev/null || printf 'не найден')"
    printf 'uv:      %s\n' "$(uv --version 2>/dev/null || printf 'не найден')"
    printf 'node:    %s\n' "$(node --version 2>/dev/null || printf 'не найден')"
    printf 'docker:  %s\n\n' "$(docker --version 2>/dev/null || printf 'не найден')"

    printf '=== РЕЕСТР ФАЙЛОВ ===\n'
    cat "$TREE"
    printf '\n=== СОДЕРЖИМОЕ ФАЙЛОВ ===\n'
    cat "$BODY"
    printf '=== КОНЕЦ СНИМКА ===\n'
} > "$OUTPUT_FILE"

printf '\nГотово.\n'
printf '  Дамп: %s (%d строк, %d байт)\n' "$OUTPUT_FILE" "$(wc -l < "$OUTPUT_FILE")" "$(stat -c '%s' "$OUTPUT_FILE")"
printf '  Включено: %d | пропущено: %d | пустых: %d | больших: %d | бинарных: %d\n' \
    "$n_ok" "$n_skip" "$n_empty" "$n_big" "$n_bin"

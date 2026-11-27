# AUTONOMY-SANDBOX-CHECKS-001 — trusted ruff/mypy configuration

**Дата:** 2026-11-27
**Статус:** FIXED / INDEPENDENT CODE REVIEW ACCEPT.
**Коммит:** `71177d2` (`fix(autonomy): copy lint configs into trusted sandbox`).

## Симптом

Два запуска `ARCADE-EMAIL-RESET-RACE-001` были остановлены trusted-проверкой
sandbox с `orchestrator checks failed: ruff, mypy`, хотя изменённые файлы
кандидата проходили проектные проверки. Это была ошибка контрольного
окружения, а не кода задачи.

## Причина

`devcontrol/sandbox/run_tests.py` копировал worktree в изолированный
контейнер по allowlist `ALLOWED_ROOTS`, но в нём отсутствовали `ruff.toml`
и `mypy.ini`:

- `ruff` запускался с дефолтной конфигурацией. На кандидате `e1c1a3e`
  первый же запуск дал **430 ошибок**, преимущественно `I001` на импортах,
  потому что не применялись `target-version`, `line-length`,
  `known-first-party` и `extend-exclude` из `ruff.toml`.
- После добавления конфигурации ruff всё ещё проверял `.claude/hooks/` и
  `manage.py`: 4 ошибки `PTH111`/`S108` в
  `.claude/hooks/bash_guard.py`. Эти файлы сознательно не входят в
  нормативный `make lint` (`apps config tests devcontrol`).
- `mypy` без `mypy.ini` не получал `django-stubs` plugin, `files` и
  project excludes, поэтому trusted-проверка не соответствовала
  проектному quality gate.

Первый кандидат `01e065b` дополнительно имел только `ruff format --check`
по новому тесту; второй `e1c1a3e` после появления конфигурации проходил
ruff check, format и mypy.

## Исправление

1. В `ALLOWED_ROOTS` добавлены `ruff.toml` и `mypy.ini`.
2. Sandbox ruff приведён к нормативному `make lint`:
   `ruff check apps config tests devcontrol && ruff format --check apps config tests devcontrol`.
3. В `tests/unit/test_devcontrol.py` добавлена регрессия: copy-результат
   обязан содержать оба конфигурационных файла.

Проверка не ослаблена: sandbox перешёл с дефолтных, более слабых правил на
полный проектный набор; исключены только пути, которые исключает сам
`make lint`.

## Проверки

- `pytest tests/unit/test_devcontrol.py -q`: **33 passed, 1 skipped**.
- `make lint`: ruff check clean, **515 files formatted**.
- `make types`: **Success, 412 source files**.
- Sandbox ruff на `e1c1a3e`: `All checks passed!`, 511 files formatted.
- Sandbox mypy на `e1c1a3e`: `Success: no issues found in 409 source files`.
- Независимый code review: **ACCEPT**, два minor residuals:
  конфигурации копируются из кандидата (как и `pyproject.toml`/`pytest.ini`),
  и unit-тест покрывает allowlist, но не строку команды ruff. Риски
  зафиксированы, блокеров нет.

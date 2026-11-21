# Breaktime Arcade

Портал коротких браузерных мини-игр с независимыми таблицами рекордов,
оценками, мультиязычным интерфейсом и CRM.

Нормативная база: `technical_specification/` — BA-PLAT-4.2, BA-GAME-2.2.
`BA-SDK-1.1` и `BA-ENV-1.1` отсутствуют; их DRAFT-версии не являются нормой.
Provenance и SHA-256: `../ai-dev/docs/project-reference/README.md` (read-only).

Актуальное состояние: `docs/status/PROJECT_STATUS.md` и
`docs/handoff/NOW.md`. Навигация — `docs/handoff/`.

## Быстрый старт

```bash
make env       # только если .env ещё нет
make certs
make assets
make up
make check     # pytest + ruff/format + mypy
./verify_stack.sh
```

Dev: https://portal.test:8443. Остановка — `make down` (volumes не удаляются).
Подробно — `docs/runbook/install.md`; E2E — `tests/e2e` из host `.venv`
(см. `.claude/skills/ba-testing/SKILL.md`).

- Архитектура: `docs/architecture.md`
- Эксплуатация: `docs/runbook/`
- Автономный запуск: `docs/runbook/autonomy.md`
- Снимок кода для анализа: `bash scripts/collect_project.sh`
- Каркас: `scripts/bootstrap_structure.sh`; наполнение — по этапам §2.25.

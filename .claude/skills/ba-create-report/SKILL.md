---
name: ba-create-report
description: Создать ОДИН ZIP-отчёт BA_AUDIT_YYYYMMDD_HHMMSS.zip для внешнего аудита ChatGPT по явной команде «Создай отчёт» или «Создай отчёт для ChatGPT». Не запускать автоматически после каждой задачи.
tools: Read, Grep, Glob, Bash
---

# BA Create Report

Запускай только по явной команде владельца. Не создавай ZIP автоматически.

## Подготовка

1. Убедись, что текущая задача завершена или что отчёт нужен по текущему
   состоянию; не выдумывай результаты.
2. Запусти доступные проверки и сохрани фактические команды/exit codes во
   временный файл (например, `/tmp/ba_test_results_$$.txt`). Если проверки
   недоступны — так и запиши.
3. Не включай `.env*`, `certs/`, `creds/`, `.claude.json`, токены, ключи,
   приватные конфигурации, `node_modules`, `.venv`, сборки, архивы и
   пользовательские данные.

## Запуск

```bash
cd /home/elkinva/projects/ba
python3 .claude/skills/ba-create-report/create_report.py \
  --task-id <TASK-ID> \
  --test-results /tmp/ba_test_results_$$.txt
```

Если файла с результатами нет, запусти без `--test-results`; генератор
создаст `TEST_RESULTS.md` с фактическими встроенными проверками и явной
пометкой о невыполненных тестах.

## Обязательные документы в ZIP

`REPORT.md`, `PROJECT_STATE.md`, `TASK_HISTORY.md`, `CHANGES.md`,
`TEST_RESULTS.md`, `GIT_STATUS.txt`, `REQUIREMENTS_COMPLIANCE.md`,
`RISKS.md`, `NEXT_STEPS.md`, `SHA256SUMS.txt`, `CODE_DIFF.patch`,
`MANIFEST.txt`.

Архив: `reports/BA_AUDIT_YYYYMMDD_HHMMSS.zip`; ровно один, без
перезаписи. Генератор сам проверяет `zipfile.testzip`, MANIFEST и
SHA-256 и сканирует материалы на секреты.

## После создания

Выведи точный путь, размер и SHA-256 архива; проверь, что в нём нет
секретов и лишних файлов. Не отправляй архив в интернет. Если проверка
не прошла — удали только собственный неполный архив и сообщи причину.

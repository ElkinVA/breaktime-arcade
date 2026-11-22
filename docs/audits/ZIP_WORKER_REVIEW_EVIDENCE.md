# ZIP Worker — independent Pro Review evidence (A6)

**Дата:** 2026-11-22
**Область:** P3 `ARCADE-P3-ZIP-WORKER-INTEGRATION-001`,
коммиты `021a36c`, `270f224`, `e9f66e2`, `9017254`, документация `99ea95a`.
**Модели review:** `deepseek-v4-pro` (`code-reviewer`,
`security-auditor`, text-only). Исполнитель: `deepseek-flash[1m]`.

## 1. Честное ограничение источника

P3 выполнялся **до** автоматического сохранения reviewer JSON в
`.autonomy/evidence/`. Полный исходный JSON ответов Pro за P3 в репозитории
отсутствует; сохранились только:

- verbatim-выдержки вердиктов/находок в
  `docs/foundation/BA-ZIP-WORKER-001_REPORT.md` (раздел 4);
- QA/developer evidence P3 в `.autonomy/evidence/`;
- итоговый product report `docs/foundation/PRODUCT_ACCEPTANCE_REPORT.md`.

Ниже — **фактически сохранённые** вердикты и находки. Не выдавать этот
документ за полный JSON, которого нет. P4 quota/storage уже имеет полный
JSON (`reviewer-3e014175…`, `reviewer-df0a0cfe…`) и фиксируется отдельно в
`ARCADE_P4_ACCEPTANCE_REPORT.md`.

## 2. Вердикты

| Этап | Reviewer | Вердикт | Условия |
|---|---|---|---|
| План | `code-reviewer` | **ACCEPT WITH CONDITIONS** | C-1…C-6 |
| План | `security-auditor` | **ACCEPT WITH CONDITIONS** | S-1…S-6, M-1…M-6 |
| План (повтор) | оба | **ACCEPT** | условия закрыты до кода |
| Реализация | `code-reviewer` | **ACCEPT WITH CONDITIONS** | исправления ниже |
| Реализация | `security-auditor` | **ACCEPT WITH CONDITIONS** | 1 MAJOR (ложный), 7 MINOR |
| Финал | `security-auditor` | **ACCEPT** | — |
| Финал | `code-reviewer` | **ACCEPT** | остаток R-036 вне диффа |

Условия плана: prefork worker; явные exchange/route; топология томов;
Dockerfile chown; TOCTOU/O_NOFOLLOW; statvfs; retention; staging overlay не
ослабляет изоляцию.

## 3. Находки реализации и исправления

| # | Находка | Severity | Исправление | Статус |
|---|---|---|---|---|
| 1 | `acks_late` не подтверждён тестом | MAJOR | per-task annotation + тест | fixed |
| 2 | ATTEMPTS не переносился до `extract_zip`; hard-kill мог зациклить redelivery | MAJOR | ATTEMPTS++ до extraction | fixed |
| 3 | FIFO/спецфайл мог заблокировать открытие source | MAJOR | `O_NONBLOCK`, fstat, `/proc/self/fd`, `(deleted)` fail-closed | fixed |
| 4 | Corrupt `COMPLETED.json` мог доверяться | MAJOR | corrupt marker → redo | fixed |
| 5 | Source не должен переоткрываться | MAJOR (ложный) | тест-доказательство, source не переоткрывается | closed |
| 6 | Source ZIP оставался после rejection/timeout | MAJOR (live) | terminal cleanup + CANCEL + TTL uploads | fixed |
| 7 | Cleanup запускался на read-only zip-worker, ложно считал removed | MAJOR | `cleanup_zip_uploads` на writable default worker; считать только фактические удаления | fixed |
| 8 | Worker volume override терял `static/media/app_var` | MAJOR | явные mounts восстановлены; compose-тест | fixed |
| 9 | Staging overlay мог ослабить изоляцию | MINOR | тест: нет networks/security_opt/cap_drop/read_only/tmpfs/volumes/user override | fixed |
| 10 | Глобальный `CELERY_TASK_ACKS_LATE=True` (pre-existing) | MINOR | вне диффа; R-036 | open residual |
| 11 | Нет graceful SIGTERM-cancel | MINOR | cleaner + TTL; не в scope | documented |
| 12 | Healthcheck под занятым child не стресс-тестирован | MINOR | — | not tested |
| 13 | Нет жёсткой FS-квоты (R-033) | MINOR | P4 app-layer quota; hard quota отдельно | partially closed |

## 4. Что проверено независимо

- `worker.py`: UUID/lock/ATTEMPTS/quarantine, source O_NOFOLLOW/fstat/
  `/proc/self/fd`, COMPLETED reuse/conflict, statvfs, CANCEL, deadline,
  post-extract budget, audit.
- `tasks.py`: `extract_zip_task`, `cleanup_zip_staging`,
  `cleanup_zip_uploads`, маршруты `zip`/default.
- `compose.yml`: `zipnet` internal, read_only, cap_drop, no-new-privileges,
  pids/mem/cpu/tmpfs, volume ownership; dev/staging overlay.
- Тесты: traversal/malformed/symlink/hash mismatch/timeout+CANCEL/
  enqueue failure/no fallback/busy/duplicate/cleanup rerun.
- Live P3: CRM upload → `ZipExtractionJob completed`; worker log
  `zip.received`/`zip.extract`/`zip.complete` (93 ms); source absent;
  cleanup task removed aged upload.

## 5. Что осталось непроверенным

- Staging/production live (нет `.env.staging`) — **NOT TESTED**.
- Hard filesystem quota — **NOT TESTED**; app-layer quota P4 не заменяет
  файловую квоту.
- Stress/load и healthcheck под занятым child — **NOT TESTED**.
- Graceful SIGTERM-cancel — **NOT IMPLEMENTED** (cleaner/TTL).
- R-036 pre-existing global `acks_late` — **OPEN**.
- Антивирус/сканер вредоносного кода — **вне scope**.

## 6. Вывод

P3 ZIP Worker имеет независимый **ACCEPT** по P3; это техническая приёмка
агента, не продуктовая. Все критические находки P3 исправлены и
подтверждены повторным review. Остаточные пункты перечислены выше и в
`docs/risks/RISK_REGISTER.md`.

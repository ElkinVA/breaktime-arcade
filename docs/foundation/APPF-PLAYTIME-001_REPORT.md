# APPF-PLAYTIME-001 — подтверждённое игровое время

**Дата:** 2026-11-20  
**Статус:** IMPLEMENTED / AWAITING OWNER ACCEPTANCE; independent review —
`code-reviewer` и `security-auditor`: **accept**, блокеров нет.  
**Основание:** BA-PLAT-4.2 §2.12.3, §2.22; APPF-RESULT-001.

## 1. Реализация

`UserGamePlaytime` (`user`, `game`, `verified_seconds`, `updated_at`;
`UNIQUE(user, game)`). Heartbeat после clamp/cap вычисляет фактическое
приращение `credited_ms`; если сессия `subject_type=user` и `mode=user`,
приращение (в целых секундах) добавляется атомарно (`F()` + retry на
IntegrityError). Гости, preview и autotest не пишут (§2.12.3: только
`mode=user`, `is_test=false`). При анонимизации аккаунта строки удаляются
(§2.10.5).

## 2. Проверки

```text
pytest tests/integration/test_game_sessions.py -> 40 passed
pytest (full) -> 273 passed, 2 skipped
make lint -> All checks passed
make types -> Success: 318 source files
```

Тесты: user heartbeat 30 с → 30, +10 с → 40; guest и preview не создают
строк; cap не завышает время; параллельные первые heartbeat'ы двух сессий
одного пользователя → оба ok, 60 с (upsert без 500); миграция 0009.

## 3. Остаточные риски

- Секундное округление: при heartbeat 30 с потерь нет; нестандартные
  интервалы теряют доли секунды (по ТЗ `verified_seconds` — секунды).
- Аккаунт с длинными сессиями может накопить большое значение — это
  ожидаемое поведение; retention/агрегаты — по §2.22.
- Heartbeat остаётся клиентским сигналом с clamp 45 с; античит — слой
  верификатора (R-031).

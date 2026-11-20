# APPF-SESSION-001 — evidence независимой проверки

**Дата:** 2026-11-20  
**Назначение:** сохранить подтверждения того, что независимые Pro-reviewers
проверяли именно код и тесты, а не только отчёт; перечень замечаний и
остаточные риски. Требование владельца OD-STATUS-006.

## 1. Проверяемые файлы и хэши

SHA-256 рабочих файлов на момент проверки (коммит `c935237` + None-guard):

```text
d7d6d7d9e177a4b9d8462cd0bff44988c95625a6b9c7839514c223729a835320  apps/gameplay/models/session.py
72b49e337f1fa063cbb6952eb94d3867fe9543113f9966f841d1ccc56bab92e6  apps/gameplay/services/sessions.py
28d8746170a4c839c8e2dad8ce840def06c48c9c2fc94bf98fa0d5a870d1ae02  apps/gameplay/api/views.py
74729ceab1315597661666db1f66c0b84c7469f912cbf3d1319194cd731128fc  apps/gameplay/api/serializers.py
e5b63248069a6f703c6b0bcb826250fe9b788061f43ada0e621a265c3ade86d7  apps/gameplay/api/throttling.py
9bab65ff45c3104419c5ddda1e742e1d6dd926c88153630e7a467ed22de22a78  apps/gameplay/api/urls.py
bcf547f94def870fc514839df443fe6093073c44ac3370f494b33b7d72494fda  apps/gameplay/migrations/0001_initial.py
b302ad8fc370fdfe846103f85bf8df0837a033321ff3609168cb3c13713dcd8f  apps/gameplay/migrations/0002_alter_gamesession_binding_nonce_hash.py
5d25f94b80cfa2446b75988398cee4a9970d5751f1f36d323075036d38c912a8  apps/accounts/services/anonymous.py
b8436347a910da4209769783dd942671b00056cf6402b3b32d4fb83b068002c8  tests/integration/test_game_sessions.py
3f661d46938d514746997489ce2fcfd897bed8dca8f0204e3c107722272d5400  tests/conftest.py
```

## 2. Как проверялось

Pro работает в text-only режиме из-за `leading-only` (R-026): инструменты
ненадёжны. Поэтому Flash передавал review-агенту **полные тексты файлов и
diff**, а не отчёт. Проверка шла в три раунда:

| Раунд | Что передано | Результат |
|---|---|---|
| 1. Полный review | Полный код моделей/сервисов/views/serializers/throttling/urls/migrations, схема тестов (24 сценария), evidence | `conditional accept` (code-reviewer, security-auditor): throttle-обход, конкурентные тесты, cookie error-path, границы, накопление строк |
| 2. Delta-review | Полные новые версии throttling/activation/views + 3 конкурентных теста + evidence | оба **accept**; security — accept; code — accept после None-guard `max_session_seconds` |
| 3. Тесты | Полный текст `tests/integration/test_game_sessions.py` (627 строк) и `tests/conftest.py`, хэши source-файлов | см. §4 |

Важно: ни один раунд не был проверкой отчёта. Раунд 1 и 2 получали код и
diff; раунд 3 — полный текст тестов. Ограничение: Pro не читал файлы с
диска (text-only), поэтому соответствие переданного текста рабочему дереву
подтверждается хэшами из §1, снятыми Flash.

## 3. Перечень замечаний и исправлений

| Замечание | Severity | Исправление | Подтверждение |
|---|---|---|---|
| Throttle ключевался сырым cookie → свежий бакет на каждый мусорный токен | major | ключ по живой `AnonymousIdentity` (decode+token_hash+expiry), иначе IP | re-review accept; тесты subject/IP |
| Нет конкурентных тестов | major (процесс) | 3 transaction-теста: один победитель, лимит 3, heartbeat без двойного зачёта | 24 passed |
| Set-Cookie теряется на error-path создания | minor | `_fail(response, exc)` на том же Response | re-review accept |
| Два формата ошибок (DRF validation vs `{code,message}`) | minor | `E_INVALID_REQUEST` | тест |
| Heartbeat после `finished` → 400 | minor | 410 `E_SESSION_FINISHED` | тест |
| Границы времени не закреплены | minor | включительная семантика + boundary-тесты | тесты |
| Накопление CREATED/identity | medium | ленивая экспирация CREATED; identity чистятся beat-задачей | re-review accept |
| Лимит ≤3 активных обходился активацией (найдено Flash вне review) | blocker (нормативный) | проверка лимита в activation под advisory-lock | последовательный + конкурентный тесты |
| Свежая БД не мигрировала (`catalog.0001` citext) | blocker (инфраструктурный) | graph-зависимость от `core.0001_extensions` | `migrate --plan` чист |
| `max_session_seconds` None-guard | blocker (code-review) | `or 1800` восстановлен | re-review accept |

## 4. Вердикт раунда 3 (полные тесты)

Проверка полного текста тестов тем же `code-reviewer` (deepseek-v4-pro,
text-only), которому ранее передавались полные исходники: **accept**
(2026-11-20). Ревьюер подтвердил: ровно 24 тестовые функции; нет
mock/monkeypatch; все тесты идут через `Client(enforce_csrf_checks=True)` или
сервисы с реальной БД; assertions не ослаблены; гонки используют Barrier(2),
отдельные соединения и реальные PG-блокировки; throttle-тесты используют
точные cache-ключи; расхождений с заявленными свойствами не найдено.

Замечания (не блокеры, приняты как тест-дефицит для APPF-SESSION-002):

1. HTTP-слой heartbeat (`POST .../heartbeat` → 204, CSRF, throttle-scope
   `heartbeat`) не покрыт — все heartbeat-тесты сервисные.
2. `test_idle_and_max_duration_boundaries_are_inclusive` проверяет только
   idle-границу; равенство max_duration не ассертировано.
3. Throttle-тесты не проверяют end-to-end окно истории и фактические ставки
   (только конфиг и ключ).
4. Не покрыты: повторная активация после терминального состояния,
   PROTECT-поведение FK.

Эти пункты включены в APPF-SESSION-002 как дополнительные тесты.

## 5. Остаточные риски

- 404 vs 403 enumeration сессий (UUIDv7; принято).
- Throttle-ключи в Redis allkeys-lru (F-6) — решение по отдельному
  noeviction-инстансу: `docs/decisions/THROTTLE_REDIS_DECISION.md`;
  реализация — APPF-SESSION-002.
- Мульти-identity амплификация (~30 identity × 30 create/час с IP; R-030) —
  закрывается APPF-SESSION-002 (subject 30/ч + IP 600/ч по Прил. E).
- Retention `GameSession` (§2.22/Прил. D) — `RETENTION_PROPOSAL.md`,
  ожидает решения владельца.
- `strings:{}` и `trustLevel:"client_reported"` — [PROP] до утверждения
  BA-SDK-1.1; не считать нормой.

## 6. Фактические проверки

```text
pytest tests/integration/test_game_sessions.py -> 24 passed
pytest (full)              -> 209 passed, 2 skipped
make lint                  -> All checks passed; 335 files formatted
make types                 -> Success: 317 source files
makemigrations --check     -> No changes detected
migrate --plan             -> No planned migration operations
./verify_stack.sh          -> СТЕК ЗДОРОВ
```

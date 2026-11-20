# APPF-STORAGE-001 — хранилище игры

**Дата:** 2026-11-20  
**Статус:** IMPLEMENTED / AWAITING OWNER ACCEPTANCE; independent review —
`code-reviewer` и `security-auditor`: **accept**, блокеров нет.  
**Основание:** BA-PLAT-4.2 §2.22/§2.23, Приложение E; DB-008 делегирован
техническому руководителю.

## 1. Модель

`GameStorage`: `game` FK PROTECT, `subject_type ∈ {user, anon}`, `user`/`anon`
FK PROTECT nullable (XOR CHECK), `data` JSONB, `bytes`, `revision`,
`expires_at`; частичные `UNIQUE(game, user)` и `UNIQUE(game, anon)`;
`CHECK bytes ≤ 65536`; индекс `expires_at`.

Migration `0007`: trigger BEFORE INSERT/UPDATE вычисляет
`bytes = octet_length(data::text)` и отклоняет >64 КиБ (ERRCODE 23514) —
DB-008. Сервис дополнительно проверяет канонический JSON (sort_keys,
без пробелов, UTF-8), ≤256 ключей, depth ≤8, ключ ≤128, без NaN/Infinity.

## 2. API

`GET /api/v1/games/{technical_id}/storage` — документ и `ETag: "<revision>"`;
гостю продлевается TTL; истёкший документ удаляется и возвращается пустой.

`PUT /api/v1/games/{technical_id}/storage` — обязательный `If-Match`
(`*` или `"<revision>"`); `select_for_update`; stale revision или отсутствие
документа без `*` → 409 `E_STORAGE_CONFLICT`; квота → 413
`E_STORAGE_QUOTA`; невалидная структура → 400; успех → 200 с новым ETag.
CSRF обязателен; авторизация — пользователь или живая guest identity,
иначе 403 `E_AUTH_REQUIRED`; только published-игра.

Гостевое TTL — 90 дней с последнего доступа; данные пользователя живут до
удаления аккаунта; данные сохраняются между версиями игры (ключ — игра +
субъект); гость не переносится в аккаунт. При анонимизации аккаунта
`delete_user_storage` удаляет документ.

## 3. Проверки

```text
pytest tests/integration/test_game_storage.py -> 12 passed
pytest (full) -> 260 passed, 2 skipped
make lint -> All checks passed
make types -> Success: 318 source files
makemigrations --check / migrate --plan -> clean
```

Тесты: create/read/revision/ETag; stale/missing/wildcard If-Match 409;
CSRF; quota 70 КиБ; >256 ключей; depth >8; ключ >128; NaN → 400; guest TTL
expiry; активная сессия обязательна (403 без неё); per-session throttle
60/min → 429; гонка двух create (один ok, один 409); cleanup просроченной
identity удаляет storage; изоляция пользователей/игр; unpublished 404;
anonymous без identity 403; `delete_user_storage`; DB bytes.

## 4. Остаточные риски

- Sliding TTL гостя: активный GET продлевает 90 дней — по семантике
  «с последнего доступа»; при желании владельца ставится общий cap.
- Retention/очистка anon-документов: истёкшие identity чистятся beat-задачей
  вместе со storage; отдельный sweeper по expires_at — кандидат.
- Гостевое хранилище не переносится в аккаунт (инвариант); UI-предупреждение
  вне среза.
- Содержимое `data` не сканируется; XSS-риск переносится на рендерящий слой
  SDK (будущий срез).

# Owner product vision — mapping and deferred scope

**Дата:** 2026-11-26. **Статус:** ANALYSIS ONLY; текущий план разработки не
переориентирован. Никакие product/SEO функции из этого документа не начаты.

## 1. Что уже соответствует концепции

- Публичный портал и каталог: карточки игр, жанры, теги, поиск, популярное,
  новинки, пагинация, локализованные страницы; гостевой запуск без регистрации.
- Аккаунты: добровольная регистрация, никнейм, профиль, личные результаты;
  гостевые результаты не попадают в рекорды/аккаунт.
- Игры: короткие браузерные сессии, отдельная таблица рекордов в рамках игры;
  оценки и рекорды независимы.
- Мультиязычность: 6 языков, языковые URL, fallback + locale badge;
  каталог/SEO учитывают активные языки.
- Публикация: ZIP pipeline, SDK/Host Bridge, runtime bundle, owner publish/
  rollback; игры не исполняются в Django.
- SEO-база: стабильные slug URL и 301, canonical, title/description/H1,
  robots.txt, sitemap-index по языкам, hreflang/x-default, noindex служебных
  страниц, crawlable HTML-ссылки, 404; play-URL закрыты robots (тонкие
  iframe-страницы не индексируются), detail-страницы содержат метаданные.
- CRM: SEO-диагностика переводов, модерация оценок/жалоб, управление играми.

## 2. Чего пока нет (future scope)

- Аватар и расширенный публичный профиль (сейчас nickname/records; avatar
  отсутствует).
- Общий рейтинг сайта (per-game ratings/leaderboards есть; site-wide нет).
- Тематические подборки кроме home-блоков/жанров/тегов.
- Социальная модель: друзья, просмотр профилей/активности, приглашения в
  онлайн-игры; открытые чаты/публикации не вводить без отдельного решения.
- AI Game Factory и массовая генерация игр; owner approval workflow для
  карточек/переводов/публикации.
- Реклама/монетизация и consent-интеграции.
- GSC/GA4/Bing/аналитика позиций/индексации, собственный игровой журнал.
- Мобильные performance budgets и регулярный SEO-acceptance аудит.

## 3. Минимальные SEO-требования до завершения платформы

1. Зафиксировать acceptance-аудит текущих canonical/hreflang/robots/sitemap/
   noindex/301/404 на реальных страницах (код уже есть; нужна проверка).
2. Убедиться, что индексируются только опубликованные игры/жанры/страницы
   каталога, а play/account/CRM закрыты; sitemap не содержит черновиков.
3. Уникальные title/description/H1 и crawlable информация игры вне iframe
   (detail-страница); не создавать mass/low-quality SEO-страницы и
   фиктивные фильтры.
4. Structured data только для реального содержимого; mobile performance и
   корректные 404/301 — проверить перед релизом.
5. Не менять URL-схему без 301 и не включать SEO-инструменты, меняющие
   production-метаданные без owner approval.

Всё остальное SEO (GSC/GA4/Bing, позиции, внешнее продвижение) — после
завершения платформы и отдельного решения владельца.

## 4. Backlog additions (не начинать)

- `ARCADE-SEO-TECH-ACCEPTANCE-001` — Critical, audit-only: проверить
  canonical/hreflang/robots/sitemap/301/404/structured data на реальном
  контенте; отчёт, без mass pages.
- `ARCADE-PROFILE-AVATAR-001` — Major: avatar/публичный профиль, moderation/
  storage/privacy.
- `ARCADE-SITE-RATING-001` — Major: общий рейтинг сайта и правила агрегации.
- `ARCADE-THEMATIC-COLLECTIONS-001` — Major: курируемые подборки.
- `ARCADE-SOCIAL-GRAPH-001` — Major, deferred: друзья/активность/приглашения;
  без открытых чатов/публикаций.
- `ARCADE-ADS-CONSENT-001` — Major, deferred: ненавязчивая реклама, consent,
  privacy/legal approval.
- `ARCADE-SEO-ANALYTICS-001` — Major, deferred: GSC/GA4/Bing/позиции/
  индексация после завершения платформы.
- `ARCADE-AI-GAME-FACTORY-001` — Major, deferred: AI подготовка игр/карточек/
  переводов с owner approval; не запускать сейчас.

## 5. Границы

Текущий план (завершение платформы, тесты, review, исправления) имеет
приоритет. Ни одна future-функция не должна менять утверждённый scope без
согласования владельца.

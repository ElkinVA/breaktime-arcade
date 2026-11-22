"""Корневые маршруты с языковыми префиксами (§2.6)."""

from __future__ import annotations

from django.conf import settings
from django.conf.urls.i18n import i18n_patterns
from django.conf.urls.static import static
from django.urls import include, path

from apps.core import health, sitemap
from apps.i18n.views import root_redirect

urlpatterns = [
    # Пробы живучести без языкового префикса
    path("healthz", health.healthz, name="healthz"),
    path("readyz", health.readyz, name="readyz"),
    # SEO: sitemap-index и robots.txt без языкового префикса (§2.19)
    path("sitemap.xml", sitemap.sitemap_index, name="sitemap_index"),
    path("robots.txt", sitemap.robots_txt, name="robots_txt"),
    # Тема
    path("", include("apps.theme.urls")),
    # CRM (без языкового префикса, с защищённым префиксом)
    path("crm/", include("apps.crm.urls", namespace="crm")),
    # Публичный API v1 (same-origin, без языкового префикса)
    path("api/v1/", include("apps.gameplay.api.urls")),
    path("api/v1/", include("apps.leaderboards.urls")),
    path("api/v1/", include("apps.ratings.api.urls")),
    path("api/v1/", include("apps.moderation.api.urls")),
]

# Языковые префиксы для публичных страниц
urlpatterns += i18n_patterns(
    # SEO: языковая карта сайта /<lang>/sitemap.xml (§2.19)
    path("sitemap.xml", sitemap.sitemap_language, name="sitemap_language"),
    # Аккаунты и кабинет
    path("auth/", include("apps.accounts.urls", namespace="accounts")),
    path("account/", include("apps.accounts.account_urls", namespace="account")),
    # Каталог
    path("", include("apps.catalog.urls", namespace="catalog")),
    prefix_default_language=True,
)

# Редирект корня / по Accept-Language
urlpatterns += [
    path("", root_redirect, name="root_redirect"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

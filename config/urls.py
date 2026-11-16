"""Корневые маршруты с языковыми префиксами (§2.6)."""
from __future__ import annotations

from django.conf import settings
from django.conf.urls.i18n import i18n_patterns
from django.conf.urls.static import static
from django.urls import include, path
from django.views.generic import RedirectView

from apps.core import health

urlpatterns = [
    # Пробы живучести без языкового префикса
    path("healthz", health.healthz, name="healthz"),
    path("readyz", health.readyz, name="readyz"),

    # Тема
    path("", include("apps.theme.urls")),

    # CRM (без языкового префикса, с защищённым префиксом)
    path("crm/", include("apps.crm.urls", namespace="crm")),
]

# Языковые префиксы для публичных страниц
urlpatterns += i18n_patterns(
    # Каталог
    path("", include("apps.catalog.urls", namespace="catalog")),
    prefix_default_language=True,
)

# Редирект корня / по Accept-Language
urlpatterns += [
    path("", RedirectView.as_view(url="/en/", permanent=False)),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

from django.apps import AppConfig


class CatalogConfig(AppConfig):
    name = "apps.catalog"
    label = "catalog"
    verbose_name = "Каталог игр"

    def ready(self) -> None:
        from apps.catalog import signals  # noqa: F401

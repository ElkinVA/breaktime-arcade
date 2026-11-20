from django.apps import AppConfig


class I18nConfig(AppConfig):
    name = "apps.i18n"
    label = "i18n"
    verbose_name = "Интернационализация"

    def ready(self) -> None:
        from apps.i18n import signals  # noqa: F401

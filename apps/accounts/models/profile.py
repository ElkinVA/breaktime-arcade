from __future__ import annotations

from django.core.validators import RegexValidator
from django.db import models

from apps.core.fields import CitextField

nickname_validator = RegexValidator(
    regex=r"^[\w]+(?: [\w]+)*$",
    message="Никнейм: 3–20 символов, буквы/цифры/_, одиночные пробелы.",
)


class UserProfile(models.Model):
    """Публичный профиль; логин и email публично не показываются."""

    user = models.OneToOneField(
        "accounts.User",
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="profile",
    )
    nickname = CitextField(max_length=20, unique=True, validators=[nickname_validator])
    nickname_skeleton = models.CharField(max_length=64, unique=True)
    language = models.ForeignKey(
        "i18n.Language",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="user_profiles",
    )
    theme = models.CharField(max_length=16, default="dark")
    age_confirmed_at = models.DateTimeField(null=True, blank=True)
    marketing_consent_at = models.DateTimeField(null=True, blank=True)
    deletion_requested_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "accounts_profile"
        verbose_name = "Профиль"
        verbose_name_plural = "Профили"

    def __str__(self) -> str:
        return self.nickname

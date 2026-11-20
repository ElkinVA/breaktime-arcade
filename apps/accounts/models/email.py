from __future__ import annotations

from django.db import models

from apps.core.fields import CitextField


class EmailAddress(models.Model):
    """Один email на пользователя в v1; подтверждение необязательно."""

    user = models.OneToOneField(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="email_address",
    )
    email = CitextField(max_length=254, unique=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    is_primary = models.BooleanField(default=True)
    bounce_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "accounts_email"
        verbose_name = "Email"
        verbose_name_plural = "Email-адреса"

    def __str__(self) -> str:
        return self.email

from __future__ import annotations

from typing import Any, ClassVar

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.core.validators import RegexValidator
from django.db import models

from apps.core.fields import UUID7, CitextField
from apps.core.ids import uuid7

login_validator = RegexValidator(
    regex=r"^[a-z0-9_.-]{3,30}$",
    message="Логин: 3–30 символов, только a-z, 0-9, '_', '.', '-'.",
)


class StaffRole(models.TextChoices):
    """CRM staff roles (§2.16). Empty value means "no CRM access"."""

    OWNER = "owner", "Владелец"
    EDITOR = "editor", "Редактор"
    MODERATOR = "moderator", "Модератор"
    OBSERVER = "observer", "Наблюдатель"


class UserManager(BaseUserManager["User"]):
    use_in_migrations = True

    def _create(self, login: str, password: str | None, **extra: Any) -> User:
        if not login:
            raise ValueError("Логин обязателен")
        login = login.strip().lower()
        user = self.model(login=login, **extra)
        user.set_password(password)
        user.full_clean(exclude=["password"])
        user.save(using=self._db)
        return user

    def create_user(self, login: str, password: str | None = None, **extra: Any) -> User:
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create(login, password, **extra)

    def create_superuser(self, login: str, password: str | None = None, **extra: Any) -> User:
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("crm_role", StaffRole.OWNER)
        if extra["is_staff"] is not True or extra["is_superuser"] is not True:
            raise ValueError("Суперпользователь требует is_staff и is_superuser")
        return self._create(login, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid7, db_default=UUID7(), editable=False)
    login = CitextField(max_length=30, unique=True, validators=[login_validator])
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    crm_role = models.CharField(
        max_length=16,
        choices=StaffRole.choices,
        blank=True,
        default="",
        db_index=True,
        help_text="Роль в CRM (§2.16); пустое значение — доступа нет.",
    )
    totp_secret = models.CharField(max_length=64, blank=True, default="")
    totp_confirmed_at = models.DateTimeField(null=True, blank=True)
    totp_last_counter = models.BigIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "login"
    REQUIRED_FIELDS: ClassVar[list[str]] = []
    EMAIL_FIELD = ""

    class Meta:
        db_table = "accounts_user"
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(crm_role="")
                | (
                    models.Q(is_staff=True)
                    & models.Q(
                        crm_role__in=[
                            StaffRole.OWNER,
                            StaffRole.EDITOR,
                            StaffRole.MODERATOR,
                            StaffRole.OBSERVER,
                        ]
                    )
                ),
                name="ck_user_crm_role_staff",
            ),
        ]

    def __str__(self) -> str:
        return self.login

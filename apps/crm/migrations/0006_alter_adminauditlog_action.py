from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("crm", "0005_alter_adminauditlog_action"),
    ]

    operations = [
        migrations.AlterField(
            model_name="adminauditlog",
            name="action",
            field=models.CharField(
                choices=[
                    ("staff.role_changed", "Смена роли сотрудника"),
                    ("staff.activated", "Активация сотрудника"),
                    ("staff.deactivated", "Деактивация сотрудника"),
                    ("game.published", "Публикация версии"),
                    ("game.rolled_back", "Откат версии"),
                    ("rating.hidden", "Скрытие оценки"),
                    ("rating.restored", "Восстановление оценки"),
                    ("complaint.assigned", "Назначение жалобы"),
                    ("complaint.resolved", "Решение по жалобе"),
                    ("complaint.rejected", "Отклонение жалобы"),
                    ("content.translation_published", "Публикация перевода"),
                    ("content.page_published", "Публикация контентной страницы"),
                    ("user.blocked", "Блокировка аккаунта"),
                    ("user.unblocked", "Разблокировка аккаунта"),
                    ("user.deletion_requested", "Запрос удаления аккаунта"),
                    ("user.deleted", "Удаление аккаунта"),
                    ("genre.created", "Создание жанра"),
                    ("genre.updated", "Изменение жанра"),
                    ("genre.deleted", "Удаление жанра"),
                    ("tag.created", "Создание тега"),
                    ("tag.updated", "Изменение тега"),
                    ("tag.deleted", "Удаление тега"),
                ],
                max_length=64,
            ),
        ),
    ]

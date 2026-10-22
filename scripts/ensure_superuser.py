"""Создаёт или обновляет суперюзера из переменных DJANGO_SUPERUSER_*.

Подаётся на stdin команды `python manage.py shell`, поэтому импортируемую
Django-обвязку (setup) запускать не нужно. Идемпотентен: при повторном
запуске юзер не дублируется, а его пароль обновляется.

Пример локального запуска (из main_app):
    DJANGO_SUPERUSER_USERNAME=admin \\
    DJANGO_SUPERUSER_EMAIL=admin@example.com \\
    DJANGO_SUPERUSER_PASSWORD=пароль \\
    python manage.py shell < ../scripts/ensure_superuser.py
"""

import os

from django.contrib.auth import get_user_model

env = os.environ
username = env["DJANGO_SUPERUSER_USERNAME"]

user, created = get_user_model().objects.get_or_create(
    username=username,
    defaults={"email": env.get("DJANGO_SUPERUSER_EMAIL", "")},
)
user.set_password(env["DJANGO_SUPERUSER_PASSWORD"])
user.is_staff = user.is_superuser = True
user.save()
print("created" if created else "updated", username)

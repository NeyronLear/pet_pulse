"""Модели БД приложения"""

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.db import models


class UsernameValidator(UnicodeUsernameValidator):
    """Как стандартный, но без «@»: LoginView по нему отличает почту от логина."""

    regex = r"^[\w.+-]+\Z"
    message = "Логин может содержать только буквы, цифры и символы . + - _."


class User(AbstractUser):
    """Пользователь — владелец питомцев.
    Почта обязательна и уникальна: по ней тоже можно войти."""

    username = models.CharField(
        "Логин",
        max_length=150,
        unique=True,
        validators=[UsernameValidator()],
        error_messages={"unique": "Пользователь с таким логином уже существует."},
    )
    email = models.EmailField(
        "Почта",
        unique=True,
        error_messages={"unique": "Пользователь с такой почтой уже существует."},
    )
    phone = models.CharField("Телефон", max_length=20, blank=True)
    avatar = models.ImageField("Аватар", upload_to="users/", blank=True, null=True)

    class Meta:
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"

    def __str__(self):
        return str(self.username)


class Pet(models.Model):
    """Карточка питомца."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="pets",
        verbose_name="Владелец",
    )
    name = models.CharField("Имя", max_length=100)
    species = models.CharField("Вид", max_length=50, default="Кот")
    breed = models.CharField("Порода", max_length=100, blank=True)
    birth_date = models.DateField("Дата рождения", null=True, blank=True)
    photo = models.ImageField("Фото", upload_to="pets/", blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]
        verbose_name = "Питомец"
        verbose_name_plural = "Питомцы"

    def __str__(self):
        return str(self.name)


class MedCard(models.Model):
    """Медицинская карта питомца."""

    pet = models.OneToOneField(
        Pet,
        on_delete=models.CASCADE,
        related_name="med_card",
        verbose_name="Питомец",
    )
    weight = models.DecimalField(
        "Вес, кг",
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
    )
    allergies = models.TextField("Аллергии", blank=True)
    chronic_conditions = models.TextField("Хронические заболевания", blank=True)
    notes = models.TextField("Заметки", blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Медкарта"
        verbose_name_plural = "Медкарты"

    def __str__(self):
        return f"Медкарта: {self.pet.name}"


class History(models.Model):
    """История здоровья / процедур / напоминаний."""

    TYPE_CHOICES = (
        ("Вакцинация", "Вакцинация"),
        ("Обработка", "Обработка от паразитов"),
        ("Визит к ветеринару", "Визит к ветеринару"),
        ("Измерение", "Измерение"),
        ("Препарат", "Препарат"),
        ("Другое", "Другое"),
    )

    pet = models.ForeignKey(
        Pet,
        on_delete=models.CASCADE,
        related_name="history",
        verbose_name="Питомец",
    )
    type = models.CharField(
        "Тип",
        max_length=30,
        choices=TYPE_CHOICES,
        default="Другое",
    )
    title = models.CharField("Название", max_length=200)
    date = models.DateField("Дата")
    time = models.TimeField("Время", null=True, blank=True)
    note = models.TextField("Наблюдения и заметки", blank=True)
    vet_conclusion = models.TextField("Заключение ветеринара", blank=True)
    next_date = models.DateField("Следующая дата", null=True, blank=True)
    done = models.BooleanField("Выполнено", default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-id"]
        verbose_name = "Запись истории"
        verbose_name_plural = "История"

    def __str__(self):
        return f"{self.pet.name}: {self.title}"


class Food(models.Model):
    """Запись о питании."""

    STATUS_CHOICES = (
        ("Наблюдать", "Наблюдать"),
        ("Подошло", "Подошло"),
        ("Не подошло", "Не подошло"),
    )
    PREFERENCE_CHOICES = (
        ("Понравилось", "Понравилось"),
        ("Не понравилось", "Не понравилось"),
    )

    pet = models.ForeignKey(
        Pet,
        on_delete=models.CASCADE,
        related_name="food",
        verbose_name="Питомец",
    )
    name = models.CharField("Название корма", max_length=200)
    date = models.DateField("Дата")
    preference = models.CharField(
        "Предпочтение",
        max_length=20,
        choices=PREFERENCE_CHOICES,
        blank=True,
    )
    status = models.CharField(
        "Переносимость",
        max_length=20,
        choices=STATUS_CHOICES,
        default="Наблюдать",
    )
    reaction = models.TextField("Нежелательные реакции", blank=True)
    note = models.TextField("Заметки", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-id"]
        verbose_name = "Корм"
        verbose_name_plural = "Питание"

    def __str__(self):
        return f"{self.pet.name}: {self.name}"


class PushSubscription(models.Model):
    """Подписка браузера на web push. У пользователя их может быть несколько:
    по одной на каждый браузер или устройство."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="push_subscriptions",
        verbose_name="Пользователь",
    )
    # адрес push-сервиса браузера, уникален для каждой подписки
    endpoint = models.URLField("Адрес подписки", max_length=1000, unique=True)
    p256dh = models.CharField("Ключ p256dh", max_length=200)
    auth = models.CharField("Ключ auth", max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Push-подписка"
        verbose_name_plural = "Push-подписки"

    def __str__(self):
        return f"{self.user}: {self.endpoint[:50]}"


class Tamagochi(models.Model):
    """Виртуальный питомец, который гуляет по сайту. У пользователя не больше одного.
    Положение на экране зависит от размера окна, поэтому хранится в браузере."""

    TYPE_CHOICES = (
        ("dog", "Собака"),
        ("cat", "Кот"),
    )

    owner = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="tamagochi",
        verbose_name="Владелец",
    )
    name = models.CharField("Имя", max_length=20)
    type = models.CharField("Тип", max_length=3, choices=TYPE_CHOICES, default="dog")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Тамагочи"
        verbose_name_plural = "Тамагочи"

    def __str__(self):
        return str(self.name)

"""Настройки админки для приложения"""

from django.contrib import admin

from .models import User, Pet, MedCard, Food, History


class AdminUser(admin.ModelAdmin):
    """Модель User для админки"""

    list_display = [
        "phone",
    ]
    search_fields = [
        "phone",
    ]
    list_filter = [
        "phone",
    ]

    class Meta:
        model = User


class AdminPet(admin.ModelAdmin):
    """Модель Pet для админки"""

    list_display = [
        "owner",
        "name",
        "species",
        "breed",
        "birth_date",
        "created_at",
        "updated_at",
    ]
    search_fields = ["owner", "name", "species", "breed"]
    list_filter = [
        "owner",
        "species",
        "breed",
        "birth_date",
        "created_at",
        "updated_at",
    ]

    class Meta:
        model = Pet


class AdminMedcard(admin.ModelAdmin):
    """Модель Medcard для админки"""

    list_display = [
        "pet",
        "weight",
        "allergies",
        "chronic_conditions",
        "notes",
        "updated_at",
    ]
    search_fields = ["pet", "allergies", "chronic_conditions"]
    list_filter = ["pet", "allergies", "chronic_conditions", "updated_at"]

    class Meta:
        model = MedCard


class AdminFood(admin.ModelAdmin):
    """Модель Food для админки"""

    list_display = [
        "pet",
        "name",
        "date",
        "preference",
        "status",
        "reaction",
        "note",
        "created_at",
    ]
    search_fields = ["pet", "name", "preference", "status", "reaction"]
    list_filter = ["pet", "preference", "status", "date"]

    class Meta:
        model = Food


class AdminHistory(admin.ModelAdmin):
    """Модель History для админки"""

    list_display = [
        "pet",
        "type",
        "title",
        "date",
        "time",
        "note",
        "vet_conclusion",
        "next_date",
        "done",
        "created_at",
    ]
    search_fields = ["pet", "type", "title", "note", "created_at"]
    list_filter = ["pet", "type", "created_at", "date", "next_date", "done"]

    class Meta:
        model = History


admin.site.register(User, AdminUser)
admin.site.register(Pet, AdminPet)
admin.site.register(MedCard, AdminMedcard)
admin.site.register(Food, AdminFood)
admin.site.register(History, AdminHistory)

admin.site.site_url = "http://127.0.0.1:8000/user"

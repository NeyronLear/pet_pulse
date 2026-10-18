"""URL-адресация в приложении проекта"""

from django.urls import path

from .views import (
    FoodView,
    HistoryView,
    LoginView,
    LogoutView,
    MainView,
    MedcardView,
    MeView,
    PasswordView,
    PetPhotoView,
    RegisterView,
    TamagochiView,
    test,
)


urlpatterns = [
    path("", MainView.as_view(), name="main"),
    path("pet_photo/<int:pet_id>", PetPhotoView.as_view(), name="pet_photo_point"),
    path("history/<int:pet_id>", HistoryView.as_view(), name="history_point"),
    path("med_card/<int:pet_id>", MedcardView.as_view(), name="med_card_point"),
    path("food/<int:pet_id>", FoodView.as_view(), name="food_point"),
    path("tamagochi", TamagochiView.as_view(), name="tamagochi"),
    path("auth/register", RegisterView.as_view(), name="register"),
    path("auth/login", LoginView.as_view(), name="login"),
    path("auth/logout", LogoutView.as_view(), name="logout"),
    path("auth/me", MeView.as_view(), name="me"),
    path("auth/password", PasswordView.as_view(), name="password"),
    path("test", test, name="test"),
]

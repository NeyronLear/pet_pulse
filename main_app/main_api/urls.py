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
    PushKeyView,
    PushSubscribeView,
    RegisterView,
    PetPhotoView,
    TamagochiView,
    WeightView,
    JudgeLoginView,
    service_worker,
    test,
)

urlpatterns = [
    path("", MainView.as_view(), name="main"),
    path("pet_photo/<int:pet_id>", PetPhotoView.as_view(), name="pet_photo_point"),
    path("history/<int:pet_id>", HistoryView.as_view(), name="history_point"),
    path("med_card/<int:pet_id>", MedcardView.as_view(), name="med_card_point"),
    path("weight/<int:pet_id>", WeightView.as_view(), name="weight_point"),
    path("food/<int:pet_id>", FoodView.as_view(), name="food_point"),
    path("tamagochi", TamagochiView.as_view(), name="tamagochi"),
    path("auth/register", RegisterView.as_view(), name="register"),
    path("auth/login", LoginView.as_view(), name="login"),
    path("auth/judge", JudgeLoginView.as_view(), name="judge_login"),
    path("auth/logout", LogoutView.as_view(), name="logout"),
    path("auth/me", MeView.as_view(), name="me"),
    path("auth/password", PasswordView.as_view(), name="password"),
    path("push/key", PushKeyView.as_view(), name="push_key"),
    path("push/subscribe", PushSubscribeView.as_view(), name="push_subscribe"),
    path("sw.js", service_worker, name="service_worker"),
    path("test", test, name="test"),
]

"""URL-адресация в приложении проекта"""

from django.urls import path

# from .views import MainView, HistoryView, MedcardView, FoodView, CalendarView, test


urlpatterns = [
    """path("", MainView.as_view(), name="main_point"),
    path("history/<int:pet_id>", HistoryView.as_view(), name="history_point"),
    path("med_card/<int:pet_id>", MedcardView.as_view(), name="med_card_point"),
    path("food/<int:pet_id>", FoodView.as_view(), name="food_point"),
    path("calendar/<int:pet_id>", CalendarView.as_view(), name="calendar_point"),
    path("test", test, name="test"),"""
]

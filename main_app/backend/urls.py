"""URL-адресация проекта"""

from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView

urlpatterns = [
    # Сайт всегда открывается с главной страницы приложения
    path("", RedirectView.as_view(pattern_name="main", permanent=False)),
    path("admin/", admin.site.urls),
    path("user/", include("main_api.urls"))
]

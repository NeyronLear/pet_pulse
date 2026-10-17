"""URL-адресация проекта"""

from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("user/", include("main_api.urls"))
]

from django.urls import include, path

urlpatterns = [
    path("api/", include("apps.investigations.urls")),
]

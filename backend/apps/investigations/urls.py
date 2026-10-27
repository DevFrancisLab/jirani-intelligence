from django.urls import path

from apps.investigations import views

urlpatterns = [
    path("health/", views.HealthView.as_view(), name="health"),
    path("status/", views.StatusView.as_view(), name="status"),
    path("connections/", views.ConnectionsView.as_view(), name="connections"),
    path("zetaris/probe/", views.ZetarisProbeView.as_view(), name="zetaris-probe"),
    path(
        "zetaris/sample/taxi-trips/",
        views.ZetarisTaxiSampleView.as_view(),
        name="zetaris-taxi-sample",
    ),
    path("investigations/", views.InvestigationView.as_view(), name="investigations"),
    path("memory/", views.MemoryView.as_view(), name="memory"),
    path(
        "nightshift/cockpit-answer/",
        views.CockpitAnswerView.as_view(),
        name="cockpit-answer",
    ),
]

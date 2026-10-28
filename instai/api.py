"""API routing. Each app contributes its own urls module; everything lives under /api/."""
from django.urls import include, path

urlpatterns = [
    path("", include("instai.core.urls")),
]

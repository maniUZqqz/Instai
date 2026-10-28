"""API routing. Each app contributes its own `api.urlpatterns`; everything lives under /api/."""
from django.urls import include, path

urlpatterns = [
    path("", include("instai.core.urls")),
    path("", include("instai.core.api")),
    path("", include("instai.pages.api")),
    path("", include("instai.styles.api")),
    path("", include("instai.story.api")),
    path("", include("instai.studio.api")),
    path("", include("instai.jobs.api")),
    path("", include("instai.assets.api")),
    path("", include("instai.publishing.api")),
]

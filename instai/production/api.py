"""Phase 3/4 API: every module below contributes its own urlpatterns; this file only gathers them."""
from django.urls import include, path

urlpatterns = [
    path("", include("instai.production.api_voices")),
    path("", include("instai.production.api_rigs")),
    path("", include("instai.production.api_hero")),
]

from django.urls import include, path, re_path

from instai.core import views as core_views

urlpatterns = [
    path("api/", include("instai.api")),
    re_path(r"^media/(?P<path>.+)$", core_views.serve_media),
    re_path(r"^(?!api/|media/|static/).*$", core_views.spa),
]

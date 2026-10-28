from django.apps import AppConfig


class StudioConfig(AppConfig):
    name = "instai.studio"
    label = "studio"

    def ready(self) -> None:
        # register the job handlers (worker, server and tests all import apps); also registers the fake-provider tasks of the studio roles
        from . import jobs  # noqa: F401

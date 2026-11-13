from django.apps import AppConfig


class IdeaBankConfig(AppConfig):
    name = "instai.ideabank"
    label = "ideabank"

    def ready(self) -> None:
        # registers the fake-provider output of the idea generator (tests, demo mode)
        from . import agent  # noqa: F401

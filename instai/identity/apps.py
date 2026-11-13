from django.apps import AppConfig


class IdentityConfig(AppConfig):
    name = "instai.identity"
    label = "identity"

    def ready(self) -> None:
        from . import jobs  # noqa: F401 - registers the job handlers and the fake-provider task of the identity role

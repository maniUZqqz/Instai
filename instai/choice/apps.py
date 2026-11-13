from django.apps import AppConfig


class ChoiceConfig(AppConfig):
    name = "instai.choice"
    label = "choice"

    def ready(self) -> None:
        from . import jobs  # noqa: F401 - registers the job handlers

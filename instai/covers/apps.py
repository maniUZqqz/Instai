from django.apps import AppConfig


class CoversConfig(AppConfig):
    name = "instai.covers"
    label = "covers"

    def ready(self) -> None:
        from . import ideation, jobs  # noqa: F401 - registers the job handler and the fake-provider answer of the cover-ideas task

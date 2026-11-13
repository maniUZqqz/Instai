from django.apps import AppConfig


class ChannelConfig(AppConfig):
    name = "instai.channel"
    label = "channel"

    def ready(self) -> None:
        from . import jobs  # noqa: F401 - registers the job handlers

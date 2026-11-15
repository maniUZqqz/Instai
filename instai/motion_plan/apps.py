from django.apps import AppConfig


class MotionPlanConfig(AppConfig):
    name = "instai.motion_plan"
    label = "motion_plan"

    def ready(self) -> None:
        from . import jobs  # noqa: F401 - registers the job handlers (motion.plan, motion.qa, motion.critique)
        from . import role, critique  # noqa: F401 - register the fake-provider tasks of the roles

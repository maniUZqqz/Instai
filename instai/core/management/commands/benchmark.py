import json

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Phase 0 benchmark. --enqueue queues it for the worker (what START.bat and the UI button do)."

    def add_arguments(self, parser):
        parser.add_argument("--enqueue", action="store_true")
        parser.add_argument("--quick", action="store_true", help="skip the slow video step")

    def handle(self, *args, **opts):
        from instai.core import benchmark

        run = benchmark.enqueue_run({"skip_video": bool(opts["quick"])})
        self.stdout.write(json.dumps({"run_id": run.pk, "status": run.status}))

import os

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Run the InstAI job worker (GPU lane + CPU lanes). START.bat runs this."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="run the queued jobs that are ready, then exit")
        parser.add_argument("--cpu-lanes", type=int, default=int(os.environ.get("INSTAI_WORKER_CPU_THREADS", "2")))

    def handle(self, *args, **opts):
        import time

        from django.db import OperationalError

        from instai.jobs.models import Worker
        from instai.jobs.worker import WorkerRunner

        for _ in range(90):  # the server may still be migrating the database when both are started together
            try:
                Worker.objects.count()
                break
            except OperationalError:
                time.sleep(1)

        runner = WorkerRunner(cpu_lanes=opts["cpu_lanes"])
        if opts["once"]:
            n = runner.drain()
            self.stdout.write(f"ran {n} job(s)")
            return
        self.stdout.write("InstAI worker is running (Ctrl+C to stop)")
        runner.run_forever()

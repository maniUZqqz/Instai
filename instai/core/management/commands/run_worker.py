import os

from django.core.management.base import BaseCommand


def migrations_pending() -> bool:
    """True while the database lacks a table or column a migration adds (the server applies them when it starts)."""
    from django.db import OperationalError, connection
    from django.db.migrations.executor import MigrationExecutor

    try:
        executor = MigrationExecutor(connection)
        return bool(executor.migration_plan(executor.loader.graph.leaf_nodes()))
    except OperationalError:
        return True


def wait_for_database(sleep, tries: int = 90) -> bool:
    """The server may still be migrating when both are started together (after an update, new migrations): wait for ALL of them, not just for the
    first table, otherwise the worker dies on `no such column`. Gives up after `tries` seconds (it then starts anyway and says what is wrong)."""
    for _ in range(tries):
        if not migrations_pending():
            return True
        sleep(1)
    return False


class Command(BaseCommand):
    help = "Run the InstAI job worker (GPU lane + CPU lanes). START.bat runs this."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="run the queued jobs that are ready, then exit")
        parser.add_argument("--cpu-lanes", type=int, default=int(os.environ.get("INSTAI_WORKER_CPU_THREADS", "2")))

    def handle(self, *args, **opts):
        import time

        from instai.jobs.worker import WorkerRunner

        wait_for_database(sleep=time.sleep)

        runner = WorkerRunner(cpu_lanes=opts["cpu_lanes"])
        if opts["once"]:
            n = runner.drain()
            self.stdout.write(f"ran {n} job(s)")
            return
        from instai.version import read_version

        self.stdout.write(f"InstAI worker v{read_version()} is running (Ctrl+C to stop)")
        runner.run_forever()

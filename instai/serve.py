"""Local production-style server (waitress). Started by START.bat:  python -m instai.serve"""
from __future__ import annotations

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "instai.settings")


def main() -> None:
    import django
    from waitress import serve

    django.setup()
    from django.conf import settings
    from django.core.management import call_command

    call_command("migrate", interactive=False, verbosity=0)
    from instai.wsgi import application

    print(f"InstAI is running on http://{settings.HOST}:{settings.PORT}/  (Ctrl+C to stop)", flush=True)
    serve(application, host=settings.HOST, port=settings.PORT, threads=8, ident="instai")


if __name__ == "__main__":
    main()

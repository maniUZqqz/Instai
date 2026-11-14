from django.db import migrations, models


class Migration(migrations.Migration):
    """A job log line may carry a code + parameters (`jobs/logtext.py`) so that the interface renders it in its own language (audit 2026-11-14)."""

    dependencies = [
        ("jobs", "0004_platform_queue"),
    ]

    operations = [
        migrations.AddField(
            model_name="joblog",
            name="code",
            field=models.CharField(blank=True, default="", max_length=40),
        ),
        migrations.AddField(
            model_name="joblog",
            name="params",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]

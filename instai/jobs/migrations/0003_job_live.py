from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("jobs", "0002_pairingcode_workernode_remotetask"),
    ]

    operations = [
        migrations.AddField(
            model_name="job",
            name="live",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]

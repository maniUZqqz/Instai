# Per-episode caption override (render/captions.py): {} = use the page's visual.caption_style.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("story", "0002_episode_studio_episode_translations_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="episode",
            name="caption_style",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]

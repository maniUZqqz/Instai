"""0.16: new pages start at -14 LUFS (what YouTube, Shorts, Reels and TikTok play at). A page made before that has an audio profile saved with the old default
(-16), and one saved even earlier may not carry the number at all - it was filled from the default when read. This migration writes -16 into every audio
profile that lacks it, so nothing changes silently: the page keeps -16 until its owner changes it in the settings."""
from django.db import migrations

LEGACY_LUFS = -16


def pin_legacy(apps, schema_editor):
    Profile = apps.get_model("pages", "SettingsProfile")
    Page = apps.get_model("pages", "ContentPage")
    for page in Page.objects.filter(audio_profile__isnull=True):          # a page without an audio profile row reads the default: give it one at -16
        row = Profile.objects.create(kind="audio", name="", data={"target_lufs": LEGACY_LUFS}, is_template=False)
        Page.objects.filter(pk=page.pk).update(audio_profile=row)
    for row in Profile.objects.filter(kind="audio"):
        data = row.data if isinstance(row.data, dict) else {}
        if "target_lufs" not in data:
            data = {**data, "target_lufs": LEGACY_LUFS}
            Profile.objects.filter(pk=row.pk).update(data=data)


class Migration(migrations.Migration):
    dependencies = [("pages", "0003_alter_contentpage_format")]
    operations = [migrations.RunPython(pin_legacy, migrations.RunPython.noop)]

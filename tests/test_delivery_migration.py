"""Pages made before 0.15 keep -16 LUFS: the data migration pins it (a new page starts at -14). Run on the real migration graph, going back to 0003 and forward again."""
from __future__ import annotations

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

pytestmark = pytest.mark.django_db(transaction=True)

BEFORE = [("pages", "0003_alter_contentpage_format")]
AFTER = [("pages", "0004_keep_legacy_loudness")]


def migrate(targets):
    ex = MigrationExecutor(connection)
    ex.migrate(targets)
    return MigrationExecutor(connection).loader.project_state(targets).apps


def test_every_old_audio_profile_is_pinned_at_minus_16_and_a_page_without_one_gets_one():
    try:
        old = migrate(BEFORE)
        Profile, Page = old.get_model("pages", "SettingsProfile"), old.get_model("pages", "ContentPage")
        saved = Profile.objects.create(kind="audio", data={"target_lufs": -20, "music_enabled": True})        # an owner's own choice stays
        no_key = Profile.objects.create(kind="audio", data={"music_enabled": False})                              # saved before the number was part of the profile
        visual = Profile.objects.create(kind="visual", data={"aspect_ratio": "9:16"})
        with_row = Page.objects.create(name="has audio", languages=["fa"], audio_profile=saved)
        without_row = Page.objects.create(name="no audio profile", languages=["fa"])
        also_without = Page.objects.create(name="visual only", languages=["fa"], visual_profile=visual)
        new = migrate(AFTER)
        Profile, Page = new.get_model("pages", "SettingsProfile"), new.get_model("pages", "ContentPage")
        assert Profile.objects.get(pk=saved.pk).data["target_lufs"] == -20
        assert Profile.objects.get(pk=no_key.pk).data["target_lufs"] == -16 and Profile.objects.get(pk=no_key.pk).data["music_enabled"] is False
        assert "target_lufs" not in Profile.objects.get(pk=visual.pk).data
        for pk in (without_row.pk, also_without.pk):
            row = Page.objects.get(pk=pk).audio_profile
            assert row is not None and row.kind == "audio" and row.data == {"target_lufs": -16}
        assert Page.objects.get(pk=with_row.pk).audio_profile_id == saved.pk
    finally:
        migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())            # leave the test database at the newest state for every other test


def test_after_the_migration_an_old_page_reads_minus_16_and_a_new_one_minus_14():
    from instai.pages.models import ContentPage, SettingsProfile

    old = ContentPage.objects.create(name="old", languages=["fa"])
    old.set_profile("audio", {"target_lufs": -16})
    fresh = ContentPage.objects.create(name="fresh", languages=["fa"])
    assert old.profile("audio")["target_lufs"] == -16 and fresh.profile("audio")["target_lufs"] == -14
    assert SettingsProfile(kind="audio", data={}).data == {} and SettingsProfile.objects.create(kind="audio", data={}).data["target_lufs"] == -14

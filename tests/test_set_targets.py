from pathlib import Path

from metadata_collector.audio_tags import diff_metadata
from metadata_collector.models import AudioFileMetadata


def test_target_fields_are_diffable_workflow_tags():
    current = AudioFileMetadata('/tmp/book.mp3', target_bitrate=64, target_channels=1, dramatic_audio=False)

    assert diff_metadata(current, {'target_bitrate': 128, 'target_channels': 2, 'dramatic_audio': True}) == {
        'target_bitrate': 128,
        'target_channels': 2,
        'dramatic_audio': True,
    }


def test_set_targets_ui_uses_required_labels_and_source_type():
    app_source = Path('metadata_collector/app.py').read_text()

    assert "ft.Button('Set Targets'" in app_source
    assert "Set Targets and Dramatic Audio" in app_source
    assert "source_type='set_targets'" in app_source
    assert "Saving target settings..." in app_source
    assert "Target settings saved." in app_source

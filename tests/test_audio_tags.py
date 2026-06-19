from mutagen.mp4 import MP4FreeForm

from metadata_collector.audio_tags import diff_metadata, normalize_tag_value, write_audio_metadata
from metadata_collector.models import AudioFileMetadata


def test_normalize_tag_value_bytes():
    assert normalize_tag_value(b'B07VBGXJT2') == 'B07VBGXJT2'


def test_normalize_tag_value_list_of_bytes():
    assert normalize_tag_value([b'One', b'Two']) == 'One, Two'


def test_normalize_tag_value_mp4_freeform():
    assert normalize_tag_value(MP4FreeForm(b'An Agent Zero Spy Thriller')) == 'An Agent Zero Spy Thriller'


def test_normalize_tag_value_list_containing_mp4_freeform():
    assert normalize_tag_value([MP4FreeForm(b'An Agent Zero Spy Thriller')]) == 'An Agent Zero Spy Thriller'


def test_normalize_tag_value_string():
    assert normalize_tag_value('A Normal Title') == 'A Normal Title'


def test_normalize_tag_value_list_of_strings():
    assert normalize_tag_value(['One', 'Two']) == 'One, Two'


def test_diff_metadata_excludes_non_writable_duration_fields():
    current = AudioFileMetadata('/tmp/book.mp3', duration=100, has_cover=False, cover_data_uri='data:image/jpeg;base64,a', title='Old')
    updates = {'duration': 200, 'has_cover': True, 'cover_data_uri': 'data:image/jpeg;base64,b', 'title': 'New'}

    assert diff_metadata(current, updates) == {'title': 'New'}


def test_write_audio_metadata_filters_non_writable_fields_before_tag_writes(monkeypatch):
    class FakeTags(dict):
        def setall(self, key, values):
            self[key] = values

    class FakeAudio:
        def __init__(self):
            self.tags = FakeTags()
            self.saved = False

        def save(self):
            self.saved = True

    fake_audio = FakeAudio()
    monkeypatch.setattr('metadata_collector.audio_tags.File', lambda path, easy=False: fake_audio)

    write_audio_metadata('/tmp/book.mp3', {'duration': 200, 'has_cover': True, 'title': 'New'})

    assert 'TIT2' in fake_audio.tags
    assert 'TXXX:DURATION' not in fake_audio.tags
    assert 'TXXX:HAS_COVER' not in fake_audio.tags
    assert fake_audio.saved is True

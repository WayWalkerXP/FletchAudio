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

JPEG_BYTES = b'\xff\xd8\xff\xe0fake-jpeg\xff\xd9'
PNG_BYTES = b'\x89PNG\r\n\x1a\nfake-png'


def _mock_cover_download(monkeypatch, data=JPEG_BYTES, content_type='image/jpeg'):
    class Response:
        content = data
        headers = {'Content-Type': content_type}

        def raise_for_status(self):
            return None

    monkeypatch.setattr('metadata_collector.audio_tags.requests.get', lambda url, timeout: Response())


def test_write_audio_metadata_inserts_mp3_cover(monkeypatch):
    from mutagen.id3 import ID3

    class FakeAudio:
        def __init__(self):
            self.tags = ID3()
            self.saved = False

        def save(self):
            self.saved = True

    fake_audio = FakeAudio()
    monkeypatch.setattr('metadata_collector.audio_tags.File', lambda path, easy=False: fake_audio)
    _mock_cover_download(monkeypatch)

    write_audio_metadata('/tmp/book.mp3', {'cover_url': 'https://example.test/cover.jpg'})

    frames = fake_audio.tags.getall('APIC')
    assert len(frames) == 1
    assert frames[0].data == JPEG_BYTES
    assert frames[0].mime == 'image/jpeg'
    assert fake_audio.saved is True


def test_write_audio_metadata_replaces_existing_mp3_cover(monkeypatch):
    from mutagen.id3 import APIC, ID3

    class FakeAudio:
        def __init__(self):
            self.tags = ID3()
            self.tags.add(APIC(encoding=3, mime='image/jpeg', type=3, desc='Old', data=b'old'))
            self.saved = False

        def save(self):
            self.saved = True

    fake_audio = FakeAudio()
    monkeypatch.setattr('metadata_collector.audio_tags.File', lambda path, easy=False: fake_audio)
    _mock_cover_download(monkeypatch, PNG_BYTES, 'image/png')

    write_audio_metadata('/tmp/book.mp3', {'cover_url': 'https://example.test/cover.png'})

    frames = fake_audio.tags.getall('APIC')
    assert len(frames) == 1
    assert frames[0].data == PNG_BYTES
    assert frames[0].mime == 'image/png'
    assert fake_audio.saved is True


def test_write_audio_metadata_inserts_mp4_cover(monkeypatch):
    import metadata_collector.audio_tags as audio_tags
    from mutagen.mp4 import MP4Cover

    class FakeMP4(audio_tags.MP4):
        def __init__(self):
            self.tags = {}
            self.saved = False

        def save(self):
            self.saved = True

    fake_audio = FakeMP4()
    monkeypatch.setattr('metadata_collector.audio_tags.File', lambda path, easy=False: fake_audio)
    _mock_cover_download(monkeypatch, PNG_BYTES, 'image/png')

    write_audio_metadata('/tmp/book.m4b', {'cover_url': 'https://example.test/cover.png'})

    covers = fake_audio.tags['covr']
    assert len(covers) == 1
    assert bytes(covers[0]) == PNG_BYTES
    assert covers[0].imageformat == MP4Cover.FORMAT_PNG
    assert fake_audio.saved is True


def test_write_audio_metadata_replaces_existing_mp4_cover(monkeypatch):
    import metadata_collector.audio_tags as audio_tags
    from mutagen.mp4 import MP4Cover

    class FakeMP4(audio_tags.MP4):
        def __init__(self):
            self.tags = {'covr': [MP4Cover(b'old', imageformat=MP4Cover.FORMAT_JPEG)]}
            self.saved = False

        def save(self):
            self.saved = True

    fake_audio = FakeMP4()
    monkeypatch.setattr('metadata_collector.audio_tags.File', lambda path, easy=False: fake_audio)
    _mock_cover_download(monkeypatch)

    write_audio_metadata('/tmp/book.m4b', {'cover_url': 'https://example.test/cover.jpg'})

    covers = fake_audio.tags['covr']
    assert len(covers) == 1
    assert bytes(covers[0]) == JPEG_BYTES
    assert covers[0].imageformat == MP4Cover.FORMAT_JPEG
    assert fake_audio.saved is True


def test_format_genres_for_tag_list_of_genres():
    from metadata_collector.audio_tags import format_genres_for_tag

    assert format_genres_for_tag(['Literature & Fiction', 'Action & Adventure', 'Mystery, Thriller & Suspense']) == 'Literature & Fiction\\\\Action & Adventure\\\\Mystery, Thriller & Suspense'


def test_format_genres_for_tag_tuple_of_genres():
    from metadata_collector.audio_tags import format_genres_for_tag

    assert format_genres_for_tag(('One', 'Two')) == 'One\\\\Two'


def test_format_genres_for_tag_list_with_duplicates():
    from metadata_collector.audio_tags import format_genres_for_tag

    assert format_genres_for_tag(['One', 'Two', 'One', 'Two']) == 'One\\\\Two'


def test_format_genres_for_tag_list_with_empty_values():
    from metadata_collector.audio_tags import format_genres_for_tag

    assert format_genres_for_tag([' One ', '', None, '  ', 'Two']) == 'One\\\\Two'


def test_format_genres_for_tag_already_formatted_string():
    from metadata_collector.audio_tags import format_genres_for_tag

    assert format_genres_for_tag('One\\\\Two') == 'One\\\\Two'


def test_format_genres_for_tag_upgrades_single_backslash_string():
    from metadata_collector.audio_tags import format_genres_for_tag

    assert format_genres_for_tag('One\\Two') == 'One\\\\Two'


def test_format_genres_for_tag_python_list_looking_string():
    from metadata_collector.audio_tags import format_genres_for_tag

    assert format_genres_for_tag("['Literature & Fiction', 'Action & Adventure', 'Mystery, Thriller & Suspense']") == 'Literature & Fiction\\\\Action & Adventure\\\\Mystery, Thriller & Suspense'


def test_diff_metadata_formats_genre_updates():
    assert diff_metadata(AudioFileMetadata('/tmp/book.mp3', genres=[]), {'genres': ['One', 'Two']}) == {'genres': 'One\\\\Two'}


def test_write_audio_metadata_formats_mp3_genres(monkeypatch):
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

    write_audio_metadata('/tmp/book.mp3', {'genres': ['One', 'Two']})

    assert fake_audio.tags['TCON'][0].text == ['One\\\\Two']

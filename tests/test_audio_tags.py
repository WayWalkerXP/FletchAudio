from mutagen.mp4 import MP4FreeForm

from metadata_collector.audio_tags import normalize_tag_value


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

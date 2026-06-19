from metadata_collector.mass_update import preview_mass_update
from metadata_collector.models import AudioFileMetadata

def test_mass_update_placeholder_formatting():
    f=AudioFileMetadata(path='/books/Book/ch1.m4b', track=1, album='Album', author='Auth')
    assert preview_mass_update([f], 'title', 'Chapter %track% - %filename% - %folder%')[0]['new_value']=='Chapter 1 - ch1 - Book'

def test_zero_padded_track_formatting():
    f=AudioFileMetadata(path='/b/ch1.m4b', track=3)
    assert preview_mass_update([f], 'title', 'Chapter %track:02%')[0]['new_value']=='Chapter 03'

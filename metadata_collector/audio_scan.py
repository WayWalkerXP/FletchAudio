import logging
import os

LOGGER = logging.getLogger(__name__)

from .audio_tags import read_audio_metadata
from .models import Book
from .utils import stable_book_key

SUPPORTED_EXTENSIONS={'.m4b','.m4a','.mp3','.flac','.ogg','.opus','.aac'}
def is_audio_file(path): return os.path.splitext(path)[1].lower() in SUPPORTED_EXTENSIONS


def _read_audio_files(folder: str, filenames: list[str], errors: list[str]):
    metas=[]
    for name in sorted(filenames):
        path=os.path.join(folder,name)
        if not is_audio_file(path): continue
        try:
            metas.append(read_audio_metadata(path))
        except Exception as e:
            LOGGER.warning('Skipping %s during audio scan: %s', path, e, exc_info=True)
            errors.append(f'{path}: {e}')
    return metas


def scan_directory(root: str):
    books=[]; errors=[]
    root=os.path.abspath(root)
    for cur, dirs, files in os.walk(root, onerror=lambda e: errors.append(str(e))):
        dirs.sort()
        metas=_read_audio_files(cur, files, errors)
        if cur == root or len(metas) == 1:
            for m in metas:
                books.append(Book(stable_book_key(m.path), m.path, False, [m]))
        elif len(metas) > 1:
            books.append(Book(stable_book_key(cur), cur, True, metas))
    return books, errors

import logging
import os
import struct

import mutagen
from mutagen.mp4 import MP4MetadataError

LOGGER = logging.getLogger(__name__)

from .audio_tags import read_audio_metadata
from .models import Book
from .utils import stable_book_key

SUPPORTED_EXTENSIONS={'.m4b','.m4a','.mp3','.flac','.ogg','.opus','.aac'}
def is_audio_file(path): return os.path.splitext(path)[1].lower() in SUPPORTED_EXTENSIONS


def _read_audio_files(folder: str, filenames: list[str], errors: list[str], progress_callback=None, processed: int = 0, total: int = 0):
    metas=[]
    for name in sorted(filenames):
        path=os.path.join(folder,name)
        if not is_audio_file(path):
            continue
        try:
            metas.append(read_audio_metadata(path))
        except (mutagen.MutagenError, MP4MetadataError, struct.error, Exception) as e:
            LOGGER.warning(
                'Audio scan warning: %s: %s',
                path,
                e,
                exc_info=LOGGER.isEnabledFor(logging.DEBUG),
            )
            errors.append(f'{path}: {e}')
        finally:
            processed += 1
            if progress_callback:
                progress_callback(processed, total, path)
    return metas, processed


def scan_directory(root: str, progress_callback=None):
    books=[]; errors=[]
    root=os.path.abspath(root)
    discovered=[]
    for cur, dirs, files in os.walk(root, onerror=lambda e: errors.append(str(e))):
        dirs.sort()
        discovered.append((cur, sorted(files)))
    total=sum(1 for cur, files in discovered for name in files if is_audio_file(os.path.join(cur, name)))
    if progress_callback:
        progress_callback(0, total, None)
    processed=0
    for cur, files in discovered:
        metas, processed=_read_audio_files(cur, files, errors, progress_callback, processed, total)
        if cur == root or len(metas) == 1:
            for m in metas:
                books.append(Book(stable_book_key(m.path), m.path, False, [m]))
        elif len(metas) > 1:
            books.append(Book(stable_book_key(cur), cur, True, metas))
    return books, errors

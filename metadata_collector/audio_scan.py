import os
from collections import defaultdict
from .audio_tags import read_audio_metadata
from .models import Book
from .utils import stable_book_key
SUPPORTED_EXTENSIONS={'.m4b','.m4a','.mp3','.flac','.ogg','.opus','.aac'}
def is_audio_file(path): return os.path.splitext(path)[1].lower() in SUPPORTED_EXTENSIONS
def scan_directory(root: str):
    by_dir=defaultdict(list); errors=[]
    for cur, dirs, files in os.walk(root, onerror=lambda e: errors.append(str(e))):
        for name in sorted(files):
            path=os.path.join(cur,name)
            if not is_audio_file(path): continue
            try: by_dir[cur].append(read_audio_metadata(path))
            except Exception as e: errors.append(f'{path}: {e}')
    books=[]
    for folder, metas in sorted(by_dir.items()):
        if len(metas)>1: books.append(Book(stable_book_key(folder), folder, True, metas))
        else:
            m=metas[0]; books.append(Book(stable_book_key(m.path), m.path, False, [m]))
    return books, errors

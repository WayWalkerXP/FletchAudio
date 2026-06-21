import os, re
SUPPORTED_TARGETS={'title','album','track','disc','narrator','series','description','author','asin'}
def _value(meta, name):
    if name=='filename': return os.path.splitext(os.path.basename(meta.path))[0]
    if name=='folder': return os.path.basename(os.path.dirname(meta.path))
    if name=='series_part': name='series_sequence'
    return getattr(meta, name, None)
def format_pattern(pattern: str, meta) -> str:
    def repl(m):
        key,width=m.group(1),m.group(2)
        val=_value(meta,key)
        if val is None: val=''
        if width:
            try: return f'{int(val):0{int(width)}d}'
            except Exception: return str(val)
        return str(val)
    return re.sub(r'%([a-z_]+)(?::0(\d+))?%', repl, pattern)
def preview_mass_update(files, target_tag: str, pattern: str):
    if target_tag not in SUPPORTED_TARGETS: raise ValueError(f'Unsupported target tag: {target_tag}')
    return [{'path':f.path,'old_value':getattr(f,target_tag,None),'new_value':format_pattern(pattern,f)} for f in files]

from dataclasses import dataclass
from pathlib import Path
import logging

from .audio_scan import is_audio_file
from .audio_tags import read_audio_metadata, write_audio_metadata
from mutagen import File
from mutagen.mp4 import MP4

LOGGER = logging.getLogger(__name__)
IGNORED_FOLDER_BOOK_FILES = {'metadata.yaml', 'metadata.yml', '__skipped__.txt'}


@dataclass
class MassUpdateTrackRow:
    path: Path
    filename: str
    original_track: str
    original_title: str
    track: str
    title: str
    selected: bool = True
    readable: bool = True
    error: str = ''

    @property
    def changed(self) -> bool:
        return self.track != self.original_track or self.title != self.original_title


def _string_value(value) -> str:
    return '' if value is None else str(value)


def read_track_text(path: Path) -> str:
    """Return the user-facing track tag exactly when the container stores text.

    ID3/Vorbis-style tags can store values such as ``01`` as text.  The main
    metadata reader normalizes tracks for other screens, but Mass Update edits
    track values as text and must preserve leading zeroes.  MP4 track tags are
    numeric tuples, so there is no padding to recover from the file itself.
    """
    audio = File(str(path), easy=False)
    if not audio or not audio.tags:
        return ''
    if isinstance(audio, MP4):
        track = (audio.tags.get('trkn') or [(None, None)])[0][0]
        return _string_value(track)
    for key in ('TRCK', 'TRACKNUMBER', 'tracknumber'):
        value = audio.tags.get(key)
        if value is not None:
            return _string_value(value).split('/', 1)[0]
    return ''

_TRACK_SEPARATORS = {' ', '-', '_', '.'}


def track_sort_key(value: str) -> tuple[int, int | str]:
    value = (value or '').strip()
    try:
        return (0, int(value))
    except ValueError:
        return (1, value.casefold())


def format_track_number(track_number: int, width: int) -> str:
    return f'{track_number:0{max(2, width)}d}'


def guess_track_number_from_filename(filename: str) -> int | None:
    base_name = os.path.basename(filename or '')
    stem, extension = os.path.splitext(base_name)
    if not stem and extension:
        stem = base_name
    candidate = stem
    if candidate.startswith('['):
        closing = candidate.find(']')
        if closing > 1:
            candidate = candidate[1:closing]
        else:
            return None
    elif candidate.startswith('('):
        closing = candidate.find(')')
        if closing > 1:
            candidate = candidate[1:closing]
        else:
            return None
    else:
        end = len(candidate)
        for index, char in enumerate(candidate):
            if char in _TRACK_SEPARATORS:
                end = index
                break
        candidate = candidate[:end]
    candidate = candidate.strip()
    if not candidate.isdigit():
        return None
    track_number = int(candidate)
    return track_number if track_number > 0 else None




def _normalize_book_chapter_title(title: str) -> str:
    return re.sub(r'\b(Book\s+\d+)\s+(Chapter\s+\d+)\b', r'\1, \2', title, flags=re.IGNORECASE)


def _starts_with_track_or_chapter_marker(title: str) -> bool:
    return bool(
        re.match(r'^\d+\s*[-_. ]+\S', title)
        or re.match(r'^Chapter\s+\d+\b', title, flags=re.IGNORECASE)
        or re.match(r'^Book\s+\d+\s+Chapter\s+\d+\b', title, flags=re.IGNORECASE)
        or re.match(r'^Part\s+\d+\b', title, flags=re.IGNORECASE)
    )


def guess_title_from_filename(filename: str) -> str | None:
    base_name = os.path.basename(filename or '')
    stem, extension = os.path.splitext(base_name)
    if not stem and extension:
        stem = base_name
    stem = stem.strip()
    if not stem:
        return None
    if stem.isdigit() or re.match(r'^[\[(]\s*\d+\s*[\])]\s*[-_. ]*$', stem):
        return None

    bracketed_match = re.match(r'^\s*[\[(]\s*\d+\s*[\])]\s*[-_. ]*\s*(.+)$', stem)
    if bracketed_match:
        title = bracketed_match.group(1).strip(' -_.\t')
        return _normalize_book_chapter_title(title) or None

    numeric_match = re.match(r'^\s*\d+\s*[-_. ]+\s*(.+)$', stem)
    if numeric_match:
        title = numeric_match.group(1).strip(' -_.\t')
        return _normalize_book_chapter_title(title) or None

    if ' - ' in stem:
        _prefix, _separator, right_side = stem.partition(' - ')
        title = right_side.strip()
        if title and _starts_with_track_or_chapter_marker(title):
            return _normalize_book_chapter_title(title) or None

    title = _normalize_book_chapter_title(stem)
    return title or None


def discover_folder_book_tracks(folder_path) -> list[MassUpdateTrackRow]:
    folder = Path(folder_path).expanduser()
    rows: list[MassUpdateTrackRow] = []
    for child in sorted(folder.iterdir(), key=lambda item: item.name.casefold()):
        if not child.is_file():
            continue
        if child.name in IGNORED_FOLDER_BOOK_FILES or not is_audio_file(str(child)):
            continue
        try:
            metadata = read_audio_metadata(str(child))
            track = read_track_text(child)
            if track == '':
                track = _string_value(metadata.track)
            rows.append(MassUpdateTrackRow(child, child.name, track, _string_value(metadata.title), track, _string_value(metadata.title)))
        except Exception as exc:
            LOGGER.warning('Mass Update unreadable audio file %s: %s', child, exc, exc_info=True)
            rows.append(MassUpdateTrackRow(child, child.name, '', '', '', '', readable=False, error=str(exc)))
    return rows


def changed_track_title_rows(rows: list[MassUpdateTrackRow]) -> list[MassUpdateTrackRow]:
    return [row for row in rows if row.readable and row.changed]


def save_track_title_rows(rows: list[MassUpdateTrackRow]) -> tuple[int, int, list[tuple[MassUpdateTrackRow, str]]]:
    successes = 0
    failures: list[tuple[MassUpdateTrackRow, str]] = []
    changed_rows = changed_track_title_rows(rows)
    for row in changed_rows:
        try:
            write_audio_metadata(str(row.path), {'track': row.track, 'title': row.title})
            row.original_track = row.track
            row.original_title = row.title
            successes += 1
        except Exception as exc:
            LOGGER.warning('Mass Update failed to save %s: %s', row.path, exc, exc_info=True)
            failures.append((row, str(exc)))
    unchanged = len([row for row in rows if row.readable]) - successes - len(failures)
    return successes, unchanged, failures

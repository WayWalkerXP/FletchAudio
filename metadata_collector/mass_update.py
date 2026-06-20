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

LOGGER = logging.getLogger(__name__)
IGNORED_FOLDER_BOOK_FILES = {'metadata.yaml', 'metadata.yml', '__skipped__.txt'}


@dataclass
class MassUpdateTrackRow:
    path: Path
    filename: str
    track: str
    title: str
    selected: bool = True
    readable: bool = True
    error: str = ''


def _string_value(value) -> str:
    return '' if value is None else str(value)

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
            rows.append(MassUpdateTrackRow(child, child.name, _string_value(metadata.track), _string_value(metadata.title)))
        except Exception as exc:
            LOGGER.warning('Mass Update unreadable audio file %s: %s', child, exc, exc_info=True)
            rows.append(MassUpdateTrackRow(child, child.name, '', '', readable=False, error=str(exc)))
    return rows


def save_track_title_rows(rows: list[MassUpdateTrackRow]) -> tuple[int, list[tuple[MassUpdateTrackRow, str]]]:
    successes = 0
    failures: list[tuple[MassUpdateTrackRow, str]] = []
    for row in rows:
        try:
            write_audio_metadata(str(row.path), {'track': row.track, 'title': row.title})
            successes += 1
        except Exception as exc:
            LOGGER.warning('Mass Update failed to save %s: %s', row.path, exc, exc_info=True)
            failures.append((row, str(exc)))
    return successes, failures

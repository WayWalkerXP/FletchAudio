from __future__ import annotations
import ast
import base64
import re
import requests

from mutagen import File
from mutagen.id3 import ID3, APIC, TIT2, TALB, TPE1, TPE2, TCOM, TCON, TDRC, TPUB, COMM, TXXX, TRCK, TPOS
from mutagen.mp4 import MP4, MP4Cover, MP4FreeForm
from .models import AudioFileMetadata

NON_WRITABLE_FIELDS = {'duration', 'has_cover', 'cover_data_uri'}


def format_genres_for_tag(genres) -> str | None:
    def normalize_many(values):
        out = []
        seen = set()
        for item in values:
            if item is None:
                continue
            text = str(item).strip()
            if not text or text in seen:
                continue
            out.append(text)
            seen.add(text)
        return "\\\\".join(out) or None

    if genres is None:
        return None
    if isinstance(genres, (list, tuple)):
        return normalize_many(genres)
    if isinstance(genres, str):
        text = genres.strip()
        if not text:
            return None
        if text.startswith('[') and text.endswith(']'):
            try:
                parsed = ast.literal_eval(text)
            except (SyntaxError, ValueError):
                return genres
            if isinstance(parsed, (list, tuple)):
                return normalize_many(parsed)
        return re.sub(r'\\+', r'\\\\', text)
    return str(genres).strip() or None


def normalize_tag_value(value):
    if value is None:
        return None
    if isinstance(value, MP4FreeForm):
        try:
            return bytes(value).decode('utf-8', errors='replace')
        except Exception:
            try:
                return value.decode('utf-8', errors='replace')
            except Exception:
                return str(value)
    if isinstance(value, bytes):
        return value.decode('utf-8', errors='replace')
    if isinstance(value, (list, tuple)):
        values=[]
        for item in value:
            normalized=normalize_tag_value(item)
            if normalized not in (None, ''):
                values.append(normalized)
        if not values:
            return None
        if len(values)==1:
            return values[0]
        return ', '.join(str(item) for item in values)
    if hasattr(value, 'text'):
        return normalize_tag_value(value.text)
    return str(value)


def _first(v):
    if isinstance(v, list): return v[0] if v else None
    return v

def _int_part(v):
    try:
        normalized=normalize_tag_value(_first(v))
        return int(normalized.split('/')[0]) if normalized else None
    except Exception: return None

def _text(tags,*keys):
    for k in keys:
        if tags and k in tags:
            return normalize_tag_value(tags[k])
    return None



def _mime_from_image_data(data, fallback=None):
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image/png'
    if data.startswith(b'\xff\xd8\xff'):
        return 'image/jpeg'
    return fallback or 'image/jpeg'

def _cover_format(mime_type):
    return MP4Cover.FORMAT_PNG if mime_type == 'image/png' else MP4Cover.FORMAT_JPEG

def _download_cover(url):
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    data = response.content
    if not data:
        raise ValueError('Downloaded cover image was empty')
    content_type = (response.headers.get('Content-Type') or '').split(';', 1)[0].strip().lower()
    if content_type not in {'image/jpeg', 'image/jpg', 'image/png'}:
        content_type = _mime_from_image_data(data)
    if content_type == 'image/jpg':
        content_type = 'image/jpeg'
    return data, content_type

def _data_uri(data, mime_type):
    if not data:
        return None
    return f'data:{mime_type};base64,{base64.b64encode(bytes(data)).decode("ascii")}'

def _mp4_cover_data_uri(tags):
    covers = tags.get('covr') if tags else None
    if not covers:
        return None
    cover = covers[0]
    mime_type = 'image/png' if getattr(cover, 'imageformat', None) == MP4Cover.FORMAT_PNG else 'image/jpeg'
    return _data_uri(cover, mime_type)

def _id3_cover_data_uri(tags):
    if not tags:
        return None
    for key, frame in tags.items():
        if str(key).startswith('APIC') and getattr(frame, 'data', None):
            return _data_uri(frame.data, getattr(frame, 'mime', None) or 'image/jpeg')
    return None

def read_audio_metadata(path: str) -> AudioFileMetadata:
    audio=File(path, easy=False)
    m=AudioFileMetadata(path=path)
    if not audio: return m
    tags=audio.tags or {}
    m.duration=int(getattr(getattr(audio,'info',None),'length',0) or 0) or None
    if isinstance(audio, MP4):
        m.title=_text(tags,'©nam'); m.album=_text(tags,'©alb'); m.author=_text(tags,'©ART'); m.albumartist=_text(tags,'aART')
        m.narrator=_text(tags,'©wrt','----:com.apple.iTunes:NARRATOR'); m.description=_text(tags,'desc','©cmt')
        m.publisher=_text(tags,'----:com.apple.iTunes:PUBLISHER'); m.published_date=_text(tags,'©day'); m.published_year=(m.published_date or '')[:4] or None
        m.language=_text(tags,'----:com.apple.iTunes:LANGUAGE'); m.series=_text(tags,'----:com.apple.iTunes:SERIES'); m.series_sequence=_text(tags,'----:com.apple.iTunes:SERIES-PART','----:com.apple.iTunes:series_part')
        m.asin=_text(tags,'----:com.apple.iTunes:ASIN'); genre=normalize_tag_value(tags.get('©gen')); m.genres=genre.split(', ') if genre else []; m.track=(tags.get('trkn') or [(None,None)])[0][0]; m.disc=(tags.get('disk') or [(None,None)])[0][0]
        m.has_cover='covr' in tags; m.cover_data_uri=_mp4_cover_data_uri(tags); m.dramatic_audio=(_text(tags,'----:com.apple.iTunes:dramatic_audio') or '').lower()=='true'
    else:
        m.title=_text(tags,'TIT2'); m.album=_text(tags,'TALB'); m.author=_text(tags,'TPE1'); m.albumartist=_text(tags,'TPE2'); m.narrator=_text(tags,'TCOM') or _text(tags,'TXXX:NARRATOR')
        m.description=_text(tags,'COMM::XXX','COMM'); m.publisher=_text(tags,'TPUB'); m.published_date=_text(tags,'TDRC'); m.published_year=(m.published_date or '')[:4] or None
        m.language=_text(tags,'TLAN'); m.series=_text(tags,'TXXX:SERIES'); m.series_sequence=_text(tags,'TXXX:SERIES-PART','TXXX:series_part'); m.asin=_text(tags,'TXXX:ASIN')
        g=_text(tags,'TCON'); m.genres=g.split(', ') if g else []; m.track=_int_part(_text(tags,'TRCK')); m.disc=_int_part(_text(tags,'TPOS')); m.has_cover=any(str(k).startswith('APIC') for k in tags.keys()); m.cover_data_uri=_id3_cover_data_uri(tags)
    return m

def diff_metadata(current: AudioFileMetadata, updates: dict) -> dict:
    normalized_updates = dict(updates)
    if 'genres' in normalized_updates:
        normalized_updates['genres'] = format_genres_for_tag(normalized_updates['genres'])
    return {k:v for k,v in normalized_updates.items() if k not in NON_WRITABLE_FIELDS and v not in (None, []) and hasattr(current,k) and (format_genres_for_tag(getattr(current,k)) if k == 'genres' else getattr(current,k))!=v}

def write_audio_metadata(path: str, updates: dict):
    updates={k:(format_genres_for_tag(v) if k == 'genres' else v) for k,v in updates.items() if k not in NON_WRITABLE_FIELDS}
    if not updates:
        return
    audio=File(path, easy=False)
    if audio is None: raise ValueError(f'Unsupported audio file: {path}')
    if isinstance(audio, MP4):
        tags=audio.tags or {}; audio.tags=tags
        mapping={'title':'©nam','album':'©alb','author':'©ART','albumartist':'aART','narrator':'©wrt','description':'desc','published_date':'©day','genres':'©gen'}
        for k,v in updates.items():
            if k == 'cover_url':
                cover_data, mime_type = _download_cover(str(v))
                tags['covr'] = [MP4Cover(cover_data, imageformat=_cover_format(mime_type))]
            elif k in mapping: tags[mapping[k]]=v if isinstance(v,list) else [str(v)]
            elif k in {'series','series_sequence','asin','publisher','language','explicit','dramatic_audio'}: tags[f'----:com.apple.iTunes:{k.upper()}']=[MP4FreeForm(str(v).encode())]
            elif k=='track': tags['trkn']=[(int(v),0)]
            elif k=='disc': tags['disk']=[(int(v),0)]
    else:
        if audio.tags is None: audio.add_tags()
        tags=audio.tags
        frame={'title':TIT2,'album':TALB,'author':TPE1,'albumartist':TPE2,'narrator':TCOM,'publisher':TPUB,'published_date':TDRC,'genres':TCON,'track':TRCK,'disc':TPOS}
        for k,v in updates.items():
            if k == 'cover_url':
                cover_data, mime_type = _download_cover(str(v))
                tags.delall('APIC')
                tags.add(APIC(encoding=3, mime=mime_type, type=3, desc='Cover', data=cover_data))
            elif k in frame: tags.setall(frame[k].__name__, [frame[k](encoding=3, text=[str(v)])])
            elif k=='description': tags.setall('COMM',[COMM(encoding=3, lang='XXX', desc='', text=str(v))])
            else: tags.setall(f'TXXX:{k.upper()}', [TXXX(encoding=3, desc=k.upper(), text=[str(v)])])
    audio.save()

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests


DUPLICATE_STATUS_DUPLICATE = 'duplicate'
DUPLICATE_STATUS_NO_DUPLICATE = 'no_duplicate'
DUPLICATE_STATUS_NO_ASIN = 'no_asin'
DUPLICATE_STATUS_ERROR = 'error'


class AbsConnectionError(RuntimeError):
    """Raised when Audiobookshelf cannot be reached or rejects authentication."""


class AbsApiEndpointError(AbsConnectionError):
    """Raised when an expected Audiobookshelf API endpoint is unavailable."""


@dataclass
class DuplicateCheckStatus:
    source_path: Path
    asin: str | None
    status: str
    match_count: int = 0
    message: str = ''


def normalize_asin_for_duplicate_check(value: str | None) -> str:
    return (value or '').strip().casefold()


def _headers(api_key: str) -> dict[str, str]:
    # Audiobookshelf accepts bearer auth for API tokens; x-api-key is included for compatibility.
    return {'Authorization': f'Bearer {api_key}', 'x-api-key': api_key}


def _abs_get(abs_url: str, api_key: str, endpoint: str, params: dict[str, Any] | None = None, timeout: int = 15) -> Any:
    base = abs_url.rstrip('/') + '/'
    response = requests.get(urljoin(base, endpoint.lstrip('/')), headers=_headers(api_key), params=params or {}, timeout=timeout)
    if response.status_code in {401, 403}:
        raise AbsConnectionError('Audiobookshelf authentication failed.')
    if response.status_code == 404:
        safe_url = response.url.split('?', 1)[0] if getattr(response, 'url', None) else urljoin(base, endpoint.lstrip('/'))
        raise AbsApiEndpointError(f'404 Not Found for {safe_url}')
    if response.status_code >= 500:
        raise AbsConnectionError('Audiobookshelf server is unavailable.')
    response.raise_for_status()
    return response.json()


def _walk_dicts(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_dicts(child)


def _dict_matches_asin(item: dict[str, Any], normalized_asin: str) -> bool:
    candidate_keys = ('asin', 'audibleAsin', 'audible_asin')
    for key in candidate_keys:
        if normalize_asin_for_duplicate_check(item.get(key)) == normalized_asin:
            return True
    metadata = item.get('media', {}).get('metadata') if isinstance(item.get('media'), dict) else None
    if isinstance(metadata, dict):
        for key in candidate_keys:
            if normalize_asin_for_duplicate_check(metadata.get(key)) == normalized_asin:
                return True
    return False


def _normalized_text(value: Any) -> str:
    return str(value or '').strip().casefold()


def _metadata_for_item(item: dict[str, Any]) -> dict[str, Any]:
    media = item.get('media')
    if isinstance(media, dict) and isinstance(media.get('metadata'), dict):
        return media['metadata']
    return {}


def _dict_matches_author_album(item: dict[str, Any], author: str, album: str) -> bool:
    normalized_author = _normalized_text(author)
    normalized_album = _normalized_text(album)
    metadata = _metadata_for_item(item)
    album_candidates = (
        item.get('title'),
        item.get('name'),
        metadata.get('title'),
        metadata.get('subtitle'),
        metadata.get('album'),
    )
    author_candidates = (
        item.get('author'),
        item.get('authorName'),
        metadata.get('authorName'),
        metadata.get('author'),
        metadata.get('authors'),
    )
    album_match = any(_normalized_text(candidate) == normalized_album for candidate in album_candidates)
    author_match = False
    for candidate in author_candidates:
        if isinstance(candidate, list):
            author_match = any(_normalized_text(entry.get('name') if isinstance(entry, dict) else entry) == normalized_author for entry in candidate)
        else:
            author_match = _normalized_text(candidate) == normalized_author
        if author_match:
            break
    return author_match and album_match


def _extract_asin_matches(payload: Any, asin: str) -> list[dict[str, Any]]:
    normalized = normalize_asin_for_duplicate_check(asin)
    matches = []
    seen = set()
    for item in _walk_dicts(payload):
        if not _dict_matches_asin(item, normalized):
            continue
        identity = id(item)
        if identity not in seen:
            seen.add(identity)
            matches.append(item)
    return matches


def _extract_libraries(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        libraries = payload.get('libraries')
        if isinstance(libraries, list):
            return [library for library in libraries if isinstance(library, dict)]
        if isinstance(payload.get('id'), str):
            return [payload]
    if isinstance(payload, list):
        return [library for library in payload if isinstance(library, dict)]
    return []


def _book_library_ids(payload: Any) -> list[str]:
    ids = []
    for library in _extract_libraries(payload):
        if library.get('mediaType') not in (None, 'book'):
            continue
        library_id = library.get('id')
        if isinstance(library_id, str) and library_id:
            ids.append(library_id)
    return ids


@lru_cache(maxsize=8)
def _abs_library_items_payload(abs_url: str, api_key: str) -> dict[str, Any]:
    libraries_payload = _abs_get(abs_url, api_key, '/api/libraries')
    library_ids = _book_library_ids(libraries_payload)
    results: list[dict[str, Any]] = []
    for library_id in library_ids:
        items_payload = _abs_get(abs_url, api_key, f'/api/libraries/{library_id}/items', params={'limit': 0, 'minified': 0, 'collapseseries': 0})
        if isinstance(items_payload, dict) and isinstance(items_payload.get('results'), list):
            results.extend(item for item in items_payload['results'] if isinstance(item, dict))
        elif isinstance(items_payload, list):
            results.extend(item for item in items_payload if isinstance(item, dict))
    return {'results': results}


def query_abs_by_asin(abs_url: str, api_key: str, asin: str) -> list[dict[str, Any]]:
    """Query ABS library items by ASIN and return exact ASIN matches only.

    This uses Audiobookshelf's documented library APIs instead of the invalid
    global /api/search endpoint: list accessible libraries, load book library
    items, then compare normalized ASIN values locally.
    """
    normalized = normalize_asin_for_duplicate_check(asin)
    if not normalized:
        return []
    payload = _abs_library_items_payload(abs_url, api_key)
    return _extract_asin_matches(payload, normalized)


def query_abs_by_author_album(abs_url: str, api_key: str, author: str, album: str) -> list[dict[str, Any]]:
    normalized_author = _normalized_text(author)
    normalized_album = _normalized_text(album)
    if not normalized_author or not normalized_album:
        return []
    payload = _abs_library_items_payload(abs_url, api_key)
    matches = []
    seen = set()
    for item in _walk_dicts(payload):
        if not _dict_matches_author_album(item, author, album):
            continue
        identity = id(item)
        if identity not in seen:
            seen.add(identity)
            matches.append(item)
    return matches

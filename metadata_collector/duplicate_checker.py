from __future__ import annotations

from dataclasses import dataclass
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


def query_abs_by_asin(abs_url: str, api_key: str, asin: str) -> list[dict[str, Any]]:
    """Query ABS by ASIN and return exact ASIN matches only.

    ABS search returns nested library/search result shapes depending on version; this function
    intentionally uses ASIN-only matching after receiving search results.
    """
    normalized = normalize_asin_for_duplicate_check(asin)
    if not normalized:
        return []
    payload = _abs_get(abs_url, api_key, '/api/search', params={'q': asin})
    return _extract_asin_matches(payload, normalized)

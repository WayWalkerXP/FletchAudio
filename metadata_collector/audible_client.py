from __future__ import annotations

from dataclasses import dataclass
import re
from urllib.parse import urlencode

BASE_URL='https://api.audible.com/1.0/catalog/products'
SEARCH_RESPONSE_GROUPS='contributors,media,product_desc,product_attrs,product_extended_attrs,series'
ASIN_RESPONSE_GROUPS='category_ladders,contributors,media,product_desc,product_attrs,product_extended_attrs,rating,series,product_details'

ASIN_PATTERN=re.compile(r'^[A-Z0-9]{10}$')


def normalize_asin(asin: str | None) -> str:
    return (asin or '').strip().upper()


def validate_asin(asin: str | None) -> tuple[bool, str | None]:
    clean=normalize_asin(asin)
    if not clean:
        return False, 'ASIN is required.'
    if not ASIN_PATTERN.fullmatch(clean):
        return False, 'ASIN must be 10 alphanumeric characters.'
    return True, None


def product_from_asin_response(response_json: dict) -> dict | None:
    if not isinstance(response_json, dict):
        raise ValueError('Malformed Audible response: expected an object.')
    product=response_json.get('product', response_json)
    if not isinstance(product, dict):
        raise ValueError('Malformed Audible response: product is not an object.')
    if not product or product.get('asin') in (None, ''):
        return None
    return product

@dataclass
class AudibleSearchResult:
    title: str | None = None
    subtitle: str | None = None
    authors: list[str] | None = None
    narrators: list[str] | None = None
    runtime_length_min: int | None = None
    series_title: str | None = None
    series_sequence: str | None = None
    asin: str | None = None
    product: dict | None = None

    @property
    def author_text(self) -> str:
        return ', '.join(self.authors or [])

    @property
    def narrator_text(self) -> str:
        return ', '.join(self.narrators or [])


def clean_title_for_search(title_or_album: str|None)->str:
    return re.sub(r'[- ]+(cd|part) ?\d+$','',title_or_album or '',flags=re.I).strip()
def build_title_author_query(author: str|None, title_or_album: str|None)->str:
    return ' '.join(p for p in [(author or '').strip(), clean_title_for_search(title_or_album)] if p)
def search_params(query: str)->dict[str,str|int]:
    return {'response_groups':SEARCH_RESPONSE_GROUPS,'image_sizes':'100','num_results':50,'products_sort_by':'Relevance','keywords':query}
def asin_params()->dict[str,str]:
    return {'response_groups':ASIN_RESPONSE_GROUPS,'image_sizes':'1000,700,500'}
def search_url(query: str)->str: return f'{BASE_URL}?{urlencode(search_params(query))}'
def asin_url(asin: str)->str: return f'{BASE_URL}/{asin}?{urlencode(asin_params())}'

def _names(product: dict, key: str) -> list[str]:
    return [item.get('name') for item in product.get(key, []) if item.get('name')]

def _runtime_minutes(value) -> int | None:
    if value is None or value == '':
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None

def parse_search_results(response_json: dict) -> list[AudibleSearchResult]:
    products=response_json.get('products') or []
    if not isinstance(products, list):
        return []
    results=[]
    for product in products:
        if not isinstance(product, dict):
            continue
        series=(product.get('series') or [{}])[0] if product.get('series') else {}
        results.append(AudibleSearchResult(
            title=product.get('title'),
            subtitle=product.get('subtitle'),
            authors=_names(product, 'authors'),
            narrators=_names(product, 'narrators'),
            runtime_length_min=_runtime_minutes(product.get('runtime_length_min')),
            series_title=series.get('title'),
            series_sequence=str(series.get('sequence')) if series.get('sequence') is not None else None,
            asin=product.get('asin'),
            product=product,
        ))
    return results

def runtime_difference_minutes(source_duration_seconds, audible_runtime_minutes) -> int | None:
    if source_duration_seconds is None or audible_runtime_minutes is None:
        return None
    try:
        source_minutes=round(float(source_duration_seconds) / 60)
        audible_minutes=int(audible_runtime_minutes)
    except (TypeError, ValueError):
        return None
    return abs(audible_minutes - source_minutes)

def sort_results_by_runtime_match(results: list[AudibleSearchResult], source_duration_seconds):
    if source_duration_seconds is None:
        return list(results)
    decorated=[]
    for index, result in enumerate(results):
        diff=runtime_difference_minutes(source_duration_seconds, result.runtime_length_min)
        decorated.append((diff is None, diff if diff is not None else 0, index, result))
    return [item[-1] for item in sorted(decorated)]

class AudibleClient:
    def __init__(self, session=None, timeout=20):
        if session is None:
            import requests
            session = requests.Session()
        self.session=session; self.timeout=timeout
    def search(self, author: str|None, title_or_album: str|None):
        r=self.session.get(BASE_URL, params=search_params(build_title_author_query(author,title_or_album)), timeout=self.timeout); r.raise_for_status(); return r.json()
    def lookup_asin(self, asin: str):
        clean=normalize_asin(asin)
        valid, error=validate_asin(clean)
        if not valid:
            raise ValueError(error)
        r=self.session.get(f'{BASE_URL}/{clean}', params=asin_params(), timeout=self.timeout); r.raise_for_status(); return r.json()

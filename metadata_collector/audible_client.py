import re
from urllib.parse import urlencode
BASE_URL='https://api.audible.com/1.0/catalog/products'
SEARCH_RESPONSE_GROUPS='contributors,media,product_desc,product_attrs,product_extended_attrs,series'
ASIN_RESPONSE_GROUPS='category_ladders,contributors,media,product_desc,product_attrs,product_extended_attrs,rating,series,product_details'
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
class AudibleClient:
    def __init__(self, session=None, timeout=20):
        if session is None:
            import requests
            session = requests.Session()
        self.session=session; self.timeout=timeout
    def search(self, author: str|None, title_or_album: str|None):
        r=self.session.get(BASE_URL, params=search_params(build_title_author_query(author,title_or_album)), timeout=self.timeout); r.raise_for_status(); return r.json()
    def lookup_asin(self, asin: str):
        clean=(asin or '').strip();
        if not clean: raise ValueError('ASIN is required')
        r=self.session.get(f'{BASE_URL}/{clean}', params=asin_params(), timeout=self.timeout); r.raise_for_status(); return r.json()

import html, re
from .models import AbsMetadata

# Audible runtime is kept on AbsMetadata.duration for display/matching only;
# write planning excludes duration as a non-writable technical field.
AUDIBLE_RUNTIME_SECONDS_FIELD = 'duration'

def _names(product, key): return ', '.join(x.get('name','') for x in product.get(key,[]) if x.get('name')) or None
def _clean_html(text):
    if not text: return None
    text=re.sub(r'<\s*br\s*/?>','\n',text,flags=re.I); text=re.sub(r'<[^>]+>','',text)
    return re.sub(r'\n{3,}','\n\n',html.unescape(text)).strip() or None
def _genres(product):
    out=[]
    for ladder in product.get('category_ladders') or []:
        for item in ladder.get('ladder') or []:
            n=item.get('name')
            if n and n not in out: out.append(n)
    return out
def _cover(product):
    imgs=product.get('product_images') or {}
    for size in ('1000','700','500','100'):
        if imgs.get(size): return imgs[size]
    return None
def _title(t): return re.sub(r'\s*\(\s*Narrated by .*?\s*\)\s*$','',t or '',flags=re.I).strip() or None
def normalize_audible_product(product: dict) -> AbsMetadata:
    release=product.get('release_date')
    desc=product.get('publisher_summary') or product.get('product_description') or product.get('merchandising_summary')
    mins=product.get('runtime_length_min')
    return AbsMetadata(title=_title(product.get('title')), subtitle=product.get('subtitle'), asin=product.get('asin'), author=_names(product,'authors'),
        narrator=_names(product,'narrators'), series=((product.get('series') or [{}])[0].get('title') if product.get('series') else None),
        series_sequence=(str((product.get('series') or [{}])[0].get('sequence')) if product.get('series') and (product.get('series') or [{}])[0].get('sequence') is not None else None),
        publisher=product.get('publisher_name'), published_date=release, published_year=release[:4] if release else None, language=product.get('language'),
        duration=int(mins)*60 if mins is not None else None, explicit=product.get('is_adult_product'), description=_clean_html(desc), genres=_genres(product), cover_url=_cover(product))
def normalize_response(data: dict) -> AbsMetadata:
    product=data.get('product', data)
    return normalize_audible_product(product)

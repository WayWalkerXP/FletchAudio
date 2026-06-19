from metadata_collector.metadata_map import normalize_audible_product

def product():
    return {'title':'Some Book (Narrated by Someone)','subtitle':'Sub','asin':'ASIN','authors':[{'name':'A'}],'narrators':[{'name':'N1'},{'name':'N2'}], 'series':[{'title':'S','sequence':'2'}], 'publisher_name':'Pub','release_date':'2020-01-02','language':'english','runtime_length_min':10,'is_adult_product':False,'publisher_summary':'<p>Hello &amp; bye</p>','category_ladders':[{'ladder':[{'name':'Fiction'},{'name':'Audio'}]},{'ladder':[{'name':'Fiction'}]}], 'product_images':{'500':'five','700':'seven'}}

def test_audible_json_to_abs_metadata_mapping():
    m=normalize_audible_product(product())
    assert m.title=='Some Book'; assert m.author=='A'; assert m.narrator=='N1, N2'; assert m.series=='S'; assert m.series_sequence=='2'
    assert m.publisher=='Pub'; assert m.published_year=='2020'; assert m.duration==600; assert m.description=='Hello & bye'

def test_genre_deduplication(): assert normalize_audible_product(product()).genres == ['Fiction','Audio']
def test_cover_url_fallback_order(): assert normalize_audible_product(product()).cover_url == 'seven'

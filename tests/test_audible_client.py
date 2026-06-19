from metadata_collector.audible_client import clean_title_for_search, search_url, asin_url, build_title_author_query

def test_audible_title_cleanup_regex():
    assert clean_title_for_search('Great Book - CD 01') == 'Great Book'
    assert clean_title_for_search('Great Book part2') == 'Great Book'

def test_audible_url_query_construction():
    url=search_url(build_title_author_query('Author','Book - Part 1'))
    assert url.startswith('https://api.audible.com/1.0/catalog/products?')
    assert 'response_groups=contributors' in url
    assert 'num_results=50' in url
    assert 'products_sort_by=Relevance' in url
    assert 'keywords=Author+Book' in url

def test_asin_url_construction():
    url=asin_url('B00TEST')
    assert '/products/B00TEST?' in url
    assert 'category_ladders' in url
    assert 'image_sizes=1000%2C700%2C500' in url

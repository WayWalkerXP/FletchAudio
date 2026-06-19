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

from metadata_collector.audible_client import parse_search_results, runtime_difference_minutes, sort_results_by_runtime_match
from metadata_collector.models import AudioFileMetadata, Book


def test_parse_search_results_multiple_products_returned():
    results = parse_search_results({'products': [
        {'title': 'One', 'asin': 'A1', 'authors': [{'name': 'Author'}], 'narrators': [{'name': 'Narr'}], 'runtime_length_min': '60', 'series': [{'title': 'S', 'sequence': 1}]},
        {'title': 'Two', 'asin': 'A2'},
    ]})

    assert len(results) == 2
    assert results[0].title == 'One'
    assert results[0].authors == ['Author']
    assert results[0].narrators == ['Narr']
    assert results[0].runtime_length_min == 60
    assert results[0].series_title == 'S'
    assert results[0].series_sequence == '1'
    assert results[1].asin == 'A2'


def test_runtime_sorting_uses_closest_source_runtime_match():
    results = parse_search_results({'products': [
        {'title': 'Far', 'asin': 'F', 'runtime_length_min': 200},
        {'title': 'Closest', 'asin': 'C', 'runtime_length_min': 121},
        {'title': 'Near', 'asin': 'N', 'runtime_length_min': 110},
    ]})

    sorted_results = sort_results_by_runtime_match(results, 120 * 60)

    assert [result.asin for result in sorted_results] == ['C', 'N', 'F']


def test_missing_source_runtime_keeps_audible_returned_order():
    results = parse_search_results({'products': [
        {'title': 'First', 'asin': '1', 'runtime_length_min': 999},
        {'title': 'Second', 'asin': '2', 'runtime_length_min': 1},
    ]})

    sorted_results = sort_results_by_runtime_match(results, None)

    assert [result.asin for result in sorted_results] == ['1', '2']


def test_missing_audible_runtime_sorts_after_runtime_matches():
    results = parse_search_results({'products': [
        {'title': 'Missing', 'asin': 'M'},
        {'title': 'Match', 'asin': 'A', 'runtime_length_min': 60},
    ]})

    assert runtime_difference_minutes(3600, None) is None
    sorted_results = sort_results_by_runtime_match(results, 3600)

    assert [result.asin for result in sorted_results] == ['A', 'M']


def test_folder_book_runtime_equals_sum_of_child_durations():
    book = Book('k', '/book', True, [AudioFileMetadata('/book/1.mp3', duration=60), AudioFileMetadata('/book/2.mp3', duration=120)])
    source_duration = sum(file.duration for file in book.files if file.duration is not None)

    assert source_duration == 180
    assert runtime_difference_minutes(source_duration, 3) == 0

from metadata_collector.audible_client import normalize_asin, product_from_asin_response, validate_asin


def test_asin_normalization_strips_whitespace_and_uppercases():
    assert normalize_asin('  b00test123  ') == 'B00TEST123'


def test_blank_asin_is_invalid():
    valid, error = validate_asin('   ')

    assert valid is False
    assert error == 'ASIN is required.'


def test_malformed_asin_is_invalid():
    valid, error = validate_asin('B00-TOO-LONG')

    assert valid is False
    assert error == 'ASIN must be 10 alphanumeric characters.'


def test_asin_lookup_response_returns_single_product_or_none():
    assert product_from_asin_response({'product': {'asin': 'B00TEST123', 'title': 'Book'}})['title'] == 'Book'
    assert product_from_asin_response({'product': {}}) is None

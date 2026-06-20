import pytest

from metadata_collector.duplicate_checker import (
    AbsConnectionError,
    _extract_asin_matches,
    normalize_asin_for_duplicate_check,
    query_abs_by_asin,
)


def test_normalize_asin_for_duplicate_check_trims_and_casefolds():
    assert normalize_asin_for_duplicate_check('  B00TeSt  ') == 'b00test'


def test_extract_asin_matches_finds_nested_exact_matches_only():
    payload = {
        'book': {'media': {'metadata': {'asin': ' B00TEST '}}},
        'other': [{'asin': 'NOPE'}, {'audibleAsin': 'b00test'}],
    }
    matches = _extract_asin_matches(payload, 'b00test')
    assert len(matches) == 3


def test_query_abs_by_asin_uses_search_and_exact_asin_matching(monkeypatch):
    calls = []

    class Response:
        status_code = 200
        def raise_for_status(self):
            pass
        def json(self):
            return {'results': [{'asin': 'B00TEST'}, {'asin': 'B00OTHER'}]}

    def fake_get(url, headers, params, timeout):
        calls.append((url, headers, params, timeout))
        return Response()

    monkeypatch.setattr('metadata_collector.duplicate_checker.requests.get', fake_get)
    matches = query_abs_by_asin('http://abs.local/', 'secret-token', ' b00test ')
    assert len(matches) == 1
    assert calls[0][0] == 'http://abs.local/api/search'
    assert calls[0][1]['Authorization'] == 'Bearer secret-token'
    assert calls[0][2] == {'q': ' b00test '}


def test_query_abs_by_asin_auth_failure_is_global_connection_error(monkeypatch):
    class Response:
        status_code = 401
        def json(self):
            return {}
    monkeypatch.setattr('metadata_collector.duplicate_checker.requests.get', lambda *args, **kwargs: Response())
    with pytest.raises(AbsConnectionError):
        query_abs_by_asin('http://abs.local', 'bad', 'B00TEST')

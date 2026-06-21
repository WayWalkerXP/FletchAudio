from pathlib import Path


APP_SOURCE = Path('metadata_collector/app.py').read_text()


def _book_top_row_source():
    return APP_SOURCE.split('        def book_top_row(book, first):', 1)[1].split('        def book_actions_row(book):', 1)[0]


def test_book_card_primary_metadata_uses_album_not_title():
    source = _book_top_row_source()

    assert 'text_cell(first.album, expand=4)' in source
    assert 'text_cell(first.title, expand=4)' not in source

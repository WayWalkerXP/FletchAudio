from pathlib import Path


APP_SOURCE = Path('metadata_collector/app.py').read_text()


def _book_top_row_source():
    return APP_SOURCE.split('        def book_top_row(book, first):', 1)[1].split('        def book_actions_row(book):', 1)[0]


def test_book_card_primary_metadata_uses_album_not_title():
    source = _book_top_row_source()

    assert 'text_cell(first.album, expand=4)' in source
    assert 'text_cell(first.title, expand=4)' not in source


def test_main_menu_places_static_header_between_status_and_scrollable_grid():
    source = APP_SOURCE

    assert "status=ft.Text('Select a working directory to begin.'); book_list_header=ft.Container(); grid=ft.Column(scroll=ft.ScrollMode.AUTO, expand=True)" in source
    assert """        return [
            toolbar,
            status,
            book_list_header,
            grid,
        ]
""" in source


def test_static_header_matches_top_level_book_card_columns():
    source = APP_SOURCE

    expected_header_cells = [
        "book_list_header_cell('Edit', width=48)",
        "book_list_header_cell('Name', expand=4)",
        "book_list_header_cell('Album', expand=4)",
        "book_list_header_cell('Author', expand=3)",
        "book_list_header_cell('Narrator', expand=3)",
        "book_list_header_cell('Series', expand=4)",
        "book_list_header_cell('ASIN', width=110)",
        "book_list_header_cell('Duplicate', width=126)",
        "book_list_header_cell('Tracks', width=92)",
        "book_list_header_spacer(width=42)",
    ]
    for header_cell in expected_header_cells:
        assert header_cell in source

    assert "book_list_header_cell('Title'" not in source
    assert "book_list_header_cell('Expand'" not in source

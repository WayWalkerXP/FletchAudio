from pathlib import Path


APP_SOURCE = Path('metadata_collector/app.py').read_text()


def _book_top_row_source():
    return APP_SOURCE.split('        def book_top_row(book, first):', 1)[1].split('        def book_actions_row(book):', 1)[0]


def test_book_card_primary_metadata_uses_album_not_title():
    source = _book_top_row_source()

    assert 'text_cell(first.album, expand=4)' in source
    assert 'text_cell(first.title, expand=4)' not in source


def test_main_menu_places_search_filter_controls_above_status_and_grid():
    source = APP_SOURCE

    assert "search_field=ft.TextField(label='Search books'" in source
    assert "filter_dropdown=ft.Dropdown(label='Filter', value='All Books'" in source
    assert "clear_search_button=ft.Button('Clear Search')" in source
    assert """        return [
            toolbar,
            search_controls,
            status,
            book_list_header,
            grid,
        ]
""" in source


def test_main_filter_dropdown_has_required_options():
    source = APP_SOURCE

    assert "('All Books', 'Folder Books', 'Single File Books', 'Missing Targets', 'Duplicate Books')" in source
    assert "attach_dropdown_selection_handler(filter_dropdown, handle_search_or_filter_change)" in source


def test_main_search_filter_helpers_use_required_fields_and_statuses():
    source = APP_SOURCE

    for expected in [
        "return (search_field.value or '').strip().casefold()",
        "return target_settings_status(book) == 'red'",
        "duplicate_status.status == 'duplicate'",
        "getattr(first, 'album', None)",
        "getattr(first, 'title', None)",
        "getattr(first, 'author', None)",
        "getattr(first, 'narrator', None)",
        "getattr(first, 'asin', None)",
        "rendered_books=filtered_books()",
        "for b in rendered_books:",
    ]:
        assert expected in source


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

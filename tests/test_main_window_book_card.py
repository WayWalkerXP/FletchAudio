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
    assert "attach_dropdown_selection_handler(filter_dropdown, handle_filter_change)" in source


def test_main_search_filter_helpers_use_required_fields_and_statuses():
    source = APP_SOURCE

    for expected in [
        "return (current_search_text or '').strip().casefold()",
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



def test_main_search_change_debounces_book_list_refresh_without_full_render():
    source = APP_SOURCE
    handler_source = source.split('    def handle_search_change(event=None):', 1)[1].split('    def handle_filter_change', 1)[0]

    assert 'pending_text=' in handler_source
    assert 'search_debounce_task.cancel()' in handler_source
    assert 'asyncio.create_task(apply_debounced_search(pending_text))' in handler_source
    assert 'render()' not in handler_source
    assert 'refresh_book_list()' not in handler_source
    assert 'await asyncio.sleep(1)' in source
    assert 'refresh_book_list()' in source.split('    async def apply_debounced_search(expected_text):', 1)[1].split('    def handle_search_change', 1)[0]


def test_clear_search_and_filter_refresh_book_list_immediately():
    source = APP_SOURCE
    filter_source = source.split('    def handle_filter_change(_=None):', 1)[1].split('    def clear_book_search', 1)[0]
    clear_source = source.split('    def clear_book_search(_=None):', 1)[1].split('    search_field.on_change', 1)[0]

    assert 'update_applied_search_text(search_field.value)' in filter_source
    assert 'refresh_book_list()' in filter_source
    assert "search_field.value=''" in clear_source
    assert "update_applied_search_text('')" in clear_source
    assert 'search_debounce_task.cancel()' in clear_source
    assert 'refresh_book_list()' in clear_source

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


def test_book_list_cards_keep_right_gap_from_scrollbar_and_header_alignment():
    source = APP_SOURCE

    assert 'BOOK_LIST_SCROLLBAR_GAP = 16' in source
    assert 'book_list_header=ft.Container(margin=margin_only(right=BOOK_LIST_SCROLLBAR_GAP))' in source
    assert 'margin=margin_only(bottom=10, right=BOOK_LIST_SCROLLBAR_GAP)' in source

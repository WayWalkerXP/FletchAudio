from pathlib import Path


APP_SOURCE = Path('metadata_collector/app.py').read_text(encoding='utf-8')

def _book_top_row_source():
    return APP_SOURCE.split('        def book_top_row(book, first):', 1)[1].split('        def book_actions_row(book):', 1)[0]

def test_book_card_primary_metadata_uses_album_not_title():
    source = _book_top_row_source()

    assert 'text_cell(first.album, expand=4)' in source
    assert 'text_cell(first.title, expand=4)' not in source

def test_top_level_book_cards_include_cover_thumbnail_or_placeholder():
    source = APP_SOURCE
    row_source = _book_top_row_source()

    assert 'BOOK_COVER_THUMBNAIL_SIZE = 64' in source
    assert 'def book_cover_file(book):' in source
    assert "next((file_meta for file_meta in book.files if getattr(file_meta, 'cover_data_uri', None)), None)" in source
    assert 'def book_cover_thumbnail(book):' in source
    assert 'ft.Image(src=cover_file.cover_data_uri, width=BOOK_COVER_THUMBNAIL_SIZE, height=BOOK_COVER_THUMBNAIL_SIZE' in source
    assert 'ft.Icon(ft.Icons.IMAGE_NOT_SUPPORTED_OUTLINED' in source
    assert 'book_cover_thumbnail(book)' in row_source
    assert row_source.index('ft.IconButton(icon=ft.Icons.EDIT') < row_source.index('book_cover_thumbnail(book)') < row_source.index('text_cell(book.display_name')

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

    top_header_source = source.split('        def build_book_list_header():', 1)[1].split('        book_list_header.content=build_book_list_header()', 1)[0]
    assert "book_list_header_cell('Title'" not in top_header_source
    assert "book_list_header_cell('Expand'" not in source

def test_book_list_cards_keep_right_gap_from_scrollbar_and_header_alignment():
    source = APP_SOURCE

    assert 'BOOK_LIST_SCROLLBAR_GAP = 16' in source
    assert 'book_list_header=ft.Container(margin=margin_only(right=BOOK_LIST_SCROLLBAR_GAP))' in source
    assert 'margin=margin_only(bottom=10, right=BOOK_LIST_SCROLLBAR_GAP)' in source

def test_expanded_folder_track_listing_uses_table_columns_and_detected_audio_values():
    source = APP_SOURCE
    track_source = source.split('        def track_detail_header_row():', 1)[1].split('        rendered_books=filtered_books()', 1)[0]

    for expected in [
        "book_list_header_cell('Filename', expand=4)",
        "book_list_header_cell('Track #', width=82)",
        "book_list_header_cell('Title', expand=4)",
        "book_list_header_cell('Bitrate', width=86)",
        "book_list_header_cell('Channels', width=92)",
        'text_cell(track_detail_filename(file_meta), expand=4)',
        'text_cell(track_detail_value(file_meta.track), width=82)',
        'text_cell(track_detail_value(file_meta.title), expand=4)',
        'text_cell(track_detail_value(get_actual_bitrate(file_meta)), width=86)',
        'text_cell(track_detail_value(get_actual_channels(file_meta)), width=92)',
    ]:
        assert expected in track_source

def test_expanded_folder_track_listing_hides_paths_sorts_and_shows_placeholders():
    source = APP_SOURCE
    filename_source = source.split('        def track_detail_filename(file_meta):', 1)[1].split('        def track_detail_value(value):', 1)[0]

    assert "filename=PureWindowsPath(raw_path).name if '\\\\' in raw_path else Path(raw_path).name" in filename_source
    assert "filename or '—'" in filename_source
    assert "return '—' if value is None or str(value).strip() == '' else value" in source
    assert "return (disc is None, int(disc) if disc is not None else 0, track is None, int(track) if track is not None else 0, filename)" in source
    assert 'enumerate(sorted(b.files, key=track_detail_sort_key))' in source
    assert '[track_detail_header_row()] + [child_file_row' in source

def test_folder_books_show_compact_folder_location_line_only_for_folder_books():
    source = APP_SOURCE

    assert 'def folder_location_text(book):' in source
    assert "relative_path=folder_path.resolve().relative_to(Path(working_directory).expanduser().resolve())" in source
    assert "return ' / '.join(relative_path.parts)" in source
    assert 'def folder_location_line(book):' in source
    assert 'if not book.is_folder_book:' in source
    assert 'return None' in source
    assert "ft.Text(f'Folder: {folder_text}'" in source
    assert 'selectable=True' in source
    assert 'tooltip=absolute_path' in source
    assert 'folder_line=folder_location_line(b)' in source

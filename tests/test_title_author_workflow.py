from pathlib import Path


APP_SOURCE = Path('metadata_collector/app.py')


def _title_author_dialog_source():
    app_source = APP_SOURCE.read_text()
    return app_source.split('async def confirm_title_author_search(book):', 1)[1].split('def create_title_author_search_handler', 1)[0]


def _title_author_handler_source():
    app_source = APP_SOURCE.read_text()
    return app_source.split('def create_title_author_search_handler(book):', 1)[1].split('def create_asin_search_handler', 1)[0]


def test_title_author_button_opens_confirmation_dialog_before_searching():
    app_source = APP_SOURCE.read_text()
    handler_source = _title_author_handler_source()

    assert "ft.Button('Search by Title & Author', on_click=create_title_author_search_handler(b))" in app_source
    assert 'await confirm_title_author_search(book)' in handler_source
    assert 'search_by_title_author(' not in handler_source


def test_title_author_dialog_uses_editable_current_metadata_fields_and_submit_values():
    dialog_source = _title_author_dialog_source()

    assert "author_field=ft.TextField(label='Author', value=first.author or first.albumartist or '', autofocus=True" in dialog_source
    assert "title_field=ft.TextField(label='Album/Title', value=first.album or first.title or book.display_name" in dialog_source
    assert "title=(title_field.value or '').strip()" in dialog_source
    assert "author=(author_field.value or '').strip()" in dialog_source
    assert "if not title:" in dialog_source
    assert "await search_by_title_author(book, author, title)" in dialog_source


def test_title_author_no_results_shows_closeable_message_and_no_selection_or_comparison():
    app_source = APP_SOURCE.read_text()
    no_results_branch = app_source.split('if not results:', 1)[1].split('return', 1)[0]

    assert "content=ft.Text('No Audible results found.')" in no_results_branch
    assert "ft.TextButton('Close', on_click=lambda e: close_dialog(no_results_dialog))" in no_results_branch
    assert 'Select Audible search result' not in no_results_branch
    assert 'show_comparison' not in no_results_branch


def test_title_author_all_results_go_to_selection_screen():
    search_source = APP_SOURCE.read_text().split('async def search_by_title_author(book, author, title_or_album):', 1)[1].split('async def lookup_asin_and_compare', 1)[0]

    assert 'Select Audible search result' in search_source
    assert 'if len(results) == 1' not in search_source
    assert 'await select_result(results[0])' not in search_source

from pathlib import Path


def test_asin_workflow_goes_directly_to_comparison_without_selection_screen():
    app_source = Path('metadata_collector/app.py').read_text()

    assert "show_comparison(book, metadata, source_type='audible_asin')" in app_source
    asin_workflow = app_source.split('async def search_by_asin(book):', 1)[1].split('def create_title_author_search_handler', 1)[0]
    assert 'Select Audible search result' not in asin_workflow


def test_asin_lookup_no_result_shows_message_and_does_not_open_comparison():
    app_source = Path('metadata_collector/app.py').read_text()

    assert "show_status(f'No Audible book found for ASIN {asin}.')" in app_source
    no_result_branch = app_source.split('if not product:', 1)[1].split('return', 1)[0]
    assert 'show_comparison' not in no_result_branch


def test_asin_workflow_reuses_metadata_comparison_write_path_with_asin_source_type():
    app_source = Path('metadata_collector/app.py').read_text()

    assert "def show_comparison(book, metadata, source_type='audible_title_author'):" in app_source
    assert "create_change_group(session, book.key, source_type, 'Audible metadata update')" in app_source
    assert "log_changes(session, group, book.key, file_metadata.path, changes, source_type)" in app_source
    assert "show_comparison(book, metadata, source_type='audible_asin')" in app_source

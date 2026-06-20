from pathlib import Path


APP_SOURCE = Path('metadata_collector/app.py')


def _comparison_source():
    app_source = APP_SOURCE.read_text()
    return app_source.split("def show_comparison(book, metadata, source_type='audible_title_author'):", 1)[1].split('async def search_by_title_author', 1)[0]


def test_comparison_save_closes_comparison_before_opening_saving_dialog():
    comparison_source = _comparison_source()
    save_flow = comparison_source.split('async def apply_selected(_):', 1)[1].split('updates=normalize_for_dirty_check', 1)[0]

    assert 'close_dialog(dialog)' in save_flow
    assert 'open_dialog(saving_dialog)' in save_flow
    assert save_flow.index('close_dialog(dialog)') < save_flow.index('open_dialog(saving_dialog)')
    assert 'page.update()' in save_flow


def test_comparison_save_success_returns_to_list_with_success_message():
    comparison_source = _comparison_source()
    success_flow = comparison_source.split('session.commit()', 1)[1].split('except Exception as exc:', 1)[0]

    assert 'close_dialog(saving_dialog)' in success_flow
    assert 'render()' in success_flow
    assert "show_success('Metadata changes saved.')" in success_flow
    assert "show_status('Metadata changes saved.')" in success_flow


def test_comparison_failure_reopens_comparison_from_error_without_stacked_dialogs():
    comparison_source = _comparison_source()
    failure_flow = comparison_source.split('except Exception as exc:', 1)[1].split("title='Audible metadata comparison'", 1)[0]

    assert 'close_dialog(saving_dialog)' in failure_flow
    assert 'def return_to_comparison(_):' in failure_flow
    assert 'close_dialog(error_dialog)' in failure_flow
    assert 'open_dialog(dialog)' in failure_flow


def test_comparison_cancel_button_closes_comparison_dialog():
    comparison_source = _comparison_source()

    assert "ft.TextButton('Cancel', on_click=lambda e: close_dialog(dialog))" in comparison_source

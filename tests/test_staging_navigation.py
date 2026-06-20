from pathlib import Path


APP_SOURCE = Path('metadata_collector/app.py')


def _app_source():
    return APP_SOURCE.read_text()


def test_staging_completion_ok_clears_dialogs_and_returns_to_main_menu():
    app_source = _app_source()
    helper_source = app_source.split('def return_to_main_menu_after_staging(dialog=None):', 1)[1].split('def open_progress_dialog', 1)[0]
    summary_dialog_source = app_source.split("title=ft.Text('Move to Staging Complete')", 1)[1].split('open_dialog(summary_dialog)', 1)[0]

    assert 'clear_dialog_state(dialog)' in helper_source
    assert "go('/')" in helper_source
    assert 'scan()' in helper_source
    assert 'page.update()' in helper_source
    assert 'return_to_main_menu_after_staging(summary_dialog)' in summary_dialog_source
    assert '(close_dialog(summary_dialog), scan())' not in summary_dialog_source


def test_staging_clear_dialog_state_removes_active_overlays():
    app_source = _app_source()
    helper_source = app_source.split('def clear_dialog_state(dialog=None):', 1)[1].split('def return_to_main_menu_after_staging', 1)[0]

    assert 'dialog.open = False' in helper_source
    assert 'page.dialog = None' in helper_source
    assert 'overlay.clear()' in helper_source


def test_staging_fresh_cancel_still_closes_staging_dialog():
    app_source = _app_source()
    staging_source = app_source.split('def show_move_to_staging(_=None):', 1)[1].split('async def run_staging_move', 1)[0]

    assert "ft.TextButton('Cancel', on_click=lambda e: close_dialog(dialog))" in staging_source

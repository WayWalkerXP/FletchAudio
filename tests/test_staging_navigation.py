from pathlib import Path


APP_SOURCE = Path('metadata_collector/app.py')


def _app_source():
    return APP_SOURCE.read_text()


def test_staging_completion_ok_clears_dialogs_and_returns_to_main_menu():
    app_source = _app_source()
    helper_source = app_source.split('def return_to_main_menu_after_staging(dialog=None, move_screen_id=None):', 1)[1].split('def open_progress_dialog', 1)[0]
    summary_dialog_source = app_source.split("def handle_completion_ok(e):", 1)[1].split('open_dialog(summary_dialog)', 1)[0]

    assert 'clear_dialog_state(dialog)' in helper_source
    assert "go('/')" not in helper_source
    assert "settings.get('working_directory')" in helper_source
    assert 'scan()' in helper_source
    assert 'render()' in helper_source
    assert 'page.update()' in helper_source
    assert 'return_to_main_menu_after_staging(summary_dialog, move_screen_id)' in summary_dialog_source
    assert 'handle_move_to_staging_cancel' not in summary_dialog_source
    assert '(close_dialog(summary_dialog), scan())' not in summary_dialog_source


def test_staging_clear_dialog_state_removes_active_overlays():
    app_source = _app_source()
    helper_source = app_source.split('def clear_dialog_state(dialog=None):', 1)[1].split('def return_to_main_menu_after_staging', 1)[0]

    assert 'dialog.open = False' in helper_source
    assert 'page.dialog = None' in helper_source
    assert 'overlay.remove(control)' in helper_source
    assert 'overlay.clear()' not in helper_source
    assert 'views.clear()' not in helper_source


def test_staging_completion_ok_does_not_reopen_staging_screen():
    app_source = _app_source()
    helper_source = app_source.split('def return_to_main_menu_after_staging(dialog=None, move_screen_id=None):', 1)[1].split('def open_progress_dialog', 1)[0]

    assert 'show_move_to_staging' not in helper_source
    assert 'run_staging_move' not in helper_source
    assert "go('/move-to-staging')" not in helper_source


def test_staging_fresh_cancel_returns_to_main_menu():
    app_source = _app_source()
    staging_source = app_source.split('def show_move_to_staging(_=None):', 1)[1].split('async def run_staging_move', 1)[0]

    assert 'def handle_move_to_staging_cancel(e):' in staging_source
    assert "return_to_main_menu_after_staging(dialog, move_screen_id)" in staging_source
    assert "ft.TextButton('Cancel', on_click=handle_move_to_staging_cancel)" in staging_source
    assert "ft.TextButton('Cancel', on_click=lambda e: close_dialog(dialog))" not in staging_source


def test_staging_candidates_are_discovered_fresh_from_working_directory():
    app_source = _app_source()
    staging_source = app_source.split('def show_move_to_staging(_=None):', 1)[1].split('async def run_staging_move', 1)[0]

    assert 'discover_staging_candidates(Path(working_directory).expanduser())' in staging_source
    assert 'candidates_from_books(books)' not in staging_source


def test_staging_completion_ok_uses_dedicated_handler_not_cancel_callback():
    app_source = _app_source()
    summary_dialog_source = app_source.split("title=ft.Text('Move to Staging Complete')", 1)[0].rsplit("logging.info('Move to Staging summary", 1)[1]

    assert 'def handle_completion_ok(e):' in summary_dialog_source
    assert "ft.TextButton('OK', on_click=handle_completion_ok)" in summary_dialog_source
    assert 'handle_move_to_staging_cancel' not in summary_dialog_source
    assert 'Move to Staging Cancel clicked' not in summary_dialog_source


def test_staging_lifecycle_id_is_retired_after_return_to_main_menu():
    app_source = _app_source()
    helper_source = app_source.split('def return_to_main_menu_after_staging(dialog=None, move_screen_id=None):', 1)[1].split('def open_progress_dialog', 1)[0]
    staging_source = app_source.split('def show_move_to_staging(_=None):', 1)[1].split('async def run_staging_move', 1)[0]

    assert 'active_move_to_staging_screen_id=None' in app_source
    assert 'active_move_to_staging_screen_id=move_screen_id' in staging_source
    assert 'active_move_to_staging_screen_id=None' in helper_source
    assert "logging.info('Retiring Move to Staging screen id=%s', move_screen_id)" in helper_source


def test_return_to_main_menu_after_staging_has_controlled_error_state():
    app_source = _app_source()
    helper_source = app_source.split('def return_to_main_menu_after_staging(dialog=None, move_screen_id=None):', 1)[1].split('def open_progress_dialog', 1)[0]

    assert 'try:' in helper_source
    assert "logging.exception('Failed to render main menu after staging')" in helper_source
    assert 'render_main_menu_error_state(str(exc))' in helper_source
    assert "ft.Button('Retry Main Menu'" in app_source

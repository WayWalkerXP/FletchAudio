from pathlib import Path

APP_SOURCE = Path('metadata_collector/app.py').read_text()
MAIN_MENU_SOURCE = APP_SOURCE.split('    def build_main_menu_controls():', 1)[1].split('    def replace_page_controls', 1)[0]
WINDOW_CLOSE_SOURCE = APP_SOURCE.split('    async def close_current_window', 1)[1].split('    def exit_app', 1)[0]
EXIT_SOURCE = APP_SOURCE.split('    def exit_app', 1)[1].split('    def build_main_menu_controls', 1)[0]


def test_main_menu_exit_button_is_on_non_expanding_toolbar():
    assert "ft.Button('Move to Staging', on_click=show_move_to_staging)" in MAIN_MENU_SOURCE
    assert "ft.Button('Exit', on_click=exit_app)" in MAIN_MENU_SOURCE
    assert 'alignment=ft.MainAxisAlignment.SPACE_BETWEEN' in MAIN_MENU_SOURCE
    assert MAIN_MENU_SOURCE.index("ft.Button('Move to Staging', on_click=show_move_to_staging)") < MAIN_MENU_SOURCE.index("ft.Button('Exit', on_click=exit_app)")
    assert 'expand=True' not in MAIN_MENU_SOURCE.split('return [', 1)[0]
    assert 'toolbar,' in MAIN_MENU_SOURCE
    assert 'grid,' in MAIN_MENU_SOURCE


def test_exit_app_presents_confirmation_dialog():
    assert "ft.AlertDialog(" in EXIT_SOURCE
    assert "title=ft.Text('Exit FletchAudio?')" in EXIT_SOURCE
    assert "content=ft.Text('Are you sure you want to exit the program?')" in EXIT_SOURCE
    assert "ft.FilledButton('Exit', on_click=confirm_exit)" in EXIT_SOURCE
    assert "ft.TextButton('Go Back', on_click=lambda _: close_dialog(exit_dialog))" in EXIT_SOURCE
    assert 'open_dialog(exit_dialog)' in EXIT_SOURCE


def test_confirmed_exit_awaits_current_flet_window_close():
    assert "getattr(page, 'window', None)" in WINDOW_CLOSE_SOURCE
    assert "getattr(window, 'close', None)" in WINDOW_CLOSE_SOURCE
    assert 'close_result = close_window()' in WINDOW_CLOSE_SOURCE
    assert 'if inspect.isawaitable(close_result):' in WINDOW_CLOSE_SOURCE
    assert 'await close_result' in WINDOW_CLOSE_SOURCE

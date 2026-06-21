from pathlib import Path

APP_SOURCE = Path('metadata_collector/app.py').read_text()
MAIN_MENU_SOURCE = APP_SOURCE.split('    def build_main_menu_controls():', 1)[1].split('    def replace_page_controls', 1)[0]
EXIT_SOURCE = APP_SOURCE.split('    def exit_app', 1)[1].split('    def build_main_menu_controls', 1)[0]


def test_main_menu_exit_button_is_on_non_expanding_toolbar():
    assert "ft.Button('Move to Staging', on_click=show_move_to_staging)" in MAIN_MENU_SOURCE
    assert "ft.Button('Exit', on_click=exit_app)" in MAIN_MENU_SOURCE
    assert 'alignment=ft.MainAxisAlignment.SPACE_BETWEEN' in MAIN_MENU_SOURCE
    assert MAIN_MENU_SOURCE.index("ft.Button('Move to Staging', on_click=show_move_to_staging)") < MAIN_MENU_SOURCE.index("ft.Button('Exit', on_click=exit_app)")
    assert 'expand=True' not in MAIN_MENU_SOURCE.split('return [', 1)[0]
    assert 'toolbar,' in MAIN_MENU_SOURCE
    assert 'grid,' in MAIN_MENU_SOURCE


def test_exit_app_closes_current_flet_window():
    assert "getattr(page, 'window', None)" in EXIT_SOURCE
    assert "getattr(window, 'close', None)" in EXIT_SOURCE
    assert 'close_window()' in EXIT_SOURCE

import flet as ft

from metadata_collector.app import (
    THEME_OPTIONS,
    attach_dropdown_selection_handler,
    theme_mode_for_setting,
)


def test_theme_mode_for_setting_maps_dropdown_values():
    assert theme_mode_for_setting('System') == ft.ThemeMode.SYSTEM
    assert theme_mode_for_setting('Light') == ft.ThemeMode.LIGHT
    assert theme_mode_for_setting('Dark') == ft.ThemeMode.DARK


def test_theme_dropdown_uses_current_flet_selection_event():
    theme = ft.Dropdown(options=[ft.dropdown.Option(x) for x in THEME_OPTIONS])

    assert hasattr(theme, 'on_select')


def test_attach_dropdown_selection_handler_uses_available_flet_events():
    theme = ft.Dropdown(options=[ft.dropdown.Option(x) for x in THEME_OPTIONS])
    handler = lambda e: None

    assert attach_dropdown_selection_handler(theme, handler) is theme

    if hasattr(theme, 'on_select'):
        assert theme.on_select is handler
    if hasattr(theme, 'on_change'):
        assert theme.on_change is handler

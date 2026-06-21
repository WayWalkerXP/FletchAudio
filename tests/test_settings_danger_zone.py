from pathlib import Path

SOURCE = Path('metadata_collector/app.py').read_text()
SETTINGS_SOURCE = SOURCE.split("    def show_settings(section='Directories'):", 1)[1].split("    def save_abs_settings", 1)[0]
DANGER_ZONE_SOURCE = SETTINGS_SOURCE.split("            else:", 1)[1].split("            refresh_nav()", 1)[0]


def test_danger_zone_uses_current_flet_border_api():
    assert 'ft.border.all' not in DANGER_ZONE_SOURCE
    assert 'border=ft.Border(' in DANGER_ZONE_SOURCE
    assert 'left=ft.BorderSide(1, ft.Colors.RED)' in DANGER_ZONE_SOURCE
    assert 'top=ft.BorderSide(1, ft.Colors.RED)' in DANGER_ZONE_SOURCE
    assert 'right=ft.BorderSide(1, ft.Colors.RED)' in DANGER_ZONE_SOURCE
    assert 'bottom=ft.BorderSide(1, ft.Colors.RED)' in DANGER_ZONE_SOURCE

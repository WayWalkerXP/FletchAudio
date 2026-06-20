from pathlib import Path


APP_SOURCE = Path('metadata_collector/app.py')


def _auto_track_source():
    app_source = APP_SOURCE.read_text()
    return app_source.split('def auto_track_clicked(e):', 1)[1].split('def return_to_main():', 1)[0]


def _save_exit_flow():
    source = _auto_track_source()
    return source.split('async def save_exit_dialog_values(e):', 1)[1].split('def cancel_dialog_values(_):', 1)[0]


def test_auto_track_save_exit_clears_dirty_before_closing_dialogs():
    save_flow = _save_exit_flow()

    assert "dialog_dirty['value']=False" in save_flow
    assert "logging.info('Auto-Track dirty state cleared" in save_flow
    assert 'close_auto_track_lifecycle_dialogs()' in save_flow
    assert save_flow.index("dialog_dirty['value']=False") < save_flow.index('close_auto_track_lifecycle_dialogs()')


def test_auto_track_save_exit_removes_stale_dialogs_before_result_dialog():
    auto_track_source = _auto_track_source()
    cleanup_flow = auto_track_source.split('def close_auto_track_lifecycle_dialogs():', 1)[1].split('async def save_exit_dialog_values(e):', 1)[0]
    save_flow = _save_exit_flow()

    assert "auto_track_dialog_open['value']=False" in cleanup_flow
    assert 'action.on_click=None' in cleanup_flow
    assert 'clear_dialog_state(dialog)' in cleanup_flow
    assert "logging.info('Removing Auto-Track overlays" in cleanup_flow
    assert save_flow.index('close_auto_track_lifecycle_dialogs()') < save_flow.index('open_dialog(result_dialog)')


def test_auto_track_cancel_ignores_stale_closed_dialog_callbacks():
    source = _auto_track_source()
    cancel_flow = source.split('def cancel_dialog_values(_):', 1)[1].split('content=ft.Column', 1)[0]

    assert "logging.info('Auto-Track Cancel clicked" in cancel_flow
    assert "logging.info('Auto-Track dirty state=%s" in cancel_flow
    assert "logging.info('Auto-Track dialog open=%s" in cancel_flow
    assert 'if not dialog_open:\n                    return' in cancel_flow
    assert "auto_track_dialog_open['value']=False" in cancel_flow


def test_auto_track_save_complete_ok_explicitly_returns_to_mass_update():
    app_source = APP_SOURCE.read_text()
    helper_source = app_source.split('def return_to_mass_update_screen_from_auto_track_result(result_dialog=None):', 1)[1].split('def cell', 1)[0]
    save_flow = _save_exit_flow()

    assert "auto_track_result_returned['value']=True" in helper_source
    assert "logging.info('Auto-Track save complete OK clicked" in helper_source
    assert "auto_track_open['value']=False" in helper_source
    assert "auto_track_dialog_state['dirty']=False" in helper_source
    assert 'clear_dialog_state()' in helper_source
    assert 'render_mass_update_screen()' in helper_source
    assert 'show_auto_track' not in helper_source
    assert 'build_auto_track' not in helper_source
    assert 'render_auto_track' not in helper_source
    assert 'return_to_auto_track' not in helper_source
    assert "auto_track_result_returned['value']=False" in app_source
    assert 'def on_auto_track_save_complete_ok(_):' in save_flow
    assert 'on_click=on_auto_track_save_complete_ok' in save_flow
    assert 'on_dismiss=lambda _: return_to_mass_update_screen_from_auto_track_result(result_dialog)' in save_flow
    assert 'on_click=lambda ev: close_dialog(result_dialog)' not in save_flow

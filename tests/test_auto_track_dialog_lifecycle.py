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

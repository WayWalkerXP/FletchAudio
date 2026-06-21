from pathlib import Path

SOURCE = Path('metadata_collector/app.py').read_text()
SET_TITLE_SOURCE = SOURCE.split('        def set_title_clicked(e):', 1)[1].split('        def auto_track_clicked(e):', 1)[0]
REBUILD_PREVIEW_SOURCE = SET_TITLE_SOURCE.split('            def rebuild_preview(_=None):', 1)[1].split('            def preset_changed(_):', 1)[0]
APPLY_SOURCE = SET_TITLE_SOURCE.split('            def apply_set_title(_):', 1)[1].split('            async def save_exit_set_title(e):', 1)[0]
SAVE_EXIT_SOURCE = SET_TITLE_SOURCE.split('            async def save_exit_set_title(e):', 1)[1].split('            def save_exit_handler(e):', 1)[0]


def test_set_title_preview_is_read_only_and_has_no_status_column():
    assert 'row.title=' not in REBUILD_PREVIEW_SOURCE
    assert 'mark_unsaved' not in REBUILD_PREVIEW_SOURCE
    assert 'save_track_title_rows' not in REBUILD_PREVIEW_SOURCE
    assert "ft.Text('Status'" not in REBUILD_PREVIEW_SOURCE
    assert "ft.Text('Filename'" in REBUILD_PREVIEW_SOURCE
    assert "ft.Text('Track'" in REBUILD_PREVIEW_SOURCE
    assert "ft.Text('Current Title'" in REBUILD_PREVIEW_SOURCE
    assert "ft.Text('New Title'" in REBUILD_PREVIEW_SOURCE


def test_set_title_actions_include_cancel_apply_save_and_exit():
    assert "ft.TextButton('Cancel'" in SET_TITLE_SOURCE
    assert "ft.Button('Apply'" in SET_TITLE_SOURCE
    assert "ft.FilledButton('Save and Exit'" in SET_TITLE_SOURCE


def test_set_title_apply_updates_memory_without_saving():
    assert 'apply_generated_titles()' in APPLY_SOURCE
    assert "mark_unsaved('set title')" in APPLY_SOURCE
    assert 'render_rows()' in APPLY_SOURCE
    assert "title=ft.Text('Set Title Complete')" in APPLY_SOURCE
    assert 'save_track_title_rows' not in APPLY_SOURCE
    assert 'await save_clicked' not in APPLY_SOURCE


def test_set_title_save_exit_reuses_mass_update_save_flow():
    assert 'apply_generated_titles()' in SAVE_EXIT_SOURCE
    assert 'render_rows()' in SAVE_EXIT_SOURCE
    assert 'await save_clicked(e, True)' in SAVE_EXIT_SOURCE


def test_set_title_dialog_preview_is_bounded_and_scrollable():
    assert 'preview_table=ft.Column(scroll=ft.ScrollMode.AUTO' in SET_TITLE_SOURCE
    assert 'preview_container=ft.Container' in SET_TITLE_SOURCE
    assert 'height=320' in SET_TITLE_SOURCE
    assert 'border=ft.border.all(1, divider_color)' in SET_TITLE_SOURCE

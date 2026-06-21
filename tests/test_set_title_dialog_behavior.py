from pathlib import Path

SOURCE = Path('metadata_collector/app.py').read_text()
SET_TITLE_SOURCE = SOURCE.split('        def set_title_clicked(e):', 1)[1].split('        def auto_track_clicked(e):', 1)[0]
REBUILD_PREVIEW_SOURCE = SET_TITLE_SOURCE.split('            def rebuild_preview(_=None):', 1)[1].split('            def set_dialog_dirty():', 1)[0]
PRESET_SOURCE = SET_TITLE_SOURCE.split('            def preset_changed(_):', 1)[1].split('            def field_changed(_):', 1)[0]
APPLY_SOURCE = SET_TITLE_SOURCE.split('            def apply_set_title(_):', 1)[1].split('            def apply_generated_titles():', 1)[0]
SAVE_APPLY_SOURCE = SET_TITLE_SOURCE.split('            def apply_generated_titles():', 1)[1].split('            async def save_exit_set_title(e):', 1)[0]
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
    assert "controls_row=ft.Row([preset_field, offset_field, template_field, apply_button]" in SET_TITLE_SOURCE
    actions_source = SET_TITLE_SOURCE.split('dialog=ft.AlertDialog', 1)[1]
    assert "ft.Button('Apply'" not in actions_source


def test_set_title_apply_updates_preview_without_saving_or_closing():
    assert 'generate_preview_titles()' in APPLY_SOURCE
    assert 'dialog_dirty' in APPLY_SOURCE
    assert 'row.title=' not in APPLY_SOURCE
    assert 'close_dialog(dialog)' not in APPLY_SOURCE
    assert 'render_rows()' not in APPLY_SOURCE
    assert "mark_unsaved('set title')" not in APPLY_SOURCE
    assert 'save_track_title_rows' not in APPLY_SOURCE
    assert 'await save_clicked' not in APPLY_SOURCE


def test_set_title_save_exit_uses_generated_titles_and_reuses_mass_update_save_flow():
    assert 'generate_preview_titles()' not in SAVE_EXIT_SOURCE
    assert 'apply_generated_titles()' in SAVE_EXIT_SOURCE
    assert 'row.title=new_title' in SAVE_APPLY_SOURCE
    assert "mark_unsaved('set title')" in SAVE_EXIT_SOURCE
    assert 'render_rows()' in SAVE_EXIT_SOURCE
    assert 'await save_clicked(e, True)' in SAVE_EXIT_SOURCE


def test_set_title_dialog_preview_is_bounded_and_scrollable():
    assert 'preview_table=ft.Column(scroll=ft.ScrollMode.AUTO' in SET_TITLE_SOURCE
    assert 'preview_container=ft.Container' in SET_TITLE_SOURCE
    assert 'height=320' in SET_TITLE_SOURCE
    assert 'border=ft.Border(' in SET_TITLE_SOURCE
    assert 'ft.BorderSide(1, divider_color)' in SET_TITLE_SOURCE


def test_set_title_presets_update_template_but_keep_template_editable():
    assert "presets={'Chapter': 'Chapter %track%', 'Part': 'Part %track%', 'Track': 'Track %track%', 'CD': 'CD %track%'}" in SET_TITLE_SOURCE
    assert "options=[ft.dropdown.Option(value) for value in ['Chapter', 'Part', 'Track', 'CD', 'Custom']]" in SET_TITLE_SOURCE
    assert 'read_only=True' not in SET_TITLE_SOURCE
    assert "if preset_field.value != 'Custom':" in PRESET_SOURCE
    assert "template_field.value=presets.get(preset_field.value, template_field.value or '')" in PRESET_SOURCE


def test_set_title_cancel_prompts_when_dirty():
    assert "def cancel_set_title(_)" in SET_TITLE_SOURCE
    assert "title=ft.Text('Discard Set Title changes?')" in SET_TITLE_SOURCE
    assert "ft.TextButton('Stay'" in SET_TITLE_SOURCE
    assert "ft.FilledButton('Discard'" in SET_TITLE_SOURCE

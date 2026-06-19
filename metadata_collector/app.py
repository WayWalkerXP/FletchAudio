import asyncio
import inspect
import logging

import flet as ft

IMAGE_CONTAIN_FIT = getattr(getattr(ft, 'ImageFit', None) or ft.BoxFit, 'CONTAIN')

from .audible_client import AudibleClient, asin_url, build_title_author_query, parse_search_results, runtime_difference_minutes, search_url, sort_results_by_runtime_match
from .config import load_settings, save_settings
from .db import init_db, get_session_factory
from .audio_scan import scan_directory
from .audio_tags import NON_WRITABLE_FIELDS, format_genres_for_tag, read_audio_metadata, write_audio_metadata
from .history import create_change_group, log_changes, store_snapshot
from .metadata_map import normalize_response
from .manual_edit import BOOLEAN_FIELDS, CoverEditState, MANUAL_EDIT_SOURCE_TYPE, MANUAL_EDIT_TAGS, build_manual_metadata_diff, filter_manual_updates_for_file, manual_changed_fields, manual_current_value, manual_edit_file_label, sorted_manual_edit_files
logging.basicConfig(level=logging.INFO)

def main(page: ft.Page):
    engine=init_db(); Session=get_session_factory(engine); settings=load_settings(); books=[]
    page.title='FletchAudio'; page.theme_mode={'Light':ft.ThemeMode.LIGHT,'Dark':ft.ThemeMode.DARK}.get(settings.get('theme'), ft.ThemeMode.SYSTEM)
    status=ft.Text('Select a working directory to begin.'); grid=ft.Column(scroll=ft.ScrollMode.AUTO, expand=True); url_launcher=ft.UrlLauncher(); audible=AudibleClient()
    if hasattr(page, 'services'):
        page.services.append(url_launcher)
    elif hasattr(page, 'overlay'):
        page.overlay.append(url_launcher)
    def show_status(message: str):
        status.value=message; page.update()
    def show_success(message: str):
        snack_bar = ft.SnackBar(ft.Text(message))
        open_control = getattr(page, 'open', None)
        if open_control:
            open_control(snack_bar)
            return
        page.snack_bar = snack_bar
        snack_bar.open = True
        page.update()

    def open_dialog(dialog):
        show_dialog = getattr(page, 'show_dialog', None)
        if show_dialog:
            show_dialog(dialog)
            return
        page.dialog = dialog
        dialog.open = True
        page.update()
    def close_dialog(dialog=None):
        pop_dialog = getattr(page, 'pop_dialog', None)
        if pop_dialog:
            pop_dialog()
            return
        if dialog:
            dialog.open = False
        page.update()
    def source_duration_seconds(book):
        durations=[f.duration for f in book.files if f.duration is not None]
        if not durations:
            return None
        return sum(durations) if book.is_folder_book else durations[0]
    def format_minutes(minutes):
        if minutes is None:
            return 'Unknown'
        hours, mins = divmod(int(minutes), 60)
        return f'{hours}h {mins}m' if hours else f'{mins}m'
    def format_source_runtime(seconds):
        return format_minutes(round(seconds / 60)) if seconds is not None else 'Unknown'
    def result_row(result, source_seconds, on_select):
        diff=runtime_difference_minutes(source_seconds, result.runtime_length_min)
        series=' '.join(p for p in [result.series_title, result.series_sequence] if p)
        return ft.Row([
            ft.Text(result.title or '', width=180),
            ft.Text(result.subtitle or '', width=120),
            ft.Text(result.author_text, width=140),
            ft.Text(result.narrator_text, width=140),
            ft.Text(format_minutes(result.runtime_length_min), width=80),
            ft.Text(format_source_runtime(source_seconds), width=90),
            ft.Text(str(diff) if diff is not None else 'Unknown', width=80),
            ft.Text(series, width=120),
            ft.Text(result.asin or '', width=90),
            ft.Button('Select', on_click=on_select),
        ], wrap=True)
    def show_comparison(book, metadata):
        first=book.files[0]
        current_cover_file=next((file for file in book.files if file.cover_data_uri), first)
        selected={}
        divider_color=ft.Colors.OUTLINE_VARIANT
        row_border=ft.Border(bottom=ft.BorderSide(1, divider_color))
        column_border=ft.Border(left=ft.BorderSide(1, divider_color))

        def is_present(value):
            if value is None:
                return False
            if isinstance(value, str):
                return bool(value.strip())
            if isinstance(value, (list, tuple, set, dict)):
                return bool(value)
            return True
        def format_duration(seconds):
            if seconds is None:
                return ''
            seconds=int(seconds)
            hours, remainder=divmod(seconds, 3600)
            minutes=round(remainder / 60)
            if minutes == 60:
                hours += 1; minutes = 0
            return f'{hours}h {minutes}m' if hours else f'{minutes}m'
        def format_bool(value):
            if value is None:
                return ''
            return 'Yes' if value else 'No'
        def format_value(value, kind=None):
            if kind == 'duration':
                return format_duration(value)
            if kind == 'genres':
                return format_genres_for_tag(value) or ''
            if kind == 'bool':
                return format_bool(value)
            return str(value) if value not in (None, []) else ''
        def downloaded_control(field, value, kind=None):
            text=format_value(value, kind)
            checkbox=selected.get(field)
            controls=([checkbox] if checkbox else []) + [ft.Text(text, selectable=True, width=300, no_wrap=False)]
            if field == 'cover_url':
                controls=([checkbox] if checkbox else [])
                if value:
                    controls.append(ft.Image(src=value, width=64, height=64, fit=IMAGE_CONTAIN_FIT))
                    controls.append(ft.Text(value, selectable=True, width=220, no_wrap=False))
                else:
                    controls.append(ft.Text('Missing', width=300))
            return ft.Row(controls, spacing=8, vertical_alignment=ft.CrossAxisAlignment.START)
        def current_control(field, value, kind=None):
            if field == 'cover_url':
                if current_cover_file.cover_data_uri:
                    return ft.Image(src=current_cover_file.cover_data_uri, width=64, height=64, fit=IMAGE_CONTAIN_FIT)
                return ft.Text('Missing', width=300)
            return format_value(value, kind)
        def cell(content, width, border=None, padding=8):
            if isinstance(content, str):
                content=ft.Text(content, selectable=True, width=width - (padding * 2), no_wrap=False)
            return ft.Container(content=content, width=width, padding=padding, border=border)
        specs=[
            ('title', 'Title', metadata.title, first.title, None),
            ('subtitle', 'Subtitle', metadata.subtitle, '', None),
            ('album', 'Album', metadata.title, first.album, None),
            ('author', 'Author', metadata.author, first.author, None),
            ('albumartist', 'Album Artist', metadata.author, first.albumartist, None),
            ('narrator', 'Narrator', metadata.narrator, first.narrator, None),
            ('series', 'Series', metadata.series, first.series, None),
            ('series_sequence', 'Series Sequence', metadata.series_sequence, first.series_sequence, None),
            ('asin', 'ASIN', metadata.asin, first.asin, None),
            ('description', 'Description', metadata.description, first.description, None),
            ('publisher', 'Publisher', metadata.publisher, first.publisher, None),
            ('published_date', 'Published Date', metadata.published_date, first.published_date, None),
            ('published_year', 'Published Year', metadata.published_year, first.published_year, None),
            ('language', 'Language', metadata.language, first.language, None),
            ('genres', 'Genres', format_genres_for_tag(metadata.genres), format_genres_for_tag(first.genres), 'genres'),
            ('duration', 'Duration', metadata.duration, first.duration, 'duration'),
            ('explicit', 'Explicit', metadata.explicit, None, 'bool'),
            ('dramatic_audio', 'Dramatic Audio', None, first.dramatic_audio, 'bool'),
            ('track', 'Track', None, first.track, None),
            ('disc', 'Disc', None, first.disc, None),
            ('cover_url', 'Cover', metadata.cover_url, current_cover_file.cover_data_uri, None),
        ]
        header=ft.Row([
            cell(ft.Text('Tag', weight=ft.FontWeight.BOLD), 170),
            cell(ft.Text('Downloaded', weight=ft.FontWeight.BOLD), 410, column_border),
            cell(ft.Text('Current', weight=ft.FontWeight.BOLD), 330, column_border),
        ], spacing=0)
        rows=[header]
        for field, label, downloaded, current, kind in specs:
            writable=field not in NON_WRITABLE_FIELDS
            if field == 'cover_url':
                selected[field]=ft.Checkbox(value=is_present(downloaded), disabled=not is_present(downloaded))
            elif writable:
                selected[field]=ft.Checkbox(value=is_present(downloaded), disabled=not is_present(downloaded))
            rows.append(ft.Container(content=ft.Row([
                cell(ft.Text(label, weight=ft.FontWeight.W_500), 170),
                cell(downloaded_control(field, downloaded, kind), 410, column_border),
                cell(current_control(field, current, kind), 330, column_border),
            ], spacing=0, vertical_alignment=ft.CrossAxisAlignment.START), border=row_border))
        async def apply_selected(_):
            apply_button.disabled=True
            saving_dialog=ft.AlertDialog(
                modal=True,
                title=ft.Text('Saving metadata changes...'),
                content=ft.Column([
                    ft.ProgressRing(),
                    ft.Text('Writing tags. Please wait...'),
                ], tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            )

            open_dialog(saving_dialog)
            page.update()
            # Yield to Flet so the modal is sent to the client before the synchronous tag write starts.
            await asyncio.sleep(0.1)
            updates={field: downloaded for field, _, downloaded, _, _ in specs if field not in NON_WRITABLE_FIELDS and selected.get(field) and selected[field].value and is_present(downloaded)}
            if not updates:
                close_dialog(saving_dialog)
                apply_button.disabled=False
                page.update()
                show_status('No downloaded metadata fields selected to apply.')
                return
            try:
                for file_metadata in book.files:
                    write_audio_metadata(file_metadata.path, updates)
                    refreshed=read_audio_metadata(file_metadata.path)
                    file_metadata.__dict__.update(refreshed.__dict__)
                close_dialog(saving_dialog)
                close_dialog(dialog)
                show_success('Metadata changes saved.')
                show_status('Metadata changes saved.')
                render()
            except Exception as exc:
                close_dialog(saving_dialog)
                apply_button.disabled=False
                error_dialog=ft.AlertDialog(
                    modal=True,
                    title=ft.Text('Could not save metadata'),
                    content=ft.Text(f'Failed to apply metadata to {book.display_name}: {exc}'),
                    actions=[
                        ft.TextButton('Retry', on_click=lambda e: close_dialog(error_dialog)),
                        ft.TextButton('Cancel', on_click=lambda e: (close_dialog(error_dialog), close_dialog(dialog))),
                    ],
                )
                open_dialog(error_dialog)
                show_status(f'Failed to apply Audible metadata to {book.display_name}: {exc}')
        title='Audible metadata comparison'
        subtitle=' · '.join(p for p in [metadata.title, metadata.asin] if p)
        dialog=ft.AlertDialog(
            title=ft.Column([ft.Text(title), ft.Text(subtitle, size=12, selectable=True)]),
            content=ft.Column(rows, scroll=ft.ScrollMode.AUTO, height=560, width=930, spacing=0),
            actions=[ft.TextButton('Cancel', on_click=lambda e: close_dialog(dialog)), (apply_button := ft.FilledButton('Confirm / Apply', on_click=apply_selected))],
        )
        open_dialog(dialog)
    async def search_by_title_author(book):
        first=book.files[0]
        query=build_title_author_query(first.author, first.title or first.album or book.display_name)
        if not query:
            show_status(f'Cannot search {book.display_name}: missing title/album and author metadata.')
            return
        try:
            response=audible.search(first.author, first.title or first.album or book.display_name)
        except Exception as exc:
            show_status(f'Audible title/author search failed for {book.display_name}: {exc}')
            return
        source_seconds=source_duration_seconds(book)
        results=sort_results_by_runtime_match(parse_search_results(response), source_seconds)
        if not results:
            show_status(f'No Audible results found for: {query}')
            return
        async def select_result(result):
            if not result.asin:
                show_status('Cannot fetch Audible details: selected result has no ASIN.')
                return
            try:
                details=audible.lookup_asin(result.asin)
                metadata=normalize_response(details)
            except Exception as exc:
                show_status(f'Audible ASIN lookup failed for {result.asin}: {exc}')
                return
            show_status(f'Selected Audible result {result.asin}; showing comparison.')
            show_comparison(book, metadata)
        if len(results) == 1:
            await select_result(results[0])
            return
        rows=[ft.Row([ft.Text('Title', width=180), ft.Text('Subtitle', width=120), ft.Text('Authors', width=140), ft.Text('Narrators', width=140), ft.Text('Audible', width=80), ft.Text('Source', width=90), ft.Text('Diff min', width=80), ft.Text('Series', width=120), ft.Text('ASIN', width=90)])]
        for result in results:
            async def handler(_, selected=result):
                close_dialog(dialog)
                await select_result(selected)
            rows.append(result_row(result, source_seconds, handler))
        dialog=ft.AlertDialog(title=ft.Text('Select Audible search result'), content=ft.Column(rows, scroll=ft.ScrollMode.AUTO, height=500, width=1300), actions=[ft.TextButton('Cancel', on_click=lambda e: close_dialog(dialog))])
        open_dialog(dialog)
        show_status(f'Found {len(results)} Audible results for: {query}. Select one to compare metadata.')
    async def search_by_asin(book):
        first=book.files[0]
        asin=(first.asin or '').strip()
        if not asin:
            show_status(f'Cannot search {book.display_name}: missing ASIN metadata.')
            return
        await url_launcher.launch_url(asin_url(asin))
        show_status(f'Opened Audible ASIN lookup for: {asin}')
    def create_title_author_search_handler(book):
        async def handler(_):
            await search_by_title_author(book)
        return handler
    def create_asin_search_handler(book):
        async def handler(_):
            await search_by_asin(book)
        return handler
    async def maybe_await(value):
        if inspect.isawaitable(value):
            return await value
        return value
    def register_page_service(service):
        service_type=getattr(ft, 'Service', None)
        if hasattr(page, 'services') and (service_type is None or isinstance(service, service_type)):
            page.services.append(service)
        elif hasattr(page, 'overlay'):
            page.overlay.append(service)
        page.update()
        return service
    def create_file_picker(on_result=None):
        file_picker_params=inspect.signature(ft.FilePicker).parameters
        picker=ft.FilePicker(on_result=on_result) if 'on_result' in file_picker_params else ft.FilePicker()
        return register_page_service(picker)
    def show_manual_edit(book):
        edit_files=sorted_manual_edit_files(book.files) if book.is_folder_book else list(book.files)
        selected_file={'meta': edit_files[0]}
        controls={}
        current_cells={}
        file_buttons={}
        cover_state=CoverEditState()
        cover_preview=ft.Column(spacing=6)
        cover_note=ft.Text('', color=ft.Colors.RED)
        DESCRIPTION_HEIGHT=180
        divider_color=ft.Colors.OUTLINE_VARIANT
        row_border=ft.Border(bottom=ft.BorderSide(1, divider_color))
        column_border=ft.Border(left=ft.BorderSide(1, divider_color))
        selected_row_bg=ft.Colors.PRIMARY_CONTAINER
        def cell(content, width, border=None, padding=8):
            if isinstance(content, str):
                content=ft.Text(content, selectable=True, width=width - (padding * 2), no_wrap=False)
            return ft.Container(content=content, width=width, padding=padding, border=border)
        def current_file():
            return selected_file['meta']
        def current_cover_control(meta):
            return ft.Image(src=meta.cover_data_uri, width=64, height=64, fit=IMAGE_CONTAIN_FIT) if meta.cover_data_uri else ft.Text('Missing', width=120)
        def edited_values():
            return {field: (bool(control.value) if isinstance(control, ft.Checkbox) else control.value) for field, control in controls.items()}
        def refresh_cover_preview():
            meta=current_file()
            cover_preview.controls.clear()
            if cover_state.delete:
                if meta.cover_data_uri:
                    cover_preview.controls.append(ft.Image(src=meta.cover_data_uri, width=64, height=64, fit=IMAGE_CONTAIN_FIT, opacity=0.35))
                cover_note.value='Cover will be removed.'
            elif cover_state.path:
                cover_preview.controls.append(ft.Image(src=cover_state.path, width=96, height=96, fit=IMAGE_CONTAIN_FIT))
                cover_note.value=f'Selected: {cover_state.path}'
            elif meta.cover_data_uri:
                cover_preview.controls.append(ft.Image(src=meta.cover_data_uri, width=64, height=64, fit=IMAGE_CONTAIN_FIT))
                cover_note.value=''
            else:
                cover_preview.controls.append(ft.Text('Missing'))
                cover_note.value=''
            cover_preview.controls.append(cover_note)
        def load_file(meta):
            selected_file['meta']=meta
            for field, control in controls.items():
                value=manual_current_value(meta, field)
                if isinstance(control, ft.Checkbox):
                    control.value=bool(value) if value is not None and value != '' else False
                else:
                    control.value=str(value)
            for field, target in current_cells.items():
                value=manual_current_value(meta, field)
                if field == 'cover':
                    target.content=current_cover_control(meta)
                elif field == 'description':
                    target.content=ft.Column([ft.Text(str(value), selectable=True, no_wrap=False)], scroll=ft.ScrollMode.AUTO)
                else:
                    target.content=ft.Text(str(value), selectable=True, width=284, no_wrap=False)
            cover_state.path=None
            cover_state.delete=False
            refresh_cover_preview()
            for file_meta_path, button in file_buttons.items():
                button.bgcolor=selected_row_bg if file_meta_path == meta.path else None
            page.update()
        def on_cover_selected(e):
            files=getattr(e, 'files', None) or []
            if files:
                cover_state.path=files[0].path
                cover_state.delete=False
                refresh_cover_preview()
                page.update()
        cover_picker=create_file_picker(on_cover_selected)
        async def choose_cover(_):
            files=cover_picker.pick_files(allow_multiple=False, allowed_extensions=['jpg', 'jpeg', 'png', 'webp'])
            if inspect.isawaitable(files):
                files=await files
            if files:
                cover_state.path=files[0].path
                cover_state.delete=False
                refresh_cover_preview()
                page.update()
        def delete_cover(_):
            cover_state.path=None
            cover_state.delete=True
            refresh_cover_preview()
            page.update()
        def edit_control(field):
            value=manual_current_value(current_file(), field)
            if field == 'description':
                control=ft.TextField(value=str(value), multiline=True, min_lines=6, max_lines=6, height=DESCRIPTION_HEIGHT, width=320)
            elif field in BOOLEAN_FIELDS:
                control=ft.Checkbox(value=bool(value) if value is not None and value != '' else False)
            else:
                control=ft.TextField(value=str(value), width=320)
            controls[field]=control
            return control
        async def save_selected(close_after=True):
            save_button.disabled=True
            page.update()
            saving_dialog=ft.AlertDialog(modal=True, title=ft.Text('Saving metadata changes...'), content=ft.Column([ft.ProgressRing(), ft.Text('Writing tags. Please wait...')], tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER))
            open_dialog(saving_dialog)
            await asyncio.sleep(0.1)
            meta=current_file()
            try:
                updates=build_manual_metadata_diff(meta, edited_values(), cover_state)
                if not updates:
                    close_dialog(saving_dialog)
                    save_button.disabled=False
                    show_status('No manual metadata changes to save.')
                    page.update()
                    return False
                with Session() as session:
                    group=create_change_group(session, book.key, MANUAL_EDIT_SOURCE_TYPE, 'Manual metadata edit')
                    changes={tag: (manual_current_value(meta, 'cover') if tag in {'cover_path', 'delete_cover'} else getattr(meta, tag, None), new) for tag, new in updates.items()}
                    write_audio_metadata(meta.path, updates)
                    refreshed=read_audio_metadata(meta.path)
                    meta.__dict__.update(refreshed.__dict__)
                    log_changes(session, group, book.key, meta.path, changes, MANUAL_EDIT_SOURCE_TYPE)
                    session.commit()
                close_dialog(saving_dialog)
                show_success('Metadata changes saved.')
                show_status('Metadata changes saved.')
                if close_after:
                    close_dialog(dialog)
                    render()
                else:
                    load_file(meta)
                return True
            except Exception as exc:
                close_dialog(saving_dialog)
                save_button.disabled=False
                page.update()
                error_dialog=ft.AlertDialog(modal=True, title=ft.Text('Could not save metadata'), content=ft.Text(f'Failed to save metadata for {meta.path}: {exc}'), actions=[ft.TextButton('OK', on_click=lambda e: close_dialog(error_dialog))])
                open_dialog(error_dialog)
                show_status(f'Failed to save manual metadata for {meta.path}: {exc}')
                return False
        def request_file_switch(next_meta):
            if next_meta is current_file():
                return
            changed_fields=manual_changed_fields(current_file(), edited_values(), cover_state)
            logging.debug('Manual edit dirty check for %s: changed fields=%s', current_file().path, changed_fields)
            if not changed_fields:
                load_file(next_meta)
                return
            unsaved_dialog=None
            async def save_then_switch(_):
                close_dialog(unsaved_dialog)
                if await save_selected(close_after=False):
                    load_file(next_meta)
            def discard_then_switch(_):
                close_dialog(unsaved_dialog)
                load_file(next_meta)
            unsaved_dialog=ft.AlertDialog(
                modal=True,
                title=ft.Text('Unsaved changes'),
                content=ft.Text('You have unsaved changes for this file. What would you like to do?'),
                actions=[ft.FilledButton('Save', on_click=save_then_switch), ft.TextButton('Discard', on_click=discard_then_switch), ft.TextButton('Cancel', on_click=lambda e: close_dialog(unsaved_dialog))],
            )
            open_dialog(unsaved_dialog)
        refresh_cover_preview()
        header=ft.Row([
            cell(ft.Text('Tag', weight=ft.FontWeight.BOLD), 170),
            cell(ft.Text('Edit', weight=ft.FontWeight.BOLD), 380, column_border),
            cell(ft.Text('Current', weight=ft.FontWeight.BOLD), 300, column_border),
        ], spacing=0)
        rows=[header]
        for field, label in MANUAL_EDIT_TAGS:
            if field == 'cover':
                edit=ft.Column([cover_preview, ft.Row([ft.IconButton(icon=ft.Icons.ADD_PHOTO_ALTERNATE, tooltip='Change cover', on_click=choose_cover), ft.IconButton(icon=ft.Icons.CLOSE, tooltip='Delete cover', icon_color=ft.Colors.RED, on_click=delete_cover)], spacing=4)], spacing=4)
                current=ft.Container(content=current_cover_control(current_file()), width=300, padding=8, border=column_border)
            else:
                edit=edit_control(field)
                current_value=manual_current_value(current_file(), field)
                if field == 'description':
                    current=ft.Container(content=ft.Column([ft.Text(str(current_value), selectable=True, no_wrap=False)], scroll=ft.ScrollMode.AUTO), height=DESCRIPTION_HEIGHT, width=300, padding=8, border=column_border, clip_behavior=ft.ClipBehavior.HARD_EDGE)
                else:
                    current=ft.Container(content=ft.Text(str(current_value), selectable=True, width=284, no_wrap=False), width=300, padding=8, border=column_border)
            current_cells[field]=current
            rows.append(ft.Container(content=ft.Row([cell(ft.Text(label, weight=ft.FontWeight.W_500), 170), cell(edit, 380, column_border), current], spacing=0, vertical_alignment=ft.CrossAxisAlignment.START), border=row_border))
        def revert(_):
            load_file(current_file())
        async def save(_):
            await save_selected(close_after=True)
        form=ft.Column(rows, scroll=ft.ScrollMode.AUTO, height=560, width=860, spacing=0)
        content=form
        if book.is_folder_book:
            file_rows=[]
            for file_meta in edit_files:
                btn=ft.Container(content=ft.Text(manual_edit_file_label(file_meta), selectable=False, no_wrap=False), padding=8, width=240, bgcolor=selected_row_bg if file_meta is current_file() else None, on_click=lambda e, meta=file_meta: request_file_switch(meta), ink=True)
                file_buttons[file_meta.path]=btn
                file_rows.append(btn)
            content=ft.Row([ft.Container(content=ft.Column(file_rows, scroll=ft.ScrollMode.AUTO), width=260, height=560, border=ft.Border(right=ft.BorderSide(1, divider_color))), form], spacing=12, vertical_alignment=ft.CrossAxisAlignment.START)
        dialog=ft.AlertDialog(
            title=ft.Column([ft.Text('Edit Metadata'), ft.Text(book.display_name, size=12, selectable=True)]),
            content=content,
            actions=[ft.TextButton('Cancel', on_click=lambda e: close_dialog(dialog)), ft.TextButton('Revert', on_click=revert), (save_button := ft.FilledButton('Save', on_click=save))],
        )
        open_dialog(dialog)
    def render():
        grid.controls.clear()
        for b in books:
            first=b.files[0]
            header_controls = [
                ft.Row([ft.IconButton(icon=ft.Icons.EDIT, tooltip='Edit metadata', on_click=lambda e, book=b: show_manual_edit(book)), ft.Text(b.display_name, width=190)], width=240, spacing=0),
                ft.Text(first.title or '', width=150),
                ft.Text(first.author or '', width=120),
                ft.Text(first.narrator or '', width=120),
                ft.Text(first.series or '', width=100),
                ft.Text(first.series_sequence or '', width=70),
                ft.Text(first.asin or '', width=90),
                ft.Text(f'Tracks: {len(b.files)}'),
                ft.Button('Restore / Review History'),
                ft.Button('Search by Title + Author', on_click=create_title_author_search_handler(b)),
                ft.Button('Search by ASIN', on_click=create_asin_search_handler(b)),
            ]
            if b.is_folder_book:
                header_controls.append(ft.Button('Mass Update'))
            header=ft.Row(header_controls, wrap=True)
            if b.is_folder_book:
                grid.controls.append(ft.ExpansionTile(title=header, controls=[ft.Text(f'Track {f.track or i+1} - {f.path} | title={f.title or ""} album={f.album or ""} disc={f.disc or ""} cover={f.has_cover} dramatic_audio={f.dramatic_audio}') for i,f in enumerate(b.files)]))
            else: grid.controls.append(header)
        page.update()
    def apply_theme(e):
        settings['theme']=theme.value; save_settings(settings); page.theme_mode={'Light':ft.ThemeMode.LIGHT,'Dark':ft.ThemeMode.DARK}.get(theme.value, ft.ThemeMode.SYSTEM); page.update()
    theme=ft.Dropdown(label='Theme', value=settings.get('theme','System'), options=[ft.dropdown.Option(x) for x in ['System','Light','Dark']])
    theme.on_change=apply_theme
    async def select_working_directory(e):
        picker=create_file_picker()
        path = await maybe_await(picker.get_directory_path())
        if path:
            scan(path)
    def scan(path=None):
        nonlocal books
        path=path or settings.get('working_directory')
        if not path: status.value='No working directory selected.'; page.update(); return
        settings['working_directory']=path; save_settings(settings); status.value=f'Scanning {path}...'; page.update()
        books, errors=scan_directory(path)
        with Session() as s:
            for b in books: store_snapshot(s,b,'scan')
        status.value=f'Found {len(books)} books.' + (f' {len(errors)} scan warnings logged.' if errors else '')
        for err in errors: logging.warning(err)
        render()
    page.add(ft.Row([ft.Button('Select Working Directory', on_click=select_working_directory), ft.Button('Rescan', on_click=lambda _: scan()), theme]), status, grid)
    if settings.get('working_directory'): scan(settings['working_directory'])
if __name__ == '__main__': ft.run(main)

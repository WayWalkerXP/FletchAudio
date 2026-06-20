import asyncio
import inspect
import logging
import uuid
from pathlib import Path

import flet as ft
from mutagen import File, MutagenError

IMAGE_CONTAIN_FIT = getattr(getattr(ft, 'ImageFit', None) or ft.BoxFit, 'CONTAIN')
THEME_OPTIONS = ('System', 'Light', 'Dark')
THEME_MODES = {'Light': ft.ThemeMode.LIGHT, 'Dark': ft.ThemeMode.DARK}


VALID_TARGET_BITRATES = {'32', '48', '64', '96', '128', '256', '384'}
VALID_TARGET_CHANNELS = {'1', '2'}
TARGET_STATUS_TOOLTIPS = {
    'green': 'Targets configured',
    'red': 'Target bitrate and/or channels not configured',
    'yellow': 'Target settings are inconsistent across files',
}
TARGET_STATUS_COLORS = {
    'green': ft.Colors.GREEN,
    'red': ft.Colors.RED,
    'yellow': ft.Colors.AMBER,
}


def _metadata_path(file_metadata_or_path):
    return getattr(file_metadata_or_path, 'path', file_metadata_or_path)


def get_actual_bitrate(file_metadata_or_path) -> int | None:
    path = _metadata_path(file_metadata_or_path)
    if not path:
        return None
    try:
        audio = File(str(path), easy=False)
    except (MutagenError, OSError):
        return None
    bitrate = getattr(getattr(audio, 'info', None), 'bitrate', None) if audio else None
    if bitrate is None:
        return None
    try:
        return round(int(bitrate) / 1000)
    except (TypeError, ValueError):
        return None


def get_actual_channels(file_metadata_or_path) -> int | None:
    path = _metadata_path(file_metadata_or_path)
    if not path:
        return None
    try:
        audio = File(str(path), easy=False)
    except (MutagenError, OSError):
        return None
    channels = getattr(getattr(audio, 'info', None), 'channels', None) if audio else None
    if channels is None:
        return None
    try:
        return int(channels)
    except (TypeError, ValueError):
        return None


def summarize_distinct_values(values) -> str:
    distinct = sorted({int(value) for value in values if value is not None})
    if not distinct:
        return 'Unknown'
    return ', '.join(str(value) for value in distinct)


def normalize_target_int(value):
    if value is None:
        return None
    try:
        return str(int(str(value).strip()))
    except (TypeError, ValueError):
        return None


def target_settings_status(book):
    bitrate_values=[]
    channel_values=[]
    for file_meta in book.files:
        bitrate=normalize_target_int(getattr(file_meta, 'target_bitrate', None))
        channels=normalize_target_int(getattr(file_meta, 'target_channels', None))
        if bitrate not in VALID_TARGET_BITRATES or channels not in VALID_TARGET_CHANNELS:
            return 'red'
        bitrate_values.append(bitrate)
        channel_values.append(channels)
    if book.is_folder_book and (len(set(bitrate_values)) > 1 or len(set(channel_values)) > 1):
        return 'yellow'
    return 'green'

def theme_mode_for_setting(setting):
    return THEME_MODES.get(setting, ft.ThemeMode.SYSTEM)


def padding_symmetric(*, horizontal=0, vertical=0):
    return ft.Padding(left=horizontal, right=horizontal, top=vertical, bottom=vertical)

def padding_only(*, left=0, right=0, top=0, bottom=0):
    return ft.Padding(left=left, right=right, top=top, bottom=bottom)

def margin_only(*, left=0, right=0, top=0, bottom=0):
    return ft.Margin(left=left, right=right, top=top, bottom=bottom)

from .audible_client import AudibleClient, build_title_author_query, normalize_asin, parse_search_results, product_from_asin_response, runtime_difference_minutes, sort_results_by_runtime_match, validate_asin
from .config import load_settings, save_settings
from .db import init_db, get_session_factory
from .audio_scan import scan_directory
from .audio_tags import NON_WRITABLE_FIELDS, format_genres_for_tag, read_audio_metadata, write_audio_metadata
from .history import create_change_group, log_changes, metadata_diff, store_snapshot
from .metadata_map import normalize_response
from .maintenance import compact_database, database_path, format_bytes, get_database_size_display
from .staging import destination_for, discover_staging_candidates, move_to_staging, safe_move_to_staging, validate_staging_dir
from .manual_edit import BOOLEAN_FIELDS, CoverEditState, MANUAL_EDIT_SOURCE_TYPE, MANUAL_EDIT_TAGS, build_baseline_values, build_manual_metadata_diff, changed_edit_fields, debug_dirty_check, filter_manual_updates_for_file, manual_current_value, manual_edit_file_label, normalize_for_dirty_check, set_debug_dirty_selected_file_path, sorted_manual_edit_files
from .history_restore import changes_for_group_file, is_restore_supported, list_change_groups_for_file, restore_selected_metadata
logging.basicConfig(level=logging.INFO)

def log_page_state(page: ft.Page, label: str) -> None:
    try:
        logging.info(
            "[PAGE STATE] %s | route=%r | views=%s | controls=%s | overlay=%s | dialog=%s",
            label,
            getattr(page, "route", None),
            [getattr(view, "route", None) for view in getattr(page, "views", [])],
            len(getattr(page, "controls", []) or []),
            len(getattr(page, "overlay", []) or []),
            type(getattr(page, "dialog", None)).__name__ if getattr(page, "dialog", None) else None,
        )
    except Exception:
        logging.exception("Failed to log page state for %s", label)

def main(page: ft.Page):
    engine=init_db(); Session=get_session_factory(engine); settings=load_settings(); books=[]
    log_page_state(page, 'app startup before main window render')
    page.title='FletchAudio'; page.theme_mode=theme_mode_for_setting(settings.get('theme'))
    status=ft.Text('Select a working directory to begin.'); grid=ft.Column(scroll=ft.ScrollMode.AUTO, expand=True); expanded_book_keys=set(); url_launcher=ft.UrlLauncher(); audible=AudibleClient(); compact_db_button=ft.Button(content='Compact Database', on_click=None)
    active_move_to_staging_screen_id=None
    if hasattr(page, 'services'):
        page.services.append(url_launcher)
    elif hasattr(page, 'overlay'):
        page.overlay.append(url_launcher)
    def show_status(message: str):
        status.value=message; page.update()
    existing_route_handler=getattr(page, 'on_route_change', None)
    if existing_route_handler:
        def diagnostic_route_change(event):
            log_page_state(page, 'before route-change handling')
            result=existing_route_handler(event)
            log_page_state(page, 'after route-change handling')
            return result
        page.on_route_change=diagnostic_route_change
    else:
        logging.info('No page.on_route_change handler installed; route-change diagnostics will rely on explicit navigation logs.')
    def compact_database_button_text() -> str:
        return f'Compact Database ({get_database_size_display(database_path(engine))})'

    def refresh_compact_database_button():
        compact_db_button.content = compact_database_button_text()

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
        close_control = getattr(page, 'close', None)
        if close_control and dialog:
            close_control(dialog)
        elif getattr(page, 'pop_dialog', None):
            page.pop_dialog()
        if dialog:
            dialog.open = False
            if getattr(page, 'dialog', None) is dialog:
                page.dialog = None
            overlay = getattr(page, 'overlay', None)
            if overlay and dialog in overlay:
                overlay.remove(dialog)
        page.update()

    def clear_dialog_state(dialog=None):
        close_control = getattr(page, 'close', None)
        dialogs_to_close = []
        if dialog:
            dialog.open = False
            dialogs_to_close.append(dialog)
        active_dialog = getattr(page, 'dialog', None)
        if active_dialog and active_dialog not in dialogs_to_close:
            dialogs_to_close.append(active_dialog)
        overlay = getattr(page, 'overlay', None)
        if overlay is not None:
            dialogs_to_close.extend(
                control for control in list(overlay)
                if isinstance(control, ft.AlertDialog) and control not in dialogs_to_close
            )
        for control in dialogs_to_close:
            if control is not dialog:
                control.open = False
            if close_control:
                close_control(control)
        if hasattr(page, 'dialog'):
            page.dialog = None
        if overlay is not None:
            for control in dialogs_to_close:
                if control in overlay:
                    overlay.remove(control)

    def return_to_main_menu_after_staging(dialog=None, move_screen_id=None):
        nonlocal active_move_to_staging_screen_id
        log_page_state(page, 'before returning to main menu after staging')
        if move_screen_id and active_move_to_staging_screen_id == move_screen_id:
            logging.info('Retiring Move to Staging screen id=%s', move_screen_id)
            active_move_to_staging_screen_id=None
        clear_dialog_state(dialog)
        if settings.get('working_directory'):
            scan()
        else:
            render()
        page.update()
        log_page_state(page, 'after returning to main menu after staging')

    def open_progress_dialog(message):
        dialog=ft.AlertDialog(
            modal=True,
            title=ft.Text(message),
            content=ft.Column([
                ft.ProgressRing(),
                ft.Text('Writing tags. Please wait...'),
            ], tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
        )
        open_dialog(dialog)
        return dialog

    def refresh_books_from_disk():
        nonlocal books
        path=settings.get('working_directory')
        if not path:
            render()
            return
        refreshed_books, errors=scan_directory(path)
        books=refreshed_books
        for err in errors:
            logging.warning(err)
        render()

    async def run_modal_save_flow(current_dialog, progress_message, save_operation, success_message, error_title, error_message):
        close_dialog(current_dialog)
        page.update()
        progress_dialog=open_progress_dialog(progress_message)
        page.update()
        # Yield to Flet so the dismissed edit modal is removed before the progress modal is shown.
        await asyncio.sleep(0.1)
        try:
            result=save_operation()
            if inspect.isawaitable(result):
                await result
            close_dialog(progress_dialog)
            page.update()
            refresh_books_from_disk()
            show_success(success_message)
            show_status(success_message)
            return True
        except Exception as exc:
            close_dialog(progress_dialog)
            page.update()
            error_dialog=ft.AlertDialog(
                modal=True,
                title=ft.Text(error_title),
                content=ft.Text(error_message(exc)),
                actions=[ft.TextButton('OK', on_click=lambda e: close_dialog(error_dialog))],
            )
            open_dialog(error_dialog)
            show_status(error_message(exc))
            return False
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
    def show_comparison(book, metadata, source_type='audible_title_author'):
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

            close_dialog(dialog)
            page.update()
            open_dialog(saving_dialog)
            page.update()
            # Yield to Flet so the comparison modal closes and the saving modal is sent to the client before the synchronous tag write starts.
            await asyncio.sleep(0.1)
            updates=normalize_for_dirty_check({field: downloaded for field, _, downloaded, _, _ in specs if field not in NON_WRITABLE_FIELDS and selected.get(field) and selected[field].value and is_present(downloaded)})
            if not updates:
                close_dialog(saving_dialog)
                apply_button.disabled=False
                open_dialog(dialog)
                page.update()
                show_status('No downloaded metadata fields selected to apply.')
                return
            try:
                with Session() as session:
                    group=create_change_group(session, book.key, source_type, 'Audible metadata update')
                    for file_metadata in book.files:
                        changes={tag: (getattr(file_metadata, tag, None), new_value) for tag, new_value in metadata_diff(file_metadata, updates).items()}
                        write_audio_metadata(file_metadata.path, updates)
                        refreshed=read_audio_metadata(file_metadata.path)
                        file_metadata.__dict__.update(refreshed.__dict__)
                        log_changes(session, group, book.key, file_metadata.path, changes, source_type)
                    session.commit()
                close_dialog(saving_dialog)
                render()
                show_success('Metadata changes saved.')
                show_status('Metadata changes saved.')
            except Exception as exc:
                close_dialog(saving_dialog)
                apply_button.disabled=False

                def return_to_comparison(_):
                    close_dialog(error_dialog)
                    open_dialog(dialog)

                def dismiss_error(_):
                    close_dialog(error_dialog)

                error_dialog=ft.AlertDialog(
                    modal=True,
                    title=ft.Text('Could not save metadata'),
                    content=ft.Text(f'Failed to apply metadata to {book.display_name}: {exc}'),
                    actions=[
                        ft.TextButton('Retry', on_click=return_to_comparison),
                        ft.TextButton('Cancel', on_click=dismiss_error),
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
    async def search_by_title_author(book, author, title_or_album):
        query=build_title_author_query(author, title_or_album)
        if not query:
            show_status(f'Cannot search {book.display_name}: missing title metadata.')
            return
        try:
            response=audible.search(author, title_or_album)
        except Exception as exc:
            show_status(f'Audible title/author search failed for {book.display_name}: {exc}')
            return
        source_seconds=source_duration_seconds(book)
        results=sort_results_by_runtime_match(parse_search_results(response), source_seconds)
        if not results:
            show_status(f'No Audible results found for: {query}')
            no_results_dialog=None
            no_results_dialog=ft.AlertDialog(
                modal=True,
                title=ft.Text('No Audible results'),
                content=ft.Text('No Audible results found.'),
                actions=[ft.TextButton('Close', on_click=lambda e: close_dialog(no_results_dialog))],
            )
            open_dialog(no_results_dialog)
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
            show_comparison(book, metadata, source_type='audible_title_author')
        rows=[ft.Row([ft.Text('Title', width=180), ft.Text('Subtitle', width=120), ft.Text('Authors', width=140), ft.Text('Narrators', width=140), ft.Text('Audible', width=80), ft.Text('Source', width=90), ft.Text('Diff min', width=80), ft.Text('Series', width=120), ft.Text('ASIN', width=90)])]
        for result in results:
            async def handler(_, selected=result):
                close_dialog(dialog)
                await select_result(selected)
            rows.append(result_row(result, source_seconds, handler))
        dialog=ft.AlertDialog(title=ft.Text('Select Audible search result'), content=ft.Column(rows, scroll=ft.ScrollMode.AUTO, height=500, width=1300), actions=[ft.TextButton('Cancel', on_click=lambda e: close_dialog(dialog))])
        open_dialog(dialog)
        show_status(f'Found {len(results)} Audible results for: {query}. Select one to compare metadata.')
    async def lookup_asin_and_compare(book, asin):
        try:
            response=audible.lookup_asin(asin)
            product=product_from_asin_response(response)
            if not product:
                show_status(f'No Audible book found for ASIN {asin}.')
                return
            metadata=normalize_response(product)
        except ValueError as exc:
            show_status(str(exc))
            return
        except Exception as exc:
            show_status(f'Audible ASIN lookup failed for {asin}: {exc}')
            return
        show_status(f'Found Audible book for ASIN {asin}; showing comparison.')
        show_comparison(book, metadata, source_type='audible_asin')

    async def search_by_asin(book):
        first=book.files[0]
        asin_field=ft.TextField(label='ASIN', value=first.asin or '', autofocus=True, width=320)
        error_text=ft.Text('', color=ft.Colors.RED)
        dialog=None
        async def submit(_):
            clean=normalize_asin(asin_field.value)
            valid, error=validate_asin(clean)
            if not valid:
                error_text.value=error
                page.update()
                return
            close_dialog(dialog)
            await lookup_asin_and_compare(book, clean)
        dialog=ft.AlertDialog(
            modal=True,
            title=ft.Text('Search Audible by ASIN'),
            content=ft.Column([ft.Text(f'Confirm or edit the ASIN for {book.display_name}.'), asin_field, error_text], tight=True, width=360),
            actions=[ft.FilledButton('Search', on_click=submit), ft.TextButton('Cancel', on_click=lambda e: close_dialog(dialog))],
        )
        open_dialog(dialog)
    async def confirm_title_author_search(book):
        first=book.files[0]
        author_field=ft.TextField(label='Author', value=first.author or first.albumartist or '', autofocus=True, width=420)
        title_field=ft.TextField(label='Album/Title', value=first.album or first.title or book.display_name, width=420)
        error_text=ft.Text('', color=ft.Colors.RED)
        warning_text=ft.Text('', color=ft.Colors.AMBER)
        dialog=None
        async def submit(_):
            title=(title_field.value or '').strip()
            author=(author_field.value or '').strip()
            if not title:
                error_text.value='Title is required.'
                warning_text.value=''
                page.update()
                return
            error_text.value=''
            if not author:
                warning_text.value='Author is blank; searching by title only.'
                show_status('Author is blank; searching by title only.')
            close_dialog(dialog)
            await search_by_title_author(book, author, title)
        dialog=ft.AlertDialog(
            modal=True,
            title=ft.Text('Search Audible by Title & Author'),
            content=ft.Column([
                ft.Text(f'Confirm or edit the Audible search terms for {book.display_name}.'),
                author_field,
                title_field,
                error_text,
                warning_text,
            ], tight=True, width=460),
            actions=[ft.FilledButton('Search', on_click=submit), ft.TextButton('Cancel', on_click=lambda e: close_dialog(dialog))],
        )
        open_dialog(dialog)
    def create_title_author_search_handler(book):
        async def handler(_):
            await confirm_title_author_search(book)
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
        files_by_path={file_meta.path: file_meta for file_meta in edit_files}
        selected_file={'meta': edit_files[0]}
        selected_file_path={'path': edit_files[0].path}
        baseline_values={'values': {}}
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
        def build_edit_values_from_controls():
            return edited_values()
        def has_unsaved_changes():
            edited=build_edit_values_from_controls()
            set_debug_dirty_selected_file_path(selected_file_path['path'])
            changed_fields=changed_edit_fields(baseline_values['values'], edited, cover_state)
            if changed_fields:
                debug_dirty_check(baseline_values['values'], edited)
                logging.debug('Dirty fields:\n%s', '\n'.join(f"  {field}: baseline={old!r} edited={new!r}" for field, (old, new) in changed_fields.items()))
            return bool(changed_fields)
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
        def load_selected_file(file_path):
            meta=files_by_path[file_path]
            normalized_baseline=normalize_for_dirty_check(build_baseline_values(meta))
            baseline_values['values']=dict(normalized_baseline)
            selected_file['meta']=meta
            selected_file_path['path']=file_path
            for field, control in controls.items():
                value=baseline_values['values'].get(field, '')
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
                button.bgcolor=selected_row_bg if file_meta_path == selected_file_path['path'] else None
            dirty=has_unsaved_changes()
            print(f'After load dirty check result: {dirty}')
            logging.info('Loaded file %s; dirty=%s', file_path, dirty)
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
        async def save_selected(close_after=False):
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
                if close_after:
                    close_dialog(dialog)
                    render()
                else:
                    load_selected_file(meta.path)
                    show_success('Metadata changes saved.')
                    show_status('Metadata changes saved.')
                    save_button.disabled=False
                    page.update()
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
            if next_meta.path == selected_file_path['path']:
                return
            if not has_unsaved_changes():
                load_selected_file(next_meta.path)
                return
            unsaved_dialog=None
            async def save_then_switch(_):
                close_dialog(unsaved_dialog)
                if await save_selected(close_after=False):
                    load_selected_file(next_meta.path)
            def discard_then_switch(_):
                close_dialog(unsaved_dialog)
                load_selected_file(next_meta.path)
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
            for field, control in controls.items():
                value=baseline_values['values'].get(field, '')
                if isinstance(control, ft.Checkbox):
                    control.value=bool(value) if value is not None and value != '' else False
                else:
                    control.value=str(value)
            cover_state.path=None
            cover_state.delete=False
            refresh_cover_preview()
            page.update()
        async def save(_):
            await save_selected(close_after=False)
        def close_editor():
            close_dialog(dialog)
            render()
        def confirm_discard_and_close():
            confirm_dialog=ft.AlertDialog(
                modal=True,
                title=ft.Text('Discard unsaved changes?'),
                content=ft.Text('Discard unsaved changes?'),
                actions=[ft.TextButton('Keep Editing', on_click=lambda e: close_dialog(confirm_dialog)), ft.FilledButton('Discard', on_click=lambda e: (close_dialog(confirm_dialog), close_editor()))],
            )
            open_dialog(confirm_dialog)
        def cancel_editor(_):
            if has_unsaved_changes():
                confirm_discard_and_close()
            else:
                close_editor()
        def exit_editor(_):
            if not has_unsaved_changes():
                close_editor()
                return
            exit_dialog=None
            async def save_and_exit(_):
                close_dialog(exit_dialog)
                await save_selected(close_after=True)
            def discard_and_exit(_):
                close_dialog(exit_dialog)
                close_editor()
            exit_dialog=ft.AlertDialog(
                modal=True,
                title=ft.Text('Unsaved changes'),
                content=ft.Text('You have unsaved changes. What would you like to do?'),
                actions=[ft.FilledButton('Save and Exit', on_click=save_and_exit), ft.TextButton('Discard and Exit', on_click=discard_and_exit), ft.TextButton('Cancel', on_click=lambda e: close_dialog(exit_dialog))],
            )
            open_dialog(exit_dialog)
        form=ft.Column(rows, scroll=ft.ScrollMode.AUTO, height=560, width=860, spacing=0)
        content=form
        if book.is_folder_book:
            file_rows=[]
            for file_meta in edit_files:
                btn=ft.Container(content=ft.Text(manual_edit_file_label(file_meta), selectable=False, no_wrap=False), padding=8, width=240, bgcolor=selected_row_bg if file_meta is current_file() else None, on_click=lambda e, meta=file_meta: request_file_switch(meta), ink=True)
                file_buttons[file_meta.path]=btn
                file_rows.append(btn)
            content=ft.Row([ft.Container(content=ft.Column(file_rows, scroll=ft.ScrollMode.AUTO), width=260, height=560, border=ft.Border(right=ft.BorderSide(1, divider_color))), form], spacing=12, vertical_alignment=ft.CrossAxisAlignment.START)
        load_selected_file(edit_files[0].path)
        dialog=ft.AlertDialog(
            title=ft.Column([ft.Text('Edit Metadata'), ft.Text(book.display_name, size=12, selectable=True)]),
            content=content,
            actions=[
                ft.Row(
                    [
                        ft.TextButton('Exit', on_click=exit_editor),
                        ft.Row([ft.FilledButton('Save', on_click=save), ft.TextButton('Revert', on_click=revert), ft.TextButton('Cancel', on_click=cancel_editor)], spacing=8),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    width=860,
                )
            ],
        )
        save_button=dialog.actions[0].controls[1].controls[0]
        open_dialog(dialog)
    def show_set_targets(book):
        valid_bitrates=tuple(sorted(VALID_TARGET_BITRATES, key=int))
        valid_channels=tuple(sorted(VALID_TARGET_CHANNELS, key=int))
        source_type='set_targets'
        divider_color=ft.Colors.OUTLINE_VARIANT
        row_border=ft.Border(bottom=ft.BorderSide(1, divider_color))
        column_border=ft.Border(left=ft.BorderSide(1, divider_color))

        def normalize_int_text(value):
            return normalize_target_int(value)

        def normalize_bool_value(value):
            if isinstance(value, bool):
                return value
            if value is None:
                return None
            text=str(value).strip().lower()
            if text in {'true', '1', 'yes', 'y', 'on', 'checked'}:
                return True
            if text in {'false', '0', 'no', 'n', 'off', 'unchecked'}:
                return False
            return None

        def distinct_values(field):
            values=[]
            seen=set()
            for file_meta in book.files:
                value=getattr(file_meta, field, None)
                if value is None or value == '':
                    continue
                normalized=normalize_bool_value(value) if field == 'dramatic_audio' else normalize_int_text(value)
                if normalized is None:
                    continue
                key=normalized
                if key not in seen:
                    seen.add(key)
                    values.append(normalized)
            return values

        def format_current(values):
            if not values:
                return 'Unset'
            return ', '.join('True' if value is True else 'False' if value is False else str(value) for value in values)

        bitrate_values=distinct_values('target_bitrate')
        channel_values=distinct_values('target_channels')
        dramatic_values=distinct_values('dramatic_audio')
        actual_bitrate_current=summarize_distinct_values(get_actual_bitrate(file_meta) for file_meta in book.files)
        actual_channels_current=summarize_distinct_values(get_actual_channels(file_meta) for file_meta in book.files)
        bitrate_prefill=bitrate_values[0] if len(bitrate_values) == 1 and str(bitrate_values[0]) in valid_bitrates else None
        channel_prefill=channel_values[0] if len(channel_values) == 1 and str(channel_values[0]) in valid_channels else '1'
        dramatic_prefill=dramatic_values[0] if len(dramatic_values) == 1 else False

        bitrate_dropdown=ft.Dropdown(width=220, value=bitrate_prefill, options=[ft.dropdown.Option(value) for value in valid_bitrates])
        channels_dropdown=ft.Dropdown(width=220, value=channel_prefill, options=[ft.dropdown.Option(value) for value in valid_channels])
        dramatic_checkbox=ft.Checkbox(value=bool(dramatic_prefill))
        error_text=ft.Text('', color=ft.Colors.RED)

        def cell(content, width, border=None, padding=8):
            if isinstance(content, str):
                content=ft.Text(content, selectable=True, width=width - (padding * 2), no_wrap=False)
            return ft.Container(content=content, width=width, padding=padding, border=border)

        rows=[ft.Row([
            cell(ft.Text('Field', weight=ft.FontWeight.BOLD), 170),
            cell(ft.Text('Target Value', weight=ft.FontWeight.BOLD), 250, column_border),
            cell(ft.Text('Current Value', weight=ft.FontWeight.BOLD), 250, column_border),
        ], spacing=0)]
        for label, control, current in [
            ('Bitrate', bitrate_dropdown, actual_bitrate_current),
            ('Channels', channels_dropdown, actual_channels_current),
            ('Dramatic Audio', dramatic_checkbox, format_current(dramatic_values)),
        ]:
            rows.append(ft.Container(content=ft.Row([
                cell(ft.Text(label, weight=ft.FontWeight.W_500), 170),
                cell(control, 250, column_border),
                cell(current, 250, column_border),
            ], spacing=0, vertical_alignment=ft.CrossAxisAlignment.START), border=row_border))
        rows.append(error_text)

        async def save_targets(_):
            error_text.value=''
            updates={}
            bitrate=normalize_int_text(bitrate_dropdown.value)
            channels=normalize_int_text(channels_dropdown.value) or '1'
            dramatic=normalize_bool_value(dramatic_checkbox.value)
            if bitrate_dropdown.value not in (None, '') and bitrate not in valid_bitrates:
                error_text.value='Bitrate must be one of: ' + ', '.join(valid_bitrates)
                page.update()
                return
            if channels not in valid_channels:
                error_text.value='Channels must be 1 or 2.'
                page.update()
                return
            if dramatic is None:
                error_text.value='Dramatic Audio must be True or False.'
                page.update()
                return
            if bitrate:
                updates['target_bitrate']=int(bitrate)
            updates['target_channels']=int(channels)
            updates['dramatic_audio']=dramatic
            save_button.disabled=True
            page.update()

            def write_target_settings():
                with Session() as session:
                    group=create_change_group(session, book.key, source_type, 'Set target settings')
                    for file_metadata in book.files:
                        changes={tag: (getattr(file_metadata, tag, None), new_value) for tag, new_value in metadata_diff(file_metadata, updates).items()}
                        if not changes:
                            continue
                        write_audio_metadata(file_metadata.path, {tag: new for tag, (_, new) in changes.items()})
                        refreshed=read_audio_metadata(file_metadata.path)
                        file_metadata.__dict__.update(refreshed.__dict__)
                        log_changes(session, group, book.key, file_metadata.path, changes, source_type)
                    session.commit()

            await run_modal_save_flow(
                dialog,
                'Saving target settings...',
                write_target_settings,
                'Target settings saved.',
                'Could not save target settings',
                lambda exc: f'Failed to save target settings for {book.display_name}: {exc}',
            )

        dialog=ft.AlertDialog(
            modal=True,
            title=ft.Column([ft.Text('Set Targets and Dramatic Audio'), ft.Text(book.display_name, size=12, selectable=True)]),
            content=ft.Column(rows, scroll=ft.ScrollMode.AUTO, height=260, width=670, spacing=0),
            actions=[(save_button := ft.FilledButton('Save', on_click=save_targets)), ft.TextButton('Cancel', on_click=lambda e: close_dialog(dialog))],
        )
        open_dialog(dialog)

    def show_metadata_history(book):
        history_files=sorted_manual_edit_files(book.files) if book.is_folder_book else list(book.files)
        files_by_path={file_meta.path: file_meta for file_meta in history_files}
        selected_file={'meta': history_files[0]}
        selected_group={'group_id': None}
        selected_changes=[]
        selected_checks={}
        group_buttons={}
        file_buttons={}
        groups_column=ft.Column(scroll=ft.ScrollMode.AUTO, expand=True)
        details_column=ft.Column(scroll=ft.ScrollMode.AUTO, expand=True)
        selected_row_bg=ft.Colors.PRIMARY_CONTAINER
        divider_color=ft.Colors.OUTLINE_VARIANT
        row_border=ft.Border(bottom=ft.BorderSide(1, divider_color))
        column_border=ft.Border(left=ft.BorderSide(1, divider_color))
        def cell(content, width, border=None, padding=8):
            if isinstance(content, str):
                content=ft.Text(content, selectable=True, width=width - (padding * 2), no_wrap=False)
            return ft.Container(content=content, width=width, padding=padding, border=border)
        def display_value(value):
            if value is None:
                return ''
            if isinstance(value, bool):
                return 'True' if value else 'False'
            if isinstance(value, list):
                return format_genres_for_tag(value) or ''
            return str(value)
        def current_value(meta, tag):
            if tag == 'genres':
                return format_genres_for_tag(meta.genres) or ''
            if not hasattr(meta, tag):
                return ''
            value=getattr(meta, tag, None)
            if isinstance(value, bool):
                return 'True' if value else 'False'
            return display_value(value)
        def refresh_group_selection():
            for group_id, button in group_buttons.items():
                button.bgcolor=selected_row_bg if group_id == selected_group['group_id'] else None
        def load_group(group_id):
            selected_group['group_id']=group_id
            selected_checks.clear()
            selected_changes.clear()
            details_column.controls.clear()
            meta=selected_file['meta']
            with Session() as session:
                changes=changes_for_group_file(session, group_id, meta.path)
                selected_changes.extend(changes)
            details_column.controls.append(ft.Row([
                cell(ft.Text('Restore', weight=ft.FontWeight.BOLD), 90),
                cell(ft.Text('Tag', weight=ft.FontWeight.BOLD), 130, column_border),
                cell(ft.Text('Old Value', weight=ft.FontWeight.BOLD), 210, column_border),
                cell(ft.Text('New Value', weight=ft.FontWeight.BOLD), 210, column_border),
                cell(ft.Text('Current Value', weight=ft.FontWeight.BOLD), 210, column_border),
            ], spacing=0))
            for change in selected_changes:
                supported=is_restore_supported(change.tag_name) and hasattr(meta, change.tag_name)
                checkbox=ft.Checkbox(value=False, disabled=not supported, tooltip='Cover, duration, and derived fields cannot be restored here.' if not supported else None)
                selected_checks[change.id]=checkbox
                details_column.controls.append(ft.Container(content=ft.Row([
                    cell(checkbox, 90),
                    cell(change.tag_name, 130, column_border),
                    cell(change.old_value or '', 210, column_border),
                    cell(change.new_value or '', 210, column_border),
                    cell(current_value(meta, change.tag_name), 210, column_border),
                ], spacing=0, vertical_alignment=ft.CrossAxisAlignment.START), border=row_border))
            refresh_group_selection()
            page.update()
        def load_file(file_path):
            selected_file['meta']=files_by_path[file_path]
            selected_group['group_id']=None
            group_buttons.clear()
            groups_column.controls.clear()
            details_column.controls.clear()
            with Session() as session:
                groups=list_change_groups_for_file(session, book.key, file_path)
            if not groups:
                groups_column.controls.append(ft.Text('No metadata history found for this item.'))
                details_column.controls.append(ft.Text('No metadata history found for this item.'))
            else:
                for item in groups:
                    group=item.group
                    timestamp=group.created_at.strftime('%Y-%m-%d %H:%M:%S') if group.created_at else ''
                    description=group.description or ''
                    label=ft.Column([
                        ft.Text(timestamp, weight=ft.FontWeight.BOLD),
                        ft.Text(f'{group.source_type} · {item.changed_field_count} changed field(s)'),
                        ft.Text(description, size=12, no_wrap=False),
                    ], spacing=2)
                    btn=ft.Container(content=label, padding=8, width=260, on_click=lambda e, gid=group.id: load_group(gid), ink=True)
                    group_buttons[group.id]=btn
                    groups_column.controls.append(btn)
                load_group(groups[0].group.id)
            for path, button in file_buttons.items():
                button.bgcolor=selected_row_bg if path == file_path else None
            page.update()
        async def restore_selected(_):
            checked_ids={change_id for change_id, checkbox in selected_checks.items() if checkbox.value}
            changes=[change for change in selected_changes if change.id in checked_ids]
            if not changes:
                show_status('No metadata history fields selected to restore.')
                return
            restore_button.disabled=True
            saving_dialog=ft.AlertDialog(modal=True, title=ft.Text('Restoring metadata...'), content=ft.Column([ft.ProgressRing(), ft.Text('Writing selected old values. Please wait...')], tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER))
            open_dialog(saving_dialog)
            await asyncio.sleep(0.1)
            try:
                with Session() as session:
                    restore_selected_metadata(session, book.key, selected_file['meta'], changes)
                close_dialog(saving_dialog)
                load_file(selected_file['meta'].path)
                show_success('Selected metadata values restored.')
                show_status('Selected metadata values restored.')
                restore_button.disabled=False
                render()
            except Exception as exc:
                close_dialog(saving_dialog)
                restore_button.disabled=False
                page.update()
                error_dialog=ft.AlertDialog(modal=True, title=ft.Text('Could not restore metadata'), content=ft.Text(f'Failed to restore metadata for {selected_file["meta"].path}: {exc}'), actions=[ft.TextButton('OK', on_click=lambda e: close_dialog(error_dialog))])
                open_dialog(error_dialog)
                show_status(f'Failed to restore metadata for {selected_file["meta"].path}: {exc}')
        left=ft.Row([ft.Container(content=groups_column, width=280, height=560, border=ft.Border(right=ft.BorderSide(1, divider_color))), ft.Container(content=details_column, width=860, height=560)], spacing=12, vertical_alignment=ft.CrossAxisAlignment.START)
        content=left
        if book.is_folder_book:
            file_rows=[]
            for file_meta in history_files:
                btn=ft.Container(content=ft.Text(manual_edit_file_label(file_meta), no_wrap=False), padding=8, width=220, on_click=lambda e, path=file_meta.path: load_file(path), ink=True)
                file_buttons[file_meta.path]=btn
                file_rows.append(btn)
            content=ft.Row([ft.Container(content=ft.Column(file_rows, scroll=ft.ScrollMode.AUTO), width=240, height=560, border=ft.Border(right=ft.BorderSide(1, divider_color))), left], spacing=12, vertical_alignment=ft.CrossAxisAlignment.START)
        dialog=ft.AlertDialog(
            title=ft.Column([ft.Text('Metadata History'), ft.Text(book.display_name, size=12, selectable=True)]),
            content=content,
            actions=[(restore_button := ft.FilledButton('Restore Selected', on_click=restore_selected)), ft.TextButton('Close', on_click=lambda e: close_dialog(dialog))],
        )
        load_file(history_files[0].path)
        open_dialog(dialog)

    def show_warning(title, message):
        warning_dialog=ft.AlertDialog(
            modal=True,
            title=ft.Text(title),
            content=ft.Text(message, selectable=True),
            actions=[ft.TextButton('OK', on_click=lambda e: close_dialog(warning_dialog))],
        )
        open_dialog(warning_dialog)
        show_status(message)

    def show_move_to_staging(_=None):
        nonlocal active_move_to_staging_screen_id
        move_screen_id=uuid.uuid4().hex[:8]
        active_move_to_staging_screen_id=move_screen_id
        logging.info('Opening Move to Staging screen id=%s', move_screen_id)
        log_page_state(page, f'before rendering Move to Staging screen id={move_screen_id}')
        staging_value=(settings.get('staging_dir') or '').strip()
        if not staging_value:
            show_warning('Staging directory required', 'No staging directory is configured. Please configure a staging directory in Settings before moving books to staging.')
            return
        staging_dir=Path(staging_value).expanduser()
        ok, message=validate_staging_dir(staging_dir)
        if not ok:
            show_warning('Staging directory unavailable', message)
            return
        working_directory=settings.get('working_directory')
        if not working_directory:
            show_warning('Working directory required', 'No working directory is selected. Please select a working directory before moving books to staging.')
            return
        candidates=discover_staging_candidates(Path(working_directory).expanduser())
        logging.info('Building Move to Staging screen id=%s candidates=%s', move_screen_id, len(candidates))
        logging.info('Move to Staging candidate count id=%s: %s', move_screen_id, len(candidates))
        logging.info('Move to Staging candidate source paths id=%s: %s', move_screen_id, [str(candidate.source_path) for candidate in candidates])
        logging.info('Move to Staging candidate destinations id=%s: %s', move_screen_id, [str(destination_for(candidate, staging_dir)) for candidate in candidates])
        logging.info('Move to Staging candidates id=%s are freshly discovered local variables; previous candidate list/view reused=False cached_view=False cached_controls=False', move_screen_id)
        selected_checks={}
        rows=[]
        divider_color=ft.Colors.OUTLINE_VARIANT
        row_border=ft.Border(bottom=ft.BorderSide(1, divider_color))
        column_border=ft.Border(left=ft.BorderSide(1, divider_color))
        def cell(content, width, border=None, padding=8):
            if isinstance(content, str):
                content=ft.Text(content, selectable=True, width=width - (padding * 2), no_wrap=False)
            return ft.Container(content=content, width=width, padding=padding, border=border)
        if candidates:
            rows.append(ft.Row([
                cell(ft.Text('Move', weight=ft.FontWeight.BOLD), 80),
                cell(ft.Text('Book', weight=ft.FontWeight.BOLD), 220, column_border),
                cell(ft.Text('Type', weight=ft.FontWeight.BOLD), 80, column_border),
                cell(ft.Text('Current Location', weight=ft.FontWeight.BOLD), 360, column_border),
                cell(ft.Text('Target Bitrate', weight=ft.FontWeight.BOLD), 130, column_border),
                cell(ft.Text('Target Channels', weight=ft.FontWeight.BOLD), 140, column_border),
            ], spacing=0))
            for candidate in candidates:
                checkbox=ft.Checkbox(value=True)
                selected_checks[candidate.source_path]=checkbox
                rows.append(ft.Container(content=ft.Row([
                    cell(checkbox, 80),
                    cell(candidate.display_name, 220, column_border),
                    cell('Folder' if candidate.item_type == 'folder' else 'File', 80, column_border),
                    cell(str(candidate.source_path), 360, column_border),
                    cell(candidate.target_bitrate, 130, column_border),
                    cell(candidate.target_channels, 140, column_border),
                ], spacing=0, vertical_alignment=ft.CrossAxisAlignment.START), border=row_border))
        else:
            rows.append(ft.Text('No books are ready for staging. Books must have both target_bitrate and target_channels defined before they can be moved.'))

        async def confirm_move(_):
            logging.info('Move to Staging Move button clicked id=%s', move_screen_id)
            log_page_state(page, f'before Move button handler id={move_screen_id}')
            selected=[candidate for candidate in candidates if selected_checks[candidate.source_path].value]
            if not selected:
                show_status('No books selected for staging.')
                return
            logging.info('Move to Staging selected count id=%s: %s', move_screen_id, len(selected))
            logging.info('Move to Staging selected source paths id=%s: %s', move_screen_id, [str(candidate.source_path) for candidate in selected])
            logging.info('Move to Staging selected destination paths id=%s: %s', move_screen_id, [str(destination_for(candidate, staging_dir)) for candidate in selected])
            for candidate in selected:
                logging.info('Selected staging item id=%s: %s', move_screen_id, candidate.source_path)
            message=f'{len(selected)} selected book(s) will be moved to:\n{staging_dir}\n\nFiles/folders will be moved out of the working directory.'
            async def run_mode(mode):
                logging.info('Move to Staging mode selected id=%s mode=%s', move_screen_id, mode)
                if mode == 'Safe Move':
                    logging.info('Move to Staging Safe Move button clicked id=%s', move_screen_id)
                else:
                    logging.info('Move to Staging Move confirm button clicked id=%s', move_screen_id)
                log_page_state(page, f'before staging async task UI update id={move_screen_id} mode={mode}')
                close_dialog(confirm_dialog)
                close_dialog(dialog)
                logging.info('Move to Staging async task scheduling run_staging_move id=%s mode=%s', move_screen_id, mode)
                await run_staging_move(selected, staging_dir, mode, move_screen_id)
            confirm_dialog=ft.AlertDialog(
                modal=True,
                title=ft.Text('Confirm Move to Staging'),
                content=ft.Text(message, selectable=True),
                actions=[
                    ft.TextButton('Cancel', on_click=lambda e: close_dialog(confirm_dialog)),
                    ft.FilledButton('Safe Move', on_click=lambda e: page.run_task(run_mode, 'Safe Move') if hasattr(page, 'run_task') else asyncio.create_task(run_mode('Safe Move'))),
                    ft.FilledButton('Move', on_click=lambda e: page.run_task(run_mode, 'Move') if hasattr(page, 'run_task') else asyncio.create_task(run_mode('Move'))),
                ],
            )
            open_dialog(confirm_dialog)

        def handle_move_to_staging_cancel(e):
            logging.info('Move to Staging Cancel clicked id=%s', move_screen_id)
            log_page_state(page, f'before Move to Staging Cancel handler id={move_screen_id}')
            return_to_main_menu_after_staging(dialog, move_screen_id)
            log_page_state(page, f'after Move to Staging Cancel handler id={move_screen_id}')

        cancel_button=ft.TextButton('Cancel', on_click=handle_move_to_staging_cancel)
        move_button=ft.FilledButton('Move', disabled=not candidates, on_click=confirm_move)
        dialog=ft.AlertDialog(
            modal=True,
            title=ft.Text('Move to Staging'),
            content=ft.Column(rows, scroll=ft.ScrollMode.AUTO, height=520, width=1030, spacing=0),
            actions=[cancel_button, move_button],
        )
        open_dialog(dialog)
        log_page_state(page, f'after rendering Move to Staging screen id={move_screen_id}')

    async def run_staging_move(selected, staging_dir: Path, mode: str, move_screen_id: str | None = None):
        ok, message=validate_staging_dir(staging_dir)
        if not ok:
            show_warning('Staging directory unavailable', message)
            return
        logging.info('Move to Staging async task starts id=%s mode=%s destination=%s selected=%s', move_screen_id, mode, staging_dir, len(selected))
        logging.info('Starting Move to Staging id=%s mode=%s destination=%s selected=%s', move_screen_id, mode, staging_dir, len(selected))
        logging.info('Move to Staging task selected source paths id=%s: %s', move_screen_id, [str(candidate.source_path) for candidate in selected])
        logging.info('Move to Staging task selected destination paths id=%s: %s', move_screen_id, [str(destination_for(candidate, staging_dir)) for candidate in selected])
        log_page_state(page, f'before staging progress dialog id={move_screen_id}')
        current_text=ft.Text('', selectable=True)
        counts_text=ft.Text('Completed: 0\nSkipped: 0\nFailed: 0')
        progress_dialog=ft.AlertDialog(modal=True, title=ft.Text('Moving to staging...'), content=ft.Column([ft.ProgressRing(), current_text, counts_text], tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER))
        open_dialog(progress_dialog)
        log_page_state(page, f'after staging progress dialog id={move_screen_id}')
        await asyncio.sleep(0.1)
        results=[]
        counts={'moved':0, 'skipped':0, 'failed':0}
        mover=safe_move_to_staging if mode == 'Safe Move' else move_to_staging
        for index, candidate in enumerate(selected, start=1):
            current_text.value=f'Moving {index} of {len(selected)}: {candidate.display_name}'
            counts_text.value=f'Completed: {counts["moved"]}\nSkipped: {counts["skipped"]}\nFailed: {counts["failed"]}'
            page.update()
            log_page_state(page, f'before staging per-item UI update id={move_screen_id} index={index}')
            result=mover(candidate, staging_dir)
            results.append(result)
            counts[result.status]=counts.get(result.status, 0) + 1
            logging.info('Staging result: %s -> %s status=%s message=%s', result.source_path, result.destination_path, result.status, result.message)
            await asyncio.sleep(0)
        logging.info('Move to Staging async task finishes id=%s mode=%s counts=%s', move_screen_id, mode, counts)
        log_page_state(page, f'before closing staging progress dialog id={move_screen_id}')
        close_dialog(progress_dialog)
        log_page_state(page, f'after closing staging progress dialog id={move_screen_id}')
        summary=f'Move to Staging Complete\n\nMoved: {counts["moved"]}\nSkipped: {counts["skipped"]}\nFailed: {counts["failed"]}\n\nDestination:\n{staging_dir}'
        details='\n'.join(result.message for result in results if result.status != 'moved')
        if details:
            summary=f'{summary}\n\nDetails:\n{details}'
        logging.info('Move to Staging summary id=%s: %s', move_screen_id, summary.replace('\n', ' | '))
        log_page_state(page, f'before showing completion dialog id={move_screen_id}')
        def handle_completion_ok(e):
            logging.info('Move to Staging completion OK clicked id=%s', move_screen_id)
            log_page_state(page, f'before completion OK return to main menu id={move_screen_id}')
            return_to_main_menu_after_staging(summary_dialog, move_screen_id)
            log_page_state(page, f'after completion OK return to main menu id={move_screen_id}')

        ok_button=ft.TextButton('OK', on_click=handle_completion_ok)
        summary_dialog=ft.AlertDialog(modal=True, title=ft.Text('Move to Staging Complete'), content=ft.Text(summary, selectable=True), actions=[ok_button])
        open_dialog(summary_dialog)
        log_page_state(page, f'after showing completion dialog id={move_screen_id}')
        show_status(f'Move to staging complete: moved {counts["moved"]}, skipped {counts["skipped"]}, failed {counts["failed"]}.')

    def render():
        log_page_state(page, 'before rendering main menu')
        refresh_compact_database_button()
        grid.controls.clear()

        def text_cell(value, *, width=None, expand=None, tooltip=None, weight=None):
            text=str(value or '')
            return ft.Container(
                content=ft.Text(text, no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS, tooltip=tooltip or text, weight=weight),
                width=width,
                expand=expand,
                padding=padding_symmetric(horizontal=4),
                alignment=ft.Alignment(-1, 0),
            )

        def toggle_book_expansion(book):
            if book.key in expanded_book_keys:
                expanded_book_keys.remove(book.key)
            else:
                expanded_book_keys.add(book.key)
            render()

        def book_top_row(book, first):
            series=' '.join(part for part in [first.series, first.series_sequence] if part)
            expanded=book.key in expanded_book_keys
            return ft.Row([
                ft.Container(
                    content=ft.IconButton(icon=ft.Icons.EDIT, tooltip='Edit metadata', on_click=lambda e, book=book: show_manual_edit(book)),
                    width=48,
                    alignment=ft.Alignment(0, 0),
                ),
                text_cell(book.display_name, expand=4, weight=ft.FontWeight.BOLD),
                text_cell(first.title, expand=4),
                text_cell(first.author, expand=3),
                text_cell(first.narrator, expand=3),
                text_cell(series, expand=4),
                text_cell(first.asin, width=110),
                text_cell(f'{len(book.files)} track' + ('' if len(book.files) == 1 else 's'), width=92),
                ft.Container(
                    content=ft.IconButton(
                        icon=ft.Icons.EXPAND_LESS if expanded else ft.Icons.EXPAND_MORE,
                        tooltip='Collapse tracks' if expanded else 'Expand tracks',
                        on_click=lambda e, book=book: toggle_book_expansion(book),
                    ) if book.is_folder_book else ft.Container(),
                    width=42,
                    alignment=ft.Alignment(0, 0),
                ),
            ], spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER)

        def book_actions_row(book):
            # Keep the canonical title/author search wiring intact: ft.Button('Search by Title & Author', on_click=create_title_author_search_handler(b))
            target_status=target_settings_status(book)
            target_button=ft.Button('Set Targets', on_click=lambda e, book=book: show_set_targets(book), bgcolor=TARGET_STATUS_COLORS[target_status], color=ft.Colors.WHITE, tooltip=TARGET_STATUS_TOOLTIPS[target_status])
            actions=[
                ft.Button('Restore / Review History', on_click=lambda e, book=book: show_metadata_history(book)),
                target_button,
                ft.Button('Search by Title & Author', on_click=create_title_author_search_handler(book)),
                ft.Button('Search by ASIN', on_click=create_asin_search_handler(book)),
            ]
            if book.is_folder_book:
                actions.append(ft.Button('Mass Update'))
            return ft.Row(actions, spacing=8, wrap=False, alignment=ft.MainAxisAlignment.START)

        def child_file_row(file_meta, index):
            filename=file_meta.path.name if hasattr(file_meta.path, 'name') else str(file_meta.path)
            return ft.Container(
                content=ft.Row([
                    text_cell(filename, expand=3),
                    text_cell(file_meta.track or index + 1, width=72),
                    text_cell(file_meta.title, expand=2),
                    text_cell(file_meta.album, expand=2),
                    text_cell(file_meta.disc, width=64),
                    text_cell('Yes' if file_meta.has_cover else 'No', width=100),
                    text_cell('Yes' if file_meta.dramatic_audio else 'No', width=120),
                ], spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                padding=padding_only(left=56, right=12, top=6, bottom=6),
            )

        for b in books:
            first=b.files[0]
            card_content=ft.Column([
                book_top_row(b, first),
                ft.Container(content=book_actions_row(b), padding=padding_only(left=52, top=8)),
            ], spacing=4)
            if b.is_folder_book and b.key in expanded_book_keys:
                card_content.controls.append(
                    ft.Container(
                        content=ft.Column([child_file_row(f, i) for i, f in enumerate(b.files)], spacing=2),
                        padding=padding_only(top=8),
                    )
                )
            grid.controls.append(
                ft.Container(
                    content=card_content,
                    padding=12,
                    margin=margin_only(bottom=10),
                    border_radius=8,
                    bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                )
            )
        page.update()
        log_page_state(page, 'after rendering main menu')

    def compact_database_handler(_):
        show_status('Compacting database...')
        try:
            result = compact_database(engine, Session)
        except Exception as exc:
            show_status(f'Database compact failed: {exc}')
            return
        before = format_bytes(result.get('before_size_bytes'))
        after = format_bytes(result.get('after_size_bytes'))
        updated_size = get_database_size_display(database_path(engine))
        logging.info('Database compacted successfully. Updated size: %s', updated_size)
        refresh_compact_database_button()
        show_success(f'Compacted database: {before} → {after}. Cleaned {result.get("snapshots", 0)} snapshots and {result.get("changes", 0)} change records.')
        show_status(f'Database compacted: {before} → {after}.')
    def apply_theme(e):
        selected_theme = getattr(getattr(e, 'control', None), 'value', None) or theme.value or 'System'
        settings['theme']=selected_theme; save_settings(settings); page.theme_mode=theme_mode_for_setting(selected_theme); page.update()
    theme=ft.Dropdown(label='Theme', value=settings.get('theme','System'), options=[ft.dropdown.Option(x) for x in THEME_OPTIONS])
    staging_dir_field=ft.TextField(label='Staging Directory', value=settings.get('staging_dir') or '', width=320)
    if hasattr(theme, 'on_select'):
        theme.on_select=apply_theme
    if hasattr(theme, 'on_change'):
        theme.on_change=apply_theme
    async def select_working_directory(e):
        picker=create_file_picker()
        path = await maybe_await(picker.get_directory_path())
        if path:
            scan(path)
    async def select_staging_directory(e):
        picker=create_file_picker()
        path = await maybe_await(picker.get_directory_path())
        if path:
            settings['staging_dir']=path; save_settings(settings); staging_dir_field.value=path; show_status(f'Staging directory set to {path}.'); page.update()
    def save_staging_directory(e):
        path=(staging_dir_field.value or '').strip()
        settings['staging_dir']=path or None; save_settings(settings); show_status('Staging directory saved.' if path else 'Staging directory cleared.'); page.update()
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
    compact_db_button.on_click = compact_database_handler
    refresh_compact_database_button()
    log_page_state(page, 'before app startup main window render')
    page.add(ft.Row([ft.Button('Select Working Directory', on_click=select_working_directory), ft.Button('Rescan', on_click=lambda _: scan()), ft.Button('Move to Staging', on_click=show_move_to_staging), compact_db_button, theme], wrap=True), ft.Row([staging_dir_field, ft.Button('Browse Staging', on_click=select_staging_directory), ft.Button('Save Staging', on_click=save_staging_directory)], wrap=True), status, grid)
    log_page_state(page, 'after app startup main window render')
    if settings.get('working_directory'):
        logging.info('App startup triggering initial scan for working_directory=%s', settings['working_directory'])
        scan(settings['working_directory'])
if __name__ == '__main__': ft.run(main)

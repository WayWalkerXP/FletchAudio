import asyncio
import inspect
import logging
import threading
import uuid
from pathlib import Path, PureWindowsPath

import flet as ft
from mutagen import File

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
BOOK_LIST_SCROLLBAR_GAP = 16
BOOK_COVER_THUMBNAIL_SIZE = 64

RUNTIME_RESULT_ROW_COLORS = {
    'green': ft.Colors.with_opacity(0.18, ft.Colors.GREEN),
    'amber': ft.Colors.with_opacity(0.18, ft.Colors.AMBER),
    'red': ft.Colors.with_opacity(0.18, ft.Colors.RED),
}

def _metadata_path(file_metadata_or_path):
    return getattr(file_metadata_or_path, 'path', file_metadata_or_path)

def get_actual_bitrate(file_metadata_or_path) -> int | None:
    path = _metadata_path(file_metadata_or_path)
    if not path:
        return None
    try:
        audio = File(str(path), easy=False)
    except Exception as exc:
        logging.warning('Skipping actual bitrate read for %s: %s', path, exc, exc_info=True)
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
    except Exception as exc:
        logging.warning('Skipping actual channel read for %s: %s', path, exc, exc_info=True)
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

def sync_folder_book_metadata_from_rows(book, rows, failures=()):
    """Refresh in-memory folder-book track/title fields after Mass Update saves."""
    failed_paths={str(getattr(row, 'path', '')) for row, _error in failures}
    rows_by_path={str(getattr(row, 'path', '')): row for row in rows if str(getattr(row, 'path', '')) not in failed_paths}
    for file_meta in getattr(book, 'files', []) or []:
        row=rows_by_path.get(str(getattr(file_meta, 'path', '')))
        if row is None:
            continue
        track=str(getattr(row, 'track', '') or '').strip()
        file_meta.track=int(track) if track.isdigit() else None
        title=str(getattr(row, 'title', '') or '').strip()
        file_meta.title=title or None

def theme_mode_for_setting(setting):
    return THEME_MODES.get(setting, ft.ThemeMode.SYSTEM)

def attach_dropdown_selection_handler(dropdown, handler):
    """Attach a selection handler across supported Flet Dropdown APIs."""
    if hasattr(dropdown, 'on_select'):
        dropdown.on_select = handler
    if hasattr(dropdown, 'on_change'):
        dropdown.on_change = handler
    return dropdown

def padding_symmetric(*, horizontal=0, vertical=0):
    return ft.Padding(left=horizontal, right=horizontal, top=vertical, bottom=vertical)

def padding_only(*, left=0, right=0, top=0, bottom=0):
    return ft.Padding(left=left, right=right, top=top, bottom=bottom)

def margin_only(*, left=0, right=0, top=0, bottom=0):
    return ft.Margin(left=left, right=right, top=top, bottom=bottom)

from .audible_client import AudibleClient, build_title_author_query, get_runtime_match_category, normalize_asin, parse_search_results, product_from_asin_response, runtime_difference_minutes, sort_results_by_runtime_match, validate_asin
from .duplicate_checker import AbsApiEndpointError, AbsConnectionError, DuplicateCheckStatus, normalize_asin_for_duplicate_check, query_abs_by_asin, query_abs_by_author_album
from .config import load_settings, save_settings
from .db import init_db, get_session_factory
from .audio_scan import scan_directory
from .audio_tags import NON_WRITABLE_FIELDS, format_genres_for_tag, read_audio_metadata, write_audio_metadata
from .history import create_change_group, log_changes, metadata_diff, store_snapshot
from .metadata_map import normalize_response
from .mass_update import apply_track_offset, changed_track_title_rows, discover_folder_book_tracks, format_track_number, guess_track_number_from_filename, guess_title_from_filename, parse_track_offset, render_title_template, save_track_title_rows, track_sort_key, validate_title_template
from .maintenance import clear_metadata_history, compact_database, database_path, format_bytes, get_database_size_display
from .staging import destination_for, discover_staging_candidates, move_to_staging, safe_move_to_staging, validate_staging_dir
from .manual_edit import BOOLEAN_FIELDS, CoverEditState, MANUAL_EDIT_SOURCE_TYPE, MANUAL_EDIT_TAGS, build_baseline_values, build_manual_metadata_diff, changed_edit_fields, debug_dirty_check, filter_manual_updates_for_file, manual_current_value, manual_edit_file_label, normalize_for_dirty_check, set_debug_dirty_selected_file_path, sorted_manual_edit_files
from .history_restore import changes_for_group_file, is_restore_supported, list_change_groups_for_file, restore_selected_metadata
from .conversion_queue import ACTIVE_STATUSES, PENDING_STATUSES, ConversionQueueService, QueueStatus
from .conversion_runner import run_conversion
from .conversion_targets import apply_guessed_targets, apply_manual_targets, build_target_state, clone_book_with_targets, format_queue_target, queue_item_dropdown_options, queue_status_color_key
from .conversion_ui import ConversionUiError, conversion_progress_status, conversion_result_status, prepare_conversion
from .move_library import (
    COLLISION_OVERWRITE,
    COLLISION_OVERWRITE_ALL,
    COLLISION_SKIP,
    COLLISION_SKIP_ALL,
    DUPLICATE_ASIN,
    DUPLICATE_AUTHOR_ALBUM,
    DUPLICATE_NO_MATCH,
    STATUS_ERROR,
    STATUS_OK,
    STATUS_WARN,
    apply_duplicate_result,
    discover_library_move_items,
    dry_run,
    move_items,
    selected_items,
)
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
    conversion_queue=ConversionQueueService()
    queue_refresh_callback={'fn': None}
    conversion_queue.subscribe(lambda item: queue_refresh_callback['fn']() if queue_refresh_callback.get('fn') else None)
    log_page_state(page, 'app startup before main window render')
    page.title='FletchAudio'; page.theme_mode=theme_mode_for_setting(settings.get('theme'))
    status=ft.Text('Select a working directory to begin.'); search_field=ft.TextField(label='Search books', hint_text='Search name, album, author, narrator, series, ASIN...', expand=True); filter_dropdown=ft.Dropdown(label='Filter', value='All Books', width=220, options=[ft.dropdown.Option(option) for option in ('All Books', 'Folder Books', 'Single File Books', 'Missing Targets', 'Duplicate Books')]); clear_search_button=ft.Button('Clear Search'); book_list_header=ft.Container(margin=margin_only(right=BOOK_LIST_SCROLLBAR_GAP)); grid=ft.Column(scroll=ft.ScrollMode.AUTO, expand=True); expanded_book_keys=set(); duplicate_statuses={}; current_search_text=''; search_debounce_task=None; url_launcher=ft.UrlLauncher(); audible=AudibleClient(); compact_db_button=ft.Button(content='Compact Database', on_click=None)
    active_move_to_staging_screen_id=None
    current_screen='main'
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


    async def close_current_window():
        window = getattr(page, 'window', None)
        close_window = getattr(window, 'close', None) if window else None
        if close_window:
            close_result = close_window()
            if inspect.isawaitable(close_result):
                await close_result
            return
        destroy_window = getattr(window, 'destroy', None) if window else None
        if destroy_window:
            destroy_result = destroy_window()
            if inspect.isawaitable(destroy_result):
                await destroy_result
            return
        window_destroy = getattr(page, 'window_destroy', None)
        if window_destroy:
            destroy_result = window_destroy()
            if inspect.isawaitable(destroy_result):
                await destroy_result

    def exit_app(_=None):
        exit_dialog = None
        active_exit_dialog = None

        async def confirm_exit(_):
            close_dialog(exit_dialog)
            await close_current_window()

        async def cancel_conversion_and_exit(_):
            close_dialog(active_exit_dialog)
            conversion_queue.cancel_current()
            await asyncio.sleep(0.1)
            await close_current_window()

        if conversion_queue.is_running:
            active_exit_dialog = ft.AlertDialog(
                modal=True,
                title=ft.Text('Conversion Queue Running'),
                content=ft.Text(
                    'A conversion is currently running. Exiting will cancel the active conversion, '
                    'terminate the external process where possible, and discard the in-memory queue.'
                ),
                actions=[
                    ft.FilledButton('Cancel Conversion and Exit', on_click=cancel_conversion_and_exit),
                    ft.TextButton('Keep Running', on_click=lambda _: close_dialog(active_exit_dialog)),
                    ft.TextButton('Go Back', on_click=lambda _: close_dialog(active_exit_dialog)),
                ],
            )
            open_dialog(active_exit_dialog)
            return

        exit_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text('Exit FletchAudio?'),
            content=ft.Text('Are you sure you want to exit the program?'),
            actions=[
                ft.FilledButton('Exit', on_click=confirm_exit),
                ft.TextButton('Go Back', on_click=lambda _: close_dialog(exit_dialog)),
            ],
        )
        open_dialog(exit_dialog)

    def build_main_menu_controls():
        toolbar = ft.Row(
            [
                ft.Row(
                    [
                        ft.Button('Settings', on_click=lambda _: show_settings()),
                        ft.Button('Rescan', on_click=lambda _: scan()),
                        ft.Button('Check for Duplicates', on_click=check_for_duplicates),
                        ft.Button('Move to Staging', on_click=show_move_to_staging),
                        ft.Button('Move to ABS Library', on_click=show_move_to_abs_library),
                        ft.Button('Conversion Queue', on_click=lambda _: show_conversion_queue()),
                    ],
                    spacing=10,
                ),
                ft.Button('Exit', on_click=exit_app),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )
        search_controls = ft.Row(
            [
                search_field,
                filter_dropdown,
                clear_search_button,
            ],
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        return [
            toolbar,
            search_controls,
            status,
            book_list_header,
            grid,
        ]

    def replace_page_controls(*controls):
        page.controls.clear()
        page.add(*controls)

    def show_success(message: str):
        snack_bar = ft.SnackBar(ft.Text(message))
        open_control = getattr(page, 'open', None)
        if open_control:
            open_control(snack_bar)
            return
        page.snack_bar = snack_bar
        snack_bar.open = True
        page.update()

    def show_conversion_error(message: str):
        def open_directory_settings(e):
            close_dialog(dialog)
            show_settings('Directories')

        dialog=ft.AlertDialog(
            modal=True,
            title=ft.Text('Conversion unavailable'),
            content=ft.Text(message, selectable=True),
            actions=[
                ft.TextButton('Settings > Directories', on_click=open_directory_settings),
                ft.TextButton('OK', on_click=lambda e: close_dialog(dialog)),
            ],
        )
        open_dialog(dialog)

    async def run_prepared_conversion(prepared, plan_dialog):
        close_dialog(plan_dialog)
        progress_text=ft.Text('Starting conversion...')
        progress_detail=ft.Text('', size=12, selectable=True)
        progress_dialog=ft.AlertDialog(
            modal=True,
            title=ft.Text('Converting audiobook'),
            content=ft.Column(
                [ft.ProgressRing(), progress_text, progress_detail],
                tight=True,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )
        open_dialog(progress_dialog)
        await asyncio.sleep(0.05)
        loop=asyncio.get_running_loop()

        def apply_progress(event):
            ui_status=conversion_progress_status(event)
            progress_text.value=ui_status.message
            progress_detail.value=str(ui_status.output_path or event.source_path)
            status.value=ui_status.message
            try:
                page.update()
            except Exception:
                logging.debug('Conversion progress UI update failed', exc_info=True)

        def receive_progress(event):
            loop.call_soon_threadsafe(apply_progress, event)

        result=await asyncio.to_thread(
            run_conversion,
            prepared.request,
            prepared.settings,
            receive_progress,
        )
        final_status=conversion_result_status(result)
        close_dialog(progress_dialog)
        status.value=final_status.message
        def close_conversion_result_dialog(e):
            close_dialog(result_dialog)
            if final_status.state == 'success':
                logging.info('Conversion result acknowledged; refreshing main book list after successful conversion')
                scan()
        result_dialog=ft.AlertDialog(
            modal=True,
            title=ft.Text('Conversion complete' if final_status.state == 'success' else 'Conversion failed'),
            content=ft.Text(final_status.message, selectable=True),
            actions=[ft.TextButton('OK', on_click=close_conversion_result_dialog)],
        )
        open_dialog(result_dialog)

    def show_conversion_plan(book):
        try:
            prepared=prepare_conversion(book, settings)
        except ConversionUiError as exc:
            show_conversion_error(str(exc))
            return
        plan=prepared.plan
        warnings='\n'.join(f'• {warning}' for warning in plan.warnings) or 'None'
        errors='\n'.join(f'• {error}' for error in plan.errors) or 'None'
        preview=ft.Column(
            [
                ft.Text(f'Output path: {plan.output_path or "Unavailable"}', selectable=True),
                ft.Text(f'Archive path: {plan.archive_path or "Unavailable"}', selectable=True),
                ft.Text(f'Target bitrate: {plan.target_bitrate or "Missing"} kbps'),
                ft.Text(f'Target channels: {plan.target_channels or "Missing"}'),
                ft.Text(f'Codec: {plan.selected_codec or "Missing"}'),
                ft.Text(f'Warnings:\n{warnings}', selectable=True),
                ft.Text(f'Errors:\n{errors}', selectable=True, color=ft.Colors.RED if plan.errors else None),
            ],
            tight=True,
            spacing=8,
            scroll=ft.ScrollMode.AUTO,
            height=360,
            width=680,
        )
        plan_dialog=ft.AlertDialog(
            modal=True,
            title=ft.Text('Conversion plan'),
            content=preview,
            actions=[
                ft.TextButton('Close', on_click=lambda e: close_dialog(plan_dialog)),
                *(
                    [ft.FilledButton('Convert', on_click=lambda e: page.run_task(run_prepared_conversion, prepared, plan_dialog) if hasattr(page, 'run_task') else asyncio.create_task(run_prepared_conversion(prepared, plan_dialog)))]
                    if plan.status == 'planned'
                    else []
                ),
            ],
        )
        open_dialog(plan_dialog)

    dialog_lifecycle_apis = {}

    def open_dialog(dialog, log_label=None):
        if log_label is None:
            title = getattr(getattr(dialog, 'title', None), 'value', None)
            if title == 'Auto-Track save complete':
                log_label = title
        open_control = getattr(page, 'open', None)
        show_dialog = getattr(page, 'show_dialog', None)
        if open_control:
            api = 'page.open'
            if log_label:
                logging.info('Opening %s dialog using API=%s dialog_id=%s', log_label, api, id(dialog))
            dialog_lifecycle_apis[id(dialog)] = api
            open_control(dialog)
            return
        if show_dialog:
            api = 'page.show_dialog'
            if log_label:
                logging.info('Opening %s dialog using API=%s dialog_id=%s', log_label, api, id(dialog))
            dialog_lifecycle_apis[id(dialog)] = api
            show_dialog(dialog)
            return
        api = 'page.dialog'
        if log_label:
            logging.info('Opening %s dialog using API=%s dialog_id=%s', log_label, api, id(dialog))
        dialog_lifecycle_apis[id(dialog)] = api
        page.dialog = dialog
        dialog.open = True
        page.update()

    def close_dialog(dialog=None, log_label=None):
        api = dialog_lifecycle_apis.get(id(dialog)) if dialog else None
        close_control = getattr(page, 'close', None)
        if log_label:
            logging.info(
                'Closing %s dialog using API=%s dialog_id=%s',
                log_label,
                'page.close' if api == 'page.open' and close_control else api or 'unknown',
                id(dialog) if dialog else None,
            )
        if dialog and api == 'page.open' and close_control:
            close_control(dialog)
        elif dialog and api == 'page.show_dialog' and close_control:
            close_control(dialog)
        elif getattr(page, 'pop_dialog', None):
            page.pop_dialog()
        if dialog:
            if api != 'page.open':
                dialog.open = False
                if getattr(page, 'dialog', None) is dialog:
                    page.dialog = None
                overlay = getattr(page, 'overlay', None)
                if overlay and dialog in overlay:
                    overlay.remove(dialog)
            dialog_lifecycle_apis.pop(id(dialog), None)
            if log_label:
                logging.info('After close: dialog open=%s dialog_id=%s', getattr(dialog, 'open', None), id(dialog))
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
            else:
                # In Flet 0.85+, page.close() does not exist. page.update() only
                # patches the page object and does NOT push dialog.open=False to
                # Flutter (dialogs live in the private _dialogs subtree). We must
                # call control.update() explicitly so Flutter receives open=False.
                try:
                    control.update()
                except Exception:
                    pass
        if hasattr(page, 'dialog'):
            page.dialog = None
        if overlay is not None:
            for control in dialogs_to_close:
                if control in overlay:
                    overlay.remove(control)

    def render_main_menu_error_state(message):
        grid.controls.clear()
        grid.controls.append(
            ft.Container(
                content=ft.Column([
                    ft.Text('Main menu could not be fully refreshed.', weight=ft.FontWeight.BOLD),
                    ft.Text(message, selectable=True),
                    ft.Button('Retry Main Menu', on_click=lambda _: safe_refresh_main_menu()),
                ], spacing=8),
                padding=12,
                margin=margin_only(bottom=10),
                border_radius=8,
                bgcolor=ft.Colors.ERROR_CONTAINER,
            )
        )
        status.value='Main menu refresh failed; see log for details.'

    def safe_refresh_main_menu():
        try:
            if settings.get('working_directory'):
                scan()
            else:
                render()
        except Exception as exc:
            logging.exception('Failed to render main menu after staging')
            render_main_menu_error_state(str(exc))
            page.update()

    def return_to_main_menu_after_staging(dialog=None, move_screen_id=None):
        nonlocal active_move_to_staging_screen_id, current_screen
        log_page_state(page, 'before returning to main menu after staging')
        if move_screen_id and active_move_to_staging_screen_id == move_screen_id:
            logging.info('Retiring Move to Staging screen id=%s', move_screen_id)
            active_move_to_staging_screen_id=None
        clear_dialog_state(dialog)
        current_screen='main'
        page.route='/'
        replace_page_controls(*build_main_menu_controls())
        try:
            if settings.get('working_directory'):
                scan()
            else:
                render()
        except Exception as exc:
            logging.exception('Failed to render main menu after staging')
            render_main_menu_error_state(str(exc))
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
        source_minutes=round(source_seconds / 60) if source_seconds is not None else None
        runtime_category=get_runtime_match_category(source_minutes, result.runtime_length_min)
        if runtime_category is None:
            logging.debug('Runtime comparison skipped for Audible result because runtime was unavailable.')
        else:
            logging.debug(
                'Audible result runtime comparison: Source=%s Result=%s Difference=%s Color=%s',
                source_minutes,
                result.runtime_length_min,
                diff,
                runtime_category,
            )
        series=' '.join(p for p in [result.series_title, result.series_sequence] if p)
        row=ft.Row([
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
        return ft.Container(
            content=row,
            bgcolor=RUNTIME_RESULT_ROW_COLORS.get(runtime_category),
            padding=padding_symmetric(horizontal=4, vertical=2),
            tooltip=f'Runtime difference: {diff} minutes' if diff is not None else None,
        )
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

    def show_mass_update(book):
        nonlocal current_screen
        mass_update_screen_id=uuid.uuid4().hex[:8]
        current_screen='mass_update'
        page.route='/mass-update'
        folder_path=Path(book.path).expanduser()
        logging.info('Mass Update screen opened id=%s folder=%s', mass_update_screen_id, folder_path)
        rows=discover_folder_book_tracks(folder_path)
        logging.info('Mass Update id=%s discovered %s audio files', mass_update_screen_id, len(rows))
        for row in rows:
            if not row.readable:
                logging.warning('Mass Update unreadable file id=%s file=%s error=%s', mass_update_screen_id, row.path, row.error)
        sort_field=ft.Dropdown(label='Sort by', value='filename', width=180, options=[ft.dropdown.Option('filename', 'Filename'), ft.dropdown.Option('track', 'Track'), ft.dropdown.Option('title', 'Title')])
        sort_direction=ft.Dropdown(label='Direction', value='ascending', width=170, options=[ft.dropdown.Option('ascending', 'Ascending'), ft.dropdown.Option('descending', 'Descending')])
        sort_apply_button=ft.FilledButton('Apply')
        table=ft.Column(scroll=ft.ScrollMode.AUTO, expand=True, spacing=0)
        action_footer_height=72
        metadata_dirty={'value': False}
        selection_dirty={'value': False}
        title_text=ft.Text('Mass Update', size=24, weight=ft.FontWeight.BOLD)
        unsaved_text=ft.Text('', color=ft.Colors.AMBER)
        divider_color=ft.Colors.OUTLINE_VARIANT
        row_border=ft.Border(bottom=ft.BorderSide(1, divider_color))
        column_border=ft.Border(left=ft.BorderSide(1, divider_color))
        row_controls={}
        auto_track_open={'value': False}
        auto_track_dialog_state={'dirty': False}

        def is_auto_track_control(control):
            if getattr(control, 'data', None) == 'auto-track-root':
                return True
            children=[]
            for attr in ('controls', 'actions'):
                value=getattr(control, attr, None)
                if value:
                    children.extend(value)
            for attr in ('content', 'title'):
                value=getattr(control, attr, None)
                if value:
                    children.append(value)
            return any(is_auto_track_control(child) for child in children)

        def auto_track_controls_present():
            containers=[]
            containers.extend(getattr(page, 'controls', []) or [])
            containers.extend(getattr(page, 'views', []) or [])
            containers.extend(getattr(page, 'overlay', []) or [])
            active_dialog=getattr(page, 'dialog', None)
            if active_dialog:
                containers.append(active_dialog)
            return any(is_auto_track_control(control) for control in containers)

        def log_auto_track_final_state():
            logging.info('Auto-Track final state id=%s auto_track_open=%s dirty=%s', mass_update_screen_id, auto_track_open['value'], auto_track_dialog_state['dirty'])
            logging.info('Auto-Track controls present after render=%s id=%s', auto_track_controls_present(), mass_update_screen_id)

        def cell(content, width, border=None, padding=8):
            if isinstance(content, str):
                content=ft.Text(content, selectable=True, width=width - (padding * 2), no_wrap=False)
            return ft.Container(content=content, width=width, padding=padding, border=border)

        def mark_unsaved(reason, row=None):
            metadata_dirty['value']=True
            unsaved_text.value='Unsaved changes'
            if row:
                logging.info('Mass Update edit change id=%s file=%s reason=%s', mass_update_screen_id, row.path, reason)
            else:
                logging.info('Mass Update edit change id=%s reason=%s', mass_update_screen_id, reason)
            page.update()

        def refresh_metadata_dirty():
            metadata_dirty['value']=any(row.changed for row in rows if row.readable)
            unsaved_text.value='Unsaved changes' if metadata_dirty['value'] else ''
            return metadata_dirty['value']

        def row_value(row, field):
            return getattr(row, field) or ''

        def sync_row_controls():
            for controls in list(row_controls.values()):
                row=controls.get('row')
                if row is None:
                    continue
                checkbox=controls.get('selected')
                track_field=controls.get('track')
                title_field=controls.get('title')
                if checkbox is not None:
                    row.selected=bool(checkbox.value)
                if track_field is not None:
                    row.track=track_field.value or ''
                if title_field is not None:
                    row.title=title_field.value or ''
            refresh_metadata_dirty()

        def sorted_visible_rows():
            reverse=sort_direction.value == 'descending'
            if sort_field.value == 'track':
                key=lambda row: track_sort_key(row.track)
            else:
                key=lambda row: row_value(row, sort_field.value).casefold()
            return sorted(rows, key=key, reverse=reverse)

        def render_mass_update_screen():
            replace_page_controls(mass_update_content)
            render_rows()

        auto_track_result_returned={'value': False}

        def return_to_mass_update_screen_from_auto_track_result(result_dialog=None):
            if auto_track_result_returned['value']:
                return
            auto_track_result_returned['value']=True
            logging.info('Auto-Track save complete OK clicked id=%s dialog_id=%s', mass_update_screen_id, id(result_dialog) if result_dialog is not None else None)
            if result_dialog is not None:
                close_dialog(result_dialog, log_label='Auto-Track save complete')
            refresh_metadata_dirty()
            logging.info('Rendering Mass Update after report OK id=%s', mass_update_screen_id)
            render_mass_update_screen()
            page.update()
            log_auto_track_final_state()

        def render_rows():
            logging.info('Grid rebuild started id=%s', mass_update_screen_id)
            table.controls=[]
            row_controls.clear()
            table.controls.append(ft.Row([
                cell(ft.Text('Select', weight=ft.FontWeight.BOLD), 90),
                cell(ft.Text('Filename', weight=ft.FontWeight.BOLD), 320, column_border),
                cell(ft.Text('Track', weight=ft.FontWeight.BOLD), 130, column_border),
                cell(ft.Text('Title', weight=ft.FontWeight.BOLD), 360, column_border),
                cell(ft.Text('Status', weight=ft.FontWeight.BOLD), 160, column_border),
            ], spacing=0))
            for row in sorted_visible_rows():
                checkbox=ft.Checkbox(value=row.selected)
                track_field=ft.TextField(value=row.track, width=112, dense=True)
                title_field=ft.TextField(value=row.title, width=342, dense=True)
                def on_selected(e, row=row):
                    row.selected=bool(e.control.value)
                    selection_dirty['value']=True
                    logging.info('Mass Update selection change id=%s file=%s selected=%s', mass_update_screen_id, row.path, row.selected)
                def on_track(e, row=row):
                    row.track=e.control.value or ''
                    if refresh_metadata_dirty():
                        mark_unsaved('track', row)
                    else:
                        logging.info('Mass Update edit reverted id=%s file=%s reason=track', mass_update_screen_id, row.path)
                        page.update()
                def on_title(e, row=row):
                    row.title=e.control.value or ''
                    if refresh_metadata_dirty():
                        mark_unsaved('title', row)
                    else:
                        logging.info('Mass Update edit reverted id=%s file=%s reason=title', mass_update_screen_id, row.path)
                        page.update()
                checkbox.on_change=on_selected
                track_field.on_change=on_track
                title_field.on_change=on_title
                row_controls[id(row)]={'row': row, 'selected': checkbox, 'track': track_field, 'title': title_field}
                status_label='OK' if row.readable else f'Unreadable: {row.error}'
                table.controls.append(ft.Container(content=ft.Row([
                    cell(checkbox, 90),
                    cell(row.filename, 320, column_border),
                    cell(track_field, 130, column_border),
                    cell(title_field, 360, column_border),
                    cell(status_label, 160, column_border),
                ], spacing=0, vertical_alignment=ft.CrossAxisAlignment.START), border=row_border))
            logging.info('Grid rebuild completed id=%s row_count=%s', mass_update_screen_id, len(rows))
            page.update()

        def apply_sort_clicked(e):
            logging.info('Mass Update sort apply clicked id=%s', mass_update_screen_id)
            logging.info('Sort field id=%s value=%s', mass_update_screen_id, sort_field.value)
            logging.info('Sort direction id=%s value=%s', mass_update_screen_id, sort_direction.value)
            logging.info('Row count id=%s value=%s', mass_update_screen_id, len(rows))
            sync_row_controls()
            render_rows()

        sort_apply_button.on_click=apply_sort_clicked

        def future_placeholder(action):
            logging.info('Mass Update future action clicked id=%s action=%s', mass_update_screen_id, action)
            dialog=ft.AlertDialog(modal=True, title=ft.Text(action), content=ft.Text('This action will be implemented in a later FA-0003 phase.'), actions=[ft.TextButton('OK', on_click=lambda e: close_dialog(dialog))])
            open_dialog(dialog)

        def selected_rows_in_visible_order():
            sync_row_controls()
            return [row for row in sorted_visible_rows() if row.selected]

        def guess_tracks_clicked(e):
            selected_rows=selected_rows_in_visible_order()
            logging.info('Guess Tracks clicked id=%s selected_rows=%s', mass_update_screen_id, len(selected_rows))
            guesses=[]
            failed=0
            for row in selected_rows:
                guessed=guess_track_number_from_filename(row.filename)
                if guessed is None:
                    failed += 1
                    logging.info('Guess Tracks parse failed id=%s file=%s', mass_update_screen_id, row.filename)
                    continue
                logging.info('Guess Tracks parse success id=%s file=%s track=%s', mass_update_screen_id, row.filename, guessed)
                guesses.append((row, guessed))
            width=max(2, len(str(max((guess for _, guess in guesses), default=0))))
            logging.info('Guess Tracks padding width id=%s width=%s', mass_update_screen_id, width)
            updated=0
            unchanged=0
            for row, guessed in guesses:
                new_track=format_track_number(guessed, width)
                if row.track == new_track:
                    unchanged += 1
                else:
                    row.track=new_track
                    updated += 1
            logging.info('Guess Tracks rows updated id=%s updated=%s unchanged=%s failed=%s', mass_update_screen_id, updated, unchanged, failed)
            if updated:
                mark_unsaved('guess tracks')
                render_rows()
            dialog=ft.AlertDialog(modal=True, title=ft.Text('Guess Tracks Complete'), content=ft.Text(f'Updated: {updated}\nUnchanged: {unchanged}\nFailed: {failed}', selectable=True), actions=[ft.TextButton('OK', on_click=lambda ev: close_dialog(dialog))])
            open_dialog(dialog)

        def auto_title_clicked(e):
            selected_rows=selected_rows_in_visible_order()
            logging.info('Auto-Title clicked id=%s', mass_update_screen_id)
            logging.info('Auto-Title selected row count id=%s selected_rows=%s', mass_update_screen_id, len(selected_rows))
            guesses=[]
            failed=0
            for row in selected_rows:
                if not row.readable:
                    failed += 1
                    logging.info('Auto-Title parse failed id=%s file=%s', mass_update_screen_id, row.filename)
                    continue
                guessed=guess_title_from_filename(row.filename)
                if guessed is None:
                    failed += 1
                    logging.info('Auto-Title parse failed id=%s file=%s', mass_update_screen_id, row.filename)
                    continue
                logging.info('Auto-Title parse success id=%s file=%s title=%s', mass_update_screen_id, row.filename, guessed)
                guesses.append((row, guessed))
            updated=0
            unchanged=0
            for row, guessed in guesses:
                if row.title == guessed:
                    unchanged += 1
                else:
                    row.title=guessed
                    updated += 1
            logging.info('Auto-Title rows updated id=%s updated=%s unchanged=%s failed=%s', mass_update_screen_id, updated, unchanged, failed)
            logging.info('Auto-Title unchanged count id=%s unchanged=%s', mass_update_screen_id, unchanged)
            logging.info('Auto-Title failed count id=%s failed=%s', mass_update_screen_id, failed)
            if updated:
                mark_unsaved('auto title')
                render_rows()
            dialog=ft.AlertDialog(modal=True, title=ft.Text('Auto-Title Complete'), content=ft.Text(f'Updated: {updated}\nUnchanged: {unchanged}\nFailed: {failed}', selectable=True), actions=[ft.TextButton('OK', on_click=lambda ev: close_dialog(dialog))])
            open_dialog(dialog)

        def set_title_clicked(e):
            selected_rows=selected_rows_in_visible_order()
            logging.info('Set Title clicked id=%s', mass_update_screen_id)
            logging.info('Set Title selected row count id=%s selected_rows=%s', mass_update_screen_id, len(selected_rows))
            preset_field=ft.Dropdown(label='Preset', value='Not Implemented', width=180, options=[ft.dropdown.Option('Not Implemented')])
            offset_field=ft.TextField(label='Track Offset', value='0', width=160, dense=True)
            template_field=ft.TextField(label='Template', value='', width=420, dense=True)
            apply_button=ft.Button('Apply')
            error_text=ft.Text('', color=ft.Colors.RED)
            preview_table=ft.Column(scroll=ft.ScrollMode.AUTO, spacing=0)
            generated_titles={}
            dialog_dirty={'value': False}

            def preview_status(row, template, offset):
                if not row.readable:
                    return '', 'Unreadable'
                if '%track%' in template:
                    adjusted_track=apply_track_offset(row.track, offset)
                    if adjusted_track is None:
                        raw_track=(row.track or '').strip()
                        return '', 'Invalid track' if not raw_track.isdigit() else 'Resulting track less than 1'
                new_title=render_title_template(template, row, offset)
                if new_title is None:
                    return '', 'Generated title is blank'
                return new_title, 'OK'

            def rebuild_preview(_=None):
                preview_table.controls=[ft.Row([
                    ft.Text('Filename', weight=ft.FontWeight.BOLD, width=300),
                    ft.Text('Track', weight=ft.FontWeight.BOLD, width=90),
                    ft.Text('Current Title', weight=ft.FontWeight.BOLD, width=240),
                    ft.Text('New Title', weight=ft.FontWeight.BOLD, width=260),
                ])]
                for row in selected_rows:
                    new_title, status_value=generated_titles.get(id(row), ('', 'Not applied'))
                    if status_value == 'OK':
                        logging.info('Set Title preview success id=%s file=%s title=%s', mass_update_screen_id, row.filename, new_title)
                    elif status_value != 'Not applied':
                        logging.info('Set Title preview failed id=%s file=%s reason=%s', mass_update_screen_id, row.filename, status_value)
                    preview_table.controls.append(ft.Row([
                        ft.Text(row.filename, selectable=True, width=300, no_wrap=False),
                        ft.Text(row.track, selectable=True, width=90),
                        ft.Text(row.title, selectable=True, width=240, no_wrap=False),
                        ft.Text(new_title, selectable=True, width=260, no_wrap=False),
                    ], vertical_alignment=ft.CrossAxisAlignment.START))
                page.update()

            def set_dialog_dirty():
                dialog_dirty['value']=True

            def field_changed(_):
                set_dialog_dirty()

            def generate_preview_titles():
                raw_offset=offset_field.value
                template=template_field.value or ''
                logging.info('Set Title selected preset id=%s preset=%s', mass_update_screen_id, preset_field.value)
                logging.info('Set Title track offset raw value id=%s value=%s', mass_update_screen_id, raw_offset)
                logging.info('Set Title template value id=%s value=%s', mass_update_screen_id, template)
                try:
                    offset=parse_track_offset(raw_offset)
                    logging.info('Set Title track offset parsed value id=%s value=%s', mass_update_screen_id, offset)
                except ValueError:
                    error_text.value='Track Offset must be an integer.'
                    rebuild_preview()
                    return None
                valid, validation_error=validate_title_template(template)
                logging.info('Set Title template validation result id=%s valid=%s reason=%s', mass_update_screen_id, valid, validation_error)
                if not valid:
                    error_text.value=validation_error or 'Template is invalid.'
                    rebuild_preview()
                    return None
                generated_titles.clear()
                updated=unchanged=failed=0
                for row in selected_rows:
                    new_title, status_value=preview_status(row, template, offset)
                    generated_titles[id(row)]=(new_title, status_value)
                    if status_value != 'OK':
                        failed += 1
                    elif row.title == new_title:
                        unchanged += 1
                    else:
                        updated += 1
                error_text.value=''
                logging.info('Set Title updated count id=%s updated=%s', mass_update_screen_id, updated)
                logging.info('Set Title unchanged count id=%s unchanged=%s', mass_update_screen_id, unchanged)
                logging.info('Set Title failed count id=%s failed=%s', mass_update_screen_id, failed)
                rebuild_preview()
                return updated, unchanged, failed

            def apply_set_title(_):
                result=generate_preview_titles()
                if result is None:
                    return
                dialog_dirty['value']=True

            def apply_generated_titles():
                updated=unchanged=failed=0
                for row in selected_rows:
                    new_title, status_value=generated_titles.get(id(row), ('', 'Not applied'))
                    if status_value != 'OK':
                        failed += 1
                    elif row.title == new_title:
                        unchanged += 1
                    else:
                        row.title=new_title
                        updated += 1
                return updated, unchanged, failed

            async def save_exit_set_title(e):
                updated, unchanged, failed=apply_generated_titles()
                logging.info('Set Title save and exit values id=%s updated=%s unchanged=%s failed=%s', mass_update_screen_id, updated, unchanged, failed)
                close_dialog(dialog)
                if updated:
                    mark_unsaved('set title')
                else:
                    refresh_metadata_dirty()
                render_rows()
                await save_clicked(e, False)

            def save_exit_handler(e):
                page.run_task(save_exit_set_title, e) if hasattr(page, 'run_task') else asyncio.create_task(save_exit_set_title(e))

            def cancel_set_title(_):
                if not dialog_dirty['value']:
                    close_dialog(dialog)
                    render_mass_update_screen()
                    return
                confirm_dialog=None
                def stay(_):
                    close_dialog(confirm_dialog)
                def discard(_):
                    close_dialog(confirm_dialog)
                    close_dialog(dialog)
                    render_mass_update_screen()
                confirm_dialog=ft.AlertDialog(modal=True, title=ft.Text('Discard Set Title changes?'), content=ft.Text('You have unsaved Set Title changes.'), actions=[ft.TextButton('Stay', on_click=stay), ft.FilledButton('Discard', on_click=discard)])
                open_dialog(confirm_dialog)

            offset_field.on_change=field_changed
            template_field.on_change=field_changed
            apply_button.on_click=apply_set_title
            controls_row=ft.Row([preset_field, offset_field, template_field, apply_button], spacing=12, vertical_alignment=ft.CrossAxisAlignment.START)
            preview_border=ft.Border(
                left=ft.BorderSide(1, divider_color),
                top=ft.BorderSide(1, divider_color),
                right=ft.BorderSide(1, divider_color),
                bottom=ft.BorderSide(1, divider_color),
            )
            preview_container=ft.Container(content=preview_table, width=930, height=320, padding=8, border=preview_border, border_radius=6)
            content=ft.Container(content=ft.Column([controls_row, error_text, preview_container], tight=True, spacing=12), width=960, padding=ft.Padding(top=4, left=4, right=4, bottom=0))
            dialog=ft.AlertDialog(modal=True, title=ft.Text('Set Title'), content=content, actions=[ft.TextButton('Cancel', on_click=cancel_set_title), ft.FilledButton('Save and Exit', on_click=save_exit_handler)])
            open_dialog(dialog)
            rebuild_preview()

        def auto_track_clicked(e):
            auto_track_open['value']=True
            auto_track_result_returned['value']=False
            selected_rows=selected_rows_in_visible_order()
            logging.info('Auto-Track opened id=%s selected_rows=%s', mass_update_screen_id, len(selected_rows))
            starting_field=ft.TextField(label='Starting Track Number', value='1', width=220, dense=True)
            error_text=ft.Text('', color=ft.Colors.RED)
            dialog_dirty={'value': False}
            track_fields=[]
            def dialog_changed(_):
                dialog_dirty['value']=True
                auto_track_dialog_state['dirty']=True
            for row in selected_rows:
                field=ft.TextField(value=row.track, width=112, dense=True, on_change=dialog_changed)
                track_fields.append((row, field))
            starting_field.on_change=dialog_changed
            list_rows=[ft.Row([ft.Text('Filename', weight=ft.FontWeight.BOLD, width=360), ft.Text('Track', weight=ft.FontWeight.BOLD, width=130)])]
            for row, field in track_fields:
                list_rows.append(ft.Row([ft.Text(row.filename, selectable=True, width=360, no_wrap=False), field], vertical_alignment=ft.CrossAxisAlignment.START))
            def parse_starting():
                raw=(starting_field.value or '').strip() or '1'
                try:
                    starting=int(raw)
                except ValueError:
                    return None
                return starting if starting >= 1 else None
            def apply_dialog_values(_):
                logging.info('Auto-Track Apply clicked id=%s', mass_update_screen_id)
                starting=parse_starting()
                logging.info('Auto-Track starting number id=%s value=%s', mass_update_screen_id, starting_field.value)
                if starting is None:
                    error_text.value='Starting Track Number must be an integer greater than or equal to 1.'
                    page.update()
                    return
                highest=starting + len(track_fields) - 1
                width=max(2, len(str(highest)))
                for index, (_, field) in enumerate(track_fields):
                    field.value=format_track_number(starting + index, width)
                dialog_dirty['value']=True
                auto_track_dialog_state['dirty']=True
                error_text.value=''
                logging.info('Auto-Track rows updated in dialog id=%s rows=%s width=%s', mass_update_screen_id, len(track_fields), width)
                page.update()
            auto_track_dialog_open=auto_track_open
            auto_track_dialog_state['dirty']=False
            def auto_track_dialog_is_open():
                return bool(auto_track_dialog_open['value'] and getattr(dialog, 'open', False))
            def apply_auto_track_to_rows():
                updated=0
                for row, field in track_fields:
                    new_track=field.value or ''
                    if row.track != new_track:
                        row.track=new_track
                        updated += 1
                return updated
            def close_auto_track_lifecycle_dialogs():
                logging.info('Closing Auto-Track dialog id=%s', mass_update_screen_id)
                auto_track_dialog_open['value']=False
                for action in dialog.actions or []:
                    if hasattr(action, 'on_click'):
                        action.on_click=None
                logging.info('Removing Auto-Track overlays id=%s', mass_update_screen_id)
                clear_dialog_state(dialog)
                page.update()
            async def save_exit_dialog_values(e):
                logging.info('Auto-Track Save and Exit clicked id=%s', mass_update_screen_id)
                apply_auto_track_to_rows()
                dialog_dirty['value']=False
                auto_track_dialog_state['dirty']=False
                logging.info('Auto-Track dirty state cleared id=%s', mass_update_screen_id)
                close_auto_track_lifecycle_dialogs()
                await asyncio.sleep(0.1)
                refresh_metadata_dirty()
                logging.info('Changed rows count id=%s value=%s', mass_update_screen_id, len(changed_track_title_rows(rows)))
                progress=open_progress_dialog('Saving Auto-Track changes...')
                await asyncio.sleep(0.1)
                successes, unchanged, failures=save_track_title_rows(rows)
                sync_folder_book_metadata_from_rows(book, rows, failures)
                close_dialog(progress)
                await asyncio.sleep(0.1)
                logging.info('Auto-Track save successful id=%s saved=%s unchanged=%s failures=%s', mass_update_screen_id, successes, unchanged, len(failures))
                logging.info('Saved rows count id=%s value=%s', mass_update_screen_id, successes)
                logging.info('Failed rows count id=%s value=%s', mass_update_screen_id, len(failures))
                refresh_metadata_dirty()
                render_mass_update_screen()
                log_auto_track_final_state()
                logging.info('Returning to Mass Update screen id=%s', mass_update_screen_id)
                logging.info('Auto-Track lifecycle complete id=%s', mass_update_screen_id)
                summary=f'Saved: {successes}\nUnchanged: {unchanged}\nFailed: {len(failures)}'
                if failures:
                    summary += '\nFailed: ' + ', '.join(f'{row.filename}: {error}' for row, error in failures[:5])
                result_dialog=None
                def on_auto_track_save_complete_ok(_):
                    return_to_mass_update_screen_from_auto_track_result(result_dialog)
                result_dialog=ft.AlertDialog(modal=True, title=ft.Text('Auto-Track save complete'), content=ft.Text(summary, selectable=True), actions=[ft.TextButton('OK', on_click=on_auto_track_save_complete_ok)])
                open_dialog(result_dialog)
            def cancel_dialog_values(_):
                dialog_open=auto_track_dialog_is_open()
                logging.info('Auto-Track Cancel clicked id=%s', mass_update_screen_id)
                logging.info('Auto-Track dirty state=%s id=%s', dialog_dirty['value'], mass_update_screen_id)
                logging.info('Auto-Track dialog open=%s id=%s', dialog_open, mass_update_screen_id)
                if not dialog_open:
                    return
                if not dialog_dirty['value']:
                    auto_track_dialog_open['value']=False
                    auto_track_dialog_state['dirty']=False
                    close_dialog(dialog)
                    render_mass_update_screen()
                    log_auto_track_final_state()
                    return
                confirm_dialog=None
                def stay(_):
                    close_dialog(confirm_dialog)
                def discard(_):
                    logging.info('Auto-Track discard confirmed id=%s', mass_update_screen_id)
                    close_dialog(confirm_dialog)
                    auto_track_dialog_open['value']=False
                    auto_track_dialog_state['dirty']=False
                    close_dialog(dialog)
                    render_mass_update_screen()
                    log_auto_track_final_state()
                confirm_dialog=ft.AlertDialog(modal=True, title=ft.Text('Discard Auto-Track changes?'), content=ft.Text('You have unsaved Auto-Track changes.'), actions=[ft.TextButton('Stay', on_click=stay), ft.FilledButton('Discard', on_click=discard)])
                open_dialog(confirm_dialog)
            content=ft.Column([starting_field, error_text, ft.Container(content=ft.Column(list_rows, scroll=ft.ScrollMode.AUTO), width=520, height=360)], tight=True, spacing=10)
            content.data='auto-track-root'
            def save_exit_handler(e):
                page.run_task(save_exit_dialog_values, e) if hasattr(page, 'run_task') else asyncio.create_task(save_exit_dialog_values(e))
            dialog=ft.AlertDialog(modal=True, title=ft.Text('Auto-Track'), content=content, actions=[ft.TextButton('Cancel', on_click=cancel_dialog_values), ft.Button('Apply', on_click=apply_dialog_values), ft.FilledButton('Save and Exit', on_click=save_exit_handler)])
            open_dialog(dialog)

        def return_to_main():
            current_screen='main'
            render()

        def cancel_clicked(e):
            logging.info('Mass Update Cancel clicked id=%s metadata_dirty=%s selection_dirty=%s', mass_update_screen_id, metadata_dirty['value'], selection_dirty['value'])
            if not metadata_dirty['value']:
                return_to_main()
                return
            def discard(_):
                logging.info('Mass Update unsaved discard confirmed id=%s', mass_update_screen_id)
                close_dialog(confirm_dialog)
                return_to_main()
            confirm_dialog=ft.AlertDialog(modal=True, title=ft.Text('Discard unsaved changes?'), content=ft.Text('You have unsaved changes. Return to the main screen without saving?'), actions=[ft.TextButton('Stay', on_click=lambda e: close_dialog(confirm_dialog)), ft.FilledButton('Discard', on_click=discard)])
            open_dialog(confirm_dialog)

        async def save_clicked(e, exit_after=False):
            logging.info('Mass Update %s clicked id=%s', 'Save & Exit' if exit_after else 'Save', mass_update_screen_id)
            sync_row_controls()
            progress=open_progress_dialog('Saving Mass Update changes...')
            await asyncio.sleep(0.1)
            successes, unchanged, failures=save_track_title_rows(rows)
            sync_folder_book_metadata_from_rows(book, rows, failures)
            close_dialog(progress)
            logging.info('Mass Update save counts id=%s successes=%s unchanged=%s failures=%s', mass_update_screen_id, successes, unchanged, len(failures))
            summary=f'Saved: {successes}\nUnchanged: {unchanged}\nFailed: {len(failures)}'
            if failures:
                summary += '\nFailed: ' + ', '.join(f'{row.filename}: {error}' for row, error in failures[:5])
            dialog=ft.AlertDialog(modal=True, title=ft.Text('Mass Update save complete'), content=ft.Text(summary, selectable=True), actions=[ft.TextButton('OK', on_click=lambda ev: close_dialog(dialog))])
            open_dialog(dialog)
            if not failures:
                refresh_metadata_dirty()
                render_rows()
                if exit_after:
                    close_dialog(dialog)
                    return_to_main()
            else:
                page.update()

        def save_button_handler(e):
            page.run_task(save_clicked, e, False) if hasattr(page, 'run_task') else asyncio.create_task(save_clicked(e, False))
        def save_exit_button_handler(e):
            page.run_task(save_clicked, e, True) if hasattr(page, 'run_task') else asyncio.create_task(save_clicked(e, True))

        action_buttons=ft.Row([
            ft.Button('Guess Tracks', on_click=guess_tracks_clicked),
            ft.Button('Auto-Track', on_click=auto_track_clicked),
            ft.Button('Auto-Title', on_click=auto_title_clicked),
            ft.Button('Set Title', on_click=set_title_clicked),
            ft.TextButton('Cancel', on_click=cancel_clicked),
            ft.FilledButton('Save', on_click=save_button_handler),
            ft.FilledButton('Save & Exit', on_click=save_exit_button_handler),
        ], spacing=8, wrap=True)
        mass_update_content=ft.Column([
            title_text,
            ft.Text(f'Folder: {folder_path}', selectable=True),
            ft.Row([sort_field, sort_direction, sort_apply_button, unsaved_text], spacing=12, wrap=True),
            ft.Container(content=table, expand=True, width=1090),
            ft.Container(
                content=action_buttons,
                height=action_footer_height,
                width=1090,
                alignment=ft.Alignment.CENTER_LEFT,
                padding=padding_only(top=12),
                border=ft.Border(top=ft.BorderSide(1, divider_color)),
            ),
        ], expand=True, spacing=8)

        render_mass_update_screen()
        log_page_state(page, f'after rendering Mass Update screen id={mass_update_screen_id}')

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
        nonlocal active_move_to_staging_screen_id, current_screen
        move_screen_id=uuid.uuid4().hex[:8]
        active_move_to_staging_screen_id=move_screen_id
        current_screen='move_to_staging'
        page.route='/move-staging'
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
            selected_candidates=[]
            for candidate in candidates:
                candidate.selected=bool(selected_checks[candidate.source_path].value)
                if candidate.selected:
                    selected_candidates.append(candidate)
            selected=list(selected_candidates)
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
                await run_staging_move(list(selected), staging_dir, mode, move_screen_id)
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
        dialog=None
        page.controls.clear()
        page.add(
            ft.Text('Move to Staging', size=24, weight=ft.FontWeight.BOLD),
            ft.Text(f'Destination: {staging_dir}', selectable=True),
            ft.Column(rows, scroll=ft.ScrollMode.AUTO, height=520, width=1030, spacing=0),
            ft.Row([cancel_button, move_button], spacing=8),
            status,
        )
        page.update()
        log_page_state(page, f'after rendering Move to Staging screen id={move_screen_id}')

    def show_move_to_abs_library(_=None):
        nonlocal current_screen
        current_screen='move_to_abs_library'
        page.route='/move-abs-library'
        abs_root_value=(settings.get('abs_library_dir') or '').strip()
        if not abs_root_value:
            show_warning('ABS library root required', 'ABS Library Directory is not configured. Set it in Settings > Directories before moving books to the ABS library.')
            return
        abs_root=Path(abs_root_value).expanduser()
        if abs_root.exists() and not abs_root.is_dir():
            show_warning('ABS library root unavailable', f'ABS Library Directory is not a folder: {abs_root}')
            return
        items, scan_errors=discover_library_move_items(settings)
        selected_checks={}
        normalize_authors=ft.Checkbox(label='Normalize Authors', value=False)
        clean_album_text=ft.Checkbox(label='Clean Album Text', value=False)
        table_rows=ft.Column(scroll=ft.ScrollMode.AUTO, expand=True, spacing=0)
        divider_color=ft.Colors.OUTLINE_VARIANT
        row_border=ft.Border(bottom=ft.BorderSide(1, divider_color))
        column_border=ft.Border(left=ft.BorderSide(1, divider_color))
        status_colors={
            STATUS_OK: ft.Colors.with_opacity(0.22, ft.Colors.GREEN),
            STATUS_WARN: ft.Colors.with_opacity(0.36, ft.Colors.AMBER_700),
            STATUS_ERROR: ft.Colors.with_opacity(0.36, ft.Colors.RED),
        }

        def cell(content, width, border=None, padding=8):
            if isinstance(content, str):
                content=ft.Text(content, selectable=True, width=width - (padding * 2), no_wrap=False)
            return ft.Container(content=content, width=width, padding=padding, border=border)

        def header_row():
            return ft.Row([
                cell(ft.Text('Select', weight=ft.FontWeight.BOLD), 70),
                cell(ft.Text('Status', weight=ft.FontWeight.BOLD), 160, column_border),
                cell(ft.Text('Duplicate', weight=ft.FontWeight.BOLD), 160, column_border),
                cell(ft.Text('Num Files', weight=ft.FontWeight.BOLD), 90, column_border),
                cell(ft.Text('Author', weight=ft.FontWeight.BOLD), 180, column_border),
                cell(ft.Text('Album', weight=ft.FontWeight.BOLD), 220, column_border),
                cell(ft.Text('Series', weight=ft.FontWeight.BOLD), 170, column_border),
                cell(ft.Text('Sequence #', weight=ft.FontWeight.BOLD), 110, column_border),
            ], spacing=0)

        def refresh_move_rows():
            table_rows.controls.clear()
            selected_checks.clear()
            if not items:
                table_rows.controls.append(ft.Text('No audiobook items found in the configured staging or converted folders.'))
                page.update()
                return
            for item in items:
                checkbox=ft.Checkbox(value=item.selected, disabled=not item.checkable)
                selected_checks[id(item)]=checkbox
                status_text=item.status if not item.status_detail else f'{item.status} {item.status_detail}'
                table_rows.controls.append(ft.Container(
                    content=ft.Row([
                        cell(checkbox, 70),
                        cell(status_text, 160, column_border),
                        cell(item.duplicate or '', 160, column_border),
                        cell(str(item.num_files), 90, column_border),
                        cell(item.author, 180, column_border),
                        cell(item.album, 220, column_border),
                        cell(item.series, 170, column_border),
                        cell(item.series_sequence, 110, column_border),
                    ], spacing=0, vertical_alignment=ft.CrossAxisAlignment.START),
                    border=row_border,
                    bgcolor=status_colors.get(item.status),
                ))
            page.update()

        def sync_selected():
            for item in items:
                checkbox=selected_checks.get(id(item))
                if checkbox is not None:
                    item.selected=bool(checkbox.value) and item.checkable

        def selected_or_warn():
            sync_selected()
            selected=selected_items(items)
            if not selected:
                show_status('No checkable ABS library items selected.')
                return []
            return selected

        def rows_for_review():
            selected=selected_or_warn()
            if not selected:
                return []
            return dry_run(items, abs_root)

        def open_review_dialog(title, rows, actions):
            if not rows:
                return
            review_rows=[
                ft.Row([
                    cell(ft.Text('Album', weight=ft.FontWeight.BOLD), 180),
                    cell(ft.Text('Author', weight=ft.FontWeight.BOLD), 150, column_border),
                    cell(ft.Text('Series', weight=ft.FontWeight.BOLD), 150, column_border),
                    cell(ft.Text('Sequence #', weight=ft.FontWeight.BOLD), 100, column_border),
                    cell(ft.Text('Type', weight=ft.FontWeight.BOLD), 80, column_border),
                    cell(ft.Text('Target', weight=ft.FontWeight.BOLD), 420, column_border),
                    cell(ft.Text('Target Exists', weight=ft.FontWeight.BOLD), 170, column_border),
                ], spacing=0)
            ]
            for row in rows:
                review_rows.append(ft.Container(content=ft.Row([
                    cell(row.item.album, 180),
                    cell(row.item.author, 150, column_border),
                    cell(row.item.series, 150, column_border),
                    cell(row.item.series_sequence, 100, column_border),
                    cell(row.target.item_type, 80, column_border),
                    cell(str(row.target.destination_folder if row.target.item_type == 'Folder' else row.target.target_paths[0]), 420, column_border),
                    cell(row.target_exists, 170, column_border),
                ], spacing=0, vertical_alignment=ft.CrossAxisAlignment.START), border=row_border))
            dialog=ft.AlertDialog(
                modal=True,
                title=ft.Text(title),
                content=ft.Column(review_rows, scroll=ft.ScrollMode.AUTO, height=500, width=1250, spacing=0),
                actions=actions,
            )
            return dialog

        async def run_duplicate_check(_=None):
            abs_url=(settings.get('abs_url') or '').strip()
            api_key=(settings.get('abs_api_key') or '').strip()
            if not abs_url or not api_key:
                show_warning('Audiobookshelf not configured', 'Audiobookshelf connection is not configured. Please enter the ABS URL and API key in Settings.')
                return
            sync_selected()
            checkable=[item for item in items if item.checkable]
            if not checkable:
                show_status('No checkable ABS library items to duplicate-check.')
                return
            progress=ft.AlertDialog(modal=True, title=ft.Text('Checking ABS duplicates...'), content=ft.Column([ft.ProgressRing(), ft.Text('Checking selected/checkable items.')], tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER))
            open_dialog(progress)
            await asyncio.sleep(0.1)
            try:
                for item in checkable:
                    duplicate=DUPLICATE_NO_MATCH
                    if item.asin:
                        asin_matches=await asyncio.to_thread(query_abs_by_asin, abs_url, api_key, item.asin)
                        if asin_matches:
                            duplicate=DUPLICATE_ASIN
                    if duplicate == DUPLICATE_NO_MATCH:
                        author_album_matches=await asyncio.to_thread(query_abs_by_author_album, abs_url, api_key, item.author, item.album)
                        if author_album_matches:
                            duplicate=DUPLICATE_AUTHOR_ALBUM
                    apply_duplicate_result(item, duplicate)
                close_dialog(progress)
                refresh_move_rows()
                show_status('ABS duplicate check complete.')
            except AbsApiEndpointError:
                close_dialog(progress)
                show_warning('Duplicate check failed', 'Duplicate check failed because an expected Audiobookshelf API endpoint returned 404.')
            except AbsConnectionError:
                close_dialog(progress)
                show_warning('Unable to connect to Audiobookshelf', 'Unable to connect to Audiobookshelf. Please verify the ABS URL and API key in Settings.')
            except Exception as exc:
                close_dialog(progress)
                show_warning('Duplicate check failed', str(exc))

        def show_dry_run(_=None):
            rows=rows_for_review()
            dialog=open_review_dialog('Move to ABS Library Dry Run', rows, [ft.TextButton('Close', on_click=lambda e: close_dialog(dialog))])
            if dialog:
                open_dialog(dialog)

        async def execute_move(review_dialog, collision_choice):
            close_dialog(review_dialog)
            progress=ft.AlertDialog(modal=True, title=ft.Text('Moving to ABS library...'), content=ft.Column([ft.ProgressRing(), ft.Text('Moving selected items. Please wait...')], tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER))
            open_dialog(progress)
            await asyncio.sleep(0.1)
            sync_selected()
            def decide_collision(item, target):
                return collision_choice
            report=await asyncio.to_thread(move_items, items, abs_root, decide_collision)
            close_dialog(progress)
            summary=(
                'Move to ABS Library Complete\n\n'
                f'Items moved successfully: {len(report.moved)}\n'
                f'Items skipped: {len(report.skipped)}\n'
                f'Items overwritten: {len(report.overwritten)}\n'
                f'Items failed: {len(report.failed)}\n'
                f'Source folders deleted: {len(report.source_folders_deleted)}\n'
                f'Source folders not deleted because not empty: {len(report.source_folders_not_deleted)}'
            )
            details=[]
            for label, values in (
                ('Skipped', report.skipped),
                ('Overwritten', report.overwritten),
                ('Failed', report.failed),
                ('Source folders not deleted', report.source_folders_not_deleted),
                ('Errors', report.errors),
            ):
                if values:
                    details.append(f'{label}:\n' + '\n'.join(values))
            if details:
                summary=f'{summary}\n\n' + '\n\n'.join(details)
            def close_report(e):
                close_dialog(report_dialog)
                render()
            report_dialog=ft.AlertDialog(modal=True, title=ft.Text('Move to ABS Library Complete'), content=ft.Text(summary, selectable=True), actions=[ft.TextButton('OK', on_click=close_report)])
            open_dialog(report_dialog)
            show_status(f'Move to ABS library complete: moved {len(report.moved)}, skipped {len(report.skipped)}, failed {len(report.failed)}.')

        def show_start_review(_=None):
            rows=rows_for_review()
            if not rows:
                return
            has_collision=any(row.target_exists != 'No' for row in rows)
            def confirm_start(e):
                close_dialog(review_dialog)
                actions=[ft.TextButton('Cancel', on_click=lambda e: close_dialog(confirm_dialog))]
                if has_collision:
                    actions.extend([
                        ft.FilledButton('Skip', on_click=lambda e: page.run_task(execute_move, confirm_dialog, COLLISION_SKIP) if hasattr(page, 'run_task') else asyncio.create_task(execute_move(confirm_dialog, COLLISION_SKIP))),
                        ft.FilledButton('Overwrite', on_click=lambda e: page.run_task(execute_move, confirm_dialog, COLLISION_OVERWRITE) if hasattr(page, 'run_task') else asyncio.create_task(execute_move(confirm_dialog, COLLISION_OVERWRITE))),
                        ft.FilledButton('Skip All', on_click=lambda e: page.run_task(execute_move, confirm_dialog, COLLISION_SKIP_ALL) if hasattr(page, 'run_task') else asyncio.create_task(execute_move(confirm_dialog, COLLISION_SKIP_ALL))),
                        ft.FilledButton('Overwrite All', on_click=lambda e: page.run_task(execute_move, confirm_dialog, COLLISION_OVERWRITE_ALL) if hasattr(page, 'run_task') else asyncio.create_task(execute_move(confirm_dialog, COLLISION_OVERWRITE_ALL))),
                    ])
                    message='One or more targets already exist. Choose how collisions should be handled for this move operation.'
                else:
                    actions.append(ft.FilledButton('Start', on_click=lambda e: page.run_task(execute_move, confirm_dialog, COLLISION_SKIP) if hasattr(page, 'run_task') else asyncio.create_task(execute_move(confirm_dialog, COLLISION_SKIP))))
                    message='Move the selected items to the configured ABS library root?'
                confirm_dialog=ft.AlertDialog(modal=True, title=ft.Text('Confirm Move to ABS Library'), content=ft.Text(message), actions=actions)
                open_dialog(confirm_dialog)
            review_dialog=open_review_dialog('Move to ABS Library Review', rows, [ft.TextButton('Cancel', on_click=lambda e: close_dialog(review_dialog)), ft.FilledButton('Start', on_click=confirm_start)])
            if review_dialog:
                open_dialog(review_dialog)

        refresh_move_rows()
        page.controls.clear()
        page.add(
            ft.Text('Move to ABS Library', size=24, weight=ft.FontWeight.BOLD),
            ft.Text(f'ABS Library Root: {abs_root}', selectable=True),
            *( [ft.Text('Scan warnings:\n' + '\n'.join(scan_errors), selectable=True, color=ft.Colors.AMBER)] if scan_errors else [] ),
            ft.Row([normalize_authors, clean_album_text, ft.Button('Duplicate Check', on_click=lambda e: page.run_task(run_duplicate_check) if hasattr(page, 'run_task') else asyncio.create_task(run_duplicate_check())), ft.Button('Dry Run', on_click=show_dry_run), ft.FilledButton('Start', on_click=show_start_review), ft.TextButton('Cancel', on_click=lambda e: render())], spacing=12, wrap=True),
            header_row(),
            table_rows,
            status,
        )
        page.update()

    async def run_staging_move(selected, staging_dir: Path, mode: str, move_screen_id: str | None = None):
        ok, message=validate_staging_dir(staging_dir)
        if not ok:
            show_warning('Staging directory unavailable', message)
            return
        selected=list(selected)
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
        logging.info('Selected candidates count: %s', len(selected))
        logging.info('Result count: %s', len(results))
        logging.info('Moved result paths: %s', [str(result.source_path) for result in results if result.status == 'moved'])
        logging.info('Skipped result paths: %s', [str(result.source_path) for result in results if result.status == 'skipped'])
        logging.info('Failed result paths: %s', [str(result.source_path) for result in results if result.status == 'failed'])
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


    async def check_for_duplicates(_=None):
        abs_url=(settings.get('abs_url') or '').strip()
        api_key=(settings.get('abs_api_key') or '').strip()
        if not abs_url or not api_key:
            show_warning('Audiobookshelf not configured', 'Audiobookshelf connection is not configured. Please enter the ABS URL and API key in Settings.')
            return
        if not books:
            show_status('No source books to check.')
            return
        logging.info('Duplicate check started.')
        logging.info('Using Audiobookshelf URL: %s', abs_url)
        logging.info('Duplicate check source books discovered: %s', len(books))
        with_asin=sum(1 for book in books if normalize_asin_for_duplicate_check(getattr(book.files[0], 'asin', None)))
        without_asin=len(books) - with_asin
        logging.info('Duplicate check books with ASIN: %s', with_asin)
        logging.info('Duplicate check books without ASIN: %s', without_asin)
        duplicate_statuses.clear()
        current_text=ft.Text('', selectable=True)
        counts_text=ft.Text('Checked: 0\nDuplicates Found: 0\nNo Duplicates: 0\nNo ASIN: 0\nErrors: 0')
        cancel_requested=threading.Event()

        def request_cancel(e):
            cancel_requested.set()
            current_text.value='Cancelling after the current request finishes...'
            page.update()

        progress_dialog=ft.AlertDialog(modal=True, title=ft.Text('Checking duplicates...'), content=ft.Column([ft.ProgressRing(), current_text, counts_text], tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER), actions=[ft.TextButton('Cancel', on_click=request_cancel)])
        open_dialog(progress_dialog)
        await asyncio.sleep(0.1)
        counts={'checked':0, 'duplicates':0, 'no_duplicates':0, 'no_asin':0, 'errors':0}
        try:
            for index, book in enumerate(books, start=1):
                if cancel_requested.is_set():
                    break
                source_path=Path(book.path)
                asin=getattr(book.files[0], 'asin', None)
                normalized=normalize_asin_for_duplicate_check(asin)
                current_text.value=f'Checking duplicates {index} of {len(books)}'
                counts_text.value=f'Checked: {counts["checked"]}\nDuplicates Found: {counts["duplicates"]}\nNo Duplicates: {counts["no_duplicates"]}\nNo ASIN: {counts["no_asin"]}\nErrors: {counts["errors"]}'
                page.update()
                if not normalized:
                    counts['no_asin'] += 1
                    duplicate_statuses[book.key]=DuplicateCheckStatus(source_path, None, 'no_asin')
                    logging.info('Duplicate check skipped %s: no ASIN', source_path)
                    render()
                    await asyncio.sleep(0)
                    continue
                counts['checked'] += 1
                logging.info('Checking ASIN %s for %s', normalized, source_path)
                try:
                    matches=await asyncio.to_thread(query_abs_by_asin, abs_url, api_key, asin)
                    if matches:
                        counts['duplicates'] += 1
                        duplicate_statuses[book.key]=DuplicateCheckStatus(source_path, asin, 'duplicate', len(matches))
                        logging.info('ABS duplicate result for ASIN %s: duplicate matches=%s', normalized, len(matches))
                    else:
                        counts['no_duplicates'] += 1
                        duplicate_statuses[book.key]=DuplicateCheckStatus(source_path, asin, 'no_duplicate', 0)
                        logging.info('ABS duplicate result for ASIN %s: no duplicate', normalized)
                except AbsApiEndpointError:
                    raise
                except AbsConnectionError:
                    raise
                except Exception as exc:
                    counts['errors'] += 1
                    duplicate_statuses[book.key]=DuplicateCheckStatus(source_path, asin, 'error', 0, str(exc))
                    logging.error('Duplicate check API error for ASIN %s: %s', normalized, exc)
                render()
                await asyncio.sleep(0)
        except AbsApiEndpointError as exc:
            close_dialog(progress_dialog)
            logging.error('Global Audiobookshelf duplicate check endpoint failure: %s', exc)
            show_warning('Duplicate check failed', 'Duplicate check failed because the Audiobookshelf search endpoint returned 404.\n\nThe ABS URL is reachable, but the API endpoint used by the app appears to be invalid.')
            return
        except AbsConnectionError as exc:
            close_dialog(progress_dialog)
            logging.error('Global Audiobookshelf duplicate check failure: %s', exc)
            show_warning('Unable to connect to Audiobookshelf', 'Unable to connect to Audiobookshelf. Please verify the ABS URL and API key in Settings.')
            return
        close_dialog(progress_dialog)
        cancelled=cancel_requested.is_set()
        remaining_not_checked=sum(1 for book in books if book.key not in duplicate_statuses)
        summary_title='Duplicate Check Cancelled' if cancelled else 'Duplicate Check Complete'
        summary=f'{summary_title}\n\nChecked: {counts["checked"]}\nDuplicates Found: {counts["duplicates"]}\nNo Duplicates: {counts["no_duplicates"]}\nNo ASIN: {counts["no_asin"]}\nErrors: {counts["errors"]}'
        if cancelled:
            summary=f'{summary}\nRemaining Not Checked: {remaining_not_checked}'
        logging.info('Duplicate check final summary: %s', summary.replace('\n', ' | '))
        summary_dialog=ft.AlertDialog(modal=True, title=ft.Text(summary_title), content=ft.Text(summary, selectable=True), actions=[ft.TextButton('OK', on_click=lambda e: close_dialog(summary_dialog))])
        open_dialog(summary_dialog)
        if cancelled:
            show_status(f'Duplicate check cancelled: checked {counts["checked"]}, remaining {remaining_not_checked}.')
        else:
            show_status(f'Duplicate check complete: {counts["duplicates"]} duplicate(s), {counts["no_duplicates"]} no duplicate(s), {counts["errors"]} error(s).')

    def current_book_filter():
        return filter_dropdown.value or 'All Books'

    def normalized_search_text():
        return (current_search_text or '').strip().casefold()

    def book_has_missing_targets(book):
        return target_settings_status(book) == 'red'

    def book_is_marked_duplicate(book):
        duplicate_status = duplicate_statuses.get(book.key)
        return bool(duplicate_status and duplicate_status.status == 'duplicate')

    def book_matches_filter(book):
        selected_filter=current_book_filter()
        if selected_filter == 'Folder Books':
            return book.is_folder_book
        if selected_filter == 'Single File Books':
            return not book.is_folder_book
        if selected_filter == 'Missing Targets':
            return book_has_missing_targets(book)
        if selected_filter == 'Duplicate Books':
            return book_is_marked_duplicate(book)
        return True

    def searchable_book_values(book):
        first=book.files[0] if book.files else None
        series=' '.join(part for part in [getattr(first, 'series', None), getattr(first, 'series_sequence', None)] if part) if first else ''
        return [
            book.display_name,
            getattr(first, 'album', None),
            getattr(first, 'title', None),
            getattr(first, 'author', None),
            getattr(first, 'narrator', None),
            series,
            getattr(first, 'asin', None),
        ]

    def book_matches_search(book, search_text):
        if not search_text:
            return True
        return any(search_text in str(value or '').casefold() for value in searchable_book_values(book))

    def filtered_books():
        search_text=normalized_search_text()
        filter_matches=[book for book in books if book_matches_filter(book)]
        return [book for book in filter_matches if book_matches_search(book, search_text)]

    def search_or_filter_active():
        return current_book_filter() != 'All Books' or bool(normalized_search_text())

    def show_conversion_queue():
        nonlocal current_screen
        current_screen='conversion_queue'
        page.route='/conversion-queue'
        selected_checks={}
        target_states={}
        target_controls={}
        queue_rows=ft.Column(scroll=ft.ScrollMode.AUTO, spacing=0)
        queue_table_width=1290
        queue_rows_container=ft.Container(
            content=queue_rows,
            width=queue_table_width,
            expand=True,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
        )
        book_rows=ft.Column(scroll=ft.ScrollMode.AUTO, spacing=0)
        books_container=ft.Container(content=book_rows, height=220, clip_behavior=ft.ClipBehavior.HARD_EDGE)
        queue_select=ft.Dropdown(label='Queued item', width=420, options=[])
        queue_status_text=ft.Text('Conversion queue is in memory and resets when the app closes.')
        bulk_bitrate=ft.Dropdown(label='Target Bitrate', width=160, options=[ft.dropdown.Option(str(value)) for value in sorted(VALID_TARGET_BITRATES, key=int)])
        bulk_channels=ft.Dropdown(label='Target Channels', width=170, options=[ft.dropdown.Option(str(value)) for value in sorted(VALID_TARGET_CHANNELS, key=int)])
        divider_color=ft.Colors.OUTLINE_VARIANT
        row_border=ft.Border(bottom=ft.BorderSide(1, divider_color))
        column_border=ft.Border(left=ft.BorderSide(1, divider_color))
        target_bitrate_options=[ft.dropdown.Option('', text='Unset')] + [ft.dropdown.Option(str(value)) for value in sorted(VALID_TARGET_BITRATES, key=int)]
        target_channel_options=[ft.dropdown.Option('', text='Unset')] + [ft.dropdown.Option(str(value)) for value in sorted(VALID_TARGET_CHANNELS, key=int)]

        def cell(content, width, border=None, padding=8, bgcolor=None):
            if isinstance(content, str):
                content=ft.Text(content, selectable=True, width=width - (padding * 2), no_wrap=False)
            return ft.Container(content=content, width=width, padding=padding, border=border, bgcolor=bgcolor)

        queue_header_height=48
        queue_row_height=64

        def queue_cell(content, width, border=None, padding=8, bgcolor=None, height=queue_row_height):
            if isinstance(content, str):
                content=ft.Text(
                    content,
                    selectable=True,
                    width=width - (padding * 2),
                    no_wrap=True,
                    overflow=ft.TextOverflow.ELLIPSIS,
                    tooltip=content,
                )
            return ft.Container(
                content=content,
                width=width,
                height=height,
                padding=padding,
                border=border,
                bgcolor=bgcolor,
                alignment=ft.Alignment(-1, 0),
            )

        def queue_status_bgcolor(status_value):
            key=queue_status_color_key(status_value)
            return {
                'light_blue': ft.Colors.with_opacity(0.18, ft.Colors.BLUE),
                'dark_blue': ft.Colors.with_opacity(0.28, ft.Colors.BLUE_900),
                'light_green': ft.Colors.with_opacity(0.18, ft.Colors.GREEN),
                'red': ft.Colors.with_opacity(0.18, ft.Colors.RED),
                'gray': ft.Colors.with_opacity(0.18, ft.Colors.GREY),
            }.get(key)

        def dropdown_int_value(control):
            value=str(control.value or '').strip()
            if not value:
                return None
            try:
                return int(value)
            except ValueError:
                return None

        def set_row_targets(book_key, state):
            target_states[book_key]=state
            controls=target_controls.get(book_key)
            if not controls:
                return
            controls['bitrate'].value=str(state.target_bitrate or '')
            controls['channels'].value=str(state.target_channels or '')
            controls['reason'].value=state.reason

        def queued_book_for_state(book_key):
            state=target_states[book_key]
            return clone_book_with_targets(state.book, state.target_bitrate, state.target_channels)

        def output_filename(output_path):
            raw=str(output_path or '')
            if not raw:
                return ''
            return PureWindowsPath(raw).name if '\\' in raw else Path(raw).name

        def queue_row(item):
            output=output_filename(item.output_path)
            message=item.error_text or item.message
            bgcolor=queue_status_bgcolor(item.status)
            return ft.Container(content=ft.Row([
                queue_cell(item.display_title, 240, bgcolor=bgcolor),
                queue_cell(item.status.value, 120, column_border, bgcolor=bgcolor),
                queue_cell(item.current_stage, 130, column_border, bgcolor=bgcolor),
                queue_cell(format_queue_target(item), 110, column_border, bgcolor=bgcolor),
                queue_cell(output, 300, column_border, bgcolor=bgcolor),
                queue_cell(message, 390, column_border, bgcolor=bgcolor),
            ], spacing=0, vertical_alignment=ft.CrossAxisAlignment.START), border=row_border, height=queue_row_height)

        queue_header=ft.Container(content=ft.Row([
            queue_cell(ft.Text('Book', weight=ft.FontWeight.BOLD), 240, height=queue_header_height),
            queue_cell(ft.Text('Status', weight=ft.FontWeight.BOLD), 120, column_border, height=queue_header_height),
            queue_cell(ft.Text('Stage', weight=ft.FontWeight.BOLD), 130, column_border, height=queue_header_height),
            queue_cell(ft.Text('Target', weight=ft.FontWeight.BOLD), 110, column_border, height=queue_header_height),
            queue_cell(ft.Text('Output', weight=ft.FontWeight.BOLD), 300, column_border, height=queue_header_height),
            queue_cell(ft.Text('Message', weight=ft.FontWeight.BOLD), 390, column_border, height=queue_header_height),
        ], spacing=0), height=queue_header_height, width=queue_table_width)

        def refresh_queue_rows():
            if current_screen != 'conversion_queue':
                return
            items=conversion_queue.snapshot()
            items_by_book_key={item.book_key: item for item in items}
            queue_rows.controls.clear()
            if items:
                queue_rows.controls.extend(queue_row(item) for item in items)
            else:
                queue_rows.controls.append(ft.Container(content=ft.Text('No conversion items are queued.'), height=queue_row_height, alignment=ft.Alignment(-1, 0), padding=8))
            removable=[item for item in items if item.status.value in {'queued', 'ready'}]
            queue_select.options=[ft.dropdown.Option(key=queue_id, text=title) for queue_id, title in queue_item_dropdown_options(removable)]
            if queue_select.value not in {item.queue_id for item in removable}:
                queue_select.value=removable[0].queue_id if removable else None
            for book in candidates:
                controls=target_controls.get(book.key)
                if not controls:
                    continue
                item=items_by_book_key.get(book.key)
                checkbox=controls['checkbox']
                bitrate_control=controls['bitrate']
                channels_control=controls['channels']
                if item is None:
                    if checkbox.disabled:
                        checkbox.value=False
                    checkbox.disabled=False
                    bitrate_control.disabled=False
                    channels_control.disabled=False
                elif item.status in {QueueStatus.FAILED, QueueStatus.CANCELLED}:
                    checkbox.value=False
                    checkbox.disabled=False
                    bitrate_control.disabled=False
                    channels_control.disabled=False
                else:
                    checkbox.value=True
                    checkbox.disabled=True
                    editable=item.status in PENDING_STATUSES
                    bitrate_control.disabled=not editable
                    channels_control.disabled=not editable
            running='running' if conversion_queue.is_running else 'idle'
            queue_status_text.value=f'Queue is {running}. State is in memory and resets when the app closes.'
            try:
                page.update()
            except Exception:
                logging.debug('Conversion queue UI update failed', exc_info=True)

        try:
            loop=asyncio.get_running_loop()
            queue_refresh_callback['fn']=lambda: loop.call_soon_threadsafe(refresh_queue_rows)
        except RuntimeError:
            queue_refresh_callback['fn']=refresh_queue_rows

        candidates=filtered_books()
        for book in candidates:
            target_states[book.key]=build_target_state(book, bitrate_reader=get_actual_bitrate, channel_reader=get_actual_channels)
        book_rows.controls.append(ft.Row([
            cell(ft.Text('Add', weight=ft.FontWeight.BOLD), 70),
            cell(ft.Text('Book', weight=ft.FontWeight.BOLD), 220, column_border),
            cell(ft.Text('Detected', weight=ft.FontWeight.BOLD), 150, column_border),
            cell(ft.Text('Target Bitrate', weight=ft.FontWeight.BOLD), 150, column_border),
            cell(ft.Text('Target Channels', weight=ft.FontWeight.BOLD), 160, column_border),
            cell(ft.Text('Reason', weight=ft.FontWeight.BOLD), 240, column_border),
            cell(ft.Text('Source', weight=ft.FontWeight.BOLD), 360, column_border),
        ], spacing=0))
        if candidates:
            for book in candidates:
                state=target_states[book.key]
                checkbox=ft.Checkbox(value=False)
                selected_checks[book.key]=checkbox
                bitrate_dropdown=ft.Dropdown(value=str(state.target_bitrate or ''), width=132, options=target_bitrate_options)
                channels_dropdown=ft.Dropdown(value=str(state.target_channels or ''), width=142, options=target_channel_options)
                reason_text=ft.Text(state.reason, selectable=True, width=224, no_wrap=False)
                def on_target_change(e, book_key=book.key, bitrate_dropdown=bitrate_dropdown, channels_dropdown=channels_dropdown):
                    current=target_states[book_key]
                    set_row_targets(book_key, apply_manual_targets(current, dropdown_int_value(bitrate_dropdown), dropdown_int_value(channels_dropdown)))
                    existing=conversion_queue.find_by_book_key(book_key)
                    if existing is not None and existing.status in PENDING_STATUSES:
                        conversion_queue.update_book(queued_book_for_state(book_key), settings)
                    page.update()
                bitrate_dropdown.on_change=on_target_change
                channels_dropdown.on_change=on_target_change
                target_controls[book.key]={'checkbox': checkbox, 'bitrate': bitrate_dropdown, 'channels': channels_dropdown, 'reason': reason_text}
                book_rows.controls.append(ft.Container(content=ft.Row([
                    cell(checkbox, 70),
                    cell(book.display_name, 220, column_border),
                    cell(state.detected_label, 150, column_border),
                    cell(bitrate_dropdown, 150, column_border, padding=4),
                    cell(channels_dropdown, 160, column_border, padding=4),
                    cell(reason_text, 240, column_border),
                    cell(str(book.path), 360, column_border),
                ], spacing=0, vertical_alignment=ft.CrossAxisAlignment.START), border=row_border))
        else:
            book_rows.controls.append(ft.Text('No books match the current search/filter.'))

        def selected_books():
            return [book for book in candidates if selected_checks.get(book.key) and selected_checks[book.key].value and not selected_checks[book.key].disabled]

        def duplicate_status_message(item):
            if item.status in ACTIVE_STATUSES:
                return f'{item.display_title} is already being converted.'
            if item.status == QueueStatus.COMPLETE:
                return f'{item.display_title} has completed. Remove or clear it before adding it again.'
            return f'{item.display_title} is already in the queue.'

        def show_duplicate_dialog(book, item, continue_add, summary):
            state=target_states[book.key]
            queued_book=clone_book_with_targets(book, state.target_bitrate, state.target_channels)
            if item.status in PENDING_STATUSES:
                dialog=ft.AlertDialog(
                    modal=True,
                    title=ft.Text('Book already queued'),
                    content=ft.Text('This book is already in the queue. Do you want to update the queued item with the current target settings?'),
                    actions=[
                        ft.TextButton('Update queued item', on_click=lambda e: (conversion_queue.update_book(queued_book, settings), summary.__setitem__('updated', summary['updated'] + 1), close_dialog(dialog), continue_add())),
                        ft.TextButton('Keep existing', on_click=lambda e: (summary.__setitem__('kept', summary['kept'] + 1), close_dialog(dialog), continue_add())),
                        ft.TextButton('Cancel', on_click=lambda e: (summary.__setitem__('skipped', summary['skipped'] + 1), close_dialog(dialog), continue_add())),
                    ],
                )
                open_dialog(dialog)
                return
            if item.status in {QueueStatus.FAILED, QueueStatus.CANCELLED}:
                dialog=ft.AlertDialog(
                    modal=True,
                    title=ft.Text('Replace queued item?'),
                    content=ft.Text('This book already has a failed or cancelled queue item. Replace it with the current target settings?'),
                    actions=[
                        ft.TextButton('Replace', on_click=lambda e: (conversion_queue.replace_book(queued_book, settings), summary.__setitem__('replaced', summary['replaced'] + 1), close_dialog(dialog), continue_add())),
                        ft.TextButton('Keep existing', on_click=lambda e: (summary.__setitem__('kept', summary['kept'] + 1), close_dialog(dialog), continue_add())),
                    ],
                )
                open_dialog(dialog)
                return
            summary['rejected'].append(duplicate_status_message(item))
            continue_add()

        def add_summary_message(summary):
            parts=[]
            for label, key in (
                ('Added', 'added'),
                ('Updated', 'updated'),
                ('Replaced', 'replaced'),
                ('Kept', 'kept'),
                ('Skipped', 'skipped'),
                ('Failed planning', 'failed'),
            ):
                if summary[key]:
                    parts.append(f'{label}: {summary[key]}')
            if summary['rejected']:
                parts.append(f'Rejected: {len(summary["rejected"])}')
            return 'Conversion queue update complete. ' + (', '.join(parts) if parts else 'No changes.')

        def process_add_books(chosen, index=0, summary=None):
            if summary is None:
                summary={'added': 0, 'updated': 0, 'replaced': 0, 'kept': 0, 'skipped': 0, 'failed': 0, 'rejected': []}
            if index >= len(chosen):
                refresh_queue_rows()
                show_status(add_summary_message(summary))
                return
            book=chosen[index]
            existing=conversion_queue.find_by_book_key(book.key)
            continue_add=lambda: process_add_books(chosen, index + 1, summary)
            if existing is not None:
                show_duplicate_dialog(book, existing, continue_add, summary)
                return
            state=target_states[book.key]
            queued_book=clone_book_with_targets(book, state.target_bitrate, state.target_channels)
            item=conversion_queue.add_books([queued_book], settings)[0]
            if item.status.value == 'failed':
                summary['failed'] += 1
            else:
                summary['added'] += 1
            continue_add()

        def add_selected(_=None):
            chosen=selected_books()
            if not chosen:
                show_status('No books selected for conversion queue.')
                return
            process_add_books(chosen)

        def set_all_targets(_=None):
            chosen=selected_books()
            if not chosen:
                show_status('No books selected for target update.')
                return
            bitrate=dropdown_int_value(bulk_bitrate)
            channels=dropdown_int_value(bulk_channels)
            if bitrate is None or channels is None:
                show_status('Choose both target bitrate and target channels before setting all targets.')
                return
            for book in chosen:
                set_row_targets(book.key, apply_manual_targets(target_states[book.key], bitrate, channels))
                existing=conversion_queue.find_by_book_key(book.key)
                if existing is not None and existing.status in PENDING_STATUSES:
                    conversion_queue.update_book(queued_book_for_state(book.key), settings)
            show_status(f'Set targets for {len(chosen)} selected book(s).')
            page.update()

        def guess_selected_targets(_=None):
            chosen=selected_books()
            if not chosen:
                show_status('No books selected for target guessing.')
                return
            for book in chosen:
                set_row_targets(book.key, apply_guessed_targets(target_states[book.key]))
                existing=conversion_queue.find_by_book_key(book.key)
                if existing is not None and existing.status in PENDING_STATUSES:
                    conversion_queue.update_book(queued_book_for_state(book.key), settings)
            show_status(f'Guessed targets for {len(chosen)} selected book(s).')
            page.update()

        async def run_queue_background():
            await asyncio.to_thread(conversion_queue.run_pending)
            completed=sum(1 for item in conversion_queue.snapshot() if item.status.value == 'complete')
            show_status(f'Conversion queue finished. Completed: {completed}.')
            refresh_queue_rows()
            if completed:
                scan()

        def start_queue(_=None):
            if conversion_queue.is_running:
                show_status('Conversion queue is already running.')
                return
            show_status('Conversion queue started in the background.')
            if hasattr(page, 'run_task'):
                page.run_task(run_queue_background)
            else:
                asyncio.create_task(run_queue_background())
            start_dialog=ft.AlertDialog(
                modal=True,
                title=ft.Text('Queue Started'),
                content=ft.Text('The conversion queue is now running in the background.\n\nYou may safely return to the main menu while conversions continue.'),
                actions=[
                    ft.TextButton('Return to Main', on_click=lambda e: (close_dialog(start_dialog), render())),
                    ft.TextButton('Stay Here', on_click=lambda e: close_dialog(start_dialog)),
                ],
            )
            open_dialog(start_dialog)
            refresh_queue_rows()

        def cancel_current(_=None):
            if conversion_queue.cancel_current():
                show_status('Cancellation requested for the active conversion.')
            else:
                show_status('No active conversion is running.')
            refresh_queue_rows()

        def remove_selected(_=None):
            queue_id=queue_select.value
            if queue_id and conversion_queue.remove_queued(queue_id):
                show_status('Removed queued conversion item.')
            else:
                show_status('Select a queued item that has not started.')
            refresh_queue_rows()

        def clear_finished(_=None):
            removed=conversion_queue.clear_terminal()
            show_status(f'Cleared {removed} completed, failed, or cancelled queue item(s).')
            refresh_queue_rows()

        header_row=ft.Row([
                ft.Text('Conversion Queue', size=24, weight=ft.FontWeight.BOLD),
                ft.Button('Back to Main', on_click=lambda e: render()),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
        bulk_controls_row=ft.Row([
                bulk_bitrate,
                bulk_channels,
                ft.Button('Set All Targets', on_click=set_all_targets),
                ft.Button('Guess Targets', on_click=guess_selected_targets),
            ], spacing=8, wrap=True)
        books_section=ft.Column([
            ft.Text('Books'),
            books_container,
        ], spacing=4)
        queue_action_row=ft.Row([
                ft.FilledButton('Add selected book(s) to queue', disabled=not candidates, on_click=add_selected),
                ft.FilledButton('Start queue', on_click=start_queue),
                ft.Button('Cancel current item', on_click=cancel_current),
                queue_select,
                ft.Button('Remove queued item', on_click=remove_selected),
                ft.Button('Clear completed/failed/cancelled items', on_click=clear_finished),
            ], spacing=8, wrap=True)
        queue_title_row=ft.Row([
                ft.Text('Queue', size=20, weight=ft.FontWeight.BOLD),
                ft.Text(f'Output Directory: {settings.get("conversion_output_dir") or "Not configured"}', selectable=True),
            ], spacing=16, vertical_alignment=ft.CrossAxisAlignment.CENTER)
        queue_section=ft.Column(
            controls=[
                queue_title_row,
                queue_header,
                queue_rows_container,
            ],
            expand=True,
            spacing=0,
        )
        conversion_queue_screen=ft.Column(
            controls=[
                header_row,
                queue_status_text,
                bulk_controls_row,
                books_section,
                queue_action_row,
                queue_section,
                status,
            ],
            expand=True,
            spacing=8,
        )
        replace_page_controls(
            conversion_queue_screen,
        )
        refresh_queue_rows()

    def update_result_status(rendered_count):
        total_count=len(books)
        if not search_or_filter_active():
            status.value=f'Found {total_count} book' + ('' if total_count == 1 else 's') + '.'
        elif rendered_count == 0:
            status.value='No books match the current search/filter.'
        else:
            status.value=f'Showing {rendered_count} of {total_count} book' + ('' if total_count == 1 else 's') + '.'

    def update_applied_search_text(value):
        nonlocal current_search_text
        current_search_text=value or ''

    async def apply_debounced_search(expected_text):
        try:
            await asyncio.sleep(1)
        except asyncio.CancelledError:
            return
        update_applied_search_text(expected_text)
        refresh_book_list()

    def handle_search_change(event=None):
        nonlocal search_debounce_task
        pending_text=getattr(getattr(event, 'control', None), 'value', search_field.value) or ''
        if search_debounce_task and not search_debounce_task.done():
            search_debounce_task.cancel()
        search_debounce_task=(page.run_task(apply_debounced_search, pending_text) if hasattr(page, 'run_task') else asyncio.create_task(apply_debounced_search(pending_text)))

    def handle_filter_change(_=None):
        update_applied_search_text(search_field.value)
        refresh_book_list()

    def clear_book_search(_=None):
        nonlocal search_debounce_task
        if search_debounce_task and not search_debounce_task.done():
            search_debounce_task.cancel()
        search_field.value=''
        update_applied_search_text('')
        refresh_book_list()

    search_field.on_change=handle_search_change
    attach_dropdown_selection_handler(filter_dropdown, handle_filter_change)
    clear_search_button.on_click=clear_book_search

    def refresh_book_list():
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

        def book_list_header_cell(label, *, width=None, expand=None):
            return ft.Container(
                content=ft.Text(label, no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS, tooltip=label, weight=ft.FontWeight.BOLD),
                width=width,
                expand=expand,
                padding=padding_symmetric(horizontal=4),
                alignment=ft.Alignment(-1, 0),
            )

        def book_list_header_spacer(*, width):
            return ft.Container(width=width, padding=padding_symmetric(horizontal=4))

        def build_book_list_header():
            return ft.Container(
                content=ft.Row([
                    book_list_header_cell('Edit', width=48),
                    book_list_header_spacer(width=BOOK_COVER_THUMBNAIL_SIZE),
                    book_list_header_cell('Name', expand=4),
                    book_list_header_cell('Album', expand=4),
                    book_list_header_cell('Author', expand=3),
                    book_list_header_cell('Narrator', expand=3),
                    book_list_header_cell('Series', expand=4),
                    book_list_header_cell('ASIN', width=110),
                    book_list_header_cell('Duplicate', width=126),
                    book_list_header_cell('Tracks', width=92),
                    book_list_header_spacer(width=42),
                ], spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                padding=padding_only(left=12, right=12, top=8, bottom=8),
                border_radius=8,
                bgcolor=ft.Colors.SURFACE_CONTAINER,
            )

        book_list_header.content=build_book_list_header()

        def toggle_book_expansion(book):
            if book.key in expanded_book_keys:
                expanded_book_keys.remove(book.key)
            else:
                expanded_book_keys.add(book.key)
            render()

        def book_cover_file(book):
            return next((file_meta for file_meta in book.files if getattr(file_meta, 'cover_data_uri', None)), None)

        def book_cover_thumbnail(book):
            cover_file=book_cover_file(book)
            if cover_file:
                return ft.Container(
                    content=ft.Image(src=cover_file.cover_data_uri, width=BOOK_COVER_THUMBNAIL_SIZE, height=BOOK_COVER_THUMBNAIL_SIZE, fit=IMAGE_CONTAIN_FIT),
                    width=BOOK_COVER_THUMBNAIL_SIZE,
                    height=BOOK_COVER_THUMBNAIL_SIZE,
                    alignment=ft.Alignment(0, 0),
                    clip_behavior=ft.ClipBehavior.HARD_EDGE,
                    border_radius=6,
                )
            return ft.Container(
                content=ft.Icon(ft.Icons.IMAGE_NOT_SUPPORTED_OUTLINED, size=28, color=ft.Colors.ON_SURFACE_VARIANT),
                width=BOOK_COVER_THUMBNAIL_SIZE,
                height=BOOK_COVER_THUMBNAIL_SIZE,
                alignment=ft.Alignment(0, 0),
                bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                border_radius=6,
                tooltip='No cover art',
            )

        def duplicate_status_pill(book):
            duplicate_status=duplicate_statuses.get(book.key)
            if not duplicate_status:
                return ft.Container(width=126)
            pill_specs={
                'duplicate': ('ABS Duplicate', ft.Colors.RED, ft.Colors.WHITE),
                'no_duplicate': ('No Duplicate', ft.Colors.GREEN, ft.Colors.WHITE),
                'no_asin': ('No ASIN', ft.Colors.GREY_600, ft.Colors.WHITE),
                'error': ('Check Failed', ft.Colors.RED_900, ft.Colors.WHITE),
            }
            label, bgcolor, color=pill_specs.get(duplicate_status.status, ('Unknown', ft.Colors.GREY_600, ft.Colors.WHITE))
            return ft.Container(content=ft.Text(label, color=color, size=12, weight=ft.FontWeight.BOLD), bgcolor=bgcolor, border_radius=999, padding=padding_symmetric(horizontal=10, vertical=4), width=126, alignment=ft.Alignment(0, 0), tooltip=duplicate_status.message or None)

        def folder_location_text(book):
            working_directory=settings.get('working_directory')
            folder_path=Path(book.path)
            if working_directory:
                try:
                    relative_path=folder_path.resolve().relative_to(Path(working_directory).expanduser().resolve())
                    if str(relative_path) != '.':
                        return ' / '.join(relative_path.parts)
                except (OSError, ValueError):
                    pass
            return str(folder_path)

        def folder_location_line(book):
            if not book.is_folder_book:
                return None
            folder_text=folder_location_text(book)
            absolute_path=str(Path(book.path))
            return ft.Container(
                content=ft.Text(f'Folder: {folder_text}', size=12, selectable=True, no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS, tooltip=absolute_path),
                padding=padding_only(left=122, bottom=4),
                alignment=ft.Alignment(-1, 0),
            )

        def book_top_row(book, first):
            series=' '.join(part for part in [first.series, first.series_sequence] if part)
            expanded=book.key in expanded_book_keys
            return ft.Row([
                ft.Container(
                    content=ft.IconButton(icon=ft.Icons.EDIT, tooltip='Edit metadata', on_click=lambda e, book=book: show_manual_edit(book)),
                    width=48,
                    alignment=ft.Alignment(0, 0),
                ),
                book_cover_thumbnail(book),
                text_cell(book.display_name, expand=4, weight=ft.FontWeight.BOLD),
                text_cell(first.album, expand=4),
                text_cell(first.author, expand=3),
                text_cell(first.narrator, expand=3),
                text_cell(series, expand=4),
                text_cell(first.asin, width=110),
                duplicate_status_pill(book),
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
                ft.Button('Plan Conversion', on_click=lambda e, book=book: show_conversion_plan(book)),
                ft.Button('Search by Title & Author', on_click=create_title_author_search_handler(book)),
                ft.Button('Search by ASIN', on_click=create_asin_search_handler(book)),
            ]
            if book.is_folder_book:
                actions.append(ft.Button('Mass Update', on_click=lambda e, book=book: show_mass_update(book)))
            return ft.Row(actions, spacing=8, wrap=False, alignment=ft.MainAxisAlignment.START)

        def track_detail_filename(file_meta):
            raw_path=str(getattr(file_meta, 'path', '') or '')
            filename=PureWindowsPath(raw_path).name if '\\' in raw_path else Path(raw_path).name
            return filename or '—'

        def track_detail_value(value):
            return '—' if value is None or str(value).strip() == '' else value

        def track_detail_sort_key(file_meta):
            filename=track_detail_filename(file_meta).casefold()
            disc=getattr(file_meta, 'disc', None)
            track=getattr(file_meta, 'track', None)
            return (disc is None, int(disc) if disc is not None else 0, track is None, int(track) if track is not None else 0, filename)

        def track_detail_header_row():
            return ft.Container(
                content=ft.Row([
                    book_list_header_cell('Filename', expand=4),
                    book_list_header_cell('Track #', width=82),
                    book_list_header_cell('Title', expand=4),
                    book_list_header_cell('Bitrate', width=86),
                    book_list_header_cell('Channels', width=92),
                ], spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                padding=padding_only(left=56, right=12, top=8, bottom=8),
                bgcolor=ft.Colors.SURFACE_CONTAINER,
                border_radius=6,
            )

        def child_file_row(file_meta, index):
            return ft.Container(
                content=ft.Row([
                    text_cell(track_detail_filename(file_meta), expand=4),
                    text_cell(track_detail_value(file_meta.track), width=82),
                    text_cell(track_detail_value(file_meta.title), expand=4),
                    text_cell(track_detail_value(get_actual_bitrate(file_meta)), width=86),
                    text_cell(track_detail_value(get_actual_channels(file_meta)), width=92),
                ], spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                padding=padding_only(left=56, right=12, top=6, bottom=6),
                bgcolor=ft.Colors.with_opacity(0.12, ft.Colors.SURFACE_CONTAINER_HIGHEST) if index % 2 else None,
                border_radius=6,
            )

        rendered_books=filtered_books()
        update_result_status(len(rendered_books))

        for b in rendered_books:
            first=b.files[0]
            card_controls=[]
            folder_line=folder_location_line(b)
            if folder_line:
                card_controls.append(folder_line)
            card_controls.extend([
                book_top_row(b, first),
                ft.Container(content=book_actions_row(b), padding=padding_only(left=122, top=8)),
            ])
            card_content=ft.Column(card_controls, spacing=4)
            if b.is_folder_book and b.key in expanded_book_keys:
                card_content.controls.append(
                    ft.Container(
                        content=ft.Column([track_detail_header_row()] + [child_file_row(f, i) for i, f in enumerate(sorted(b.files, key=track_detail_sort_key))], spacing=2),
                        padding=padding_only(top=8),
                    )
                )
            grid.controls.append(
                ft.Container(
                    content=card_content,
                    padding=12,
                    margin=margin_only(bottom=10, right=BOOK_LIST_SCROLLBAR_GAP),
                    border_radius=8,
                    bgcolor=ft.Colors.with_opacity(0.34, ft.Colors.AMBER_900) if duplicate_statuses.get(b.key) and duplicate_statuses[b.key].status == 'duplicate' else ft.Colors.SURFACE_CONTAINER_HIGHEST,
                )
            )
        page.update()
        log_page_state(page, 'after refreshing main book list')

    def render():
        nonlocal current_screen
        current_screen='main'
        page.route='/'
        replace_page_controls(*build_main_menu_controls())
        log_page_state(page, 'before rendering main menu')
        refresh_book_list()
        log_page_state(page, 'after rendering main menu')

    def show_settings(section='Directories'):
        nonlocal current_screen
        current_screen='settings'
        page.route='/settings'
        active={'section': section}
        sections=('Directories', 'API Settings', 'Appearance', 'Danger Zone')
        fields={}
        danger_days_saved={'value': '3'}
        content=ft.Column(expand=True, scroll=ft.ScrollMode.AUTO, spacing=12)
        nav=ft.Column(width=180, spacing=8)

        def saved(section_name):
            return {
                'Directories': {
                    'working_directory': settings.get('working_directory') or '',
                    'staging_dir': settings.get('staging_dir') or '',
                    'conversion_output_dir': settings.get('conversion_output_dir') or '',
                    'archive_dir': settings.get('archive_dir') or '',
                    'abs_library_dir': settings.get('abs_library_dir') or '',
                },
                'API Settings': {
                    'abs_url': settings.get('abs_url') or '',
                    'abs_api_key': settings.get('abs_api_key') or '',
                },
                'Appearance': {'theme': settings.get('theme', 'System')},
                'Danger Zone': {'days_to_keep': danger_days_saved['value']},
            }[section_name]

        staged={name: saved(name) for name in sections}

        def section_dirty(section_name):
            return staged[section_name] != saved(section_name)

        def set_field(key, value):
            staged[active['section']][key] = value or ''

        def save_section(section_name):
            values=staged[section_name]
            if section_name == 'Directories':
                settings['working_directory']=values['working_directory'].strip() or None
                settings['staging_dir']=values['staging_dir'].strip() or None
                settings['conversion_output_dir']=values['conversion_output_dir'].strip() or None
                settings['archive_dir']=values['archive_dir'].strip() or None
                settings['abs_library_dir']=values['abs_library_dir'].strip() or None
            elif section_name == 'API Settings':
                settings['abs_url']=values['abs_url'].strip() or None
                settings['abs_api_key']=values['abs_api_key'].strip() or None
            elif section_name == 'Appearance':
                settings['theme']=values['theme'] or 'System'
                page.theme_mode=theme_mode_for_setting(settings['theme'])
            elif section_name == 'Danger Zone':
                danger_days_saved['value']=values.get('days_to_keep') or '3'
            if section_name != 'Danger Zone':
                save_settings(settings)
            staged[section_name]=saved(section_name)
            show_status(f'{section_name} settings saved.')

        def refresh_nav():
            nav.controls.clear()
            nav.controls.append(ft.Text('Settings', size=22, weight=ft.FontWeight.BOLD))
            nav.controls.append(ft.Button('Back to Main', on_click=lambda e: request_navigation(None)))
            for name in sections:
                label=f'{name} *' if section_dirty(name) else name
                nav.controls.append(ft.FilledButton(label, on_click=lambda e, name=name: request_navigation(name)) if name == active['section'] else ft.Button(label, on_click=lambda e, name=name: request_navigation(name)))

        def render_section():
            content.controls.clear()
            refresh_nav()
            name=active['section']
            content.controls.append(ft.Text(name, size=24, weight=ft.FontWeight.BOLD))
            if name == 'Directories':
                working=ft.TextField(label='Working Directory', value=staged[name]['working_directory'], width=520, on_change=lambda e: set_field('working_directory', e.control.value))
                staging=ft.TextField(label='Staging Directory', value=staged[name]['staging_dir'], width=520, on_change=lambda e: set_field('staging_dir', e.control.value))
                conversion_output=ft.TextField(label='Conversion Output Directory', value=staged[name]['conversion_output_dir'], width=520, on_change=lambda e: set_field('conversion_output_dir', e.control.value))
                archive=ft.TextField(label='Archive Directory', value=staged[name]['archive_dir'], width=520, on_change=lambda e: set_field('archive_dir', e.control.value))
                abs_library=ft.TextField(label='ABS Library Directory', value=staged[name]['abs_library_dir'], width=520, on_change=lambda e: set_field('abs_library_dir', e.control.value))
                fields['working_directory']=working; fields['staging_dir']=staging; fields['conversion_output_dir']=conversion_output; fields['archive_dir']=archive; fields['abs_library_dir']=abs_library
                async def browse_working(e):
                    picker=create_file_picker()
                    path=await maybe_await(picker.get_directory_path())
                    if path:
                        working.value=path; set_field('working_directory', path); page.update()
                async def browse_staging(e):
                    picker=create_file_picker()
                    path=await maybe_await(picker.get_directory_path())
                    if path:
                        staging.value=path; set_field('staging_dir', path); page.update()
                async def browse_conversion_output(e):
                    picker=create_file_picker()
                    path=await maybe_await(picker.get_directory_path())
                    if path:
                        conversion_output.value=path; set_field('conversion_output_dir', path); page.update()
                async def browse_archive(e):
                    picker=create_file_picker()
                    path=await maybe_await(picker.get_directory_path())
                    if path:
                        archive.value=path; set_field('archive_dir', path); page.update()
                async def browse_abs_library(e):
                    picker=create_file_picker()
                    path=await maybe_await(picker.get_directory_path())
                    if path:
                        abs_library.value=path; set_field('abs_library_dir', path); page.update()
                content.controls.extend([
                    ft.Row([working, ft.Button('Browse', on_click=browse_working)], wrap=True),
                    ft.Row([staging, ft.Button('Browse', on_click=browse_staging)], wrap=True),
                    ft.Row([conversion_output, ft.Button('Browse', on_click=browse_conversion_output)], wrap=True),
                    ft.Row([archive, ft.Button('Browse', on_click=browse_archive)], wrap=True),
                    ft.Row([abs_library, ft.Button('Browse', on_click=browse_abs_library)], wrap=True),
                    ft.Row([ft.FilledButton('Save Directories', on_click=lambda e: (save_section(name), render_section(), page.update())), ft.Button('Cancel/Clear', on_click=lambda e: (staged.__setitem__(name, saved(name)), render_section(), page.update()))]),
                ])
            elif name == 'API Settings':
                content.controls.extend([
                    ft.TextField(label='ABS Base URL', value=staged[name]['abs_url'], width=520, on_change=lambda e: set_field('abs_url', e.control.value)),
                    ft.TextField(label='ABS API Key', value=staged[name]['abs_api_key'], password=True, can_reveal_password=False, width=520, on_change=lambda e: set_field('abs_api_key', e.control.value)),
                    ft.Row([ft.FilledButton('Save API Settings', on_click=lambda e: (save_section(name), render_section(), page.update())), ft.Button('Cancel/Clear', on_click=lambda e: (staged.__setitem__(name, saved(name)), render_section(), page.update()))]),
                ])
            elif name == 'Appearance':
                mode=attach_dropdown_selection_handler(
                    ft.Dropdown(label='Mode', value=staged[name]['theme'], options=[ft.dropdown.Option(x) for x in THEME_OPTIONS]),
                    lambda e: set_field('theme', e.control.value),
                )
                content.controls.extend([mode, ft.Row([ft.FilledButton('Save Appearance', on_click=lambda e: (save_section(name), render_section(), page.update())), ft.Button('Cancel/Clear', on_click=lambda e: (staged.__setitem__(name, saved(name)), render_section(), page.update()))])])
            else:
                days=attach_dropdown_selection_handler(
                    ft.Dropdown(label='Days of Metadata to Keep', value=staged[name]['days_to_keep'], options=[ft.dropdown.Option(x) for x in ('0','3','7','14','30')]),
                    lambda e: set_field('days_to_keep', e.control.value),
                )
                box=ft.Container(
                    content=ft.Column([
                        ft.Text('Clear Historical Metadata / Clear Metadata from Database', weight=ft.FontWeight.BOLD, color=ft.Colors.RED),
                        ft.Text('Deletes metadata snapshots and change history only. Settings and app configuration are preserved.'),
                        days,
                        ft.Row([ft.FilledButton('Proceed', bgcolor=ft.Colors.RED, color=ft.Colors.WHITE, on_click=lambda e: confirm_clear_history()), ft.Button('Cancel/Clear', on_click=lambda e: (staged.__setitem__(name, saved(name)), render_section(), page.update()))]),
                    ]),
                    border=ft.Border(
                        left=ft.BorderSide(1, ft.Colors.RED),
                        top=ft.BorderSide(1, ft.Colors.RED),
                        right=ft.BorderSide(1, ft.Colors.RED),
                        bottom=ft.BorderSide(1, ft.Colors.RED),
                    ),
                    border_radius=8,
                    padding=12,
                )
                content.controls.append(box)
            refresh_nav()

        def navigate_to(destination):
            if destination is None:
                render()
                return
            active['section']=destination
            render_section()
            page.update()

        def request_navigation(destination):
            current=active['section']
            if not section_dirty(current):
                navigate_to(destination)
                return
            def go_back(e):
                close_dialog(dialog)
            def ignore(e):
                staged[current]=saved(current)
                close_dialog(dialog)
                navigate_to(destination)
            def save(e):
                save_section(current)
                close_dialog(dialog)
                navigate_to(destination)
            dialog=ft.AlertDialog(
                modal=True,
                title=ft.Text('Settings changed'),
                content=ft.Text('You have unsaved changes in this settings section.'),
                actions=[ft.TextButton('Go Back', on_click=go_back), ft.TextButton('Ignore Changes', on_click=ignore), ft.FilledButton('Save', on_click=save)],
            )
            open_dialog(dialog)

        def confirm_clear_history():
            def cancel(e):
                close_dialog(dialog)
            async def proceed(e):
                close_dialog(dialog)
                progress=ft.AlertDialog(modal=True, title=ft.Text('Clearing historical metadata...'), content=ft.Column([ft.ProgressRing(), ft.Text('Deleting metadata history. Please wait...')], tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER))
                open_dialog(progress)
                await asyncio.sleep(0.1)
                result=await asyncio.to_thread(clear_metadata_history, engine, Session, staged['Danger Zone']['days_to_keep'])
                close_dialog(progress)
                message=f'Deleted {result.get("snapshots", 0)} snapshot(s), {result.get("changes", 0)} change record(s), and {result.get("change_groups", 0)} empty change group(s).'
                complete=ft.AlertDialog(modal=True, title=ft.Text('Job Complete'), content=ft.Text(message), actions=[ft.TextButton('OK', on_click=lambda e: (close_dialog(complete), render_section(), page.update()))])
                open_dialog(complete)
            dialog=ft.AlertDialog(
                modal=True,
                title=ft.Text('Confirm historical metadata cleanup'),
                content=ft.Text('Historical metadata will be deleted and this cannot be undone. Settings and app configuration will be preserved.'),
                actions=[ft.TextButton('Cancel', on_click=cancel), ft.FilledButton('Proceed', bgcolor=ft.Colors.RED, color=ft.Colors.WHITE, on_click=proceed)],
            )
            open_dialog(dialog)

        render_section()
        replace_page_controls(ft.Row([nav, ft.VerticalDivider(width=1), content], expand=True, spacing=16))
        page.update()

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
    abs_url_field=ft.TextField(label='ABS Base URL', value=settings.get('abs_url') or '', width=320)
    abs_api_key_field=ft.TextField(label='ABS API Key', value=settings.get('abs_api_key') or '', password=True, can_reveal_password=False, width=260)
    attach_dropdown_selection_handler(theme, apply_theme)
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
    def save_abs_settings(e):
        abs_url=(abs_url_field.value or '').strip()
        api_key=(abs_api_key_field.value or '').strip()
        settings['abs_url']=abs_url or None
        settings['abs_api_key']=api_key or None
        save_settings(settings)
        abs_api_key_field.value=api_key
        show_status('Audiobookshelf settings saved.' if abs_url and api_key else 'Audiobookshelf settings incomplete.')
        page.update()
    def build_scan_progress_dialog():
        progress_bar=ft.ProgressBar(value=None, width=360)
        progress_text=ft.Text('Preparing to scan files and extract metadata...')
        detail_text=ft.Text('', size=12, selectable=True)
        dialog=ft.AlertDialog(
            modal=True,
            title=ft.Text('Scanning Working Directory'),
            content=ft.Column(
                [
                    ft.Text('Scanning files and extracting metadata...'),
                    progress_bar,
                    progress_text,
                    detail_text,
                ],
                tight=True,
                spacing=10,
            ),
        )
        return dialog, progress_bar, progress_text, detail_text

    async def scan_async(path=None):
        nonlocal books
        path=path or settings.get('working_directory')
        if not path:
            status.value='No working directory selected.'; page.update(); return
        settings['working_directory']=path; save_settings(settings); status.value=f'Scanning {path}...'; page.update()
        progress_dialog, progress_bar, progress_text, detail_text=build_scan_progress_dialog()
        loop=asyncio.get_running_loop()

        def apply_scan_progress(processed, total, current_path):
            if total:
                progress_bar.value=processed / total
                progress_text.value=f'{processed} of {total} files processed'
            else:
                progress_bar.value=None
                progress_text.value='Discovering audio files...'
            detail_text.value=str(current_path) if current_path else ''
            try:
                page.update()
            except Exception:
                logging.debug('Scan progress update failed', exc_info=True)

        def update_scan_progress(processed, total, current_path):
            loop.call_soon_threadsafe(apply_scan_progress, processed, total, current_path)

        open_dialog(progress_dialog)
        await asyncio.sleep(0.1)
        try:
            scanned_books, errors=await asyncio.to_thread(scan_directory, path, update_scan_progress)
            with Session() as s:
                for b in scanned_books: store_snapshot(s,b,'scan')
            books=scanned_books
            status.value=f'Found {len(books)} books.' + (f' {len(errors)} scan warnings logged.' if errors else '')
            for err in errors: logging.warning('Audio scan warning: %s', err)
            close_dialog(progress_dialog)
            render()
        except Exception as exc:
            close_dialog(progress_dialog)
            logging.exception('Failed to scan and render main menu for %s', path)
            render_main_menu_error_state(str(exc))
            page.update()

    def scan(path=None):
        if hasattr(page, 'run_task'):
            return page.run_task(scan_async, path)
        try:
            loop=asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(scan_async(path))
        return loop.create_task(scan_async(path))
    compact_db_button.on_click = compact_database_handler
    refresh_compact_database_button()
    log_page_state(page, 'before app startup main window render')
    replace_page_controls(*build_main_menu_controls())
    log_page_state(page, 'after app startup main window render')
    if settings.get('working_directory'):
        logging.info('App startup triggering initial scan for working_directory=%s', settings['working_directory'])
        scan(settings['working_directory'])
if __name__ == '__main__': ft.run(main)

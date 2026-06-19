import logging

import flet as ft

from .audible_client import AudibleClient, asin_url, build_title_author_query, parse_search_results, runtime_difference_minutes, search_url, sort_results_by_runtime_match
from .config import load_settings, save_settings
from .db import init_db, get_session_factory
from .audio_scan import scan_directory
from .history import store_snapshot
from .metadata_map import normalize_response
logging.basicConfig(level=logging.INFO)

def main(page: ft.Page):
    engine=init_db(); Session=get_session_factory(engine); settings=load_settings(); books=[]
    page.title='FletchAudio'; page.theme_mode={'Light':ft.ThemeMode.LIGHT,'Dark':ft.ThemeMode.DARK}.get(settings.get('theme'), ft.ThemeMode.SYSTEM)
    status=ft.Text('Select a working directory to begin.'); grid=ft.Column(scroll=ft.ScrollMode.AUTO, expand=True); url_launcher=ft.UrlLauncher(); audible=AudibleClient()
    def show_status(message: str):
        status.value=message; page.update()
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
            ft.ElevatedButton('Select', on_click=on_select),
        ], wrap=True)
    def show_comparison(book, metadata):
        first=book.files[0]
        rows=[]
        for label, current, new_value in [
            ('Title', first.title, metadata.title), ('Subtitle', None, metadata.subtitle), ('Author', first.author, metadata.author),
            ('Narrator', first.narrator, metadata.narrator), ('Series', first.series, metadata.series),
            ('Series #', first.series_sequence, metadata.series_sequence), ('ASIN', first.asin, metadata.asin),
            ('Duration', first.duration, metadata.duration), ('Publisher', first.publisher, metadata.publisher),
            ('Published', first.published_date, metadata.published_date), ('Language', first.language, metadata.language),
        ]:
            rows.append(ft.Row([ft.Text(label, width=100), ft.Text(str(current or ''), width=240), ft.Text(str(new_value or ''), width=240)], wrap=True))
        page.open(ft.AlertDialog(title=ft.Text('Current / New metadata comparison'), content=ft.Column(rows, scroll=ft.ScrollMode.AUTO, height=400), actions=[ft.TextButton('Close', on_click=lambda e: page.close(e.control.parent))]))
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
                page.close(dialog)
                await select_result(selected)
            rows.append(result_row(result, source_seconds, handler))
        dialog=ft.AlertDialog(title=ft.Text('Select Audible search result'), content=ft.Column(rows, scroll=ft.ScrollMode.AUTO, height=500, width=1300), actions=[ft.TextButton('Cancel', on_click=lambda e: page.close(dialog))])
        page.open(dialog)
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
    def render():
        grid.controls.clear()
        for b in books:
            first=b.files[0]
            header_controls = [
                ft.Text(b.display_name, width=220),
                ft.Text(first.title or '', width=150),
                ft.Text(first.author or '', width=120),
                ft.Text(first.narrator or '', width=120),
                ft.Text(first.series or '', width=100),
                ft.Text(first.series_sequence or '', width=70),
                ft.Text(first.asin or '', width=90),
                ft.Text(f'Tracks: {len(b.files)}'),
                ft.ElevatedButton('Restore / Review History'),
                ft.ElevatedButton('Search by Title + Author', on_click=create_title_author_search_handler(b)),
                ft.ElevatedButton('Search by ASIN', on_click=create_asin_search_handler(b)),
            ]
            if b.is_folder_book:
                header_controls.append(ft.ElevatedButton('Mass Update'))
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
        path = await ft.FilePicker().get_directory_path()
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
    page.add(ft.Row([ft.ElevatedButton('Select Working Directory', on_click=select_working_directory), ft.ElevatedButton('Rescan', on_click=lambda _: scan()), theme]), status, grid)
    if settings.get('working_directory'): scan(settings['working_directory'])
if __name__ == '__main__': ft.run(main)

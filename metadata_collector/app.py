import logging

import flet as ft

from .audible_client import asin_url, build_title_author_query, search_url
from .config import load_settings, save_settings
from .db import init_db, get_session_factory
from .audio_scan import scan_directory
from .history import store_snapshot
logging.basicConfig(level=logging.INFO)

def main(page: ft.Page):
    engine=init_db(); Session=get_session_factory(engine); settings=load_settings(); books=[]
    page.title='FletchAudio'; page.theme_mode={'Light':ft.ThemeMode.LIGHT,'Dark':ft.ThemeMode.DARK}.get(settings.get('theme'), ft.ThemeMode.SYSTEM)
    status=ft.Text('Select a working directory to begin.'); grid=ft.Column(scroll=ft.ScrollMode.AUTO, expand=True)
    def show_status(message: str):
        status.value=message; page.update()
    def search_by_title_author(book):
        first=book.files[0]
        query=build_title_author_query(first.author, first.title or first.album or book.display_name)
        if not query:
            show_status(f'Cannot search {book.display_name}: missing title/album and author metadata.')
            return
        page.launch_url(search_url(query))
        show_status(f'Opened Audible title/author search for: {query}')
    def search_by_asin(book):
        first=book.files[0]
        asin=(first.asin or '').strip()
        if not asin:
            show_status(f'Cannot search {book.display_name}: missing ASIN metadata.')
            return
        page.launch_url(asin_url(asin))
        show_status(f'Opened Audible ASIN lookup for: {asin}')
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
                ft.ElevatedButton('Search by Title + Author', on_click=lambda _, book=b: search_by_title_author(book)),
                ft.ElevatedButton('Search by ASIN', on_click=lambda _, book=b: search_by_asin(book)),
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

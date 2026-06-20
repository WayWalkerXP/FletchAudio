from pathlib import Path

from metadata_collector.maintenance import (
    format_database_size,
    get_database_size_bytes,
    get_database_size_display,
)


def test_compact_database_button_label_is_valid_flet_button_content():
    from flet import Button

    button = Button(content='Compact Database')
    button.content = f'Compact Database ({get_database_size_display(Path("missing.db"))})'

    assert button.content == 'Compact Database (0 KB)'


def test_format_database_size_uses_kb_below_1000_kb():
    assert format_database_size(14 * 1024) == '14 KB'
    assert format_database_size(999 * 1024) == '999 KB'


def test_format_database_size_uses_mb_at_or_above_1000_kb():
    assert format_database_size(1000 * 1024) == '1.0 MB'
    assert format_database_size(1536 * 1024) == '1.5 MB'
    assert format_database_size(12400 * 1024) == '12.1 MB'


def test_get_database_size_bytes_returns_zero_for_missing_database(tmp_path):
    assert get_database_size_bytes(tmp_path / 'missing.db') == 0
    assert get_database_size_display(tmp_path / 'missing.db') == '0 KB'


def test_get_database_size_display_handles_os_errors(monkeypatch, caplog):
    def raise_os_error(self):
        raise OSError('stat failed')

    monkeypatch.setattr(Path, 'exists', lambda self: True)
    monkeypatch.setattr(Path, 'stat', raise_os_error)

    assert get_database_size_display(Path('unreadable.db')) == 'Size unavailable'
    assert 'Unable to determine database size' in caplog.text

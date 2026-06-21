from __future__ import annotations
import logging
from pathlib import Path
from sqlalchemy import text
from .history import cleanup_cover_bloat
from .history import cleanup_metadata_history

logger = logging.getLogger(__name__)


def database_path(engine) -> Path | None:
    database = getattr(engine.url, 'database', None)
    if not database or database in {':memory:', ''}:
        return None
    return Path(database).expanduser()


def database_size_bytes(engine) -> int | None:
    path = database_path(engine)
    if not path or not path.exists():
        return None
    return path.stat().st_size


def get_database_size_bytes(db_path: Path) -> int:
    if not db_path.exists():
        return 0
    return db_path.stat().st_size


def format_database_size(size_bytes: int) -> str:
    size_kb = size_bytes / 1024
    if size_kb < 1000:
        return f'{round(size_kb)} KB'
    return f'{size_kb / 1024:.1f} MB'


def get_database_size_display(db_path: Path | None) -> str:
    if db_path is None:
        logger.info('Database size read: 0 KB')
        return '0 KB'
    try:
        size_display = format_database_size(get_database_size_bytes(db_path))
    except OSError:
        logger.exception('Unable to determine database size')
        return 'Size unavailable'
    logger.info('Database size read: %s', size_display)
    return size_display


def compact_database(engine, Session) -> dict[str, int | None]:
    before = database_size_bytes(engine)
    with Session() as session:
        cleanup = cleanup_cover_bloat(session)
    with engine.connect() as connection:
        connection.execute(text('VACUUM'))
    after = database_size_bytes(engine)
    return {'before_size_bytes': before, 'after_size_bytes': after, **cleanup}


def clear_metadata_history(engine, Session, days_to_keep=3) -> dict[str, int | None]:
    before = database_size_bytes(engine)
    with Session() as session:
        cleanup = cleanup_metadata_history(session, days_to_keep)
    with engine.connect() as connection:
        connection.execute(text('VACUUM'))
    after = database_size_bytes(engine)
    return {'before_size_bytes': before, 'after_size_bytes': after, **cleanup}


def format_bytes(size: int | None) -> str:
    if size is None:
        return 'unknown size'
    value = float(size)
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if value < 1024 or unit == 'TB':
            return f'{value:.1f} {unit}' if unit != 'B' else f'{int(value)} B'
        value /= 1024

from __future__ import annotations
from pathlib import Path
from sqlalchemy import text
from .history import cleanup_cover_bloat


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


def compact_database(engine, Session) -> dict[str, int | None]:
    before = database_size_bytes(engine)
    with Session() as session:
        cleanup = cleanup_cover_bloat(session)
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

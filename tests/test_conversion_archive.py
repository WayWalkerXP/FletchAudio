from pathlib import Path

from metadata_collector.conversion_archive import archive_source_file


def test_archive_source_file_moves_to_archive_directory(tmp_path):
    source = tmp_path / "Book.m4b"
    source.write_bytes(b"source")
    archive_dir = tmp_path / "archive"

    archived = archive_source_file(source, archive_dir)

    assert archived == archive_dir / "Book.m4b"
    assert archived.read_bytes() == b"source"
    assert not source.exists()


def test_archive_source_file_uses_numeric_suffix_for_collisions(tmp_path):
    source = tmp_path / "Book.m4b"
    source.write_bytes(b"source")
    archive_dir = tmp_path / "archive"
    archive_dir.mkdir()
    (archive_dir / "Book.m4b").write_bytes(b"existing")
    (archive_dir / "Book (1).m4b").write_bytes(b"existing 1")

    archived = archive_source_file(source, archive_dir)

    assert archived == archive_dir / "Book (2).m4b"
    assert archived.read_bytes() == b"source"
    assert (archive_dir / "Book.m4b").read_bytes() == b"existing"
    assert (archive_dir / "Book (1).m4b").read_bytes() == b"existing 1"

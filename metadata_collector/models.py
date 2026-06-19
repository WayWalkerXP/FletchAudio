from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any

try:
    from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Text
    from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
    HAVE_SQLALCHEMY = True
except ModuleNotFoundError:
    HAVE_SQLALCHEMY = False

@dataclass
class AbsMetadata:
    title: str | None = None; subtitle: str | None = None; author: str | None = None; narrator: str | None = None
    series: str | None = None; series_sequence: str | None = None; asin: str | None = None; description: str | None = None
    publisher: str | None = None; published_year: str | None = None; published_date: str | None = None; language: str | None = None
    genres: list[str] = field(default_factory=list); cover_url: str | None = None; duration: int | None = None; explicit: bool | None = None
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass
class AudioFileMetadata:
    path: str
    title: str | None = None; album: str | None = None; author: str | None = None; albumartist: str | None = None
    narrator: str | None = None; series: str | None = None; series_sequence: str | None = None; asin: str | None = None
    description: str | None = None; publisher: str | None = None; published_year: str | None = None; published_date: str | None = None
    language: str | None = None; genres: list[str] = field(default_factory=list); track: int | None = None; disc: int | None = None
    duration: int | None = None; has_cover: bool = False; cover_data_uri: str | None = None; dramatic_audio: bool | None = None
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass
class Book:
    key: str; path: str; is_folder_book: bool; files: list[AudioFileMetadata]
    @property
    def display_name(self) -> str:
        import os
        return os.path.basename(self.path.rstrip(os.sep))

if HAVE_SQLALCHEMY:
    class Base(DeclarativeBase): pass
    class BookSnapshot(Base):
        __tablename__ = 'book_snapshot'
        id: Mapped[int] = mapped_column(Integer, primary_key=True)
        book_key: Mapped[str] = mapped_column(Text, index=True)
        path: Mapped[str] = mapped_column(Text)
        is_folder_book: Mapped[bool] = mapped_column(Boolean)
        created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
        source_type: Mapped[str] = mapped_column(Text)
        metadata_json: Mapped[str] = mapped_column(Text)
    class ChangeGroup(Base):
        __tablename__ = 'change_group'
        id: Mapped[int] = mapped_column(Integer, primary_key=True)
        book_key: Mapped[str] = mapped_column(Text, index=True)
        created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
        source_type: Mapped[str] = mapped_column(Text)
        description: Mapped[str | None] = mapped_column(Text, nullable=True)
        changes: Mapped[list['MetadataChange']] = relationship(back_populates='group')
    class MetadataChange(Base):
        __tablename__ = 'metadata_change'
        id: Mapped[int] = mapped_column(Integer, primary_key=True)
        change_group_id: Mapped[int] = mapped_column(ForeignKey('change_group.id'))
        book_key: Mapped[str] = mapped_column(Text, index=True)
        file_path: Mapped[str] = mapped_column(Text)
        tag_name: Mapped[str] = mapped_column(Text)
        old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
        new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
        changed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
        source_type: Mapped[str] = mapped_column(Text)
        status: Mapped[str] = mapped_column(Text, default='success')
        error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
        group: Mapped[ChangeGroup] = relationship(back_populates='changes')
else:
    class Base: pass
    @dataclass
    class BookSnapshot(Base):
        book_key: str; path: str; is_folder_book: bool; source_type: str; metadata_json: str
        id: int | None = None; created_at: datetime = field(default_factory=datetime.utcnow)
    @dataclass
    class ChangeGroup(Base):
        book_key: str; source_type: str; description: str | None = None
        id: int | None = None; created_at: datetime = field(default_factory=datetime.utcnow)
    @dataclass
    class MetadataChange(Base):
        change_group_id: int; book_key: str; file_path: str; tag_name: str; old_value: str | None; new_value: str | None; source_type: str
        id: int | None = None; changed_at: datetime = field(default_factory=datetime.utcnow); status: str = 'success'; error_message: str | None = None

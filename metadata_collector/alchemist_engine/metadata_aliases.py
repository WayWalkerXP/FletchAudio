"""Reusable loading, validation, and resolution of canonical metadata aliases."""
from __future__ import annotations

import configparser
import logging
import os
from pathlib import Path
from typing import Mapping

from .errors import ConfigError

TAG_REFERENCES_SECTION = "tag_references"
DEFAULT_METADATA_ALIASES: dict[str, tuple[str, ...]] = {
    "author": ("artist", "albumartist", "author"),
    "album": ("album", "title"),
    "title": ("title", "album"),
    "series": ("TXXX:SERIES", "----:com.apple.iTunes:series", "series"),
    "series_part": ("TXXX:SERIESPART", "TXXX:SERIES-PART", "TXXX:SERIES_PART", "----:com.apple.iTunes:series-part", "series-part", "series_part"),
    "asin": ("TXXX:ASIN", "----:com.apple.iTunes:ASIN", "asin"),
    "narrator": ("TXXX:NARRATOR", "----:com.apple.iTunes:narrator", "composer", "narrator"),
}
SUPPORTED_CANONICAL_FIELDS = frozenset(DEFAULT_METADATA_ALIASES)

def get_supported_canonical_fields() -> frozenset[str]:
    """Return metadata field names accepted by alias config and required_tags."""
    return SUPPORTED_CANONICAL_FIELDS

def write_default_metadata_alias_config(path: Path) -> None:
    """Create a metadata alias INI with the built-in defaults."""
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    parser[TAG_REFERENCES_SECTION] = {field: ", ".join(candidates) for field, candidates in DEFAULT_METADATA_ALIASES.items()}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8") as alias_file:
            parser.write(alias_file)
    except FileExistsError:
        return
    except OSError as exc:
        raise ConfigError(f"metadata alias config path is not writable: {path}: {exc}") from exc
    logging.info("Created metadata alias configuration: %s", path)

def validate_metadata_aliases(alias_config: configparser.ConfigParser) -> dict[str, tuple[str, ...]]:
    """Validate parsed alias configuration and return normalized candidates."""
    if TAG_REFERENCES_SECTION not in alias_config:
        raise ConfigError("metadata alias config is missing [tag_references]")
    aliases: dict[str, tuple[str, ...]] = {}
    for raw_field, raw_candidates in alias_config.items(TAG_REFERENCES_SECTION):
        field = raw_field.strip().casefold()
        if field not in SUPPORTED_CANONICAL_FIELDS:
            raise ConfigError(f"unsupported canonical metadata field '{field}'")
        candidates = tuple(candidate.strip() for candidate in raw_candidates.split(",") if candidate.strip())
        if not candidates:
            raise ConfigError(f"canonical metadata field '{field}' must have at least one usable alias")
        aliases[field] = candidates
    return aliases

def load_metadata_alias_config(path: Path) -> dict[str, tuple[str, ...]]:
    """Create a missing alias file, then load and validate it."""
    path = path.expanduser().resolve()
    if not path.exists():
        write_default_metadata_alias_config(path)
    if not path.is_file() or not os.access(path, os.R_OK):
        raise ConfigError(f"metadata alias config path is not readable: {path}")
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    try:
        with path.open(encoding="utf-8") as alias_file:
            parser.read_file(alias_file)
    except (OSError, configparser.Error) as exc:
        raise ConfigError(f"could not read metadata alias config {path}: {exc}") from exc
    return validate_metadata_aliases(parser)

def resolve_metadata_aliases(raw_metadata: Mapping[str, object], aliases: Mapping[str, tuple[str, ...] | list[str]], *, log_resolutions: bool = False) -> dict[str, str]:
    """Resolve raw tags to canonical names using first-non-empty alias priority."""
    casefolded = {str(key).strip().casefold(): str(value).strip() for key, value in raw_metadata.items() if value is not None}
    resolved: dict[str, str] = {}
    for field, candidates in aliases.items():
        resolved[field] = ""
        for candidate in candidates:
            value = casefolded.get(candidate.strip().casefold(), "")
            if not value:
                continue
            resolved[field] = value
            if log_resolutions and candidate.strip().casefold() != field.casefold():
                logging.warning("%s resolved from %s", field, candidate)
            break
    return resolved

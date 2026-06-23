"""Small, testable helpers for the proof-of-workflow conversion UI."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .conversion_adapter import (
    ConversionRequest,
    ConversionRequestError,
    ConversionSettings,
    build_conversion_request,
)
from .conversion_planner import ConversionPlanResult, plan_conversion
from .conversion_runner import ConversionProgressEvent, ConversionResult, ConversionStatus
from .models import Book

FOLDER_CONVERSION_UNSUPPORTED = "Folder conversion is not implemented yet"
ARCHIVE_DIRECTORY_REQUIRED = (
    "Archive Directory is not configured. Please configure it in "
    "Settings > Directories before using conversion features."
)


class ConversionUiError(ValueError):
    """User-facing validation failure before conversion execution."""


@dataclass(frozen=True)
class ConversionUiStatus:
    state: str = "idle"
    message: str = ""
    stage: str | None = None
    output_path: Path | None = None


@dataclass(frozen=True)
class PreparedConversion:
    request: ConversionRequest
    settings: ConversionSettings
    plan: ConversionPlanResult


def build_ui_conversion_settings(app_settings: Mapping[str, object]) -> ConversionSettings:
    output_value = str(app_settings.get("conversion_output_dir") or "").strip()
    if not output_value:
        raise ConversionUiError(
            "Conversion output directory is not configured. "
            "Set it in Settings > Directories."
        )
    output_dir = Path(output_value).expanduser()
    if not output_dir.exists():
        raise ConversionUiError(
            f"Conversion output directory does not exist: {output_dir}"
        )
    if not output_dir.is_dir():
        raise ConversionUiError(
            f"Conversion output path is not a directory: {output_dir}"
        )
    archive_value = str(app_settings.get("archive_dir") or "").strip()
    if not archive_value:
        raise ConversionUiError(ARCHIVE_DIRECTORY_REQUIRED)
    archive_dir = Path(archive_value).expanduser()
    if archive_dir.exists() and not archive_dir.is_dir():
        raise ConversionUiError(
            f"Archive Directory path is not a directory: {archive_dir}"
        )
    return ConversionSettings(
        output_dir=output_dir,
        processed_dir=archive_dir,
        archive_original=True,
    )


def prepare_conversion(book: Book, app_settings: Mapping[str, object]) -> PreparedConversion:
    if book.is_folder_book:
        raise ConversionUiError(FOLDER_CONVERSION_UNSUPPORTED)
    settings = build_ui_conversion_settings(app_settings)
    try:
        request = build_conversion_request(book)
    except ConversionRequestError as exc:
        raise ConversionUiError(
            f"Required conversion request data could not be built: {exc}"
        ) from exc
    plan = plan_conversion(request, settings)
    return PreparedConversion(request=request, settings=settings, plan=plan)


def conversion_progress_status(event: ConversionProgressEvent) -> ConversionUiStatus:
    return ConversionUiStatus(
        state="running",
        stage=event.stage,
        message=event.message,
        output_path=event.final_output_path,
    )


def conversion_result_status(result: ConversionResult) -> ConversionUiStatus:
    if result.status == ConversionStatus.SUCCESS:
        output = result.final_output_path
        message = result.message
        if output is not None:
            message = f"{message}: {output}"
        return ConversionUiStatus(
            state="success",
            stage="complete",
            message=message,
            output_path=output,
        )
    details = f": {result.error_details}" if result.error_details else ""
    return ConversionUiStatus(
        state="failure",
        stage="failed",
        message=f"{result.message}{details}",
        output_path=result.final_output_path,
    )

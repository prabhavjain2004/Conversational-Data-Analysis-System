"""
CSV Processing Module
======================
Responsible for everything that happens to a file before it is available
for querying:
  - File type validation (extension + MIME type)
  - Encoding detection and normalisation
  - Data type inference and correction
  - Date column detection and parsing
  - Missing value handling (median for numeric, mode for categorical)
  - Outlier detection using IQR method (flag only, never remove)
  - String normalisation (whitespace trimming)
  - Schema and statistical profiling
  - Cleaning report generation

Reference: PRD Section 6.1 (csv_handler.py), Section 12 (Data Cleaning Pipeline)
"""

from __future__ import annotations

import io
import logging
import re
from typing import Any, Dict, List, Tuple

import chardet
import pandas as pd
from fastapi import UploadFile

from backend.exceptions import CSVCleaningError, CSVValidationError
from backend.models import CleaningReport, ColumnProfile


# ── Constants ──────────────────────────────────────────────────────────

ALLOWED_EXTENSIONS = {".csv"}
ALLOWED_MIME_TYPES = {
    "text/csv",
    "application/csv",
    "text/plain",
    "application/vnd.ms-excel",
    "application/octet-stream",  # Some browsers send this for CSV
}
DATE_PATTERNS = [
    r"\d{4}-\d{2}-\d{2}",          # 2024-01-15
    r"\d{2}/\d{2}/\d{4}",          # 01/15/2024
    r"\d{2}-\d{2}-\d{4}",          # 01-15-2024
    r"\d{4}/\d{2}/\d{2}",          # 2024/01/15
    r"\d{2}\.\d{2}\.\d{4}",        # 15.01.2024
]
SAMPLE_SIZE = 5  # Number of sample values to include in column profiles


# ═══════════════════════════════════════════════════════════════════════
#  Public API
# ═══════════════════════════════════════════════════════════════════════


async def process_csv_file(
    upload_file: UploadFile,
    request_id: str,
    max_file_size_bytes: int,
) -> Tuple[pd.DataFrame, List[ColumnProfile], CleaningReport]:
    """
    Full CSV processing pipeline: validate → read → clean → profile.

    Returns:
        (cleaned_dataframe, column_profiles, cleaning_report)
    """
    filename = upload_file.filename or "unnamed.csv"

    # ── Step 1: Validate file type and size ─────────────────────────
    _validate_file(upload_file, filename, max_file_size_bytes, request_id)

    # ── Step 2: Read raw bytes and detect encoding ──────────────────
    raw_bytes = await upload_file.read()
    _validate_size(raw_bytes, filename, max_file_size_bytes, request_id)

    encoding = _detect_encoding(raw_bytes, filename, request_id)

    # ── Step 3: Parse CSV into DataFrame ────────────────────────────
    df = _parse_csv(raw_bytes, encoding, filename, request_id)

    rows_before = len(df)

    # ── Step 4: Run cleaning pipeline ───────────────────────────────
    df, report_data = _run_cleaning_pipeline(df, filename, request_id)

    # ── Step 5: Generate column profiles ────────────────────────────
    column_profiles = _generate_profiles(df)

    # ── Step 6: Build cleaning report ───────────────────────────────
    cleaning_report = CleaningReport(
        filename=filename,
        rows_before=rows_before,
        rows_after=len(df),
        **report_data,
    )

    return df, column_profiles, cleaning_report


# ═══════════════════════════════════════════════════════════════════════
#  Validation
# ═══════════════════════════════════════════════════════════════════════


def _validate_file(
    upload_file: UploadFile,
    filename: str,
    max_file_size_bytes: int,
    request_id: str,
) -> None:
    """Validate file extension and MIME type."""
    # Extension check
    ext = ""
    if "." in filename:
        ext = "." + filename.rsplit(".", 1)[-1].lower()

    if ext not in ALLOWED_EXTENSIONS:
        raise CSVValidationError(
            message=f"Invalid file type: '{filename}'. Only .csv files are accepted.",
            request_id=request_id,
        )

    # MIME type check
    content_type = upload_file.content_type or ""
    if content_type and content_type not in ALLOWED_MIME_TYPES:
        raise CSVValidationError(
            message=f"Invalid MIME type '{content_type}' for file '{filename}'. "
            f"Expected a CSV content type.",
            request_id=request_id,
        )


def _validate_size(
    raw_bytes: bytes,
    filename: str,
    max_file_size_bytes: int,
    request_id: str,
) -> None:
    """Validate file size against configured maximum."""
    if len(raw_bytes) > max_file_size_bytes:
        size_mb = len(raw_bytes) / (1024 * 1024)
        max_mb = max_file_size_bytes / (1024 * 1024)
        raise CSVValidationError(
            message=f"File '{filename}' is {size_mb:.1f} MB, which exceeds "
            f"the maximum allowed size of {max_mb:.0f} MB.",
            request_id=request_id,
        )


# ═══════════════════════════════════════════════════════════════════════
#  Encoding Detection  (PRD Section 12.1 — fallback strategy)
# ═══════════════════════════════════════════════════════════════════════


def _detect_encoding(
    raw_bytes: bytes, filename: str, request_id: str
) -> str:
    """
    Detect file encoding. Fallback chain: chardet → UTF-8 → latin-1.
    Per PRD Section 17.4: attempt UTF-8, then latin-1; error if both fail.
    """
    # Try chardet first
    detection = chardet.detect(raw_bytes)
    if detection and detection.get("encoding"):
        detected = detection["encoding"]
        confidence = detection.get("confidence", 0)
        if confidence > 0.5:
            return detected

    # Fallback: try UTF-8
    try:
        raw_bytes.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        pass

    # Fallback: try latin-1 (never fails, but may produce garbage)
    try:
        raw_bytes.decode("latin-1")
        return "latin-1"
    except UnicodeDecodeError:
        raise CSVValidationError(
            message=f"Unable to detect encoding for file '{filename}'. "
            f"Please ensure the file is saved in UTF-8 or latin-1 encoding.",
            request_id=request_id,
        )


# ═══════════════════════════════════════════════════════════════════════
#  CSV Parsing
# ═══════════════════════════════════════════════════════════════════════


def _parse_csv(
    raw_bytes: bytes,
    encoding: str,
    filename: str,
    request_id: str,
) -> pd.DataFrame:
    """Parse raw CSV bytes into a Pandas DataFrame."""
    try:
        text = raw_bytes.decode(encoding)
        df = pd.read_csv(io.StringIO(text))
    except Exception as e:
        raise CSVValidationError(
            message=f"Failed to parse '{filename}' as CSV: {e}",
            request_id=request_id,
            detail=str(e),
        )

    if df.empty or len(df.columns) == 0:
        raise CSVValidationError(
            message=f"File '{filename}' is empty or has no recognisable columns.",
            request_id=request_id,
        )

    return df


# ═══════════════════════════════════════════════════════════════════════
#  Cleaning Pipeline  (PRD Section 12.1)
# ═══════════════════════════════════════════════════════════════════════


def _run_cleaning_pipeline(
    df: pd.DataFrame,
    filename: str,
    request_id: str,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Execute the full cleaning pipeline in order:
      1. Type inference
      2. Date detection
      3. Null handling
      4. Outlier detection (IQR)
      5. String normalisation
    Returns the cleaned DataFrame and a dict of report fields.
    """
    try:
        report_data: Dict[str, Any] = {
            "date_columns_converted": [],
            "nulls_filled": {},
            "outliers_flagged": {},
            "string_columns_normalised": [],
        }

        # ── Stage 1: Type inference ─────────────────────────────────
        df = _infer_types(df)

        # ── Stage 2: Date detection ─────────────────────────────────
        df, date_cols = _detect_and_convert_dates(df)
        report_data["date_columns_converted"] = date_cols

        # ── Stage 3: Null handling ──────────────────────────────────
        df, nulls_filled = _handle_nulls(df)
        report_data["nulls_filled"] = nulls_filled

        # ── Stage 4: Outlier detection (flag only) ──────────────────
        outliers_flagged = _detect_outliers(df)
        report_data["outliers_flagged"] = outliers_flagged

        # ── Stage 5: String normalisation ───────────────────────────
        df, normalised_cols = _normalise_strings(df)
        report_data["string_columns_normalised"] = normalised_cols

        return df, report_data

    except CSVCleaningError:
        raise
    except Exception as e:
        raise CSVCleaningError(
            message=f"Cleaning pipeline failed for '{filename}': {e}",
            request_id=request_id,
            detail=str(e),
        )


def _infer_types(df: pd.DataFrame) -> pd.DataFrame:
    """
    Stage 1: Re-infer column types.
    Pandas defaults to 'object' for mixed columns; attempt numeric
    conversion where possible.
    """
    for col in df.columns:
        if df[col].dtype == object:
            # Try numeric conversion
            converted = pd.to_numeric(df[col], errors="coerce")
            non_null_original = df[col].dropna()
            non_null_converted = converted.dropna()

            # Accept conversion if we don't lose too many values
            if len(non_null_original) > 0:
                loss_ratio = 1 - (len(non_null_converted) / len(non_null_original))
                if loss_ratio < 0.1:  # Less than 10% data loss
                    df[col] = converted

    return df


def _detect_and_convert_dates(
    df: pd.DataFrame,
) -> Tuple[pd.DataFrame, List[str]]:
    """
    Stage 2: Detect columns likely containing dates using pattern matching
    on values; convert matched columns to datetime64.
    """
    converted_columns: List[str] = []
    compiled_patterns = [re.compile(p) for p in DATE_PATTERNS]

    for col in df.columns:
        if df[col].dtype != object:
            continue

        # Sample non-null string values
        sample = df[col].dropna().astype(str).head(20)
        if len(sample) == 0:
            continue

        # Check if majority of sampled values match a date pattern
        match_count = 0
        for val in sample:
            val_stripped = val.strip()
            for pattern in compiled_patterns:
                if pattern.fullmatch(val_stripped):
                    match_count += 1
                    break

        match_ratio = match_count / len(sample)
        if match_ratio >= 0.6:
            try:
                df[col] = pd.to_datetime(df[col], infer_datetime_format=True, errors="coerce")
                converted_columns.append(col)
            except Exception:
                pass  # Skip columns that fail datetime conversion

    return df, converted_columns


def _handle_nulls(
    df: pd.DataFrame,
) -> Tuple[pd.DataFrame, Dict[str, int]]:
    """
    Stage 3: Fill missing values.
    - Numeric columns: fill with column median.
    - Categorical (object/string) columns: fill with mode.
    """
    nulls_filled: Dict[str, int] = {}

    for col in df.columns:
        null_count = int(df[col].isnull().sum())
        if null_count == 0:
            continue

        if pd.api.types.is_numeric_dtype(df[col]):
            median_val = df[col].median()
            df[col] = df[col].fillna(median_val)
            nulls_filled[col] = null_count
        elif df[col].dtype == object or pd.api.types.is_string_dtype(df[col]):
            mode_val = df[col].mode()
            if len(mode_val) > 0:
                df[col] = df[col].fillna(mode_val.iloc[0])
                nulls_filled[col] = null_count

    return df, nulls_filled


def _detect_outliers(df: pd.DataFrame) -> Dict[str, int]:
    """
    Stage 4: Flag outliers using IQR method (Q1 - 1.5×IQR, Q3 + 1.5×IQR).
    Outliers are flagged but NEVER removed (non-destructive pipeline).
    """
    outliers_flagged: Dict[str, int] = {}

    for col in df.select_dtypes(include=["number"]).columns:
        q1 = df[col].quantile(0.25)
        q3 = df[col].quantile(0.75)
        iqr = q3 - q1

        if iqr == 0:
            continue

        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr
        outlier_count = int(
            ((df[col] < lower_bound) | (df[col] > upper_bound)).sum()
        )

        if outlier_count > 0:
            outliers_flagged[col] = outlier_count

    return outliers_flagged


def _normalise_strings(
    df: pd.DataFrame,
) -> Tuple[pd.DataFrame, List[str]]:
    """
    Stage 5: Strip leading/trailing whitespace and normalise encoding
    on string/object columns. Prevents join failures due to whitespace.
    """
    normalised_columns: List[str] = []

    for col in df.select_dtypes(include=["object"]).columns:
        original = df[col].copy()
        df[col] = df[col].astype(str).str.strip()

        # Check if any values actually changed
        if not original.equals(df[col]):
            normalised_columns.append(col)

    return df, normalised_columns


# ═══════════════════════════════════════════════════════════════════════
#  Profile Generation  (PRD Section 12.1 — Profile generation stage)
# ═══════════════════════════════════════════════════════════════════════


def _generate_profiles(df: pd.DataFrame) -> List[ColumnProfile]:
    """
    Generate column-level statistical profiles used for:
      1. The schema context block in the LLM prompt (PRD Section 11.3)
      2. The upload API response (PRD Section 10.1)
    """
    profiles: List[ColumnProfile] = []

    for col in df.columns:
        series = df[col]

        # Collect sample values (non-null, stringified)
        non_null = series.dropna()
        sample_values: List[Any] = []
        if len(non_null) > 0:
            sample = non_null.head(SAMPLE_SIZE).tolist()
            sample_values = [_serialise_value(v) for v in sample]

        profiles.append(
            ColumnProfile(
                column=col,
                dtype=str(series.dtype),
                null_count=int(series.isnull().sum()),
                unique_count=int(series.nunique()),
                sample_values=sample_values,
            )
        )

    return profiles


def _serialise_value(value: Any) -> Any:
    """Convert a pandas value to a JSON-safe Python primitive."""
    if pd.isna(value):
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, (int, float, str, bool)):
        return value
    return str(value)

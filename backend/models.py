"""
Pydantic Request / Response Schemas
=====================================
All request and response shapes are defined here as Pydantic models.
Nothing enters or leaves the API without passing through schema validation.

Reference: PRD Section 6.1 (models.py), Section 10 (API Contract),
           Section 12.2 (Cleaning Report)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════════════
#  Column-Level Schema Profile
# ═══════════════════════════════════════════════════════════════════════


class ColumnProfile(BaseModel):
    """Statistical profile of a single column in an uploaded CSV file."""

    column: str = Field(..., description="Column name")
    dtype: str = Field(..., description="Inferred data type after cleaning")
    null_count: int = Field(..., ge=0, description="Number of null values")
    unique_count: int = Field(..., ge=0, description="Number of unique values")
    sample_values: List[Any] = Field(
        default_factory=list,
        description="Representative sample values from the column",
    )


# ═══════════════════════════════════════════════════════════════════════
#  Cleaning Report  (PRD Section 12.2)
# ═══════════════════════════════════════════════════════════════════════


class CleaningReport(BaseModel):
    """
    Non-destructive cleaning report generated per file.

    The detailed variant is used internally and logged; the summary fields
    map directly to the API response contract in PRD Section 10.1.
    """

    filename: str
    rows_before: int = Field(..., ge=0)
    rows_after: int = Field(..., ge=0)
    nulls_filled: Dict[str, int] = Field(
        default_factory=dict,
        description="Column → count of null values filled",
    )
    date_columns_converted: List[str] = Field(
        default_factory=list,
        description="Columns converted to datetime64",
    )
    outliers_flagged: Dict[str, int] = Field(
        default_factory=dict,
        description="Column → count of IQR outliers flagged",
    )
    string_columns_normalised: List[str] = Field(
        default_factory=list,
        description="Columns where whitespace was trimmed / encoding normalised",
    )


class CleaningReportSummary(BaseModel):
    """
    Condensed cleaning report for the upload API response.
    Matches the JSON shape in PRD Section 10.1.
    """

    nulls_filled: int = Field(0, ge=0)
    date_columns_converted: List[str] = Field(default_factory=list)
    outliers_flagged: int = Field(0, ge=0)
    string_columns_normalised: List[str] = Field(default_factory=list)

    @classmethod
    def from_detailed(cls, report: CleaningReport) -> "CleaningReportSummary":
        """Create a summary from a detailed CleaningReport."""
        return cls(
            nulls_filled=sum(report.nulls_filled.values()),
            date_columns_converted=report.date_columns_converted,
            outliers_flagged=sum(report.outliers_flagged.values()),
            string_columns_normalised=report.string_columns_normalised,
        )


# ═══════════════════════════════════════════════════════════════════════
#  Detected Relationship  (PRD Section 10.1)
# ═══════════════════════════════════════════════════════════════════════


class DetectedRelationship(BaseModel):
    """A detected foreign key relationship between two uploaded files."""

    file_a: str
    file_b: str
    join_column: str
    overlap_ratio: float = Field(..., ge=0.0, le=1.0)
    join_column_a: Optional[str] = None
    join_column_b: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════════
#  File Processing Result
# ═══════════════════════════════════════════════════════════════════════


class FileProcessed(BaseModel):
    """Processing result for a single uploaded CSV file."""

    model_config = {"populate_by_name": True}

    filename: str
    rows: int = Field(..., ge=0)
    columns: int = Field(..., ge=0)
    cleaning_report: CleaningReportSummary
    column_schema: List[ColumnProfile] = Field(
        ...,
        alias="schema",
        serialization_alias="schema",
        description="Column-level statistical profiles",
    )


# ═══════════════════════════════════════════════════════════════════════
#  Upload Endpoint  (PRD Section 10.1 — POST /upload)
# ═══════════════════════════════════════════════════════════════════════


class UploadResponse(BaseModel):
    """Response schema for POST /upload."""

    session_id: str
    files_processed: List[FileProcessed]
    detected_relationships: List[DetectedRelationship]


# ═══════════════════════════════════════════════════════════════════════
#  Query Endpoint  (PRD Section 10.2 — POST /query)
# ═══════════════════════════════════════════════════════════════════════


class QueryRequest(BaseModel):
    """Request schema for POST /query."""

    session_id: str
    question: str = Field(..., min_length=1)


class QueryResponse(BaseModel):
    """Response schema for POST /query."""

    type: str = Field(..., pattern="^(text|chart)$")
    answer: Optional[str] = None
    figure: Optional[Any] = None  # Plotly JSON object or null
    reasoning: str
    request_id: str
    latency_ms: int = Field(..., ge=0)


# ═══════════════════════════════════════════════════════════════════════
#  Session Endpoint  (PRD Section 10.3 — DELETE /session/{session_id})
# ═══════════════════════════════════════════════════════════════════════


class SessionClearResponse(BaseModel):
    """Response schema for DELETE /session/{session_id}."""

    cleared: bool = True


# ═══════════════════════════════════════════════════════════════════════
#  Error Response  (PRD Section 17.2)
# ═══════════════════════════════════════════════════════════════════════


class ErrorResponse(BaseModel):
    """Structured error body returned on all failure paths."""

    error_code: str
    message: str
    request_id: Optional[str] = None

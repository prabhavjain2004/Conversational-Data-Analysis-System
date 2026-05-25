"""
Custom Exception Hierarchy
===========================
Every exception carries a *request_id* and a human-readable *message*.
The global handler in main.py converts these to structured HTTP error responses.

Hierarchy (PRD Section 6.1 — exceptions.py):
    AppException (base)
    ├── CSVValidationError
    ├── CSVCleaningError
    ├── RelationshipDetectionError
    ├── LLMCallError
    ├── LLMParseError
    └── CodeExecutionError
"""

from __future__ import annotations

from typing import Optional


class AppException(Exception):
    """
    Base exception for the Conversational Data Analysis System.

    All typed exceptions inherit from this class so that the global
    exception handler in main.py can intercept them uniformly and
    produce structured error responses with request traceability.
    """

    error_code: str = "INTERNAL_ERROR"
    http_status: int = 500

    def __init__(
        self,
        message: str,
        request_id: Optional[str] = None,
        *,
        detail: Optional[str] = None,
    ) -> None:
        self.message = message
        self.request_id = request_id
        self.detail = detail  # Internal-only detail (never sent to client)
        super().__init__(message)


# ── CSV Pipeline Exceptions ───────────────────────────────────────────


class CSVValidationError(AppException):
    """Raised when an uploaded file fails type, encoding, or size validation."""

    error_code: str = "CSV_VALIDATION_ERROR"
    http_status: int = 400


class CSVCleaningError(AppException):
    """Raised when the data cleaning pipeline encounters an unrecoverable error."""

    error_code: str = "CSV_CLEANING_ERROR"
    http_status: int = 500


# ── Relationship Detection Exceptions ─────────────────────────────────


class RelationshipDetectionError(AppException):
    """Raised when the automatic FK detection process fails."""

    error_code: str = "RELATIONSHIP_DETECTION_ERROR"
    http_status: int = 500


# ── LLM Exceptions ───────────────────────────────────────────────────


class LLMCallError(AppException):
    """Raised when the external LLM API call fails (network, rate-limit, 5xx)."""

    error_code: str = "LLM_CALL_ERROR"
    http_status: int = 502


class LLMParseError(AppException):
    """Raised when the LLM response cannot be parsed into the expected JSON schema."""

    error_code: str = "LLM_PARSE_ERROR"
    http_status: int = 502


# ── Code Execution Exceptions ────────────────────────────────────────


class CodeExecutionError(AppException):
    """Raised when LLM-generated Python code fails to execute in the sandbox."""

    error_code: str = "CODE_EXECUTION_ERROR"
    http_status: int = 500

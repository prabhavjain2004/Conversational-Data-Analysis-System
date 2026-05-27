"""
FastAPI Application Entry Point
================================
Defines all API routes, generates a request_id (UUID4) at the entry point
of every request, passes request_id to all downstream functions, handles
CORS for Next.js communication, and registers global exception handlers.

Reference: PRD Section 6.1 (main.py), Section 14 (Observability),
           Section 10 (API Contract), Section 17 (Error Handling Strategy)
"""

from __future__ import annotations

import json
import logging
import sys
import time
import traceback
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

import pandas as pd
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.config import settings
from backend.csv_handler import process_csv_file
from backend.exceptions import AppException, CodeExecutionError
from backend.models import (
    CleaningReportSummary,
    ColumnProfile,
    DetectedRelationship,
    ErrorResponse,
    FileProcessed,
    QueryRequest,
    QueryResponse,
    SessionClearResponse,
    UploadResponse,
)
from backend.relationship_detector import detect_relationships
from backend.llm_service import build_system_prompt, build_conversation_messages, call_llm
from backend.chart_engine import safe_execute_chart, safe_execute_text
from backend.logger import log_event
from backend.memory import ConversationMemory


# ═══════════════════════════════════════════════════════════════════════
#  In-Memory Session Store
# ═══════════════════════════════════════════════════════════════════════


class SessionStore:
    """
    Lightweight in-memory store for session data.

    Each session holds:
      - dataframes: dict mapping filename → pd.DataFrame
      - schemas: dict mapping filename → list of ColumnProfile dicts
      - cleaning_reports: dict mapping filename → CleaningReport
      - relationships: list of DetectedRelationship dicts
      - memory: ConversationMemory (sliding window deque, PRD Section 13)
    """

    def __init__(self) -> None:
        self._sessions: Dict[str, Dict[str, Any]] = {}

    def get_or_create(self, session_id: str) -> Dict[str, Any]:
        if session_id not in self._sessions:
            self._sessions[session_id] = {
                "dataframes": {},
                "schemas": {},
                "cleaning_reports": {},
                "relationships": [],
                "memory": ConversationMemory(),
            }
        return self._sessions[session_id]

    def get(self, session_id: str) -> Dict[str, Any] | None:
        return self._sessions.get(session_id)

    def delete(self, session_id: str) -> bool:
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False

    def exists(self, session_id: str) -> bool:
        return session_id in self._sessions


session_store = SessionStore()


# ═══════════════════════════════════════════════════════════════════════
#  FastAPI Application
# ═══════════════════════════════════════════════════════════════════════

app = FastAPI(
    title="Conversational Data Analysis System",
    description="Upload CSV files and query them using natural language.",
    version="1.0.0",
)

# ── CORS for Next.js communication (PRD Section 6.1) ──────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)


# ═══════════════════════════════════════════════════════════════════════
#  Request-ID Middleware  (PRD Section 14.2)
# ═══════════════════════════════════════════════════════════════════════


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """
    Assigns a unique request_id (UUID4) to every incoming request.
    The ID is attached to the request state, included in every log entry,
    and returned in the response headers.
    """
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id

    log_event(
        "request_received",
        request_id=request_id,
        method=request.method,
        path=str(request.url.path),
    )

    start_time = time.perf_counter()
    response = await call_next(request)
    latency_ms = int((time.perf_counter() - start_time) * 1000)

    response.headers["X-Request-ID"] = request_id
    log_event(
        "request_complete",
        request_id=request_id,
        status_code=response.status_code,
        latency_ms=latency_ms,
    )
    return response


# ═══════════════════════════════════════════════════════════════════════
#  Global Exception Handler  (PRD Section 17)
# ═══════════════════════════════════════════════════════════════════════


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    """
    Converts typed AppException subclasses to structured HTTP error
    responses. Users see human-readable messages; stack traces are logged
    but never sent to the client.
    """
    request_id = getattr(request.state, "request_id", exc.request_id)
    log_event(
        "error",
        request_id=request_id,
        level=logging.ERROR,
        exception_type=type(exc).__name__,
        error_code=exc.error_code,
        message=exc.message,
        detail=exc.detail,
        stage=type(exc).__name__,
    )
    return JSONResponse(
        status_code=exc.http_status,
        content=ErrorResponse(
            error_code=exc.error_code,
            message=exc.message,
            request_id=request_id,
        ).model_dump(),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """
    Catch-all for any unhandled exception. Logs full traceback internally
    but returns only a generic user-facing message.
    """
    request_id = getattr(request.state, "request_id", None)
    log_event(
        "error",
        request_id=request_id,
        level=logging.ERROR,
        exception_type=type(exc).__name__,
        message=str(exc),
        traceback=traceback.format_exc(),
        stage="unhandled",
    )
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error_code="INTERNAL_ERROR",
            message="An unexpected error occurred. Please try again.",
            request_id=request_id,
        ).model_dump(),
    )


# ═══════════════════════════════════════════════════════════════════════
#  Health Check
# ═══════════════════════════════════════════════════════════════════════


@app.get("/health")
async def health_check():
    """Simple liveness probe for container orchestration."""
    return {"status": "healthy", "service": "backend"}


# ═══════════════════════════════════════════════════════════════════════
#  POST /upload  (PRD Section 10.1)
# ═══════════════════════════════════════════════════════════════════════


@app.post("/upload", response_model=UploadResponse)
async def upload_files(
    request: Request,
    files: List[UploadFile] = File(...),
    session_id: str = Form(...),
):
    """
    Upload one or more CSV files for processing.

    Pipeline per file: validate → clean → profile → detect relationships.
    """
    request_id: str = request.state.request_id

    log_event(
        "file_upload_received",
        request_id=request_id,
        session_id=session_id,
        file_count=len(files),
        file_names=[f.filename for f in files],
    )

    session = session_store.get_or_create(session_id)
    files_processed: List[FileProcessed] = []

    for upload_file in files:
        # ── Process each CSV through the full cleaning pipeline ─────
        df, column_profiles, cleaning_report = await process_csv_file(
            upload_file=upload_file,
            request_id=request_id,
            max_file_size_bytes=settings.max_file_size_bytes,
        )

        # Sanitise filename for safe use as a dataframe variable name
        safe_name = (
            upload_file.filename.replace(" ", "_")
            .replace("-", "_")
            .replace(".", "_")
            if upload_file.filename
            else "unnamed"
        )

        # ── Store in session ────────────────────────────────────────
        session["dataframes"][safe_name] = df
        session["schemas"][safe_name] = column_profiles
        session["cleaning_reports"][safe_name] = cleaning_report

        # ── Build API response for this file ────────────────────────
        summary = CleaningReportSummary.from_detailed(cleaning_report)
        files_processed.append(
            FileProcessed(
                filename=upload_file.filename or "unnamed",
                rows=len(df),
                columns=len(df.columns),
                cleaning_report=summary,
                column_schema=column_profiles,
            )
        )

        log_event(
            "file_processing_complete",
            request_id=request_id,
            filename=upload_file.filename,
            rows=len(df),
            columns=len(df.columns),
            cleaning_changes={
                "nulls_filled": sum(cleaning_report.nulls_filled.values()),
                "dates_converted": len(cleaning_report.date_columns_converted),
                "outliers_flagged": sum(
                    cleaning_report.outliers_flagged.values()
                ),
            },
        )

    # ── Detect relationships across all uploaded files ──────────────
    relationships: List[DetectedRelationship] = detect_relationships(
        dataframes=session["dataframes"],
        threshold=settings.fk_overlap_threshold,
        request_id=request_id,
    )
    session["relationships"] = relationships

    log_event(
        "relationship_detection_complete",
        request_id=request_id,
        detected_pairs=len(relationships),
        threshold_used=settings.fk_overlap_threshold,
    )

    return UploadResponse(
        session_id=session_id,
        files_processed=files_processed,
        detected_relationships=relationships,
    )


# ═══════════════════════════════════════════════════════════════════════
#  POST /query  (PRD Section 10.2) — Phase 2: Full Intelligence Pipeline
# ═══════════════════════════════════════════════════════════════════════


@app.post("/query", response_model=QueryResponse)
async def query_data(request: Request, body: QueryRequest):
    """
    Submit a natural language question for the currently uploaded files.

    Pipeline (PRD Section 4.2):
      Question → retrieve session → build prompt → call LLM →
      parse JSON → execute code (if any) → return response →
      update conversation history → log everything
    """
    request_id: str = request.state.request_id
    start_time = time.perf_counter()

    # ── Validate session exists ─────────────────────────────────────
    session = session_store.get(body.session_id)
    if session is None:
        raise AppException(
            message="Session not found. Please upload files first.",
            request_id=request_id,
        )

    dataframes: Dict[str, Any] = session["dataframes"]
    schemas: Dict[str, Any] = session["schemas"]
    relationships = session["relationships"]
    memory: ConversationMemory = session["memory"]

    # ── Build structured prompt (PRD Section 11) ────────────────────
    system_prompt = build_system_prompt(schemas, dataframes, relationships)

    # ── Build conversation messages ─────────────────────────────────
    messages = build_conversation_messages(memory.get_history(), body.question)

    # ── Call LLM with retry logic (PRD Section 17.3) ────────────────
    llm_response = call_llm(
        system_prompt=system_prompt,
        messages=messages,
        request_id=request_id,
    )

    response_type = llm_response.get("type", "text")
    answer = llm_response.get("answer")
    code = llm_response.get("code")
    reasoning = llm_response.get("reasoning", "")
    figure_json = None

    # ── Route response based on type (PRD Section 7.2) ──────────────
    if response_type == "chart" and code:
        try:
            fig = safe_execute_chart(code, dataframes, request_id)
            figure_json = json.loads(fig.to_json())
        except CodeExecutionError:
            # PRD Section 17.1: Chart failure degrades gracefully
            # Do NOT crash the session — return error message instead
            log_event(
                "chart_fallback",
                request_id=request_id,
                level=logging.WARNING,
                reason="Chart execution failed, returning error to user",
            )
            response_type = "text"
            answer = (
                "I attempted to create a chart but the generated code "
                "encountered an error. Please try rephrasing your question "
                "or asking for a text-based answer instead."
            )
            figure_json = None

    elif response_type == "text" and code:
        # LLM generated code for a text answer — execute it
        try:
            result = safe_execute_text(code, dataframes, request_id)
            
            # Check for zero, null, or empty dataframe/series/collection (Hallucination Guard)
            is_empty_collection = hasattr(result, '__len__') and len(result) == 0
            is_numeric_zero = isinstance(result, (int, float)) and result == 0
            
            if result is None or is_empty_collection or is_numeric_zero:
                answer = "The data does not contain any records for the requested period."
            else:
                # Synthesize a beautiful natural language answer using the Gemini LLM
                from backend.llm_service import synthesize_final_answer
                answer = synthesize_final_answer(
                    question=body.question,
                    code=code,
                    result=result,
                    request_id=request_id,
                )
        except CodeExecutionError:
            log_event(
                "text_code_fallback",
                request_id=request_id,
                level=logging.WARNING,
                reason="Text code execution failed, returning LLM's raw answer",
            )
            # Fall back to whatever text the LLM provided
            if not answer:
                answer = (
                    "I attempted to compute an answer but the generated code "
                    "encountered an error. Please try rephrasing your question."
                )

    # ── Final Answer Sanitization Guard (prevents template leaks) ──
    if answer and ("{result}" in answer or "{Result}" in answer):
        log_event(
            "template_leak_detected",
            request_id=request_id,
            level=logging.WARNING,
            raw_answer=answer[:200],
        )
        # The LLM left a {result} placeholder — the synthesis layer must
        # have failed or was bypassed. Re-synthesize if we have a result.
        if response_type == "text" and code:
            try:
                from backend.llm_service import synthesize_final_answer, format_raw_result_for_llm
                # Re-execute code to get the result for synthesis
                _result = safe_execute_text(code, dataframes, request_id)
                if _result is not None:
                    answer = synthesize_final_answer(
                        question=body.question,
                        code=code,
                        result=_result,
                        request_id=request_id,
                    )
                else:
                    answer = answer.replace("{result}", "the requested value").replace("{Result}", "the requested value")
            except Exception:
                answer = answer.replace("{result}", "the requested value").replace("{Result}", "the requested value")
        else:
            answer = answer.replace("{result}", "the requested value").replace("{Result}", "the requested value")

    # ── Update conversation memory (PRD Section 13) ─────────────────
    assistant_content = answer or f"[Chart: {reasoning}]"
    memory.add_turn(body.question, assistant_content)

    # ── Calculate latency and log ───────────────────────────────────
    latency_ms = int((time.perf_counter() - start_time) * 1000)

    log_event(
        "query_complete",
        request_id=request_id,
        response_type=response_type,
        total_latency_ms=latency_ms,
    )

    return QueryResponse(
        type=response_type,
        answer=answer,
        figure=figure_json,
        reasoning=reasoning,
        request_id=request_id,
        latency_ms=latency_ms,
    )


# ═══════════════════════════════════════════════════════════════════════
#  DELETE /session/{session_id}  (PRD Section 10.3)
# ═══════════════════════════════════════════════════════════════════════


@app.delete("/session/{session_id}", response_model=SessionClearResponse)
async def clear_session(request: Request, session_id: str):
    """
    Clear all uploaded files and conversation history for a session.
    """
    request_id: str = request.state.request_id
    cleared = session_store.delete(session_id)

    log_event(
        "session_cleared",
        request_id=request_id,
        session_id=session_id,
        cleared=cleared,
    )

    return SessionClearResponse(cleared=cleared)


# ═══════════════════════════════════════════════════════════════════════
#  Entrypoint
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.main:app",
        host=settings.backend_host,
        port=settings.backend_port,
        reload=True,
    )

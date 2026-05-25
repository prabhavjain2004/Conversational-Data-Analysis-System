"""
Safe Code Execution Sandbox (Chart Engine)
============================================
Receives Plotly code string from LLM response, executes it in a restricted
namespace (only Pandas and Plotly Express in scope), returns a Plotly figure
object or raises a typed exception on failure. Never uses unrestricted exec().

Reference: PRD Section 6.1 (chart_engine.py), Section 8.7 (Safe Code Execution),
           Section 16.1 (Code Execution Sandbox)
"""

from __future__ import annotations

import logging
import time
import traceback
from typing import Any, Dict, Optional

import pandas as pd
import plotly.express as px
from plotly.graph_objects import Figure

from backend.exceptions import CodeExecutionError


def safe_execute_chart(
    code: str,
    dataframes: Dict[str, pd.DataFrame],
    request_id: str,
) -> Figure:
    """
    Execute LLM-generated Plotly code in a restricted sandbox.

    The sandbox (PRD Section 8.7 / 16.1):
      - __builtins__ set to empty dict (no built-in access)
      - Only pandas (pd) and plotly.express (px) are available
      - Only the uploaded dataframes are injected
      - Cannot import, call open(), exec(), eval(), os, sys, etc.

    The generated code MUST assign the chart to a variable named "fig".

    Args:
        code: LLM-generated Python code string.
        dataframes: Mapping of sanitised filenames → DataFrames.
        request_id: For log tracing.

    Returns:
        A plotly Figure object.

    Raises:
        CodeExecutionError: If the code fails to execute or does not
            produce a valid Figure.
    """
    from backend.main import log_event  # Avoid circular import at module level

    # ── Build restricted namespace (PRD Section 8.7) ───────────────
    allowed_globals: Dict[str, Any] = {
        "__builtins__": {},     # No built-ins at all
        "pd": pd,              # Pandas only
        "px": px,              # Plotly Express only
        **dataframes,          # Only the uploaded dataframes
    }
    local_scope: Dict[str, Any] = {}

    start_time = time.perf_counter()

    try:
        exec(code, allowed_globals, local_scope)  # noqa: S102
    except Exception as e:
        execution_ms = int((time.perf_counter() - start_time) * 1000)
        log_event(
            "code_execution_failure",
            request_id=request_id,
            level=logging.ERROR,
            error_type=type(e).__name__,
            error_message=str(e),
            code_snippet=code[:500],
            execution_time_ms=execution_ms,
            traceback=traceback.format_exc(),
        )
        raise CodeExecutionError(
            message="The chart could not be generated. "
            "Please try rephrasing your question.",
            request_id=request_id,
            detail=f"{type(e).__name__}: {e}",
        )

    execution_ms = int((time.perf_counter() - start_time) * 1000)

    # ── Validate output ────────────────────────────────────────────
    fig = local_scope.get("fig")
    if fig is None:
        log_event(
            "code_execution_failure",
            request_id=request_id,
            level=logging.ERROR,
            error_type="MissingFigVariable",
            error_message="Code executed but did not assign to 'fig'.",
            code_snippet=code[:500],
            execution_time_ms=execution_ms,
        )
        raise CodeExecutionError(
            message="The chart code did not produce a figure. "
            "Please try rephrasing your question.",
            request_id=request_id,
            detail="Variable 'fig' not found in local scope after execution.",
        )

    if not isinstance(fig, Figure):
        log_event(
            "code_execution_failure",
            request_id=request_id,
            level=logging.ERROR,
            error_type="InvalidFigType",
            error_message=f"'fig' is {type(fig).__name__}, expected Figure.",
            code_snippet=code[:500],
            execution_time_ms=execution_ms,
        )
        raise CodeExecutionError(
            message="The chart code produced an invalid output. "
            "Please try rephrasing your question.",
            request_id=request_id,
            detail=f"'fig' is type {type(fig).__name__}, expected plotly Figure.",
        )

    log_event(
        "code_execution_success",
        request_id=request_id,
        chart_type=_detect_chart_type(fig),
        execution_time_ms=execution_ms,
    )

    return fig


def safe_execute_text(
    code: str,
    dataframes: Dict[str, pd.DataFrame],
    request_id: str,
) -> Any:
    """
    Execute LLM-generated Pandas code for text answers in a restricted sandbox.

    The generated code MUST assign the computed value to a variable named "result".

    Args:
        code: LLM-generated Python code string.
        dataframes: Mapping of sanitised filenames → DataFrames.
        request_id: For log tracing.

    Returns:
        The computed result value.

    Raises:
        CodeExecutionError: If the code fails or doesn't produce a result.
    """
    from backend.main import log_event  # Avoid circular import at module level

    allowed_globals: Dict[str, Any] = {
        "__builtins__": {},
        "pd": pd,
        "px": px,
        **dataframes,
    }
    local_scope: Dict[str, Any] = {}

    start_time = time.perf_counter()

    try:
        exec(code, allowed_globals, local_scope)  # noqa: S102
    except Exception as e:
        execution_ms = int((time.perf_counter() - start_time) * 1000)
        log_event(
            "code_execution_failure",
            request_id=request_id,
            level=logging.ERROR,
            error_type=type(e).__name__,
            error_message=str(e),
            code_snippet=code[:500],
            execution_time_ms=execution_ms,
            traceback=traceback.format_exc(),
        )
        raise CodeExecutionError(
            message="Failed to compute the answer. "
            "Please try rephrasing your question.",
            request_id=request_id,
            detail=f"{type(e).__name__}: {e}",
        )

    execution_ms = int((time.perf_counter() - start_time) * 1000)

    result = local_scope.get("result")
    if result is None:
        log_event(
            "code_execution_failure",
            request_id=request_id,
            level=logging.ERROR,
            error_type="MissingResultVariable",
            error_message="Code executed but did not assign to 'result'.",
            code_snippet=code[:500],
            execution_time_ms=execution_ms,
        )
        raise CodeExecutionError(
            message="The computation did not produce a result. "
            "Please try rephrasing your question.",
            request_id=request_id,
            detail="Variable 'result' not found in local scope after execution.",
        )

    log_event(
        "code_execution_success",
        request_id=request_id,
        result_type=type(result).__name__,
        execution_time_ms=execution_ms,
    )

    return result


def _detect_chart_type(fig: Figure) -> str:
    """Extract the chart type from a Plotly figure for logging."""
    try:
        if fig.data and len(fig.data) > 0:
            return type(fig.data[0]).__name__
    except Exception:
        pass
    return "unknown"

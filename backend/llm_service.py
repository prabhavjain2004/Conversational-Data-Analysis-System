"""
LLM Integration Layer
======================
Constructs the structured system prompt (schema context + relationships +
conversation history + user question), calls the Gemini API, parses and
validates the JSON response, handles retries on transient failures, and
logs token counts and latency.

Reference: PRD Section 6.1 (llm_service.py), Section 8.5 (Direct API Calls),
           Section 8.8 (LLM Selection), Section 11 (Prompt Engineering Strategy),
           Section 17.3 (Retry Strategy), Section 17.4 (Fallback Behaviour)
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional

from google import genai
from google.genai import types

from backend.config import settings
from backend.exceptions import LLMCallError, LLMParseError
from backend.logger import log_event
from backend.models import ColumnProfile, DetectedRelationship


# ═══════════════════════════════════════════════════════════════════════
#  Gemini Client (New Unified SDK)
# ═══════════════════════════════════════════════════════════════════════

_client: Optional[genai.Client] = None


def _get_client() -> genai.Client:
    """Lazily initialise the Gemini client singleton."""
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


# ═══════════════════════════════════════════════════════════════════════
#  Prompt Construction  (PRD Section 11)
# ═══════════════════════════════════════════════════════════════════════

# ── [1] Role and Instructions Block  (PRD Section 11.2) ───────────────

ROLE_AND_INSTRUCTIONS = """\
You are a data analysis assistant. You have access to the following \
structured data files. Your job is to answer the user's question by \
analysing the data.

Rules:
- Always respond in valid JSON matching the schema below
- Never invent data. If the answer cannot be determined from the \
provided files, say so clearly in the answer field
- For numerical questions, generate Pandas code to compute the answer \
and set type to "text"
- For trend, comparison, or distribution questions, generate Plotly \
Express code and set type to "chart"
- The code field must assign the final result to a variable named "fig" \
for charts, or "result" for text
- Available dataframes in scope: {dataframe_variable_names}
- Available libraries: pandas (as pd), plotly.express (as px)
- For generated charts, ALWAYS apply a premium, minimalist monochrome/greyscale palette. Avoid colorful blues, greens, or purples. Use neutral shades like white, silver, and varying greys (e.g., color_discrete_sequence=['#ffffff', '#cccccc', '#999999', '#666666']). Customize the Plotly figure to use template='plotly_dark' and set a transparent background if appropriate, ensuring axes labels are highly readable in white or light silver.
- If the computed result from your Pandas query code is zero, null, or returns an empty dataframe/series, explicitly state in the answer field that no data was found for this query or requested period. Never hallucinate, assume non-zero values, or present $0 as a valid figure without confirming matching records exist in the dataset.
- When type is "text" and you generate code to compute a result, your "answer" field MUST contain the literal placeholder "{result}" where the computed value will be dynamically plugged in. You MUST NOT guess or include any hardcoded numbers, quantities, dates, names, or values inside the "answer" string itself. Design the answer as a natural template, for example: "The product with the highest revenue last week was {result}." or "The total revenue computed was {result}."


Response schema:
{{
  "type": "text | chart",
  "answer": "natural language answer or null if chart",
  "code": "executable Python string or null if simple text",
  "reasoning": "one sentence explaining why you chose this format"
}}
"""

# ── JSON reminder for retry on invalid JSON (PRD Section 17.4) ────────

JSON_REMINDER = """
IMPORTANT: Your previous response was not valid JSON. You MUST respond \
with ONLY a valid JSON object matching the schema above. No markdown \
fences, no explanatory text outside the JSON. Just the raw JSON object.
"""


def build_system_prompt(
    schemas: Dict[str, List[ColumnProfile]],
    dataframes: Dict[str, Any],
    relationships: List[DetectedRelationship],
) -> str:
    """
    Construct the full system prompt dynamically.

    Structure (PRD Section 11.1):
      [1] ROLE AND INSTRUCTIONS
      [2] SCHEMA CONTEXT (all uploaded files)
      [3] DETECTED RELATIONSHIPS
    """
    parts: List[str] = []

    # ── [1] Role and Instructions ───────────────────────────────────
    df_names = ", ".join(schemas.keys())
    parts.append(
        ROLE_AND_INSTRUCTIONS.format(dataframe_variable_names=df_names)
    )

    # ── [2] Schema Context  (PRD Section 11.3) ─────────────────────
    parts.append("=" * 60)
    parts.append("DATA FILES")
    parts.append("=" * 60)

    for var_name, columns in schemas.items():
        df = dataframes.get(var_name)
        row_count = len(df) if df is not None else 0
        col_count = len(df.columns) if df is not None else 0

        parts.append(f"\nFILE: {var_name}")
        parts.append(f"Rows: {row_count} | Columns: {col_count}")
        parts.append(f"Dataframe variable: {var_name}")
        parts.append("")
        parts.append("Columns:")
        parts.append(
            "| Column | Type | Nulls | Uniques | Sample Values |"
        )
        parts.append(
            "|--------|------|-------|---------|---------------|"
        )

        for col in columns:
            sample_str = ", ".join(str(v) for v in col.sample_values[:5])
            parts.append(
                f"| {col.column} | {col.dtype} | {col.null_count} "
                f"| {col.unique_count} | {sample_str} |"
            )

    # ── [3] Detected Relationships  (PRD Section 11.4) ─────────────
    if relationships:
        parts.append("")
        parts.append("=" * 60)
        parts.append("DETECTED RELATIONSHIPS (use these for joins):")
        parts.append("=" * 60)
        for rel in relationships:
            overlap_pct = int(rel.overlap_ratio * 100)
            parts.append(
                f"- {rel.file_a}.{rel.join_column} → "
                f"{rel.file_b}.{rel.join_column} (overlap: {overlap_pct}%)"
            )

    return "\n".join(parts)


def build_conversation_messages(
    history: List[Dict[str, str]],
    question: str,
) -> List[types.Content]:
    """
    Build the conversation messages array for the Gemini API.

    Structure (PRD Section 11.1):
      [4] CONVERSATION HISTORY (last N turns)
      [5] CURRENT QUESTION
    """
    messages: List[types.Content] = []

    # ── [4] Conversation history ────────────────────────────────────
    for turn in history:
        role = turn.get("role", "user")
        content = turn.get("content", "")
        # Gemini API uses "user" and "model" roles
        gemini_role = "model" if role == "assistant" else "user"
        messages.append(
            types.Content(role=gemini_role, parts=[types.Part(text=content)])
        )

    # ── [5] Current question ────────────────────────────────────────
    messages.append(
        types.Content(role="user", parts=[types.Part(text=question)])
    )

    return messages


# ═══════════════════════════════════════════════════════════════════════
#  LLM Call with Retry  (PRD Section 17.3)
# ═══════════════════════════════════════════════════════════════════════


def call_llm(
    system_prompt: str,
    messages: List[types.Content],
    request_id: str,
    retry_count: int = 0,
) -> Dict[str, Any]:
    """
    Call the Gemini API and parse the structured JSON response.

    Retry strategy (PRD Section 17.3):
      - Up to 3 retries with exponential backoff on transient errors
      - Permanent errors (invalid API key, malformed request) fail immediately

    Fallback (PRD Section 17.4):
      - If LLM returns invalid JSON, retry once with explicit JSON reminder

    Returns:
        Parsed dict with keys: type, answer, code, reasoning
    """
    client = _get_client()
    max_retries = 3
    last_error: Optional[Exception] = None

    for attempt in range(max_retries + 1):
        try:
            # Build the effective system instruction
            effective_system = system_prompt
            if retry_count > 0:
                effective_system = system_prompt + "\n" + JSON_REMINDER

            start_time = time.perf_counter()

            log_event(
                "llm_request_sent",
                request_id=request_id,
                model=settings.llm_model,
                attempt=attempt + 1,
                history_length=len(messages) - 1,  # Exclude current question
            )

            response = client.models.generate_content(
                model=settings.llm_model,
                contents=messages,
                config=types.GenerateContentConfig(
                    system_instruction=effective_system,
                    temperature=0.1,  # Low temperature for deterministic output
                    response_mime_type="application/json",
                ),
            )

            latency_ms = int((time.perf_counter() - start_time) * 1000)

            # Extract response text
            response_text = response.text
            if not response_text:
                raise LLMCallError(
                    message="LLM returned an empty response.",
                    request_id=request_id,
                )

            log_event(
                "llm_response_received",
                request_id=request_id,
                latency_ms=latency_ms,
                response_length=len(response_text),
            )

            # Parse JSON response
            parsed = _parse_llm_response(response_text, request_id)

            log_event(
                "llm_response_received",
                request_id=request_id,
                response_type=parsed.get("type"),
                latency_ms=latency_ms,
                reasoning=parsed.get("reasoning"),
            )

            return parsed

        except LLMParseError:
            # PRD Section 17.4: Retry once with JSON reminder
            if retry_count == 0:
                log_event(
                    "llm_json_retry",
                    request_id=request_id,
                    level=logging.WARNING,
                    reason="Invalid JSON from LLM, retrying with reminder",
                )
                return call_llm(
                    system_prompt, messages, request_id, retry_count=1
                )
            raise  # Already retried once, propagate the error

        except (LLMCallError, LLMParseError):
            raise  # Permanent errors — don't retry

        except Exception as e:
            last_error = e

            # Determine if retryable (transient network/rate-limit errors)
            error_str = str(e).lower()
            is_transient = any(
                keyword in error_str
                for keyword in [
                    "rate limit",
                    "429",
                    "500",
                    "502",
                    "503",
                    "504",
                    "timeout",
                    "connection",
                    "unavailable",
                ]
            )

            if not is_transient or attempt >= max_retries:
                raise LLMCallError(
                    message=f"LLM API call failed: {e}",
                    request_id=request_id,
                    detail=str(e),
                )

            # Exponential backoff: 1s, 2s, 4s
            backoff = 2**attempt
            log_event(
                "llm_retry",
                request_id=request_id,
                level=logging.WARNING,
                attempt=attempt + 1,
                backoff_seconds=backoff,
                error=str(e),
            )
            time.sleep(backoff)

    # Should not reach here, but safety net
    raise LLMCallError(
        message=f"LLM API call failed after {max_retries} retries: {last_error}",
        request_id=request_id,
    )


# ═══════════════════════════════════════════════════════════════════════
#  Response Parsing  (PRD Section 8.3 — Structured JSON Contract)
# ═══════════════════════════════════════════════════════════════════════


def _parse_llm_response(
    response_text: str, request_id: str
) -> Dict[str, Any]:
    """
    Parse the LLM response text into the expected JSON structure.

    Expected schema (PRD Section 8.3):
    {
        "type": "text | chart",
        "answer": "string or null",
        "code": "executable Python string or null",
        "reasoning": "string"
    }
    """
    # Strip markdown fences if present (common LLM behaviour)
    cleaned = response_text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    if cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise LLMParseError(
            message="The AI returned a response that could not be parsed. "
            "Please try rephrasing your question.",
            request_id=request_id,
            detail=f"JSON parse error: {e}. Raw: {cleaned[:200]}",
        )

    # Validate required fields
    if not isinstance(parsed, dict):
        raise LLMParseError(
            message="The AI returned an unexpected response format.",
            request_id=request_id,
            detail=f"Expected dict, got {type(parsed).__name__}",
        )

    response_type = parsed.get("type")
    if response_type not in ("text", "chart"):
        raise LLMParseError(
            message="The AI returned an unexpected response type.",
            request_id=request_id,
            detail=f"type='{response_type}', expected 'text' or 'chart'",
        )

    if "reasoning" not in parsed:
        parsed["reasoning"] = "No reasoning provided by the model."

    # Ensure nullable fields have defaults
    parsed.setdefault("answer", None)
    parsed.setdefault("code", None)

    return parsed

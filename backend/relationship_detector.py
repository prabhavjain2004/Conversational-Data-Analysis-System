"""
Automatic Foreign Key Detection Module
========================================
Detects semantic and string-matched relationship candidates using LLM guidance,
and validates them with Jaccard value overlap checks.

Reference: PRD Section 6.1 (relationship_detector.py), Section 8.4
"""

from __future__ import annotations

import json
import logging
from itertools import combinations
from typing import Any, Dict, List, Optional

import pandas as pd

from backend.config import settings
from backend.models import DetectedRelationship
from backend.logger import log_event

# Lazily initialized Gemini Client
_client = None


def _get_client():
    """Lazily initialises the Gemini Client."""
    global _client
    if _client is None:
        from google import genai
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


def _get_proposed_relationships_from_llm(
    schemas_input: str,
    request_id: str | None = None,
) -> List[Dict[str, str]]:
    """
    Call the Gemini LLM to propose candidate semantic relationships between files.
    """
    try:
        from google.genai import types
        client = _get_client()

        system_prompt = (
            "You are an expert database administrator and data modeling assistant. "
            "Your task is to analyze the schemas of multiple uploaded datasets (represented as DataFrames) "
            "and identify potential primary-key/foreign-key relationship candidates between them.\n\n"
            "Guidelines:\n"
            "- For each potential relationship, the columns do NOT need to have the same name, but they must "
            "have a logical, semantic relationship (e.g., users_csv.id and orders_csv.user_id, or regions_csv.region_id and customers_csv.region).\n"
            "- Only suggest relationships between columns of compatible types (e.g., do not join an integer with a date).\n"
            "- Avoid suggesting relationships between columns that are descriptively or semantically unrelated, "
            "even if their names are similar or their values overlap (e.g., do not join 'is_active' with 'has_discount').\n\n"
            "You must respond in valid JSON with a single key \"relationships\", containing a list of objects. "
            "Each object must have the following fields:\n"
            "  - \"file_a\": name of the first DataFrame\n"
            "  - \"column_a\": join column in file_a\n"
            "  - \"file_b\": name of the second DataFrame\n"
            "  - \"column_b\": join column in file_b\n\n"
            "JSON Response Schema:\n"
            "{\n"
            "  \"relationships\": [\n"
            "    {\n"
            "      \"file_a\": \"users_csv\",\n"
            "      \"column_a\": \"id\",\n"
            "      \"file_b\": \"orders_csv\",\n"
            "      \"column_b\": \"user_id\"\n"
            "    }\n"
            "  ]\n"
            "}"
        )

        contents = [
            types.Content(
                role="user",
                parts=[
                    types.Part(
                        text=f"Identify semantic relationships between these datasets:\n\n{schemas_input}"
                    )
                ]
            )
        ]

        log_event(
            "llm_relationship_proposal_request",
            request_id=request_id,
            model=settings.llm_model,
        )

        response = client.models.generate_content(
            model=settings.llm_model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.1,
                response_mime_type="application/json",
            ),
        )

        text = response.text.strip() if response.text else ""
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        parsed = json.loads(text)
        return parsed.get("relationships", [])

    except Exception as e:
        log_event(
            "llm_relationship_proposal_failure",
            request_id=request_id,
            level=logging.WARNING,
            error=str(e),
        )
        return []


def _is_relationship_candidate(col_name: str, series: pd.Series) -> bool:
    """
    Check if a column is a viable primary or foreign key candidate.
    Excludes boolean columns, flag columns, status fields, and obvious non-key descriptors.
    """
    # 1. Exclude boolean type
    if series.dtype == bool or series.dtype == 'boolean':
        return False

    # 2. Exclude columns containing boolean-like values
    try:
        unique_vals = set(series.dropna().astype(str).str.lower().unique())
        bool_sets = [
            {"true", "false"},
            {"t", "f"},
            {"y", "n"},
            {"yes", "no"},
            {"1", "0"},
            {"1.0", "0.0"}
        ]
        for b_set in bool_sets:
            if unique_vals.issubset(b_set) and len(unique_vals) > 0:
                return False
    except Exception:
        pass

    # 3. Exclude flags and status indicators from column names
    col_lower = col_name.lower()
    flag_words = {"is_", "has_", "active", "flag", "discount", "enabled", "status"}
    if any(word in col_lower for word in flag_words):
        return False

    return True


def detect_relationships(
    dataframes: Dict[str, pd.DataFrame],
    threshold: float = 0.5,
    request_id: str | None = None,
) -> List[DetectedRelationship]:
    """
    Detect semantic and string-matched relationship candidates and validate them using data overlap.
    """
    if len(dataframes) < 2:
        return []

    # Common descriptive or non-key attribute names to ignore for fallback joins
    IGNORED_COLUMNS = {
        "address", "city", "state", "country", "zipcode", "postal_code", "zip",
        "name", "first_name", "last_name", "title", "description", "details", "summary",
        "status", "type", "category", "genre", "tag", "tags",
        "email", "phone", "website", "url", "fax",
        "date", "time", "year", "month", "day", "hour", "minute", "second",
        "created_at", "updated_at", "timestamp", "created", "modified",
        "rating", "score", "review", "comment", "comments",
        "amount", "price", "revenue", "cost", "quantity", "count", "value",
        "notes", "remarks", "text", "message", "subject"
    }

    candidates: List[tuple[str, str, str, str]] = []

    # ── [1] Generate Rich Schema Summary for LLM ─────────────────────
    schemas_summary = []
    for var_name, df in dataframes.items():
        schemas_summary.append(f"DataFrame: {var_name}")
        schemas_summary.append("Columns:")
        for col in df.columns:
            # Skip non-candidates (e.g. booleans) to reduce tokens and focus LLM attention
            if not _is_relationship_candidate(col, df[col]):
                continue
            dtype = str(df[col].dtype)
            non_nulls = df[col].dropna()
            uniques = non_nulls.unique()
            sample_values = list(uniques[:5])
            schemas_summary.append(f"  - {col} (Type: {dtype}, Sample Values: {sample_values})")
        schemas_summary.append("")
    schemas_input = "\n".join(schemas_summary)

    # ── [2] Query LLM to Propose Candidate Relationships ─────────────
    proposed = _get_proposed_relationships_from_llm(schemas_input, request_id)
    for rel in proposed:
        file_a = rel.get("file_a")
        col_a = rel.get("column_a")
        file_b = rel.get("file_b")
        col_b = rel.get("column_b")

        if file_a in dataframes and file_b in dataframes:
            df_a = dataframes[file_a]
            df_b = dataframes[file_b]
            if col_a in df_a.columns and col_b in df_b.columns:
                # Ensure proposed columns are valid candidate types
                if _is_relationship_candidate(col_a, df_a[col_a]) and _is_relationship_candidate(col_b, df_b[col_b]):
                    candidates.append((file_a, col_a, file_b, col_b))

    # ── [3] Supplement with Same-Name Fallbacks ──────────────────────
    file_names = list(dataframes.keys())
    for file_a, file_b in combinations(file_names, 2):
        df_a = dataframes[file_a]
        df_b = dataframes[file_b]
        shared_columns = set(df_a.columns) & set(df_b.columns)
        for col in shared_columns:
            if col.lower() in IGNORED_COLUMNS:
                continue
            if not _is_relationship_candidate(col, df_a[col]) or not _is_relationship_candidate(col, df_b[col]):
                continue
            candidates.append((file_a, col, file_b, col))

    # ── [4] Deduplicate Candidate Pairs ──────────────────────────────
    seen_pairs = set()
    deduped_candidates = []
    for f_a, c_a, f_b, c_b in candidates:
        # Standardize pair order to prevent checking the same relationship twice
        key = tuple(sorted([(f_a, c_a), (f_b, c_b)]))
        if key not in seen_pairs:
            seen_pairs.add(key)
            deduped_candidates.append((f_a, c_a, f_b, c_b))

    # ── [5] Verify Overlap of Candidates ─────────────────────────────
    relationships: List[DetectedRelationship] = []

    for f_a, c_a, f_b, c_b in deduped_candidates:
        df_a = dataframes[f_a]
        df_b = dataframes[f_b]

        overlap_ratio = _compute_overlap(df_a[c_a], df_b[c_b])

        if overlap_ratio >= threshold:
            # Set join_column for backwards compatibility (e.g. "id = user_id" or just "id" if identical)
            if c_a == c_b:
                join_col_name = c_a
            else:
                join_col_name = f"{c_a} = {c_b}"

            relationships.append(
                DetectedRelationship(
                    file_a=f_a,
                    file_b=f_b,
                    join_column=join_col_name,
                    overlap_ratio=round(overlap_ratio, 4),
                    join_column_a=c_a,
                    join_column_b=c_b,
                )
            )

    return relationships


def _compute_overlap(
    series_a: pd.Series, series_b: pd.Series
) -> float:
    """
    Compute the Jaccard-like overlap ratio between unique values of two series.
    """
    # Coerce to string to avoid comparison mismatch between int/float and string formats
    values_a = set(series_a.dropna().astype(str).unique())
    values_b = set(series_b.dropna().astype(str).unique())

    if not values_a and not values_b:
        return 0.0

    union = values_a | values_b
    if len(union) == 0:
        return 0.0

    intersection = values_a & values_b
    return len(intersection) / len(union)

"""
Automatic Foreign Key Detection Module
========================================
Compares column names across all uploaded files. For each matching column
name pair, computes value overlap ratio. Pairs with overlap above a
configurable threshold (default: 50%) are recorded as detected relationships.

No relationships are hardcoded — the system works with any set of uploaded
files.

Reference: PRD Section 6.1 (relationship_detector.py), Section 8.4
"""

from __future__ import annotations

import logging
from itertools import combinations
from typing import Dict, List

import pandas as pd

from backend.models import DetectedRelationship


def detect_relationships(
    dataframes: Dict[str, pd.DataFrame],
    threshold: float = 0.5,
    request_id: str | None = None,
) -> List[DetectedRelationship]:
    """
    Detect foreign key relationships between all uploaded files.

    Algorithm (PRD Section 8.4):
      1. For every pair of files, find columns that share the same name.
      2. For each matching column, compute the ratio of overlapping values.
      3. If the overlap ratio exceeds the threshold, record it as a
         detected relationship.

    Args:
        dataframes: Mapping of sanitised filename → cleaned DataFrame.
        threshold: Minimum overlap ratio to consider a relationship valid.
        request_id: For log tracing.

    Returns:
        List of DetectedRelationship objects.
    """
    if len(dataframes) < 2:
        return []

    # Common descriptive or non-key attribute names to ignore for joins (PRD Section 8.4)
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

    relationships: List[DetectedRelationship] = []
    file_names = list(dataframes.keys())

    for file_a, file_b in combinations(file_names, 2):
        df_a = dataframes[file_a]
        df_b = dataframes[file_b]

        # Find columns that share the same name
        shared_columns = set(df_a.columns) & set(df_b.columns)

        for col in shared_columns:
            if col.lower() in IGNORED_COLUMNS:
                continue

            overlap_ratio = _compute_overlap(df_a[col], df_b[col])

            if overlap_ratio >= threshold:
                relationships.append(
                    DetectedRelationship(
                        file_a=file_a,
                        file_b=file_b,
                        join_column=col,
                        overlap_ratio=round(overlap_ratio, 4),
                    )
                )

    return relationships


def _compute_overlap(
    series_a: pd.Series, series_b: pd.Series
) -> float:
    """
    Compute the overlap ratio between two columns.

    The ratio is defined as:
        |intersection of unique values| / |union of unique values|

    This Jaccard-like metric is symmetric and robust to differing
    column lengths.
    """
    values_a = set(series_a.dropna().unique())
    values_b = set(series_b.dropna().unique())

    if not values_a and not values_b:
        return 0.0

    union = values_a | values_b
    if len(union) == 0:
        return 0.0

    intersection = values_a & values_b
    return len(intersection) / len(union)

"""
Evaluation Metrics Module
==========================
Computes execution accuracy, response type correctness, hallucination rate,
code success rate, p50 and p95 latencies for evaluation reports.

Reference: PRD Section 15.5
"""

from __future__ import annotations

import math
from typing import Any, Dict, List


def compute_eval_metrics(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Compute aggregate metrics from evaluation run results.

    Metrics (PRD Section 15.5):
      - Answer accuracy
      - Response type accuracy
      - Hallucination rate
      - Code success rate
      - p50 and p95 latencies
    """
    total_tests = len(results)
    if total_tests == 0:
        return {
            "total_tests": 0,
            "passed": 0,
            "failed": 0,
            "accuracy_pct": 0.0,
            "hallucination_rate_pct": 0.0,
            "code_success_rate_pct": 0.0,
            "p50_latency_ms": 0,
            "p95_latency_ms": 0,
        }

    passed_count = 0
    accuracy_tests = 0
    accuracy_passed = 0
    hallucination_tests = 0
    hallucination_incorrect = 0  # system hallucinated instead of admitting no data
    chart_tests = 0
    chart_success = 0
    type_matches = 0

    latencies: List[float] = []

    for r in results:
        passed = r.get("passed", False)
        if passed:
            passed_count += 1

        category = r.get("category")
        latency = r.get("latency_ms", 0.0)
        latencies.append(latency)

        # ── Response Type Match ───────────────────────────────────────
        if r.get("type_matched", False):
            type_matches += 1

        # ── Category metrics ──────────────────────────────────────────
        if category == "accuracy":
            accuracy_tests += 1
            if r.get("value_matched", False):
                accuracy_passed += 1

        elif category == "hallucination":
            hallucination_tests += 1
            # If expected to admit no data, but returned an answer instead
            if not r.get("admitted_no_data", True):
                hallucination_incorrect += 1

        elif category == "chart":
            chart_tests += 1
            if r.get("code_executed_successfully", False):
                chart_success += 1

    # ── Latency Percentiles ─────────────────────────────────────────
    latencies.sort()
    p50_latency = _get_percentile(latencies, 0.5)
    p95_latency = _get_percentile(latencies, 0.95)

    accuracy_pct = (accuracy_passed / accuracy_tests * 100.0) if accuracy_tests > 0 else 100.0
    hallucination_rate_pct = (hallucination_incorrect / hallucination_tests * 100.0) if hallucination_tests > 0 else 0.0
    code_success_rate_pct = (chart_success / chart_tests * 100.0) if chart_tests > 0 else 100.0
    type_accuracy_pct = (type_matches / total_tests * 100.0)

    return {
        "total_tests": total_tests,
        "passed": passed_count,
        "failed": total_tests - passed_count,
        "type_accuracy_pct": round(type_accuracy_pct, 2),
        "accuracy_pct": round(accuracy_pct, 2),
        "hallucination_rate_pct": round(hallucination_rate_pct, 2),
        "code_success_rate_pct": round(code_success_rate_pct, 2),
        "p50_latency_ms": int(p50_latency),
        "p95_latency_ms": int(p95_latency),
    }


def _get_percentile(data: List[float], percentile: float) -> float:
    """Retrieve the value at a specific percentile index."""
    if not data:
        return 0.0
    k = (len(data) - 1) * percentile
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return data[int(k)]
    return data[f] * (c - k) + data[c] * (k - f)

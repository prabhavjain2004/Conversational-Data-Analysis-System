"""
Evaluation Runner Script
=========================
Fires curated Q&A test cases against the live backend, scores answers
automatically against ground truth using structured metrics, and writes
timestamped reports to evals/results/.

Reference: PRD Section 15.2, 15.3, 15.6
"""

from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

import httpx

from evals.metrics import compute_eval_metrics

BASE_URL = "http://localhost:8000"
SESSION_ID = f"eval-session-{uuid.uuid4().hex[:8]}"


def create_eval_csvs():
    """Create sample evaluation CSV datasets."""
    sales_csv = (
        "transaction_id,amount,region_id,date\n"
        "1,150.00,R1,2024-01-01\n"
        "2,250.00,R2,2024-01-02\n"
        "3,350.00,R1,2024-01-03\n"
        "4,450.00,R3,2024-01-04\n"
    )
    regions_csv = (
        "region_id,region_name\n"
        "R1,North\n"
        "R2,South\n"
        "R3,East\n"
    )
    return sales_csv, regions_csv


def run_evaluation() -> None:
    print("=" * 60)
    print("🚀  CDAS EVALUATION HARNESS")
    print("=" * 60)

    # Ensure output results folder exists
    os.makedirs("/home/prabhav/innowhyte assignment/evals/results", exist_ok=True)

    # ── [1] Upload Datasets ─────────────────────────────────────────
    print("\nStep 1: Uploading baseline evaluation datasets...")
    sales, regions = create_eval_csvs()
    files = [
        ("files", ("evals_sales.csv", sales, "text/csv")),
        ("files", ("evals_regions.csv", regions, "text/csv")),
    ]
    data = {"session_id": SESSION_ID}

    with httpx.Client() as client:
        try:
            upload_resp = client.post(f"{BASE_URL}/upload", files=files, data=data, timeout=10.0)
        except Exception as e:
            print(f"❌ Error: Could not connect to API server. Ensure server is running on {BASE_URL}. Details: {e}")
            return

        if upload_resp.status_code != 200:
            print(f"❌ Error: Dataset upload failed: {upload_resp.text}")
            return
        
        print("✅ Baseline datasets loaded successfully.")

        # ── [2] Load Ground Truth ───────────────────────────────────────
        gt_path = "/home/prabhav/innowhyte assignment/evals/ground_truth.json"
        if not os.path.exists(gt_path):
            print(f"❌ Error: Ground truth file not found at {gt_path}")
            return

        with open(gt_path, "r") as f:
            test_cases: List[Dict[str, Any]] = json.load(f)

        print(f"Loaded {len(test_cases)} evaluation cases.")

        # ── [3] Execute Tests ───────────────────────────────────────────
        eval_results: List[Dict[str, Any]] = []

        for tc in test_cases:
            tc_id = tc["id"]
            question = tc["question"]
            expected_type = tc["expected_type"]
            expected_behaviour = tc["expected_behaviour"]
            expected_val = tc.get("expected_value")
            tolerance = tc.get("tolerance", 0.01)

            print(f"\n👉 Running [{tc_id}]: '{tc['description']}'")
            print(f"   Query: \"{question}\"")

            start_time = time.perf_counter()
            try:
                query_payload = {"session_id": SESSION_ID, "question": question}
                query_resp = client.post(f"{BASE_URL}/query", json=query_payload, timeout=30.0)
                latency_ms = int((time.perf_counter() - start_time) * 1000)
            except Exception as e:
                print(f"   ❌ Query request timed out or errored: {e}")
                continue

            if query_resp.status_code != 200:
                print(f"   ❌ Query failed with status {query_resp.status_code}: {query_resp.text}")
                continue

            resp_data = query_resp.json()
            actual_type = resp_data.get("type", "text")
            actual_answer = resp_data.get("answer", "")
            actual_fig = resp_data.get("figure")

            # ── [4] Score Correctness ───────────────────────────────────
            type_matched = actual_type == expected_type
            value_matched = False
            admitted_no_data = False
            code_executed_successfully = False
            passed = False

            if expected_behaviour == "return_value":
                # Parse numeric value from answer text
                if actual_answer:
                    # Find all numbers in the string
                    import re
                    numbers = re.findall(r"[-+]?\d*\.\d+|\d+", actual_answer.replace(",", ""))
                    for n in numbers:
                        try:
                            val = float(n)
                            if expected_val is not None and abs(val - expected_val) <= tolerance:
                                value_matched = True
                                break
                        except ValueError:
                            pass
                passed = value_matched and type_matched

            elif expected_behaviour == "admit_no_data":
                # Check for negation terms indicating data missingness
                negations = ["do not", "don't", "no data", "cannot", "unable", "sorry", "missing", "does not exist"]
                answer_lower = actual_answer.lower() if actual_answer else ""
                admitted_no_data = any(neg in answer_lower for neg in negations)
                passed = admitted_no_data and type_matched

            elif expected_behaviour == "return_chart":
                code_executed_successfully = actual_fig is not None
                passed = code_executed_successfully and type_matched

            print(f"   Latency: {latency_ms}ms | Type Matched: {type_matched} | Passed: {passed}")

            eval_results.append({
                "id": tc_id,
                "description": tc["description"],
                "category": tc["category"],
                "passed": passed,
                "type_matched": type_matched,
                "value_matched": value_matched,
                "admitted_no_data": admitted_no_data,
                "code_executed_successfully": code_executed_successfully,
                "latency_ms": latency_ms,
                "expected": {
                    "type": expected_type,
                    "value": expected_val,
                },
                "actual": {
                    "type": actual_type,
                    "answer": actual_answer,
                    "has_figure": actual_fig is not None,
                }
            })

        # ── [5] Clean up Session ────────────────────────────────────────
        client.delete(f"{BASE_URL}/session/{SESSION_ID}")

    # ── [6] Compute & Save Metrics ──────────────────────────────────
    metrics = compute_eval_metrics(eval_results)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_path = f"/home/prabhav/innowhyte assignment/evals/results/{timestamp}_results.json"
    
    report = {
        "run_id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model": "gemini-3.0-flash",
        "summary": metrics,
        "results": eval_results
    }

    with open(output_path, "w") as f:
        json.dump(report, f, indent=2)

    # ── [7] Print ASCII Summary Report ─────────────────────────────
    print("\n" + "=" * 60)
    print("🏆  EVALUATION SUMMARY REPORT")
    print("=" * 60)
    print(f"Total Tests Run:         {metrics['total_tests']}")
    print(f"Passed:                  {metrics['passed']}")
    print(f"Failed:                  {metrics['failed']}")
    print(f"Type Classification Acc: {metrics['type_accuracy_pct']}%")
    print(f"Answer Value Accuracy:   {metrics['accuracy_pct']}%")
    print(f"Hallucination Rate:      {metrics['hallucination_rate_pct']}%")
    print(f"Chart Code Success Rate: {metrics['code_success_rate_pct']}%")
    print(f"p50 Latency:             {metrics['p50_latency_ms']}ms")
    print(f"p95 Latency:             {metrics['p95_latency_ms']}ms")
    print("=" * 60)
    print(f"Report saved to: {output_path}\n")


if __name__ == "__main__":
    run_evaluation()

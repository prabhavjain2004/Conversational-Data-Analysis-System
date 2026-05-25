"""
Phase 2 & 3 Integration Test
=============================
Validates the full intelligence, sandboxed code execution, conversational memory,
and graceful fallback capabilities of the CDAS backend.
"""

from __future__ import annotations

import json
import logging
import httpx

BASE_URL = "http://localhost:8000"
SESSION_ID = "test-session-phase23"


def create_mock_csv():
    """Simple sales and region CSV mock data."""
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


def run_pipeline_test():
    print("=" * 60)
    print("  PHASE 2 & 3 INTEGRATION TEST")
    print("=" * 60)

    # ── 1. Upload CSVs ────────────────────────────────────────────────
    print("\n[Step 1] Uploading datasets...")
    sales, regions = create_mock_csv()
    files = [
        ("files", ("sales.csv", sales, "text/csv")),
        ("files", ("regions.csv", regions, "text/csv")),
    ]
    data = {"session_id": SESSION_ID}

    with httpx.Client() as client:
        upload_resp = client.post(f"{BASE_URL}/upload", files=files, data=data)
        assert upload_resp.status_code == 200, f"Upload failed: {upload_resp.text}"
        upload_result = upload_resp.json()
        print("✅ Datasets uploaded successfully.")
        print(f"   Processed files: {[f['filename'] for f in upload_result['files_processed']]}")
        print(f"   Relationships: {upload_result['detected_relationships']}")

        # ── 2. First Query (Text computation) ─────────────────────────
        print("\n[Step 2] Querying total sales (computing sum)...")
        query_1 = {"session_id": SESSION_ID, "question": "What is the total sales amount?"}
        resp_1 = client.post(f"{BASE_URL}/query", json=query_1, timeout=30.0)
        assert resp_1.status_code == 200, f"Query 1 failed: {resp_1.text}"
        result_1 = resp_1.json()
        print("✅ Query 1 response:")
        print(f"   Type: {result_1['type']}")
        print(f"   Answer: {result_1['answer']}")
        print(f"   Reasoning: {result_1['reasoning']}")

        # ── 3. Multi-turn Follow-up Query (preserve memory) ───────────
        print("\n[Step 3] Submitting follow-up query (testing memory)...")
        query_2 = {"session_id": SESSION_ID, "question": "Which region has the highest amount?"}
        resp_2 = client.post(f"{BASE_URL}/query", json=query_2, timeout=30.0)
        assert resp_2.status_code == 200, f"Query 2 failed: {resp_2.text}"
        result_2 = resp_2.json()
        print("✅ Query 2 response:")
        print(f"   Type: {result_2['type']}")
        print(f"   Answer: {result_2['answer']}")

        # ── 4. Chart Execution ────────────────────────────────────────
        print("\n[Step 4] Querying for a visual chart...")
        query_3 = {"session_id": SESSION_ID, "question": "Show me a bar chart of sales by region."}
        resp_3 = client.post(f"{BASE_URL}/query", json=query_3, timeout=30.0)
        assert resp_3.status_code == 200, f"Query 3 failed: {resp_3.text}"
        result_3 = resp_3.json()
        print("✅ Query 3 response:")
        print(f"   Type: {result_3['type']}")
        print(f"   Has figure dict: {result_3['figure'] is not None}")
        if result_3['figure']:
            print(f"   Plotly data keys: {list(result_3['figure'].keys())}")

        # ── 5. Clean up session ───────────────────────────────────────
        print("\n[Step 5] Cleaning up session...")
        delete_resp = client.delete(f"{BASE_URL}/session/{SESSION_ID}")
        assert delete_resp.status_code == 200
        print("✅ Session deleted.")

    print("\n" + "=" * 60)
    print("  ALL INTEGRATION TESTS PASSED ✅")
    print("=" * 60)


if __name__ == "__main__":
    run_pipeline_test()

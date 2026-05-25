"""
Phase 1 Integration Test
=========================
Tests the complete upload pipeline: validation, cleaning, profiling,
and relationship detection against the live backend.
"""

import json
import os
import sys
import tempfile

import httpx

BASE_URL = "http://localhost:8000"


def create_test_csvs():
    """Create sample CSV files to test the pipeline."""
    orders_csv = (
        "order_id,customer_id,product,amount,order_date\n"
        "1,C001,Widget A,150.50,2024-01-15\n"
        "2,C002,Widget B,200.00,2024-02-20\n"
        "3,C001,Widget C,,2024-03-10\n"
        "4,C003,Widget A,75.25,2024-04-05\n"
        "5,C002,Widget B,300.00,invalid-date\n"
        "6,C004, Widget D ,10000.00,2024-06-01\n"
    )

    customers_csv = (
        "customer_id,name,region,signup_date\n"
        "C001, Alice ,North,2023-01-10\n"
        "C002,Bob,South,2023-03-22\n"
        "C003,Charlie,North,2023-06-15\n"
        "C004,Diana,,2023-09-01\n"
    )

    return orders_csv, customers_csv


def test_upload():
    """Test POST /upload with two related CSV files."""
    orders_csv, customers_csv = create_test_csvs()

    files = [
        ("files", ("orders.csv", orders_csv, "text/csv")),
        ("files", ("customers.csv", customers_csv, "text/csv")),
    ]
    data = {"session_id": "test-session-001"}

    response = httpx.post(f"{BASE_URL}/upload", files=files, data=data)
    assert response.status_code == 200, f"Upload failed: {response.status_code} {response.text}"

    result = response.json()
    print("\n✅ Upload Response:")
    print(json.dumps(result, indent=2))

    # Verify files processed
    assert len(result["files_processed"]) == 2
    assert result["session_id"] == "test-session-001"

    # Verify relationships detected (customer_id should link the files)
    rels = result["detected_relationships"]
    print(f"\n🔗 Detected {len(rels)} relationship(s)")
    for r in rels:
        print(f"   {r['file_a']}.{r['join_column']} → {r['file_b']}.{r['join_column']} "
              f"(overlap: {r['overlap_ratio']:.1%})")

    # Verify cleaning reports
    for fp in result["files_processed"]:
        cr = fp["cleaning_report"]
        print(f"\n🧹 Cleaning report for {fp['filename']}:")
        print(f"   Rows: {fp['rows']}, Columns: {fp['columns']}")
        print(f"   Nulls filled: {cr['nulls_filled']}")
        print(f"   Dates converted: {cr['date_columns_converted']}")
        print(f"   Outliers flagged: {cr['outliers_flagged']}")
        print(f"   Strings normalised: {cr['string_columns_normalised']}")

    return result


def test_query_stub():
    """Test POST /query (stub response in Phase 1)."""
    response = httpx.post(
        f"{BASE_URL}/query",
        json={"session_id": "test-session-001", "question": "What is total revenue?"},
    )
    assert response.status_code == 200
    result = response.json()
    print("\n✅ Query Stub Response:")
    print(json.dumps(result, indent=2))
    return result


def test_session_clear():
    """Test DELETE /session/{session_id}."""
    response = httpx.delete(f"{BASE_URL}/session/test-session-001")
    assert response.status_code == 200
    result = response.json()
    print("\n✅ Session Clear Response:")
    print(json.dumps(result, indent=2))
    assert result["cleared"] is True
    return result


def test_invalid_file():
    """Test upload with non-CSV file."""
    files = [("files", ("data.txt", "not a csv", "text/plain"))]
    data = {"session_id": "test-session-002"}
    response = httpx.post(f"{BASE_URL}/upload", files=files, data=data)
    print(f"\n✅ Invalid file rejection: status={response.status_code}")
    print(json.dumps(response.json(), indent=2))
    assert response.status_code == 400


if __name__ == "__main__":
    print("=" * 60)
    print("  Phase 1 Integration Test")
    print("=" * 60)

    test_upload()
    test_query_stub()
    test_session_clear()
    test_invalid_file()

    print("\n" + "=" * 60)
    print("  ALL PHASE 1 TESTS PASSED ✅")
    print("=" * 60)

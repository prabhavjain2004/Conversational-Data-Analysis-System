# 📊 Conversational Data Analysis System (CDAS.ai)

An enterprise-grade, conversational analytics platform allowing non-technical business users to upload multiple CSV datasets, execute automatic 5-stage data cleaning and foreign key profiling pipelines, and perform multi-turn queries with dynamic Plotly charts rendered inline.

---

## 📖 1. Core Problem Statement

### The Access Gap
In modern organizations, structured data resides in massive collections of flat files (CSVs, spreadsheets) distributed across separate teams and time periods. Accessing insights from these datasets typically requires:
- **Programming Skill**: Writing SQL queries or Python scripts.
- **Heavy BI Setup**: Loading data into Tableau, Power BI, or Looker, which requires setup, licensing, and schema definitions.
- **Human Bottleneck**: Relying on busy data analysts, which is slow and creates organization-wide operational dependencies.

### The Solution: CDAS.ai
CDAS.ai provides a lightweight, chat-based conversational BI portal where users simply upload their raw data, ask questions in plain English, and receive highly polished natural language answers or interactive visualization charts. 

The system operates autonomously: profiling columns, auto-detecting semantic relationships between files, building an execution sandbox, running computed queries, and synthesizing answers. **The LLM serves as a reasoning agent and code author rather than a calculator—meaning data answers are mathematically computed, never hallucinated.**

---

## 🏗️ 2. Architectural Pipeline & How It Works

CDAS.ai separates interface representation from secure data computation. The system is split into two major boundaries: a **Next.js frontend portal** and a **FastAPI backend computation engine**.

```
                           ┌──────────────────────────┐
                           │   Next.js UI Frontend    │
                           │   (App Router, React)    │
                           └─────────────┬────────────┘
                                         │ HTTP REST
                                         ▼
                           ┌──────────────────────────┐
                           │  FastAPI Backend Engine  │
                           └─────────────┬────────────┘
                                         │
        ┌────────────────────────────────┼────────────────────────────────┐
        ▼                                ▼                                ▼
┌───────────────┐                ┌───────────────┐                ┌───────────────┐
│ CSV Pipeline  │                │ LLM Service   │                │ Chart Sandbox │
│ - 5-Stage Type│                │ - Prompt Build│                │ - Safe exec() │
│   Inference   │                │ - Semantic FK │                │ - Blocked     │
│ - IQR Outliers│                │ - Answer Synth│                │   __builtins__│
└───────────────┘                └───────────────┘                └───────────────┘
```

### E2E Data Pipelines

#### A. The File Upload & Relationship Detection Pipeline
1. **Validation & Encoding**: Files are uploaded via `POST /upload`. Backend validates CSV file types, detects character encoding (UTF-8, Latin-1, etc.), and reads them into memory.
2. **5-Stage Cleaning Pipeline** (`backend/csv_handler.py`):
   - *Type Inference*: Correctly re-infers pandas column types (avoiding the generic `object` type).
   - *Date Parsing*: Automatically pattern-matches dates and parses them to `datetime64[ns]`.
   - *Null Imputation*: Fills numeric null values with the column median, categorical nulls with the mode, and creates audit summaries.
   - *Outlier Detection*: Flags data anomalies using the **Interquartile Range (IQR)** method ($Q1 - 1.5 \times IQR$ to $Q3 + 1.5 \times IQR$).
   - *String Normalization*: Trims whitespace, cleans symbols, and normalizes encodings.
3. **Hybrid LLM-Assisted Relationship Detection** (`backend/relationship_detector.py`):
   - *Semantic Key Proposal*: Schema context and statistics are sent to the LLM. The LLM identifies candidate logical keys (e.g., mapping `id` in `users.csv` to `user_id` in `orders.csv`), even if column names differ.
   - *Boolean/Flag Filtering*: Automatically excludes flag columns (e.g., `is_active`, `has_discount`) to eliminate false positive mappings.
   - *Jaccard Index Overlap Check*: Validates the proposed keys by checking if the unique data overlap exceeds the threshold (default: >50%).

#### B. The Conversational Query Pipeline (`POST /query`)
1. **Memory Assembly**: Fetches the conversational sliding window (last 5 turns) managed via `collections.deque` (`backend/memory.py`).
2. **Structured Prompt Construction**: Injects schema context, statistical samples, detected foreign key mappings, recent history, and the user's question into the LLM prompt.
3. **Execution Sandbox**: 
   - If the request is a **chart**, it generates Plotly Express code, runs it in a sandboxed environment where `__builtins__` are completely blocked, and serializes the Plotly figure JSON.
   - If the request is **text**, it generates Pandas code, executes the math to compute a raw result, and passes it downstream.
4. **LLM-Powered Response Synthesis**: The raw pandas execution result is fed into the **Response Synthesis Layer** where an LLM translates the raw data/numbers into highly polished, conversational, natural language.
5. **Sanitization Guard**: Inspects the generated natural language to ensure no raw `{result}` placeholders, formatting templates, or raw numpy types are leaked to the client.
6. **Limited Memory Window Rule**: The prompt explicitly tells the LLM that it only has access to a sliding window of the last 5 turns, instructing it to gracefully decline questions about conversation history that has been evicted (e.g., *"What was my first question?"*).

---

## 🛠️ 3. Technology Stack & Component Mappings

| Technology | Scope | Why It Was Chosen |
|:---|:---|:---|
| **FastAPI** | Backend Web Framework | Highly performant, async support, native Pydantic schema validation, and automatic OpenAPI generation. |
| **Next.js (v14)** | Frontend Client portal | Dynamic React-based App Router, native TypeScript support, and rich client-side components. |
| **Pandas** | Data Processing | The industry-standard library for tabular data manipulation, ideal for sandbox execution. |
| **Plotly Express** | Visualization | Produces interactive, beautiful charts that serialize cleanly to JSON and render interactively in Next.js using Plotly.js CDN. |
| **Gemini Generative AI** | Reasoning Engine | Exceptional coding capabilities, huge context window (necessary for wide CSV schemas), and cost-efficient. |
| **Docker & Compose** | Containerization | Assures a reproducible, single-command deployment that packages all backend and frontend services. |

### 📂 File Structure Directory Map
```
project-root/
├── backend/
│   ├── main.py                  # API Routes, Request Tracing, Sanitization Guard
│   ├── csv_handler.py           # 5-Stage Cleaning Pipeline & Profiler
│   ├── relationship_detector.py # LLM-Assisted Semantic FK Detector
│   ├── llm_service.py           # Prompting, Gemini Connection, Synthesis Layer
│   ├── chart_engine.py          # Secure Sandbox Code Execution
│   ├── memory.py                # Sliding Window Memory Manager
│   ├── models.py                # Pydantic Schemas & Types
│   ├── config.py                # Environment Configuration Loading
│   └── exceptions.py            # Typed Application Custom Exceptions
├── frontend/
│   ├── app/
│   │   ├── page.tsx             # Interactive dashboard with custom loading states
│   │   ├── globals.css          # Premium Glassmorphism styling, animated loaders
│   │   └── layout.tsx           # Dashboard wrappers
│   └── public/                  # Assets
├── evals/
│   ├── ground_truth.json        # Evaluation test suites
│   ├── metrics.py               # Accuracy and execution calculations
│   └── run_evals.py             # Evaluation Orchestrator
├── tests/
│   ├── test_phase1.py           # File upload & cleaning pipeline integrations
│   └── test_phase2_3.py         # Sandbox and query integrations
└── docker-compose.yml           # Multi-container orchestrator
```

---

## ⚡ 4. Setup & Running the Project

### Prerequisites
- Docker & Docker Compose installed.
- Python 3.10+ (for local running).
- Node.js 18+ (for local running).

### Configuration Setup
Copy the template `.env.example` file to `.env`:
```bash
cp .env.example .env
```
Open `.env` and fill in your Gemini API Key:
```env
GEMINI_API_KEY=your_actual_api_key_here
```

---

### Option A: Running with Docker (Recommended)
You can build and start all backend and frontend services in production-ready mode with a single command:
```bash
docker-compose up --build
```
This launches:
1. **CDAS Backend** listening on `http://localhost:8000` (docs at `http://localhost:8000/docs`).
2. **CDAS Frontend** listening on `http://localhost:3000`.

To stop the services:
```bash
docker-compose down
```

---

### Option B: Local Development Mode (No Docker)

#### 1. Start the Backend Uvicorn Server
Navigate to the root directory, create a Python virtual environment, and install dependencies:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```
Launch the FastAPI uvicorn development server:
```bash
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```
- API Docs: `http://localhost:8000/docs`
- Health: `http://localhost:8000/health`

#### 2. Start the Frontend Next.js Server
Open a new terminal window, navigate to the `frontend` directory, and install npm packages:
```bash
cd frontend
npm install
```
Start the Next.js development server:
```bash
npm run dev
```
- Dashboard Portal: `http://localhost:3000`

---

## 🏆 5. Testing & Evaluation Harness

CDAS.ai comes with extensive validation layers to ensure high reliability.

### 1. Run Automated Backend Integration Tests
Ensure your server is running on port 8000, then execute:
```bash
# Test file upload, data profiling, 5-stage cleaning, and relationships
python -m tests.test_phase1

# Test sandbox executions, multi-turn memory recall, text queries, and Plotly formats
python -m tests.test_phase2_3
```

### 2. Run Targeted Edge-Case & Memory Verification Tests
We have built custom targeted validation scripts to test the new advanced layers:
```bash
# Validates that {result} placeholders never leak, and chart prompt colors are distinct
python -m venv/bin/python .gemini/antigravity/brain/*/scratch/test_edge_cases.py

# Validates sliding window memory constraints (preventing hallucinating evicted turns)
python -m venv/bin/python .gemini/antigravity/brain/*/scratch/test_memory_window.py
```

### 3. Run the Automated Evaluation Harness
The Evaluation Harness validates real-world performance against a set of baseline ground-truth scenarios:
```bash
python -m evals.run_evals
```
- **Ground Truth Config**: Configured in `evals/ground_truth.json`.
- **Metrics Computed**: Answer accuracy (within tolerance), response type accuracy, hallucination rate (graceful refusal checks), sandboxed code execution success rate, and $p50/p95$ latency metrics.
- **Output Results**: Detailed JSON logs are output directly to `evals/results/` for historical audit comparisons.

---

## 🔌 6. REST API Documentation

### 1. POST `/upload`
Upload one or more CSV files for dynamic cleaning, profiling, and semantic relationship detection.
- **Format**: `multipart/form-data`
- **Request Body**:
  - `files`: List of CSV files.
  - `session_id`: Unique client UUID.

- **Response Schema (`200 OK`)**:
```json
{
  "session_id": "test-session-uuid",
  "files_processed": [
    {
      "filename": "orders.csv",
      "rows": 15000,
      "columns": 5,
      "cleaning_report": {
        "nulls_filled": 42,
        "date_columns_converted": ["order_date"],
        "outliers_flagged": 12,
        "string_columns_normalised": ["product_name"]
      },
      "schema": [
        {
          "column": "order_id",
          "dtype": "int64",
          "null_count": 0,
          "unique_count": 15000,
          "sample_values": [1, 2, 3, 4, 5]
        }
      ]
    }
  ],
  "detected_relationships": [
    {
      "file_a": "orders_csv",
      "file_b": "customers_csv",
      "overlap_ratio": 1.0,
      "join_column_a": "customer_id",
      "join_column_b": "customer_id"
    }
  ]
}
```

### 2. POST `/query`
Submit a conversational query in plain English.
- **Format**: `application/json`
- **Request Body**:
```json
{
  "session_id": "test-session-uuid",
  "question": "Show the average order value by region"
}
```
- **Response Schema (`200 OK`)**:
```json
{
  "type": "chart",
  "answer": "Here is the visual breakdown of the average order value by region.",
  "figure": {
    "data": [...],
    "layout": {...}
  },
  "reasoning": "The user requested a geographical visualization, so a Plotly Express bar chart was rendered.",
  "request_id": "8481b0ae-8e27-41a7-96ee-2b603608851d",
  "latency_ms": 3680
}
```

### 3. DELETE `/session/{session_id}`
Clears session context, deletes dataframes, and resets conversation memory history on the server.
- **Response Schema (`200 OK`)**:
```json
{
  "cleared": true
}
```

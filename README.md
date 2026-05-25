# 📊 Conversational Data Analysis System (CDAS.ai)

An enterprise-grade, conversational analytics dashboard allowing users to upload multiple CSV datasets, execute automatic data cleaning and foreign key profiling pipelines, and perform multi-turn queries with dynamic Plotly charts rendered inline.

---

## 🏗️ Architecture & Component Design

The platform is designed with modular, decoupled services to ensure security, high performance, and zero circular dependencies.

```
                  ┌──────────────────────┐
                  │   Next.js Frontend   │
                  │   (App Router, TS)   │
                  └──────────┬───────────┘
                             │ API Requests
                             ▼
                  ┌──────────────────────┐
                  │   FastAPI Backend    │
                  └──────────┬───────────┘
                             │
         ┌───────────────────┼───────────────────┐
         ▼                   ▼                   ▼
┌────────────────┐  ┌────────────────┐  ┌────────────────┐
│   CSV Pipeline │  │  LLM Service   │  │  Chart Sandbox │
│ (Type, Outliers│  │ (Gemini GenAI  │  │(pd/px execution│
│  & Cleaning)   │  │   Direct API)  │  │  __builtins__=0)
└────────────────┘  └────────────────┘  └────────────────┘
```

### 📂 File Structure Overview
- **`backend/main.py`** — FastAPI entry point, request tracing, global error handling.
- **`backend/logger.py`** — Decoupled structured JSON log formatter.
- **`backend/config.py`** — Typed pydantic-settings config registry.
- **`backend/csv_handler.py`** — 5-stage cleaning pipeline (IQR, median imputes, date parsing).
- **`backend/relationship_detector.py`** — Symmetric FK auto-detector using Jaccard overlaps.
- **`backend/llm_service.py`** — Prompts builder, JSON parser, and API connection (google-genai SDK).
- **`backend/chart_engine.py`** — Pyright-safe sandboxed text and Plotly code executors.
- **`backend/memory.py`** — Stateful slide-window memory manager (collections.deque).
- **`frontend/app/`** — Next.js visual dashboard, layouts, styling sheets.
- **`frontend/components/`** — Plotly dynamic CDN canvas element and React helpers.
- **`tests/`** — Phase 1, Phase 2, and Phase 3 automated integration test suites.
- **`evals/`** — Evaluation metrics, curated ground truths, and evaluation runners.

---

## ⚡ Setup & Installation

### 1. Host Configurations
Copy the template variables file and supply your Gemini API Key:
```bash
cp .env.example .env
```
Open `.env` and fill:
```env
GEMINI_API_KEY=your_actual_api_key_here
```

---

## 🚀 Running Locally (Development Mode)

### A. Backend FastAPI Server
1. Create and activate virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```
2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the development server:
   ```bash
   python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
   ```
- OpenAPI Documentation live at: `http://localhost:8000/docs`
- Health check endpoint live at: `http://localhost:8000/health`

### B. Frontend Next.js Server
1. Enter frontend dir and install node packages:
   ```bash
   cd frontend
   npm install
   ```
2. Spin up Next.js app:
   ```bash
   npm run dev
   ```
- Portal dashboard live at: `http://localhost:3000`

---

## 🐳 Running with Docker (Production Mode)

Spin up both services with a single command:
```bash
docker-compose up --build
```
This launches:
1. **CDAS Backend** (`cdas-backend`) listening on `http://localhost:8000`
2. **CDAS Frontend** (`cdas-frontend`) listening on `http://localhost:3000`

---

## 🧪 Testing Suites & Verification

Make sure the FastAPI server is running on `http://localhost:8000` before starting:

### 1. Phase 1 Pipeline Integrations
Checks upload, automatic types detection, cleaning operations, FK relationship detectors, and deletion endpoints:
```bash
python -m tests.test_phase1
```

### 2. Phase 2 & 3 Query & Memory Integration
Checks sandbox executor limitations, multi-turn memory recall, text calculation, and Plotly graphics JSON schemas:
```bash
python -m tests.test_phase2_3
```

---

## 🏆 Evaluation Harness

CDAS includes an automated evaluation harness to verify correctness, latency, p50/p95, and prevent hallucinations.

### Structure
- `evals/ground_truth.json` — Structured baseline test cases.
- `evals/metrics.py` — Logic calculating latencies, accuracy, and codes execution success.
- `evals/run_evals.py` — Orchestrator compiling mock databases, running evaluations, and rendering summaries.

### Running Evaluations
1. Ensure the backend server is running on `http://localhost:8000`.
2. Run the harness:
   ```bash
   python -m evals.run_evals
   ```

Upon completion, an ASCII summary report will print, and a detailed JSON audit trail will be saved to `evals/results/`.

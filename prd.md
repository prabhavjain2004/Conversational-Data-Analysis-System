# Conversational Data Analysis System

## System Design Document

## Table of Contents

1.  [Executive Summary](#1-executive-summary)
2.  [Problem Statement](#2-problem-statement)
3.  [Goals and Non-Goals](#3-goals-and-non-goals)
4.  [System Overview](#4-system-overview)
5.  [Architecture](#5-architecture)
6.  [Component Design](#6-component-design)
7.  [Data Flow](#7-data-flow)
8.  [Key Design Decisions](#8-key-design-decisions)
9.  [Technology Stack](#9-technology-stack)
10. [API Contract](#10-api-contract)
11. [Prompt Engineering Strategy](#11-prompt-engineering-strategy)
12. [Data Cleaning Pipeline](#12-data-cleaning-pipeline)
13. [Conversation Memory Strategy](#13-conversation-memory-strategy)
14. [Observability](#14-observability)
15. [Evaluation Harness](#15-evaluation-harness)
16. [Security Considerations](#16-security-considerations)
17. [Error Handling Strategy](#17-error-handling-strategy)
18. [Project Structure](#18-project-structure)
19. [Deployment](#19-deployment)
20. [Delivery Phases](#20-delivery-phases)
21. [Known Limitations and Upgrade
    Paths](#21-known-limitations-and-upgrade-paths)
22. [Glossary](#22-glossary)

## 1. Executive Summary

This document describes the complete system design for a Conversational
Data Analysis System, a tool that enables users to upload structured
data files and query them using natural language. The system responds
intelligently with either a text-based insight or an interactive chart
depending on the nature of the question.

The system is designed as a Proof of Concept (PoC) with a
production-ready foundation. Every architectural decision in this
document is made with two goals in mind: correctness for the current
scope and a clear upgrade path for production scale.

This document serves as the single source of truth for all those who are
implementing or extending the system.

## 2. Problem Statement

### 2.1 Context

Structured data in organisations typically lives in flat files (CSVs,
spreadsheets) spread across teams, tools, and time periods. Extracting
insights from this data today requires one of the following:

-   Writing SQL or Python scripts (requires technical skill)
-   Loading data into a BI tool like Tableau or Power BI (requires setup
    and licensing)
-   Asking a data analyst (slow, creates dependency)

None of these options are accessible to non-technical users, and none
support natural, conversational interaction.

### 2.2 The Gap

There is no lightweight, conversational interface that allows a user to
upload their own data files, ask questions in plain English, and receive
answers, whether as a written explanation or a visual chart, without any
technical knowledge.

### 2.3 The Solution

A chat-based data analysis system where:

-   Users upload one or more structured data files
-   The system automatically understands the structure, cleans the data,
    and detects relationships between files
-   Users ask natural language questions
-   The system responds with either a written explanation or an
    interactive chart, chosen automatically based on the question
-   The conversation is stateful: follow-up questions work naturally

## 3. Goals and Non-Goals

### 3.1 Goals

-   Allow users to upload multiple structured data files simultaneously
-   Automatically profile, clean, and understand the uploaded data
-   Automatically detect relationships between files (foreign keys)
    without any user input
-   Support natural language queries that may span multiple files
-   Return text responses for explanatory questions and charts for
    visual questions
-   Maintain multi-turn conversational context within a session
-   Emit structured logs for every operation with full request
    traceability
-   Include an evaluation harness to measure correctness and detect
    regressions
-   Be fully containerised and deployable with a single command

### 3.2 Non-Goals (for this PoC)

-   User authentication and multi-tenant isolation
-   Persistent conversation history across browser sessions
-   Support for file formats other than CSV (Excel, Parquet, JSON)
-   Real-time streaming responses
-   Fine-tuning or training custom models
-   Integration with external databases or data warehouses
-   Role-based access control

Each non-goal has a defined upgrade path in Section 21.

## 4. System Overview

The system consists of two independently deployable services:

  ---------- -------------------- -------------------------------------------------------
  Backend    FastAPI (Python)     Data processing, LLM integration, response generation
  Frontend   Streamlit (Python)   File upload, chat interface, chart rendering
  ---------- -------------------- -------------------------------------------------------

The two services communicate over HTTP. The frontend never talks to the
LLM directly, all intelligence lives in the backend.

### 4.1 What the User Experiences

1.  Open the web interface
2.  Upload one or more CSV files
3.  See a summary of what was uploaded, what was cleaned, and what
    relationships were detected
4.  Type a question in the chat box
5.  Receive either a written answer or an interactive chart
6.  Ask follow-up questions that reference prior context
7.  Upload new files or clear the session to start fresh

### 4.2 What Happens Behind the Scenes

Every user question triggers the following internal pipeline:

Question received\
→ Conversation history retrieved (last N turns)\
→ CSV schemas, samples, and detected relationships assembled\
→ Structured prompt constructed\
→ LLM called with full context\
→ LLM returns structured JSON (type: text or chart)\
→ If chart: generated code executed in sandbox → Plotly figure returned\
→ If text: markdown answer returned\
→ Response sent to frontend\
→ Conversation history updated\
→ All events logged with request_id

## 5. Architecture

### 5.1 Architecture Diagram

┌─────────────────────────────────────────────────────────┐\
│ USER BROWSER │\
└───────────────────────┬─────────────────────────────────┘\
│ HTTP\
┌───────────────────────▼─────────────────────────────────┐\
│ STREAMLIT FRONTEND │\
│ │\
│ ┌─────────────┐ ┌─────────────┐ ┌─────────────────┐ │\
│ │ File Upload │ │ Chat UI │ │ Chart Renderer │ │\
│ └─────────────┘ └─────────────┘ └─────────────────┘ │\
└───────────────────────┬─────────────────────────────────┘\
│ HTTP (REST API)\
┌───────────────────────▼─────────────────────────────────┐\
│ FASTAPI BACKEND │\
│ │\
│ ┌──────────────┐ ┌──────────────┐ ┌───────────────┐ │\
│ │ CSV Handler │ │ LLM Service │ │ Chart Engine │ │\
│ │ - validate │ │ - prompt │ │ - safe exec │ │\
│ │ - clean │ │ build │ │ - sandbox │ │\
│ │ - profile │ │ - call API │ └───────────────┘ │\
│ │ - detect FKs │ │ - parse JSON │ │\
│ └──────────────┘ └──────────────┘ ┌───────────────┐ │\
│ │ Memory │ │\
│ ┌──────────────┐ │ sliding window│ │\
│ │ Models / │ └───────────────┘ │\
│ │ Schemas │ │\
│ │ (Pydantic) │ │\
│ └──────────────┘ │\
└───────────────────────┬─────────────────────────────────┘\
│ HTTPS\
┌───────────────────────▼─────────────────────────────────┐\
│ EXTERNAL LLM API │\
│ (Gemini 3.0 Flash via │\
│ Google AI Studio API) │\
└─────────────────────────────────────────────────────────┘

### 5.2 Deployment Architecture

docker-compose\
├── backend (FastAPI) → port 8000\
└── frontend (Streamlit) → port 8501

Both containers share a Docker network. The frontend communicates with
the backend via the internal Docker network hostname, not localhost.

## 6. Component Design

### 6.1 Backend Components

#### *main.py - *FastAPI Application Entry Point

-   Defines all API routes
-   Generates a *request_id* (UUID4) at the entry point of every request
-   Passes *request_id* to all downstream functions
-   Handles CORS for Streamlit communication
-   Registers global exception handlers

#### *csv_handler.py - *CSV Processing Module

Responsible for everything that happens to a file before it is available
for querying:

-   File type validation
-   Encoding detection and normalisation
-   Data type inference and correction
-   Date column detection and parsing
-   Missing value handling
-   Outlier detection using IQR method
-   Schema and statistical profiling
-   Cleaning report generation

#### *relationship_detector.py - *Automatic Foreign Key Detection

-   Compares column names across all uploaded files
-   For each matching column name pair, computes value overlap ratio
-   Pairs with overlap above a configurable threshold (default: 50%) are
    recorded as detected relationships
-   Detected relationships are passed to the LLM prompt so it knows how
    to join files
-   No relationships are hardcoded, the system works with any set of
    uploaded files

#### *llm_service.py - *LLM Integration Layer

-   Constructs the structured system prompt (schema context +
    relationships + conversation history + user question)
-   Calls the Gemini API
-   Parses and validates the JSON response
-   Handles retries on transient failures
-   Logs token counts and latency

#### *chart_engine.py - *Safe Code Execution Sandbox

-   Receives Plotly code string from LLM response
-   Executes it in a restricted namespace (only Pandas and Plotly
    Express in scope)
-   Returns a Plotly figure object or raises a typed exception on
    failure
-   Never uses unrestricted *exec()*

#### *memory.py - *Conversation History Manager

-   Maintains a sliding window of the last N conversation turns
    (default: 5)
-   Implemented as a *collections.deque* with *maxlen*
-   Each turn stored as *{role: \"user\" \| \"assistant\", content:
    \"\...\"}* to match LLM API format
-   History is serialisable for logging

#### *models.py - *Pydantic Schemas

All request and response shapes are defined here as Pydantic models.
Nothing enters or leaves the API without passing through schema
validation.

#### *config.py - *Configuration Management

-   All configuration loaded from environment variables via
    *pydantic-settings*
-   No hardcoded values anywhere in the codebase
-   Includes: API keys, model name, memory window size, FK overlap
    threshold, log level, CORS origins

#### *exceptions.py - *Custom Exception Hierarchy

AppException (base)\
├── CSVValidationError\
├── CSVCleaningError\
├── RelationshipDetectionError\
├── LLMCallError\
├── LLMParseError\
└── CodeExecutionError

Every exception carries *request_id* and a human-readable message. The
global handler in *main.py* converts these to structured HTTP error
responses.

### 6.2 Frontend Components

#### *app.py - *Streamlit Application

-   File upload widget (accepts multiple CSVs)
-   Calls backend */upload* endpoint on file selection
-   Displays cleaning report and detected relationships after upload
-   Chat input and message history display
-   Calls backend */query* endpoint on message send
-   Renders Plotly charts inline when response type is *chart*
-   Maintains session state for conversation history display

### 6.3 Evaluation Components

#### *evals/run_evals.py - *Evaluation Runner

-   Loads ground truth from *ground_truth.json*
-   Fires each question against the live backend
-   Compares responses to expected values/types
-   Writes timestamped results to *evals/results/*

#### *evals/metrics.py - *Metrics Calculator

-   Answer accuracy (numeric tolerance comparison)
-   Response type accuracy (text vs chart classification)
-   Hallucination rate (out-of-scope questions answered honestly)
-   Code execution success rate
-   p50/p95 latency

## 7. Data Flow

### 7.1 File Upload Flow

User selects files\
→ Frontend sends multipart/form-data to POST /upload\
→ Backend validates file type and encoding\
→ For each file:\
→ Detect and fix data types\
→ Parse date columns\
→ Handle missing values\
→ Detect outliers\
→ Generate column profile (name, dtype, nulls, uniques, sample values)\
→ Generate cleaning report (what changed and why)\
→ Run relationship detector across all files\
→ Store processed dataframes and schema context in session\
→ Return: schema summary + cleaning reports + detected relationships\
→ Frontend displays summary to user

### 7.2 Query Flow

User types question\
→ Frontend sends POST /query {session_id, question}\
→ Backend retrieves session (dataframes, schema context, conversation
history)\
→ Construct prompt:\
→ System instructions\
→ Schema context for all files (columns, types, stats, sample rows)\
→ Detected relationships between files\
→ Last N conversation turns\
→ Current user question\
→ Call LLM API\
→ Parse JSON response {type, answer, code, reasoning}\
→ If type == \"chart\":\
→ Pass code to chart_engine.safe_execute()\
→ Serialise Plotly figure to JSON\
→ Return {type: \"chart\", figure: \<plotly json\>}\
→ If type == \"text\":\
→ Return {type: \"text\", answer: \"\...\"}\
→ Update conversation history (append user question + assistant
response)\
→ Log full request/response with request_id and latency\
→ Frontend renders response

### 7.3 Error Flow

Any exception raised in backend\
→ Caught by global exception handler in main.py\
→ Mapped to appropriate HTTP status code\
→ Response body: {error_code, message, request_id}\
→ Full traceback logged with request_id at ERROR level\
→ Frontend displays human-readable error message (not stack trace)

## 8. Key Design Decisions

This section documents every significant architectural choice, the
alternatives that were considered, and the reasoning behind the decision
made. This is the most important section for any engineer or agent
implementing or extending this system.

### 8.1 Schema-Aware Prompt Injection vs RAG

**Decision:** Use schema-aware prompt injection. Do not use RAG.

**What RAG is:** Retrieval Augmented Generation is an architecture where
a large corpus of unstructured text is chunked, embedded into a vector
space, and stored in a vector database. At query time, the user\'s
question is embedded and the most semantically similar chunks are
retrieved and injected into the prompt.

**Why RAG does not apply here:** The input data is structured (CSV files
with defined columns and types). There are no unstructured text chunks
to embed or retrieve. The relevant context for answering any question is
not a subset of rows, it is the schema (what columns exist, what types
they are, what the value distribution looks like) plus a small
representative sample. This context is compact enough to fit directly in
the prompt.

**What schema-aware prompt injection does instead:** For each uploaded
file, the system extracts column names, inferred data types, null
counts, unique value counts, minimum/maximum values for numeric columns,
and a fixed number of sample rows. This structured metadata is
serialised and injected into the LLM prompt on every query. The LLM uses
this to understand the data and generate correct analysis code without
ever needing to retrieve rows from a vector store.

**Tradeoff:** If files are extremely wide (many hundreds of columns) or
contain many files simultaneously, the injected schema context grows
large. This is addressed in Section 21.

### 8.2 Code Generation vs Direct Answer

**Decision:** The LLM generates executable Pandas/Plotly code for
analysis and visualisation rather than attempting to compute answers
directly.

**Why:** LLMs are not reliable calculators. Asking an LLM to compute
*SUM(revenue) WHERE region = \'North\'* directly risks hallucinated
numbers. Instead, the LLM generates Python code that performs the
computation correctly using Pandas, and the system executes that code
against the actual data. The result is always computed from real data,
never invented by the model.

**For text answers:** The LLM generates Pandas code that computes a
value, the system executes it, and the result is interpolated back into
a natural language response.

**For charts:** The LLM generates Plotly Express code, the system
executes it in a sandbox, and the resulting figure is sent to the
frontend.

**This means the LLM\'s role is reasoning and code authoring, not
arithmetic.** The data never lies because the code runs against the
actual uploaded files.

### 8.3 Structured JSON Response Contract

**Decision:** The LLM is instructed to always respond in a strict,
machine-parseable JSON schema.

**Why:** Free-form LLM responses require fragile string parsing to
determine whether to render a chart or display text. A strict JSON
contract makes the system deterministic, testable, and maintainable.

**The contract:**

{\
\"type\": \"text \| chart\",\
\"answer\": \"string or null\",\
\"code\": \"executable Python string or null\",\
\"reasoning\": \"string explaining why this format was chosen\"\
}

The *reasoning* field serves two purposes: it encourages the LLM to
think carefully about format selection (chain-of-thought), and it
provides a human-readable explanation that aids debugging when the
system chooses unexpectedly.

### 8.4 Automatic Relationship Detection vs Manual Configuration

**Decision:** Detect foreign key relationships between files
automatically. Never require the user to specify joins, and never
hardcode relationships in the codebase.

**Why:** Hardcoding relationships makes the system work only for one
specific dataset. Requiring users to specify joins manually creates
friction and assumes technical knowledge. Auto-detection makes the
system generalizable to any set of CSV files a user uploads.

**How it works:**

1.  For every pair of files, find columns that share the same name
2.  For each matching column, compute the ratio of overlapping values
    between the two files
3.  If the overlap ratio exceeds the configured threshold (default 50%),
    record it as a detected relationship
4.  Pass all detected relationships to the LLM in structured form so it
    knows which files can be joined and on which column

**Tradeoff:** Heuristic detection can produce false positives (columns
that share a name but are not actually related). The configurable
threshold and the LLM\'s reasoning capability mitigate this, if a
detected relationship does not make semantic sense, the LLM will ignore
it.

### 8.5 Direct LLM API Calls vs LangChain

**Decision:** Call the LLM API directly. Do not use LangChain or any
orchestration framework.

**Why:** LangChain introduces multiple layers of abstraction between the
application and the LLM API. These layers:

-   Make prompt construction opaque and harder to debug
-   Introduce framework-specific bugs that are difficult to isolate
-   Add unnecessary dependency weight
-   Change behaviour between versions in ways that are hard to predict

Direct API calls mean the prompt is exactly what the code constructs,
the response is exactly what the API returns, and every step is fully
visible and testable. For a system where prompt quality is the core
engineering challenge, this visibility is essential.

**The only things LangChain would add here are things the system does
not need:** agent loops, tool routing, and document retrieval. None of
these apply to this architecture.

### 8.6 Sliding Window Memory vs Full Memory Layer

**Decision:** Maintain conversation memory as a sliding window of the
last N turns (default: 5). Do not implement a vector-based memory layer.

**Why a full memory layer is not appropriate here:** A vector-based
memory layer (such as LangMem or a custom implementation using ChromaDB)
makes sense for long-lived assistants where a user might reference
something from 50 or 100 turns ago, or across separate sessions spanning
days or weeks. Data analysis sessions are fundamentally different: they
are short, focused, and self-contained. A user uploading files and
asking questions about them rarely needs context from more than a few
turns back.

**Why 5 turns:** Five turns (10 messages: 5 user + 5 assistant) captures
enough context for natural follow-up questions (\"Now break it down by
region\", \"What about the previous year?\") while keeping the prompt
size predictable and bounded.

**Implementation:** Python\'s *collections.deque* with *maxlen=5*. When
a new turn is added and the deque is full, the oldest turn is
automatically discarded. This requires zero additional infrastructure.

**The upgrade path:** If the system is extended into a persistent
multi-session assistant, the sliding window can be replaced with a
proper memory layer without changing any other component, because memory
is isolated in *memory.py*.

### 8.7 Safe Code Execution Sandbox

**Decision:** Execute all LLM-generated code in a restricted namespace.
Never use unrestricted *exec()*.

**Why:** LLM-generated code is untrusted code. Even in a PoC
environment, executing it with unrestricted access to Python\'s global
namespace creates a security risk. An LLM could generate code
(maliciously or accidentally) that reads environment variables, makes
network calls, writes to disk, or imports dangerous modules.

**How the sandbox works:**

def safe_execute(code: str, dataframes: dict) -\> Figure:\
allowed_globals = {\
\"\_\_builtins\_\_\": {}, \# no built-ins\
\"pd\": pd, \# Pandas only\
\"px\": px, \# Plotly Express only\
\*\*dataframes \# only the uploaded dataframes\
}\
local_scope = {}\
exec(code, allowed_globals, local_scope)\
return local_scope\[\"fig\"\]

The LLM can only access Pandas, Plotly Express, and the uploaded
dataframes. It cannot import anything, call any built-in, or access any
other system resource.

### 8.8 LLM Selection: Gemini 3.0 Flash

**Decision:** Use Google Gemini 3.0 Flash as the language model.

**Why this model:**

-   Large context window, essential for injecting multiple CSV schemas
    and sample data into a single prompt without truncation
-   Strong code generation capability, the core of the system\'s
    analysis mechanism relies on correct Pandas and Plotly code
    generation
-   Fast response times, suitable for interactive chat
-   Cost-efficient, appropriate for a PoC where API usage costs should
    be minimal
-   Actively maintained, Gemini 1.5 series models have been retired; 3.0
    Flash is the current stable generation

**Model name in API:** *gemini-3.0-flash*

**Configuration:** The model name is stored in *config.py* as an
environment variable. Switching to a different model requires changing
one environment variable, not modifying code.

### 8.9 Frontend: Streamlit

**Decision:** Use Streamlit for the frontend.

**Why Streamlit over plain HTML or other frameworks:**

-   File upload, chat interface, and Plotly chart rendering are all
    built-in, zero custom frontend code needed
-   The entire frontend is Python, keeping the codebase in a single
    language
-   Streamlit\'s session state handles UI state without a separate state
    management layer
-   Rapid iteration: changes to the UI take seconds to reflect

**Why not plain HTML with JavaScript:** Would require writing a file
upload handler, a WebSocket or polling mechanism for responses, a chart
rendering library integration, and custom CSS. This adds significant
frontend work with no benefit for a demo or PoC.

## 9. Technology Stack

  -------------------- --------------------------------- --------------- --------------------------------------------------------------------------
  Backend framework    FastAPI                           Latest stable   Async support, automatic OpenAPI docs, Pydantic integration, type safety
  Frontend framework   Streamlit                         Latest stable   Built-in file upload, chat UI, Plotly support; pure Python
  Data processing      Pandas                            Latest stable   Industry standard for CSV manipulation; what the LLM generates code for
  LLM                  Gemini 3.0 Flash                  Current         Large context window, strong code gen, cost-efficient
  Visualisation        Plotly Express                    Latest stable   Interactive charts; works natively in Streamlit; what the LLM generates
  Schema validation    Pydantic v2                       Latest stable   Type-safe request/response models; used by FastAPI natively
  Configuration        pydantic-settings                 Latest stable   Environment variable loading with type validation
  Containerisation     Docker + Compose                  Latest stable   Reproducible, single-command deployment
  Logging              Python logging + JSON formatter   stdlib          Structured logs without external dependencies
  HTTP client          httpx                             Latest stable   Async HTTP for LLM API calls
  -------------------- --------------------------------- --------------- --------------------------------------------------------------------------

## 10. API Contract

### 10.1 POST */upload*

Upload one or more CSV files for processing.

**Request:** *multipart/form-data*

files: List\[UploadFile\] \# one or more CSV files\
session_id: str \# client-generated UUID

**Response:** *200 OK*

{\
\"session_id\": \"uuid\",\
\"files_processed\": \[\
{\
\"filename\": \"string\",\
\"rows\": 0,\
\"columns\": 0,\
\"cleaning_report\": {\
\"nulls_filled\": 0,\
\"date_columns_converted\": \[\"col1\"\],\
\"outliers_flagged\": 0,\
\"string_columns_normalised\": \[\"col2\"\]\
},\
\"schema\": \[\
{\
\"column\": \"string\",\
\"dtype\": \"string\",\
\"null_count\": 0,\
\"unique_count\": 0,\
\"sample_values\": \[\"val1\", \"val2\"\]\
}\
\]\
}\
\],\
\"detected_relationships\": \[\
{\
\"file_a\": \"string\",\
\"file_b\": \"string\",\
\"join_column\": \"string\",\
\"overlap_ratio\": 0.0\
}\
\]\
}

**Error responses:**

-   *400 - *invalid file type or encoding
-   *422 - *request schema validation failure
-   *500 - *internal processing error

### 10.2 POST */query*

Submit a natural language question for the currently uploaded files.

**Request:** *application/json*

{\
\"session_id\": \"uuid\",\
\"question\": \"string\"\
}

**Response:** *200 OK*

{\
\"type\": \"text \| chart\",\
\"answer\": \"string or null\",\
\"figure\": \"\<plotly json or null\>\",\
\"reasoning\": \"string\",\
\"request_id\": \"uuid\",\
\"latency_ms\": 0\
}

**Error responses:**

-   *404 - *session not found (files not uploaded yet)
-   *422 - *request schema validation failure
-   *502 - *LLM API call failed
-   *500 - *code execution failure or internal error

### 10.3 DELETE */session/{session_id}*

Clear all uploaded files and conversation history for a session.

**Response:** *200 OK*

{ \"cleared\": true }

## 11. Prompt Engineering Strategy

### 11.1 System Prompt Structure

The system prompt is constructed dynamically on every request. It has
five sections assembled in order:

\[1\] ROLE AND INSTRUCTIONS\
\[2\] SCHEMA CONTEXT (all uploaded files)\
\[3\] DETECTED RELATIONSHIPS\
\[4\] CONVERSATION HISTORY (last N turns)\
\[5\] CURRENT QUESTION

### 11.2 Role and Instructions Block

You are a data analysis assistant. You have access to the following\
structured data files. Your job is to answer the user\'s question by\
analysing the data.\
\
Rules:\
- Always respond in valid JSON matching the schema below\
- Never invent data. If the answer cannot be determined from the\
provided files, say so clearly in the answer field\
- For numerical questions, generate Pandas code to compute the answer\
and set type to \"text\"\
- For trend, comparison, or distribution questions, generate Plotly\
Express code and set type to \"chart\"\
- The code field must assign the final result to a variable named
\"fig\"\
for charts, or \"result\" for text\
- Available dataframes in scope: {dataframe_variable_names}\
- Available libraries: pandas (as pd), plotly.express (as px)\
\
Response schema:\
{\
\"type\": \"text \| chart\",\
\"answer\": \"natural language answer or null if chart\",\
\"code\": \"executable Python string or null if simple text\",\
\"reasoning\": \"one sentence explaining why you chose this format\"\
}

### 11.3 Schema Context Block

For each uploaded file:

FILE: {filename}\
Rows: {row_count} \| Columns: {column_count}\
Dataframe variable: {variable_name}\
\
Columns:\
\| Column \| Type \| Nulls \| Uniques \| Sample Values \|\
\|\-\-\-\-\-\-\--\|\-\-\-\-\--\|\-\-\-\-\-\--\|\-\-\-\-\-\-\-\--\|\-\-\-\-\-\-\-\-\-\-\-\-\-\--\|\
\| col_a \| int \| 0 \| 500 \| 1, 2, 3 \|\
\| col_b \| str \| 12 \| 8 \| \"A\", \"B\", \"C\" \|\
\| col_c \| date \| 0 \| 365 \| 2024-01-01 \|

### 11.4 Relationships Block

DETECTED RELATIONSHIPS (use these for joins):\
- {file_a}.{column} → {file_b}.{column} (overlap: {ratio}%)\
- {file_a}.{column} → {file_c}.{column} (overlap: {ratio}%)

### 11.5 Why This Prompt Structure Works

-   **Role clarity** prevents the LLM from responding conversationally
    when it should be generating code
-   **Strict JSON schema** makes parsing deterministic, no regex
    required
-   **Explicit variable names** prevent the LLM from guessing what the
    dataframes are called
-   **Relationship block** enables correct multi-file joins without the
    LLM having to infer them
-   **The *****reasoning***** field** forces the model to justify format
    selection, improving accuracy through chain-of-thought

## 12. Data Cleaning Pipeline

Every uploaded file passes through a sequential cleaning pipeline before
being stored in the session. The pipeline is non-destructive in the
sense that it logs every change it makes and presents this to the user.

### 12.1 Pipeline Stages

  ---------------------- ---------------------------------------------------------------------------------------------------- ------------------------------------------------------------
  Type inference         Re-infers column types after loading (Pandas defaults to *object* for mixed columns)                 Ensures numeric operations work correctly
  Date detection         Detects columns likely to contain dates using pattern matching on values; converts to *datetime64*   Enables time-based queries and sorting
  Null handling          Fills numeric nulls with column median; fills categorical nulls with mode; flags remaining nulls     Prevents computation errors on null values
  Outlier detection      Uses IQR method (Q1 - 1.5×IQR, Q3 + 1.5×IQR) to flag outliers; does not remove them                  Informs the LLM about data quality without destroying data
  String normalisation   Strips leading/trailing whitespace; normalises encoding                                              Prevents join failures on string keys due to whitespace
  Profile generation     Computes column-level statistics: null count, unique count, min, max, top values                     Feeds the schema context block in the prompt
  ---------------------- ---------------------------------------------------------------------------------------------------- ------------------------------------------------------------

### 12.2 Cleaning Report

After processing, the system generates a cleaning report per file:

{\
\"filename\": \"string\",\
\"date_columns_converted\": \[\"col1\", \"col2\"\],\
\"nulls_filled\": { \"col3\": 12, \"col4\": 3 },\
\"outliers_flagged\": { \"col5\": 7 },\
\"string_columns_normalised\": \[\"col6\"\],\
\"rows_before\": 0,\
\"rows_after\": 0\
}

This report is displayed in the frontend and included in the API
response. Transparency about what was changed builds user trust and
makes the system auditable.

## 13. Conversation Memory Strategy

### 13.1 Design

Memory is managed in *memory.py* as a per-session *collections.deque*
with a configurable *maxlen* (default: 5 turns = 10 messages).

Each turn is stored as:

\[\
{\"role\": \"user\", \"content\": \"What is total revenue?\"},\
{\"role\": \"assistant\", \"content\": \"Total revenue is \...\"}\
\]

This format matches the Gemini API\'s message format directly, so
history can be passed without transformation.

### 13.2 Memory Lifecycle

  --------------------- -----------------------------------
  Session created       Empty deque initialised
  User sends question   User message appended
  LLM responds          Assistant message appended
  Deque full            Oldest pair automatically dropped
  Session cleared       Deque replaced with empty deque
  --------------------- -----------------------------------

### 13.3 Why Not a Vector Memory Layer

A vector memory layer stores conversation history as embeddings and
retrieves the most semantically relevant past turns at query time. This
is appropriate when:

-   Sessions span many hours or days
-   Users reference things from far back in the conversation
-   Memory needs to persist across separate browser sessions

None of these conditions apply to this system. Data analysis sessions
are short and focused. A user\'s follow-up questions reference the
immediately prior context, not something from 30 turns ago. Sliding
window is the right tool for this scope.

## 14. Observability

### 14.1 Design Philosophy

Observability is designed into the system from the start, not bolted on
after. The principle is: **every meaningful event in the system should
produce a structured, searchable log entry that can be correlated back
to a specific user request.**

### 14.2 Request ID Tracing

Every incoming request to the FastAPI backend is assigned a *request_id*
(UUID4) at the point of entry. This ID is:

-   Passed as a parameter to every downstream function
-   Included in every log entry for that request
-   Returned to the client in the response body
-   Used in all exceptions and error responses

This means any error reported by a user can be traced through the entire
call stack using a single *request_id*.

### 14.3 Structured Log Format

All logs are emitted as newline-delimited JSON using Python\'s *logging*
module with a custom *JsonFormatter*. This format is directly ingestible
by Datadog, CloudWatch, Grafana Loki, and any other log aggregation
tool.

{\
\"timestamp\": \"ISO8601\",\
\"level\": \"INFO \| WARNING \| ERROR\",\
\"request_id\": \"uuid\",\
\"event\": \"event_name\",\
\"service\": \"backend \| frontend\",\
\...event-specific fields\...\
}

### 14.4 Logged Events

  ----------------------------------- --------------------- ----------------------------------------------------------
  *file_upload_received*              POST /upload called   session_id, file_count, file_names
  *file_processing_complete*          One file processed    filename, rows, columns, cleaning_changes
  *relationship_detection_complete*   FK detection done     detected_pairs, threshold_used
  *llm_request_sent*                  LLM API called        request_id, model, prompt_token_estimate, history_length
  *llm_response_received*             LLM API responded     request_id, response_type, latency_ms, reasoning
  *code_execution_success*            Chart code ran        request_id, chart_type, execution_time_ms
  *code_execution_failure*            Chart code failed     request_id, error_type, code_snippet
  *query_complete*                    /query responded      request_id, response_type, total_latency_ms
  *error*                             Any exception         request_id, exception_type, message, traceback, stage
  ----------------------------------- --------------------- ----------------------------------------------------------

### 14.5 Log Levels

  ----------- -------------------------------------------------------------------------------------
  *DEBUG*     Prompt content, raw LLM responses, detailed execution traces
  *INFO*      Normal operation events (upload complete, query complete, response type)
  *WARNING*   Recoverable issues (outliers detected, FK overlap below threshold, LLM retry)
  *ERROR*     Failures requiring attention (LLM call failed, code execution error, parsing error)
  ----------- -------------------------------------------------------------------------------------

*DEBUG* is off by default and enabled via the *LOG_LEVEL* environment
variable.

## 15. Evaluation Harness

### 15.1 Purpose

The evaluation harness exists to answer three questions that arise
whenever an AI system is in use:

1.  Is the system actually giving correct answers?
2.  When the system fails, which component failed?
3.  If the model or prompt is changed, did the system get better or
    worse?

Without an eval harness, these questions can only be answered by
manually testing the system after every change. The harness automates
this.

### 15.2 Structure

evals/\
├── ground_truth.json \# Curated Q&A test cases\
├── run_evals.py \# Test runner, fires questions against live backend\
├── metrics.py \# Computes accuracy, hallucination rate, latency\
└── results/ \# Timestamped JSON output files per eval run

### 15.3 Test Case Schema

{\
\"id\": \"unique_test_identifier\",\
\"description\": \"human-readable description of what is being
tested\",\
\"question\": \"the natural language question to ask\",\
\"expected_type\": \"text \| chart\",\
\"expected_value\": null,\
\"tolerance\": 0.01,\
\"expected_chart_type\": null,\
\"expected_behaviour\": \"admit_no_data \| return_value \|
return_chart\",\
\"category\": \"accuracy \| hallucination \| edge_case \| chart \|
performance\"\
}

### 15.4 Test Categories

  ----------------- --------------------------------------------------------------------
  *accuracy*        Numeric answers match ground truth within tolerance
  *hallucination*   System admits it does not know when data is unavailable
  *chart*           Chart code executes without error; chart type matches expectation
  *edge_case*       System handles missing data, ambiguous questions, cross-file joins
  *performance*     Response latency stays within acceptable bounds
  ----------------- --------------------------------------------------------------------

### 15.5 Metrics Per Eval Run

  ------------------------ -----------------------------------------------------------------------------
  Answer accuracy          \% of *accuracy* tests where result matches expected value within tolerance
  Response type accuracy   \% of tests where text/chart classification matches expected type
  Hallucination rate       \% of *hallucination* tests where system incorrectly invented an answer
  Code success rate        \% of *chart* tests where generated code executed without error
  p50 latency              Median end-to-end response time across all tests
  p95 latency              95th percentile end-to-end response time across all tests
  ------------------------ -----------------------------------------------------------------------------

### 15.6 Eval Run Output

Each run writes a timestamped file to *evals/results/*:

{\
\"run_id\": \"uuid\",\
\"timestamp\": \"ISO8601\",\
\"model\": \"gemini-3.0-flash\",\
\"summary\": {\
\"total_tests\": 0,\
\"passed\": 0,\
\"failed\": 0,\
\"accuracy_pct\": 0.0,\
\"hallucination_rate_pct\": 0.0,\
\"p50_latency_ms\": 0,\
\"p95_latency_ms\": 0\
},\
\"results\": \[\...\]\
}

This output format allows two eval runs to be compared directly, for
example, before and after a prompt change or model upgrade.

## 16. Security Considerations

### 16.1 Code Execution Sandbox

All LLM-generated Python code is executed in a restricted namespace. The
sandbox allows only:

-   The *pandas* library (aliased as *pd*)
-   The *plotly.express* library (aliased as *px*)
-   The uploaded dataframes (by variable name)

The *\_\_builtins\_\_* key is set to an empty dict, preventing access to
Python built-ins including *import*, *open*, *exec*, *eval*, *os*, and
*sys*.

### 16.2 File Validation

-   Only *.csv* files are accepted (validated by extension and MIME
    type)
-   Maximum file size is configurable via environment variable
-   Files are processed in memory and never written to disk on the
    server

### 16.3 API Key Management

-   LLM API keys are loaded exclusively from environment variables via
    *pydantic-settings*
-   Keys are never logged, printed, or included in any response
-   The *.env* file is listed in *.gitignore* and never committed to
    version control

### 16.4 Input Sanitisation

-   All user input passes through Pydantic validation before processing
-   Session IDs are validated as UUID4 format
-   File names are sanitised before use in any log messages

## 17. Error Handling Strategy

### 17.1 Principles

1.  **Every error is typed.** No bare *except Exception* without
    re-raising a typed exception.
2.  **Every error carries a *****request_id*****.** Errors are always
    traceable.
3.  **Users see human-readable messages.** Stack traces never appear in
    the API response or UI.
4.  **The system degrades gracefully.** A chart generation failure falls
    back to a text response if possible; it does not crash the session.

### 17.2 Error Response Format

{\
\"error_code\": \"CODE_EXECUTION_ERROR\",\
\"message\": \"The chart could not be generated. Please try rephrasing
your question.\",\
\"request_id\": \"uuid\"\
}

### 17.3 Retry Strategy

LLM API calls are retried up to 3 times with exponential backoff on
transient errors (rate limits, 5xx responses). Permanent errors (invalid
API key, malformed request) are not retried and fail immediately.

### 17.4 Fallback Behaviour

  ----------------------------------------- ---------------------------------------------------------------------------------
  LLM returns invalid JSON                  Retry once with explicit JSON reminder in prompt; return error if still invalid
  Generated chart code fails to execute     Return error response with user-friendly message; log full traceback
  File encoding detection fails             Attempt UTF-8, then latin-1; return validation error if both fail
  Relationship detection finds no matches   Proceed without relationships; log a warning
  ----------------------------------------- ---------------------------------------------------------------------------------

## 18. Project Structure

project-root/\
│\
├── backend/\
│ ├── main.py \# FastAPI app, routes, global error handler\
│ ├── csv_handler.py \# File validation, cleaning pipeline, profiling\
│ ├── relationship_detector.py \# Automatic foreign key detection\
│ ├── llm_service.py \# Prompt construction, Gemini API calls, response
parsing\
│ ├── chart_engine.py \# Safe code execution sandbox\
│ ├── memory.py \# Sliding window conversation history\
│ ├── models.py \# Pydantic request/response schemas\
│ ├── config.py \# Environment variable configuration\
│ └── exceptions.py \# Custom exception hierarchy\
│\
├── frontend/\
│ └── app.py \# Streamlit UI\
│\
├── evals/\
│ ├── ground_truth.json \# Curated test cases\
│ ├── run_evals.py \# Evaluation runner\
│ ├── metrics.py \# Metrics computation\
│ └── results/ \# Timestamped eval output files\
│\
├── .env.example \# Template for required environment variables\
├── .gitignore \# Excludes .env, \_\_pycache\_\_, results/\
├── Dockerfile.backend \# Backend container definition\
├── Dockerfile.frontend \# Frontend container definition\
├── docker-compose.yml \# Orchestrates both services\
├── requirements.txt \# All Python dependencies with pinned versions\
└── README.md \# Setup and run instructions

### 18.1 Environment Variables

\# LLM\
GEMINI_API_KEY=your_key_here\
LLM_MODEL=gemini-3.0-flash\
\
\# Backend\
BACKEND_HOST=0.0.0.0\
BACKEND_PORT=8000\
MAX_FILE_SIZE_MB=50\
FK_OVERLAP_THRESHOLD=0.5\
\
\# Memory\
CONVERSATION_WINDOW_SIZE=5\
\
\# Logging\
LOG_LEVEL=INFO\
\
\# Frontend\
BACKEND_URL=http://backend:8000\
FRONTEND_PORT=8501

## 19. Deployment

### 19.1 Local Development

\# Clone repository\
git clone \<repo-url\>\
cd project-root\
\
\# Copy environment template\
cp .env.example .env\
\# Add GEMINI_API_KEY to .env\
\
\# Start all services\
docker-compose up \--build\
\
\# Access\
\# Frontend: http://localhost:8501\
\# Backend API docs: http://localhost:8000/docs

### 19.2 Docker Compose Configuration

version: \"3.9\"\
services:\
backend:\
build:\
context: .\
dockerfile: Dockerfile.backend\
ports:\
 - \"8000:8000\"\
env_file: .env\
\
frontend:\
build:\
context: .\
dockerfile: Dockerfile.frontend\
ports:\
 - \"8501:8501\"\
env_file: .env\
depends_on:\
 - backend

### 19.3 Running Evaluations

\# With services running\
docker-compose exec backend python -m evals.run_evals\
\
\# Results written to evals/results/\<timestamp\>.json

## 20. Delivery Phases

### Phase 1 - Foundation

-   Project scaffold with full folder structure
-   FastAPI backend with health check endpoint
-   CSV upload endpoint with validation
-   Cleaning pipeline (all stages)
-   Relationship detection
-   Pydantic models, config, custom exceptions
-   Structured logging with request_id tracing

**Exit criteria:** Files can be uploaded, cleaned, profiled, and
relationships detected. All events are logged.

### Phase 2 - Intelligence

-   LLM service with prompt construction
-   Structured JSON response parsing
-   Safe code execution sandbox
-   Text response generation
-   Chart response generation
-   Retry logic and error fallbacks

**Exit criteria:** A question can be asked, the LLM generates code, code
executes, and the correct response type is returned.

### Phase 3 - Conversation and Frontend

-   Sliding window memory implementation
-   Multi-turn conversation support in */query* endpoint
-   Streamlit frontend (file upload, chat UI, chart rendering)
-   Cleaning report display in UI
-   Relationship summary display in UI
-   Human-readable error messages in UI

**Exit criteria:** A full end-to-end conversation with follow-up
questions works. Charts render. Errors are handled gracefully.

### Phase 4 - Hardening and Delivery

-   Evaluation harness (*evals/* folder, ground truth, runner, metrics)
-   Docker and docker-compose setup
-   *.env.example* with all required variables
-   README with full setup and run instructions
-   Code review: type hints, docstrings, no bare exceptions, no
    hardcoded values
-   Final eval run, results documented

**Exit criteria:** Single command brings up the full system. Eval
harness runs and produces a results file. README is self-sufficient for
a new engineer to set up the project.

## 21. Known Limitations and Upgrade Paths

  ------------------------ ----------------------------------------------------- ------------------------------------------------------------------------------------------------
  Very wide files          Schema injection grows large with 100+ column files   Add column selection strategy: rank columns by relevance to query before injection
  Very large files         Full file loaded into memory                          Switch to DuckDB or SQLite for large file querying; use Text-to-SQL instead of Pandas code gen
  Single user              Session stored in-memory on backend process           Replace with Redis session store; add session TTL
  No persistence           Conversation lost on browser refresh                  Persist sessions to Redis or a database
  No authentication        Any user can access any session                       Add JWT authentication; scope sessions to authenticated users
  No streaming             Response appears all at once                          Implement SSE or WebSocket streaming from backend
  Eval harness is manual   Must be triggered manually                            Add to CI/CD pipeline; run on every pull request
  Heuristic FK detection   Can produce false positives                           Add semantic similarity check on column names as secondary signal
  No model fallback        Single LLM, no fallback                               Add configurable fallback model; route based on prompt size
  ------------------------ ----------------------------------------------------- ------------------------------------------------------------------------------------------------

## 22. Glossary

  ----------------------- --------------------------------------------------------------------------------------------------------------------------
  **CSV**                 Comma-Separated Values, a plain text file format for tabular data
  **LLM**                 Large Language Model, a neural network trained on text, used here for code generation and natural language understanding
  **RAG**                 Retrieval Augmented Generation, an architecture for unstructured text retrieval; explicitly not used in this system
  **Schema injection**    The practice of inserting structured metadata (column names, types, statistics) directly into an LLM prompt
  **Foreign key (FK)**    A column in one file whose values reference rows in another file, enabling joins
  **Sliding window**      A fixed-size buffer of recent conversation turns; older turns are dropped as new ones are added
  **Sandbox**             A restricted execution environment with limited access to system resources
  **request_id**          A UUID assigned to each incoming request and propagated through all log events for traceability
  **IQR**                 Interquartile Range, a statistical method for detecting outliers (values below Q1−1.5×IQR or above Q3+1.5×IQR)
  **Pydantic**            A Python library for data validation using type annotations
  **PoC**                 Proof of Concept, a working prototype demonstrating feasibility
  **p50 / p95 latency**   The 50th and 95th percentile of response time distribution across a set of requests
  **Hallucination**       When an LLM generates plausible-sounding but factually incorrect information
  **Ground truth**        A curated dataset of questions with known correct answers, used to evaluate system accuracy
  ----------------------- --------------------------------------------------------------------------------------------------------------------------

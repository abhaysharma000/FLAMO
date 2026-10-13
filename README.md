# FLAMO — Autonomous AI Operations Agent

[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688.svg)](https://fastapi.tiangolo.com)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2%2B-orange.svg)](https://github.com/langchain-ai/langgraph)
[![Playwright](https://img.shields.io/badge/Playwright-Chromium-green.svg)](https://playwright.dev/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**FLAMO** is an enterprise-grade, stateful autonomous AI operations agent platform orchestrated using **LangGraph**, **Google Gemini** (`gemini-3.5-flash-lite`), **Playwright Headless Browser Automation**, **FastAPI**, and **Pydantic v2**.

Unlike naive conversational bots or single-prompt wrappers, FLAMO implements a production-grade, evidence-grounded autonomous lifecycle: objective decomposition, multi-agent specialist swarm dispatch, Playwright browser navigation, claim extraction, primary-source evidence comparison, contradiction detection, semantic memory indexing, human-in-the-loop checkpoints, bounded failure recovery, real-time Server-Sent Events (SSE) streaming, and an interactive Control Center interface.

---

## Architecture Overview

FLAMO models autonomous operations as a hierarchical multi-agent state graph orchestrated via LangGraph. The workflow coordinates specialized sub-agents with bounded authority, grounded observations, and persistent semantic memory.

```
                         USER / API / CONTROL CENTER UI
                                      │
                   ┌──────────────────┴──────────────────┐
                   ▼                                     ▼
        REST API & SSE Stream                  WebSocket Connection
       (/api/tasks, /events)                   (/ws/tasks/{task_id})
                   │                                     │
                   └──────────────────┬──────────────────┘
                                      ▼
                        ┌───────────────────────────┐
                        │      SUPERVISOR NODE      │ ◄──────────────────┐
                        └─────────────┬─────────────┘                    │
                                      │ (Route & Plan)                   │
                                      ▼                                  │
                        ┌───────────────────────────┐                    │
                        │       PLANNER AGENT       │                    │
                        └─────────────┬─────────────┘                    │
                                      │ (Structured Decomposition)       │
                                      ▼                                  │
                        ┌───────────────────────────┐                    │
                        │    SPECIALIST DISPATCH    │                    │
                        └─────────────┬─────────────┘                    │
                                      │                                  │
     ┌──────────────────┬─────────────┴─────────────┬──────────────────┐ │
     ▼                  ▼                           ▼                  ▼ │
┌──────────┐     ┌──────────┐                ┌──────────┐       ┌──────────┐
│ RESEARCH │     │ BROWSER  │                │ DOCUMENT │       │ RECOVERY │
│  AGENT   │     │  AGENT   │                │  AGENT   │       │  ENGINE  │
└────┬─────┘     └────┬─────┘                └────┬─────┘       └────┬─────┘
     │                │ (Playwright)              │                  │
     ├────────────────┴─────────────┬─────────────┘                  │
     │                              │                                │
     ▼                              ▼                                │
┌──────────────────┐       ┌──────────────────┐                      │
│ EVIDENCE SERVICE │       │ PERSISTENT MEMORY│                      │
│ • Source Trust   │       │ • SQLite Backend │                      │
│ • Claim Matching │       │ • PgVector Store │                      │
│ • Contradictions │       │ • Cosine Match   │                      │
└────────┬─────────┘       └──────────────────┘                      │
         │                                                           │
         ▼                                                           │
┌───────────────────────────┐                                        │
│    VERIFICATION AGENT     │                                        │
│  (Audit Evidence Claims)  │                                        │
└────────┬──────────────────┘                                        │
         │                                                           │
         ├─► [SENSITIVE ACTION] ─► HUMAN-IN-THE-LOOP ─► [Approve/Reject]
         │
         ├─► [PASSED] ───────────► FINALIZE ─────────► TASK_COMPLETED
         │
         └─► [FLAGGED / FAILED] ─► RECOVERY POLICY ──► (Retry / Replan)
                                         │
                                         └─► Max Retries Exceeded ──► TASK_FAILED
```

---

## 14 Production Upgrades

### Upgrade 1: Evidence-First Research Pipeline
- Grounded data models: `Source`, `Evidence`, `Claim`, and `VerificationResult`.
- Distinguishes 4 verification statuses: `VERIFIED`, `PARTIALLY_VERIFIED`, `CONFLICTING`, `UNVERIFIED`.
- Strict authority classification: Primary documentation & official repos (`weight=1.0`) ranked above secondary blogs (`weight=0.5`).
- Never outputs unsubstantiated claims as verified facts.

### Upgrade 2: Claim Verification & Contradiction Detection
- Automatically extracts claims from research outputs, compares multiple independent sources, and identifies direct contradictions (e.g., framework feature availability or breaking changes across versions).
- Resolves conflicts by preferring authoritative primary documentation and flagging persistent disagreements explicitly in final synthesis.

### Upgrade 3: Playwright Sandboxed Browser Tool & Agent
- Headless Chromium browser automation tool (`app/tools/browser.py`) and specialist `BrowserAgent` (`app/agents/browser_agent.py`).
- Supported actions: `navigate`, `inspect`, `extract_text`, `click`, `type`, `screenshot`.
- Strict sandbox guards: Blocks dangerous URI schemes (`file://`, `javascript:`, `data:`), enforces a 15-second navigation timeout, and limits maximum redirections.

### Upgrade 4: Persistent Semantic Memory
- Decoupled `MemoryStore` interface (`app/services/memory.py`) with support for:
  1. `SqliteMemoryStore` (built-in development backend with stemmed token cosine similarity indexing).
  2. `PgVectorMemoryStore` (production-ready PostgreSQL + pgvector integration).
- Partitioned memory categories: `TASK_MEMORY`, `USER_PREFERENCES`, `FINDINGS`, `REUSABLE_KNOWLEDGE`.
- Query filtering by threshold relevance scores (`min_relevance=0.4`) to prevent context bloat.

### Upgrade 5: Hierarchical Multi-Agent Swarm
- **Supervisor**: Coordinates agent routing, escalation, and conditional graph branch termination.
- **Research Agent**: Scrapes web search indexes and ranks primary sources.
- **Browser Agent**: Interacts with dynamic websites, DOM structures, and JS-rendered pages.
- **Document Agent**: Manages sandboxed file operations in `./workspace/`.
- **Verification Agent**: Audits facts, arithmetic grounding, and cross-source evidence consistency.

### Upgrade 6: Live Control Center with SSE & WebSockets
- Real-time event streaming via Server-Sent Events (`GET /api/tasks/{task_id}/events`) and WebSockets (`/ws/tasks/{task_id}`).
- Streaming timeline dynamically updates task plan, current node, active specialist agent, tool calls, observations, claims, verification scores, and recovery attempts.

### Upgrade 7: Hierarchical Agent Trace Viewer
- Detailed execution tree inspectable via the Control Center side drawer and API (`GET /api/tasks/{task_id}/trace`).
- Event types: `task_started`, `planning_started`, `tool_started`, `tool_completed`, `evidence_collected`, `claim_verified`, `conflict_detected`, `human_approval_required`, and `task_completed`.

### Upgrade 8: Cost & Performance Telemetry
- Real-time metrics tracking: execution duration (seconds), LLM call count, tool invocation count, retry count, and token usage.
- Fallback message: Displays `"Not available from provider"` if the provider does not expose token usage.

### Upgrade 9: Human-In-The-Loop (HITL) Checkpoints
- Tasks triggering sensitive actions (e.g. system configurations, destructive modifications) enter `AWAITING_APPROVAL` status.
- Resumes execution on `POST /api/tasks/{task_id}/approve` or halts on `POST /api/tasks/{task_id}/reject`.
- Control Center displays an interactive banner with one-click **[Approve]** and **[Reject]** buttons.

### Upgrade 10: Advanced Failure Recovery Policies
- Categorizes errors into: `TRANSIENT`, `TOOL_ERROR`, `AUTH_ERROR`, `INVALID_INPUT`, `RATE_LIMIT`, `NETWORK_ERROR`, `LOGIC_ERROR`, and `VERIFICATION_FAILURE`.
- Deterministic recovery actions: exponential backoff, alternate source retrieval, replanning, or graceful degradation.
- Strict iteration and retry ceiling to eliminate infinite loops.

### Upgrade 11: Machine-Readable Evaluation Benchmark Framework
- Benchmark runner (`python -m app.evaluation.benchmark`) executing 35 curated tasks:
  - 10 Arithmetic tasks
  - 10 Research tasks
  - 5 Multi-step composite tasks
  - 5 Failure & bounded recovery tasks
  - 5 Evidence verification & conflict tasks
- Emits machine-readable benchmark reports (`evaluation_report.json`) tracking completion rate (100%), average execution duration, tool selection accuracy, and zero hallucinations.

### Upgrade 12: Security Hardening & Zero Arbitrary Execution
- Path traversal prevention: Strict rejection of absolute paths (`/etc/passwd`, `C:\Windows`) and parent directory escapes (`../`).
- Sandboxed workspace isolation: Confined strictly to `./workspace/`.
- Python AST expression validator: Rejects arbitrary code execution (`__import__`, `eval`, `os.system`).
- Automatic secret redaction: Redacts `GEMINI_API_KEY` and bearer tokens from logs and trace events.

### Upgrade 13: Spectacular Portfolio Demonstration Script
- Run `python scripts/run_demo.py` to observe autonomous multi-framework research, Playwright browser extraction, claim verification, conflict detection, and workspace report generation.

### Upgrade 14: Zero Regression & Preserved MVP Guarantees
- All 27 original automated tests pass without modification.
- Full test suite expanded to 43 unit, integration, browser, and security tests.

---

## Directory Structure

```
Flamo/
├── app/
│   ├── main.py                  # FastAPI application, CLI entrypoint, static files
│   ├── config.py                # Pydantic Settings, environment security configuration
│   ├── api/
│   │   ├── routes_tasks.py      # Task management, execution, HITL approve/reject
│   │   ├── routes_stream.py     # Real-time SSE and WebSocket streaming endpoints
│   │   ├── routes_memory.py     # Semantic memory storage, search, and deletion
│   │   └── routes_health.py     # System health and registered tool inspection
│   ├── agents/
│   │   ├── supervisor.py        # Central workflow supervisor and routing logic
│   │   ├── planner.py           # Objective decomposition and step plan generator
│   │   ├── executor.py          # LLM tool-binding and synthesis coordinator
│   │   ├── research_agent.py    # Specialist research agent (Web search & ranking)
│   │   ├── browser_agent.py     # Specialist browser agent (Playwright automation)
│   │   ├── document_agent.py    # Specialist document agent (Workspace management)
│   │   ├── verification_agent.py# Specialist verification agent (Claim audits)
│   │   ├── verifier.py          # Deterministic verifier and arithmetic validator
│   │   └── recovery.py          # Advanced failure classification and recovery
│   ├── workflows/
│   │   ├── state.py             # FlamoAgentState strongly-typed state definition
│   │   ├── nodes.py             # LangGraph workflow node implementations
│   │   └── graph.py             # LangGraph StateGraph builder and transitions
│   ├── tools/
│   │   ├── registry.py          # Tool registry with validation and metadata
│   │   ├── calculator.py        # Safe arithmetic AST evaluator
│   │   ├── web_search.py        # DuckDuckGo search integration
│   │   ├── url_fetcher.py       # Resilient HTTP web page scraper
│   │   ├── browser.py           # Playwright sandboxed headless browser tool
│   │   ├── file_reader.py       # Sandboxed workspace file reader
│   │   └── workspace.py         # Sandboxed workspace file manager
│   ├── models/
│   │   ├── task.py              # Task schemas, TaskStatus, HITL actions
│   │   ├── plan.py              # ExecutionPlan and PlanStep models
│   │   ├── tool.py              # ToolCallRecord and VerificationResult
│   │   ├── trace.py             # TraceEvent, TraceEventType, and tree schemas
│   │   ├── evidence.py          # Source, Evidence, Claim, EvidencePipelineResult
│   │   └── memory.py            # MemoryCategory, MemoryItem, MemoryQuery
│   ├── services/
│   │   ├── llm.py               # Google Gemini model factory
│   │   ├── database.py          # SQLite TaskRepository implementation
│   │   ├── memory.py            # MemoryStore (SqliteMemoryStore, PgVectorMemoryStore)
│   │   ├── evidence_service.py  # Evidence parsing, claim pairing, conflict analysis
│   │   ├── event_bus.py         # In-memory async pub/sub bus for SSE and WebSockets
│   │   ├── task_service.py      # Lifecycle orchestration, telemetry, and HITL
│   │   └── trace_service.py     # Sanitized trace auditing service
│   └── evaluation/
│       └── benchmark.py         # 35-task benchmark runner and report generator
├── frontend/
│   ├── index.html               # Control Center dashboard with real-time SSE stream
│   ├── style.css                # Premium glassmorphic interface design system
│   └── app.js                   # Reactive event listeners, SSE client, drawer controls
├── scripts/
│   └── run_demo.py              # Portfolio demonstration script
├── tests/
│   ├── test_calculator.py       # Calculator unit tests (5 tests)
│   ├── test_tools.py            # Tool registry isolation tests (6 tests)
│   ├── test_state_and_models.py # State transitions and model tests (4 tests)
│   ├── test_verifier_and_recovery.py # Verification and recovery tests (4 tests)
│   ├── test_api.py              # FastAPI endpoints tests (4 tests)
│   ├── test_end_to_end.py       # End-to-end multi-step workflow tests (4 tests)
│   ├── test_evidence_and_claims.py # Evidence pipeline and conflict detection (4 tests)
│   ├── test_memory.py           # Persistent semantic memory store tests (2 tests)
│   ├── test_hitl.py             # Human-In-The-Loop approval workflow tests (2 tests)
│   ├── test_browser_tool.py     # Playwright browser tool automation tests (3 tests)
│   └── test_security_hardening.py # Security sandboxing and path traversal tests (5 tests)
├── workspace/                   # Isolated agent workspace sandbox directory
├── evaluation_report.json       # Generated benchmark evaluation report
├── requirements.txt             # Project dependencies
├── .env.example                 # Environment configuration template
└── README.md                    # Project documentation
```

---

## Installation & Setup

### 1. Prerequisites
- Python 3.12 or newer
- A Google Gemini API key ([Google AI Studio](https://aistudio.google.com/))

### 2. Setup Environment
```bash
# Clone the repository
git clone https://github.com/your-org/flamo.git
cd flamo

# Create and activate virtual environment
python -m venv .venv

# On Linux/macOS:
source .venv/bin/activate
# On Windows PowerShell:
.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Install Playwright browser binary
python -m playwright install chromium
```

### 3. Configure Environment Variables
Copy `.env.example` to `.env` and configure your settings:
```bash
cp .env.example .env
```

#### Essential Settings:
```ini
# Primary Google Gemini LLM API Key (or GOOGLE_API_KEY)
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-3.5-flash-lite

# Memory Backend: "sqlite" (default deterministic) or "chroma" (semantic vector store)
MEMORY_BACKEND=sqlite
EMBEDDING_MODEL=gemini-embedding-001
CHROMA_PERSIST_DIRECTORY=./chroma_db

# Network Binding & Single-Operator Authentication
# Set HOST=127.0.0.1 for local workstation (safe loopback development mode)
# Set HOST=0.0.0.0 for Docker / remote deployments (requires AUTH_ENABLED=true and SECRET_KEY)
HOST=127.0.0.1
PORT=8000
AUTH_ENABLED=true
OPERATOR_USERNAME=admin

# Generate secure password hash via:
# python -c "from app.services.auth_service import hash_password; print(hash_password('your_secret'))"
OPERATOR_PASSWORD_HASH=pbkdf2_sha256$100000$salt$hash

# Generate 32-byte secret key via:
# python -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=replace_with_random_32_byte_secret_key_in_production
SESSION_EXPIRE_MINUTES=480

# Restrictive CORS: NEVER use wildcard '*' with credentials
CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,http://localhost:8000,http://127.0.0.1:8000

# Storage & Observability
DATABASE_URL=sqlite:///./flamo.db
WORKSPACE_DIR=./workspace
LOG_LEVEL=INFO
```

---

## Deployment & Running FLAMO

### Mode A: Local Workstation Development (Non-Docker)

1. **Build Frontend**:
   ```bash
   cd frontend
   npm install
   npm run build
   cd ..
   ```

2. **Start Backend & Control Center**:
   ```bash
   python -m app.main
   # or with Uvicorn directly:
   uvicorn app.main:app --host 127.0.0.1 --port 8000
   ```

3. **Access Control Center**:
   - Web UI: [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
   - Interactive OpenAPI Docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
   - Liveness Probe: [http://127.0.0.1:8000/api/health/live](http://127.0.0.1:8000/api/health/live)
   - Readiness Probe: [http://127.0.0.1:8000/api/health/ready](http://127.0.0.1:8000/api/health/ready)

### Mode B: Production Docker Deployment

FLAMO includes a multi-stage `Dockerfile` and a hardened `docker-compose.yml` with non-root execution (`flamo` UID 1000), named volumes, resource constraints, and health checks:

1. **Prepare Environment**:
   Ensure `.env` contains valid `GEMINI_API_KEY`, `AUTH_ENABLED=true`, `OPERATOR_PASSWORD` (or `OPERATOR_PASSWORD_HASH`), and `SECRET_KEY`.

2. **Launch with Docker Compose**:
   ```bash
   docker compose up -d --build
   ```

3. **Verify Container Health & Logs**:
   ```bash
   docker compose ps
   docker compose logs -f flamo
   ```

4. **Persistence Volumes**:
   - `flamo_persistent_data`: Houses `flamo.db` (SQLite task/state persistence) and `/app/data/chroma_db` (vector embeddings).
   - `flamo_persistent_workspace`: Houses generated research reports and evidence artifacts.
   - `flamo_persistent_backups`: Houses consistent atomic backups.

---

## Authentication & Access Control

FLAMO features a single-operator security model:
- **Server-Managed Sessions**: In-memory session store generating cryptographically random session tokens with configurable expiration (`SESSION_EXPIRE_MINUTES`).
- **HttpOnly Cookies**: Session cookies set with `HttpOnly`, `SameSite=Lax`, and `Secure` (when `COOKIE_SECURE=true`).
- **CSRF Defense**: All mutating requests (`POST`, `PUT`, `DELETE`) authenticated via cookies require a matching `X-CSRF-Token` header.
- **Bearer Token Support**: Programmatic API clients can supply `Authorization: Bearer <session_id>` (bypasses ambient cookie CSRF requirements).
- **Brute-Force Rate Limiting**: Bounded login attempts (default: 5 failures within 300 seconds per client IP) return HTTP 429.
- **Fail-Closed Public Binding**: When `HOST=0.0.0.0`, the server refuses to boot unless `AUTH_ENABLED=true`, a password/hash is provided, and `SECRET_KEY` is configured.
- **Safe Local Loopback Mode**: Loopback requests (`127.0.0.1`, `localhost`) can run with `AUTH_ENABLED=false` for frictionless local development.

---

## Consistent Backup & Restore

To ensure atomic consistency under SQLite WAL mode and preserve workspace artifacts and vector memory, dedicated scripts are provided:

### 1. Online Consistent Backup
```bash
python scripts/backup.py --tag manual_v1
```
- Uses `sqlite3.Connection.backup()` to safely copy committed pages while the database is live.
- Runs `PRAGMA integrity_check` on the backup.
- Copies all reports from `workspace/` and vector files from `chroma_db/`.
- Calculates SHA-256 checksums and writes a signed `manifest.json`.

### 2. Verified Restore
```bash
python scripts/restore.py --backup-dir backups/backup_20261011_120000_manual_v1
```
- Validates SHA-256 checksums of all backed-up files against `manifest.json`.
- Restores SQLite database using atomic backup connection.
- Restores workspace reports and ChromaDB data.
- Runs `PRAGMA integrity_check` to verify database consistency.

---

## Automated Verification & Test Suites

### Complete Backend Regression Suite:
```bash
# Run all 134 deterministic unit, security, memory, and deployment tests:
pytest -v
```

### Targeted Phase 7 Security Suite:
```bash
pytest tests/test_phase7_security_and_deployment.py -v
```

### Frontend Tests & Production Build:
```bash
cd frontend
npm run test -- --run   # 25 Vitest unit and integration tests
npm run build           # Compiles production TypeScript bundle to dist/
cd ..
```

---

## API Specification

| Method | Endpoint | Access Level | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/health` | Public | System status, model, memory backend, and tool count |
| `GET` | `/api/health/live` | Public | Lightweight container liveness probe (`{"status": "alive"}`) |
| `GET` | `/api/health/ready` | Public | Dependency readiness probe (DB, workspace, API key; 503 if unready) |
| `GET` | `/api/auth/status` | Public | Check operator authentication and auth mode |
| `POST`| `/api/auth/login` | Public (Rate Limited)| Authenticate single operator, returns CSRF token and sets HttpOnly cookie |
| `POST`| `/api/auth/logout` | Authenticated | Revoke session and delete session cookie |
| `POST`| `/api/tasks` | Authenticated (CSRF)| Create and enqueue autonomous agent task |
| `GET` | `/api/tasks` | Authenticated | List persisted tasks |
| `GET` | `/api/tasks/{task_id}` | Authenticated | Retrieve task status, claims, plan, and metrics |
| `GET` | `/api/tasks/{task_id}/trace` | Authenticated | Execution trace events audit log |
| `GET` | `/api/tasks/{task_id}/events`| Authenticated | Real-time Server-Sent Events (SSE) stream |
| `WS`  | `/ws/tasks/{task_id}` | Authenticated | WebSocket trace event stream (closes with 1008 if unauthenticated)|
| `POST`| `/api/tasks/{task_id}/approve` | Authenticated (CSRF)| HITL: Approve sensitive pending action |
| `POST`| `/api/tasks/{task_id}/reject` | Authenticated (CSRF)| HITL: Reject sensitive pending action |
| `POST`| `/api/tasks/{task_id}/cancel` | Authenticated (CSRF)| Cancel active task execution |
| `GET` | `/api/reports` | Authenticated | List generated workspace research reports |
| `GET` | `/api/reports/{filename}` | Authenticated | Preview report content (path-traversal guarded) |
| `GET` | `/api/reports/{filename}/download`| Authenticated | Download report file attachment |
| `POST`| `/api/memory` | Authenticated (CSRF)| Store semantic memory item |
| `GET` | `/api/memory/search` | Authenticated | Query semantic memory with relevance scoring |
| `DELETE`| `/api/memory/{id}` | Authenticated (CSRF)| Delete semantic memory entry |

---

## Security Hardening & Operational Safeguards

1. **Sensitive Data Redaction**:
   - `SensitiveDataFilter` intercepts log streams and redacts Gemini API keys (`AIzaSy...`), passwords, session cookies, and bearer tokens.
   - Execution traces mask credentials before recording to persistence.
2. **Safe Workspace Sandbox**:
   - All file operations are constrained to `WORKSPACE_DIR` via resolved relative path validation. Path traversal (`../`, absolute paths) raises security exceptions.
3. **Safe Expression Evaluator**:
   - Mathematical calculations use a strict AST visitor whitelist. Arbitrary code execution (`eval`, `exec`, `os.system`) is prevented.
4. **Correlation Tracing**:
   - All HTTP requests accept and inject `X-Correlation-ID` for end-to-end request tracing.
5. **Deployment Boundaries & Public Exposure Limitations**:
   - FLAMO is architected for single-operator deployments.
   - When exposing beyond a trusted private network, FLAMO **must** be deployed behind a TLS-terminating reverse proxy (e.g., Caddy, Nginx, Cloudflare) with `COOKIE_SECURE=true`.
   - Never bind to `0.0.0.0` with `AUTH_ENABLED=false`. The application will intentionally refuse to start.


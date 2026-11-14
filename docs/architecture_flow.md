# SentinelARC Architecture & Flow Documentation

> **System Architecture**: SentinelARC is an enterprise-grade, asynchronous, multi-agent academic research and fact-checking platform. Agents operate as distributed micro-services coordinated by a stateless hub-and-spoke state machine over RabbitMQ (AMQP), exposing Model Context Protocol (MCP) tool interfaces and serving a reactive Streamlit web dashboard.

---

## 1. Architectural Paradigm: Asynchronous Micro-Agents (Hub-and-Spoke)

SentinelARC replaces brittle monolithic research scripts with an **asynchronous hub-and-spoke event-driven swarm**. 

```
                          ┌──────────────────────────┐
                          │   Streamlit Web UI       │
                          │   (Port 8501, Auth/Chat) │
                          └─────────────┬────────────┘
                                        │ HTTP POST /research
                                        ▼
                          ┌──────────────────────────┐
                          │   FastAPI Core Engine    │
                          │   (Port 8000, async_main)│
                          └─────────────┬────────────┘
                                        │ In-Memory Invocation
                                        ▼
                          ┌──────────────────────────┐
                          │ AsyncOrchestratorAgent   │
                          │ (Stateless Hub Director) │
                          └─────────────┬────────────┘
                                        │
           ┌────────────────────────────┼───────────────────────────┐
           │ AMQP (TASK_ASSIGN)         │ AMQP (TASK_ASSIGN)        │ AMQP (TASK_ASSIGN)
           ▼                            ▼                           ▼
┌──────────────────────┐    ┌──────────────────────┐    ┌──────────────────────┐
│  AsyncSearchAgent    │    │ AsyncExtractionAgent │    │ AsyncFactCheckerAgent│
│  - HyDE Expansion    │    │ - Batch Semaphore(5) │    │ - 4-Layer NLI Funnel │
│  - 5 Parallel APIs   │    │ - Native PyPDF2      │    │ - Benchmark Anchoring│
│  - Citation Velocity │    │ - Unpaywall/CORE OA  │    │ - Epistemic Weighting│
│  - 1-Hop Lineage Tree│    │ - IMRAD Token Strip  │    │ - Consensus Engine   │
└──────────┬───────────┘    └──────────┬───────────┘    └──────────┬───────────┘
           │ DATA_SUBMIT                │ DATA_SUBMIT               │ DATA_SUBMIT
           └────────────────────────────┼───────────────────────────┘
                                        │
           ┌────────────────────────────┴───────────────────────────┐
           │ AMQP (TASK_ASSIGN)                                     │ AMQP (TASK_ASSIGN)
           ▼                                                        ▼
┌───────────────────────────────┐               ┌───────────────────────────────┐
│     AsyncSynthesisAgent       │               │      AsyncFileSaveAgent       │
│ - 5-Part Survey Paper Taxonomy│               │ - Atomic Tempfile + Rename    │
│ - Executive Consensus Banner  │               │ - Markdown + .meta.json + HTML│
│ - Comparative Technical Matrix│               │ - SHA-256 Checksum            │
│ - Clickable Inline Citations  │               │ - SQLite Reports DB Insert    │
└──────────────┬────────────────┘               └───────────────┬───────────────┘
               │ DATA_SUBMIT                                    │ DATA_SUBMIT
               └────────────────────────┼───────────────────────┘
                                        ▼
                          ┌──────────────────────────┐
                          │ Workflow Complete        │
                          │ (UI Poller picks report) │
                          └──────────────────────────┘
```

### Why Hub-and-Spoke over Linear Daisy-Chaining?
1. **Isolated State Machine**: In a pipeline (Agent A -> Agent B -> Agent C), a failure in Agent B crashes the entire flow with zero recovery. In SentinelARC's Hub-and-Spoke design, every agent communicates exclusively with the `AsyncOrchestratorAgent`. The Orchestrator retains full lifecycle control, retrying failed stages, falling back across secondary models, and pruning completed tasks.
2. **Stateless Concurrency (`task_id`)**: The Orchestrator stores active jobs in `self.active_workflows[task_id]`. There are no global mutable variables, ensuring zero cross-talk across hundreds of concurrent research tasks.
3. **Decoupled Heavy Compute**: Specialized workers (Search, Extract, Fact-Check, Synthesis) scale independently across threads, Docker containers, or Kubernetes pods without altering application logic.

---

## 2. The Complete 6-Stage Research Lifecycle

### Stage 1: Request Initiation & Authentication (`streamlit_app.py` & `async_main.py`)
1. **User Authentication**: The user logs in or registers via Streamlit. Passwords are pre-hashed using `SHA-256` before passing into `bcrypt` (bypassing bcrypt's 72-byte truncation limit while guaranteeing maximum entropy).
2. **Request Dispatch**: The user submits a research prompt (e.g., *"Direct Preference Optimization vs RLHF in LLM Alignment"*). Streamlit dispatches an HTTP `POST` request to `http://synapse-agents:8000/research` containing:
   - `query`: The user's query string.
   - `user_id`: The authenticated integer ID.
   - `task_id`: A unique UUID string (e.g., `task_a8f9b2c1`).
3. **In-Memory Handoff**: FastAPI receives the JSON payload, creates a workflow entry in `AsyncOrchestratorAgent` via `orchestrator.start_research(task_id, query, user_id)`, and immediately returns `{"status": "accepted", "task_id": task_id}` to Streamlit.
4. **Non-Blocking UI Polling**: Streamlit enters a polling loop with `time.sleep(2)` and `st.rerun()`, checking `sentinelarc.db` and `/output/reports/{user_id}/` for the finished artifact.

### Stage 2: Central Orchestration (`src/agents/async_orchestrator.py`)
1. **Workflow Allocation**: The Orchestrator registers `task_id` in `self.active_workflows[task_id]`:
   ```python
   self.active_workflows[task_id] = {
       "task_id": task_id,
       "user_id": user_id,
       "query": query,
       "search_results": [],
       "extracted_content": [],
       "fact_check_results": {},
       "synthesis_report": {},
       "start_time": datetime.utcnow(),
       "status": "searching"
   }
   ```
2. **Task Assignment**: The Orchestrator serializes a `TaskAssignPayload` (`task_type="web_search"`) inside an `ACPMessage` and dispatches it over AMQP directly to the `search_agent` queue.

### Stage 3: Multi-Source Empirical Search (`src/agents/async_search_agent.py`)
1. **HyDE Semantic Query Expansion**: The Search Agent constructs a hypothetical scientific abstract using Groq (or local Ollama fallback) to generate dense semantic keywords, academic acronym expansions, and Boolean query operators.
2. **5-Engine Parallel Ingestion**: Uses `asyncio.gather()` to query 5 scientific engines concurrently:
   - **OpenAlex API**: Broad open metadata, concepts, and citation metrics.
   - **Semantic Scholar API**: Influential citations and TLDR abstracts (with 3-stage exponential backoff for 429 rate limits).
   - **arXiv API**: Preprints and physics/CS literature via direct Atom XML parsing.
   - **PubMed API**: Biomedical and clinical research publications.
   - **Crossref API**: Formal publication records, publisher metadata, and verified DOIs.
3. **Citation Velocity Metric ($\frac{\text{citations}}{\Delta t}$)**: Instead of ranking purely on raw citation counts (which heavily biases toward older papers), the agent computes:
   $$\text{Velocity} = \frac{\text{Total Citations}}{\max(1, \text{Current Year} - \text{Publication Year})}$$
4. **Seminal Anchor Detection**: Identifies breakthrough papers exceeding $3\times$ the batch median citation count, tagging them as foundational reference anchors.
5. **1-Hop Citation Lineage Tree**: Gathers key references and citing papers for the top seminal anchors to build contextual depth.
6. **Search Memoization**: Checks `search_cache` in `output/sentinelarc.db` before network calls ($0.21\text{ms}$ return on cache hit).
7. **Handoff**: Packages up to 10 structured paper metadata objects and transmits them back to Orchestrator via `DATA_SUBMIT`.

### Stage 4: Batch Extraction & Paywall Bypass (`src/agents/async_extraction_agent.py`)
1. **Batch Concurrency**: Receives a single `batch_extract` task and processes papers concurrently bounded by `asyncio.Semaphore(5)`.
2. **Native PDF Stream Parsing**: Detects `.pdf` URLs and downloads the byte stream directly into a memory buffer (`io.BytesIO`), parsing text natively with `PyPDF2` (bypassing slow and lossy HTML DOM scrapers).
3. **Open-Access Paywall Bypass**:
   - Queries **Unpaywall API** (`https://api.unpaywall.org/v2/`) using paper DOIs to locate legal open-access PDF mirrors.
   - Falls back to **CORE API** (`https://api.core.ac.uk/v3/`) for institutional repository full texts.
4. **IMRAD Structure Segmentation & Reference Stripping**: Academic papers dedicate 30% to 50% of their text to bibliographies, author affiliations, and appendices. The Extraction Agent identifies standard IMRAD headers (*Introduction, Methods, Results, Discussion*) and strips bibliography sections, cutting context tokens by ~45% and preventing LLM context window overflows.
5. **Quantitative Benchmark Extraction**: Employs rigorous regex patterns to isolate empirical benchmarks (e.g., `87.4% accuracy`, `3.2x speedup`, `p < 0.001`, `12ms latency`), packaging them into `numerical_benchmarks`.
6. **Document Cache**: Persists parsed clean texts in `document_cache` ($0.42\text{ms}$ retrieval).
7. **Handoff**: Returns clean full texts, IMRAD sections, and numerical benchmarks via `DATA_SUBMIT`.

### Stage 5: 4-Layer Grounded Scientific Verification Funnel (`src/agents/async_fact_checker_agent.py`)
Unlike naive LLM fact-checkers that perform zero-shot parametric "truth tests" (which hallucinate heavily), SentinelARC runs a **4-Layer Grounded Verification Funnel**:

1. **Layer 1: Grounded Natural Language Inference (NLI)**:
   - **Premise**: The raw extracted IMRAD text snippet from the source paper.
   - **Hypothesis**: The extracted scientific claim.
   - **Classification**: LLM acts as a strict NLI evaluator outputting `ENTAILMENT`, `CONTRADICTION`, or `NEUTRAL / UNVERIFIABLE`, accompanied by a verbatim 1-sentence grounding quote.
2. **Layer 2: Quantitative & Benchmark Anchoring**:
   - Isolates all numbers, metrics, and percentages in the hypothesis.
   - Cross-matches against `numerical_benchmarks` using regex and semantic alignment.
   - Flags digit swaps, unit errors, or fabricated speedups.
3. **Layer 3: Epistemic Weighting (Source Credibility)**:
   - Calibrates NLI confidence with empirical metadata:
     - Base NLI Confidence: $0.0 - 1.0$
     - Crossref DOI Verified: $+0.05$
     - High Citation Velocity / Peer Reviewed: $+0.10$
     - Non-reviewed Preprint with 0 citations: $-0.05$
4. **Layer 4: Cross-Document Scientific Consensus Engine**:
   - Cross-references entailed claims across all papers.
   - If Paper A claims *"Method X improves generalization"* while Paper B claims *"Method X causes catastrophic forgetting under condition Y"*, the status automatically shifts to `CONTESTED / SCIENTIFIC DEBATE`.
5. **Fact Cache**: Stores results in `fact_check_cache` ($0.34\text{ms}$).
6. **Handoff**: Emits comprehensive verification breakdown, verified claims list, contested debates, and epistemic confidence scores to the Orchestrator.

### Stage 6: 5-Part Survey Paper Synthesis (`src/agents/async_synthesis_agent.py`)
1. **Taxonomy Enforcement**: Synthesizes a structured survey paper strictly formatted into 5 sections:
   - **Section 1: Executive Consensus & Disagreement Banner**: Displays high-level consensus, contested debates, and epistemic confidence badges.
   - **Section 2: Comprehensive Comparative Technical Matrix**: A Markdown comparison table summarizing:
     - `Paper / Method`
     - `Datasets / Benchmarks`
     - `Reported Metrics`
     - `NLI Entailment Status`
     - `Epistemic Tier`
   - **Section 3: Thematic Deep Dives & Synthesis**: Methodological taxonomies, theoretical foundations, and empirical trade-offs across papers.
   - **Section 4: Critical Open Challenges & Vulnerabilities**: Limitations, failure modes, scalability bottlenecks, and benchmark saturation.
   - **Section 5: Grounded Epistemic Bibliography**: Full citations with verified DOIs, open-access URLs, publication venues, and citation counts.
2. **Clickable Inline Citations**: Strictly enforces markdown link citations throughout prose (e.g., `[Vaswani et al.](https://doi.org/...)` or `[^1]`), eliminating unanchored claims.
3. **Synthesis Cache**: Checks `synthesis_cache` for identical query/source pairings ($< 1\text{ms}$).
4. **Handoff**: Sends finalized report markdown to Orchestrator via `DATA_SUBMIT`.

### Stage 7: Atomic Persistence & Multi-Tenant Storage (`src/agents/async_file_save_agent.py`)
1. **User Isolation**: Formats destination path to `/output/reports/{user_id}/` (e.g., `/output/reports/1/`).
2. **POSIX Atomic Tempfile Write**:
   - Writes raw content to a unique temporary file (`.tmp_xyz`) in the target directory.
   - Performs `os.replace(temp_path, final_path)`, which is an atomic filesystem operation on POSIX kernels.
   - Prevents zero-byte file corruptions if processes are terminated mid-write.
3. **Artifact Ecosystem Generated**:
   - **Markdown Report**: `research_report_YYYYMMDD_HHMMSS.md`
   - **Metadata Sidecar**: `research_report_YYYYMMDD_HHMMSS.meta.json` containing query, timestamp, sources count, verified facts count, SHA-256 hash, and user ID.
   - **Standalone HTML Export**: Beautifully styled self-contained HTML document with clean typography and responsive tables.
4. **SQLite Persistence**: Directly connects to `output/sentinelarc.db` using native `sqlite3` driver with Write-Ahead Logging (WAL) to insert records into the `reports` table.
5. **Handoff**: Emits completion payload to Orchestrator. The Streamlit UI poller detects the database entry and file, immediately rendering the interactive report on screen!

---

## 3. Dual-Mode Execution Architecture

SentinelARC supports two distinct operational modes:

| Feature | Deep Research Mode | Direct Bypass (General Chat) |
|---|---|---|
| **Trigger** | Research query, "Research" button, or academic prompt | General conversational prompt |
| **Backend Route** | `POST /research` | `POST /general_chat` |
| **Execution** | Asynchronous Multi-Agent Swarm (AMQP) | Direct synchronous streaming proxy |
| **Workers Involved** | Search, Extraction, FactChecker, Synthesis, FileSave | Direct Groq/Ollama LLM connection |
| **End-to-End Latency** | 22–31 seconds | Sub-second (< 800ms) |
| **Output Artifacts** | Markdown Report, `.meta.json`, HTML, DB row | Streamed chat response in UI |
| **Fact-Checking** | 4-Layer Grounded NLI Funnel | Single-shot model reasoning |

---

## 4. Multi-Tier Caching Architecture

To achieve low latency and avoid redundant network and LLM costs, SentinelARC features multi-tier SQLite caching at `output/sentinelarc.db`:

```
User Query ──► [Search Cache] ──(Hit)──► Instant Sources (0.21ms)
                     │ (Miss)
                     ▼
              Multi-Source Web Search
                     │
Paper URLs ──► [Document Cache] ─(Hit)──► Instant Clean Text (0.42ms)
                     │ (Miss)
                     ▼
              Batch Extraction & Paywall Bypass
                     │
Claims/Premise►[Fact Cache] ────(Hit)──► Instant NLI Verification (0.34ms)
                     │ (Miss)
                     ▼
              4-Layer NLI Verification Funnel
                     │
Report Context►[Synthesis Cache]─(Hit)──► Instant Final Report (0.89ms)
                     │ (Miss)
                     ▼
              5-Part Survey Synthesis
```

---

## 5. Summary of System Specifications

- **Message Broker**: RabbitMQ 3.x (Management on `:15672`, AMQP on `:5672`).
- **Core API Engine**: FastAPI + Uvicorn on `:8000`.
- **Frontend Dashboard**: Streamlit on `:8501`.
- **MCP Primary Tooling Server**: FastAPI on `:8001` (SSE streaming & scraping).
- **MCP Filesystem Server**: FastAPI on `:8002` (Sandboxed file operations with MCP Roots).
- **Primary LLM**: Groq API (`qwen/qwen3.8-27b` or `llama-3.3-70b-versatile`).
- **Local Fallback LLM**: Ollama (`http://localhost:11434`).
- **Database Engine**: SQLite 3 with Write-Ahead Logging (`output/sentinelarc.db`).
- **Monitoring & Telemetry**: Prometheus on `:9090`, Grafana on `:3000`.

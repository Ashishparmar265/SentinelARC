# SentinelARC Architecture & Flow Documentation

> **Architecture Update Note**: This documentation has been modernized for the SentinelARC platform. Where applicable, assume that agents now run under the Phantom Supervisor (CRIU) runtime and communicate through the C++ AMQP Interceptor.



This document explains the overarching system flow of SentinelARC. It breaks down how the individual Python files interact, the underlying message broker system, and the "why" behind the distributed multi-agent approach.

---

## 1. Architectural Paradigm: Asynchronous Micro-Agents
SentinelARC is not a traditional monolith script. It is built entirely on a publish/subscribe (Pub-Sub) event-driven architecture using **RabbitMQ**.

### Why Pub/Sub?
When conducting deep academic research, you cannot rely on a sequential pipeline. If the model fetches 10 papers, downloading, scraping, parsing, fact-checking, and synthesizing them synchronously could take upwards of 15 minutes. Using an async message bus ensures that:
- Components can scale horizontally (e.g., you can spin up 3 Extraction Agents down the road).
- The system is incredibly fault-tolerant. If the Fact-Checker agent crashes on paper #3, the message remains in the queue, and the orchestrator doesn't lose the entire process.
- Each Agent acts independently, triggered only by rigid `ACPMessage` payloads.

---

## 2. The Core Flow (Step-by-Step)

The research pipeline starts the moment the user types a query into the Streamlit dashboard and traverses a 6-step lifecycle. 

### Step 1: The Request (`streamlit_app.py` & `main.py`)
1. User enters a query (e.g., "RAG graph implementation").
2. Streamlit calls the lightweight FastAPI endpoint via an HTTP POST request to `http://synapse-agents:8000/research`.
3. The FastAPI server (`main.py`) converts this HTTP JSON into an internal RabbitMQ message and routes it to the `async_orchestrator.py` via the `TASK_ASSIGN` protocol.

### Step 2: Orchestration (`async_orchestrator.py`)
**Role:** The mastermind of the system. 
**Flow:** The orchestrator maintains the state machine for the current research cycle. 
1. It receives the prompt and immediately assigns a `web_search` task payload. 
2. It pushes this payload onto the `search_agent` queue.
3. It waits. As progress logs fly back across the bus, the orchestrator updates its internal `self.extracted_content` arrays.

### Step 3: Source Identification (`async_search_agent.py`)
**Role:** Finding empirical data.
**Flow:** 
1. Intercepts the query and passes it into local **Ollama** (Llama 3.1) to magically "expand" the query into complicated Boolean operators (`(RAG OR "Retrieval Augmented") AND Graph`).
2. Fires the query against the **Semantic Scholar API**. 
3. If Semantic Scholar fails (due to 429 rate limits), it seamlessly transitions into the XML-based **arXiv API Fallback**.
4. Packages a JSON list of 10 paper dictionaries containing URLs, DOIs, and Titles.
5. Emits them back to the Orchestrator via `DATA_SUBMIT`.

### Step 4: Web Extraction (`async_extraction_agent.py`)
**Role:** Parsing the actual text from the internet.
**Flow:**
1. The Orchestrator rips apart the 10 papers and assigns 10 parallel `extract_content` tasks to the Extraction Agent.
2. The agent utilizes **Model Context Protocol (MCP)** toolings. It calls the `Primary Tooling Server` to execute `browse_and_extract` against the URL. 
3. It packages the raw 5000+ words of text and transmits it back. (If a site blocks scraping, it falls back to the Academic Abstract provided in Step 3).

### Step 5: Critical Fact-Checking (`async_fact_checker_agent.py`)
**Role:** Mitigating LLM Hallucinations natively.
**Flow:**
1. The Orchestrator aggregates the text and passes it here. 
2. The agent splits the text into semantic sentences mapping to scholarly indicators (e.g., sentences with the word "shows", "proposes", "is").
3. Each individual sentence is fed individually to Ollama, demanding a `"VALID: True"` or `"VALID: False"` confirmation accompanied by a `CONFIDENCE` float and `EVIDENCE` summary.
4. Returns an aggregated Confidence Score. If the score is `< 0.70`, the Orchestrator is programmed to throw the papers out and start over at Step 3 with a different query.

### Step 6: Synthesis & Finalization (`async_synthesis_agent.py` & `async_file_save_agent.py`)
**Role:** Writing the Markdown Report.
**Flow:**
1. The Orchestrator hands the fully vetted, highly confident dataset over.
2. The Synthesis agent sequentially commands Ollama to write the:
   - `_create_introduction()`
   - `_create_source_analysis()` (For all 5 verified papers separately)
   - `_create_conclusion()`
3. Combines them into a Markdown blob and dispatches it to the File Save Agent.
4. The **File Save Agent** performs directory validation checks and writes the final Markdown document identically formatted as `research_report_YYYYMMDD_HHMMSS.md` onto the underlying volume mapped Docker partition.
5. The Streamlit loop detects the appearance of this file locally and automatically injects it into the frontend!

---

## [Update: 2026-04-04] Advanced Search Refactoring
The architecture of SentinelARC has been fundamentally upgraded to a multi-source, multi-hop pipeline. 

### Previous Implementation
- **Search**: A completely synchronous process querying a single API (Semantic Scholar).
- **Reranking**: Non-existent. It scraped the first 10 papers indiscriminately.
- **Extraction**: Relied entirely on the MCP web scraper, which often failed on pure PDF links.
- **Synthesis**: Fed all data into a single, massive context window which caused the LLM to skip critical academic details.

### New Implementation (v2)
- **Parallel Source Identification:** `asyncio.gather()` is now utilized in `async_search_agent.py` to simultaneously hit Semantic Scholar, ArXiv, and PubMed. 
- **LLM Cross-Encoder Reranking:** Before extraction, Llama 3.1 actively drops scientifically irrelevant metadata from the search results to clean the pipeline.
- **Native PDF Ingestion:** `PyPDF2` was securely injected into the backend Docker container, allowing `async_extraction_agent.py` to bypass MCP scraping and ingest binary PDF streams directly from open-access journals.
- **Recursive Mapping:** The Orchestrator now contains a state-machine hook that actively intercepts high-citation "Anchor Papers" and optionally triggers an entirely new workflow cycle to recursively map citation curves. 
- **Multi-Hop RAG Synthesis:** `async_synthesis_agent.py` dynamically prompts the LLM to slice complex research queries into three granular sub-questions. It answers them sequentially before stitching them together for near-perfect factual density.

---

## [Update: 2026-04-04] SaaS & Multi-Tenant Transformation

The platform has been scaled from a research tool into a full-stack SaaS environment.

### 1. Multi-User Identity & Data Isolation
- **Authentication Gateway:** `streamlit_app.py` now implements a secure login/registration gate using **SQLAlchemy** and **PassLib**.
- **User-Scoped Storage:** The `AsyncFileSaveAgent` and `AsyncOrchestratorAgent` now propagate a `user_id` through the RabbitMQ bus. Final reports are dynamically routed to `/output/reports/{user_id}/`, ensuring total data isolation between users.
- **Database Persistence:** A local SQLite database (`sentinelarc.db`) tracks user credentials and research history.

### 2. General AI "Direct Bypass" Mode
- **Zero-Latency Proxy:** To support simple queries without the overhead of the agent swarm, a new `/general_chat` FastAPI endpoint was added to `async_main.py`.
- **Offline LLM Execution:** This endpoint proxies requests directly to a local **Ollama** instance, allowing for sub-second response times for general assistance.
- **Conversational Memory:** Streamlit maintains a `chat_history` array that is piped to the backend, enabling persistent context for General AI sessions.

### 3. Optimized Container Mesh
- **Layered Dependencies:** Docker builds are now partitioned by service (Agents vs. Dashboard vs. MCP) to optimize for speed and deployment size.
- **Health-Aware Orchestration:** The service mesh uses Docker `healthchecks` to ensure RabbitMQ and the MCP Tooling layer are fully booted before launching the resource-heavy AI Swarm.


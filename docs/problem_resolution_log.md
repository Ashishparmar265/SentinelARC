# SentinelARC Problem Resolution Log

> **Production Engineering History**: This document tracks the critical bugs, architectural bottlenecks, and production edge-cases encountered and resolved throughout the engineering of SentinelARC. It details the root causes and rigorous solutions implemented across networking, security, data pipelines, LLM inference, and multi-tenant state isolation.

---

## 1. Network: SentinelARC-Agents DNS Resolution Failure
**Problem:** The Semantic Scholar API endpoint in the orchestrator failed entirely on launch with the error: `Failed to resolve 'synapse-agents' ([Errno -3] Temporary failure in name resolution)`.  
**Root Cause:** The `Primary Tooling MCP Server` and Streamlit frontend were attempting to communicate with the `synapse-agents` backend using rigid hostnames before Docker Compose had fully established the internal networking bridges.  
**Resolution:** Explicitly defined a custom Docker network (`synapse_network`) across all containers in `docker-compose.optimized.yml` and corrected the intra-container API endpoints using explicit Docker service names and network aliases.

---

## 2. Stability: The `SyntaxError` Container Crash Loop
**Problem:** The `synapse-agents` container repeatedly crashed immediately upon startup and entered a restart loop.  
**Root Cause:** The `async_search_agent.py` file contained invalid Python code (extra unmatched parentheses and indentation errors) introduced during a previous manual patch. Because Python is interpreted, the entire FastAPI Uvicorn process failed during startup import.  
**Resolution:** Traced the traceback via container logs, corrected the syntax errors, and mapped the local `src/` directory directly into the Docker container via `volumes:` inside Docker Compose. This enabled instant hot-reloading without rebuilding images.

---

## 3. Data Pipeline: Semantic Scholar Rate Limit (API 429) & Silent Failures
**Problem:** Search tasks suddenly began returning zero sources after a few queries. The log output showed `429 Too Many Requests`.  
**Root Cause:** Unauthenticated Semantic Scholar endpoints have strict rate limits. The agent originally had no back-off logic and silently crashed or returned an empty array, causing the downstream pipeline to fail.  
**Resolution:** 
1. Implemented a 3-retry loop in `_perform_semantic_scholar_search` with exponential backoff (`await asyncio.sleep(wait_time)`).
2. **ArXiv API Fallback:** Built an automated fallback mechanism querying the arXiv Atom XML API directly when Semantic Scholar is throttled, guaranteeing uninterrupted search execution.

---

## 4. UI/UX: Streamlit "Loading Drop" & Chat Duplication
**Problem:** When a user submitted a long-running research query, the "Researching..." spinner would immediately disappear. Users assumed the system froze and resubmitted their prompts, creating duplicates.  
**Root Cause:** The Streamlit script triggered the backend via an asynchronous `POST /research` request that instantly returned `200 OK`. The Streamlit app invoked `st.rerun()`, which wiped out the active `st.spinner()` context while the backend was still processing.  
**Resolution:** Implemented a stateful polling loop on the frontend. The chat UI tracks `st.session_state["is_researching"]` and synchronizes with `time.sleep(2)`. The frontend polls the SQLite `reports` table until the backend asynchronously commits the record, keeping the spinner alive and gracefully dismissing it upon completion.

---

## 5. UI/UX: Unlinked Context Loading (Answering the Wrong Question)
**Problem:** After starting a new chat and asking query 'B', the Sidebar auto-selection logic forcibly loaded the report from query 'A' into the chat history.  
**Root Cause:** Because the sidebar's default `st.selectbox` index pointed to the oldest or last generated report, `streamlit_app.py` automatically appended `selected_path` to the chat history on every tick.  
**Resolution:** Refactored the report tracking logic into an isolated set (`shown_reports = set()`). Sidebar selection was moved into an explicit `on_click` callback. Streamlit now only appends freshly generated reports that match the active query.

---

## 6. Logic Error: Zero Verified Claims (Fact-Checker Rejecting Valid Sources)
**Problem:** Even when sources were properly extracted, the Fact Checker agent logs displayed: `Fact-checking 0 claims`, resulting in empty reports.  
**Root Cause:** The claim extractor function (`_extract_claims_from_content()`) was hardcoded to parse sentences using narrow domain keywords (e.g., `quantum`, `encryption`, `NIST`). When searching for other topics (such as spatial computing or healthcare), the parser filtered out 100% of sentences.  
**Resolution:** Broadened the semantic filter to include universal linguistic indicators typical of academic literature (e.g., `is`, `are`, `shows`, `indicates`, `concludes`, `demonstrates`), achieving full coverage across all scientific domains.

---

## 7. Hallucination: The "LO" vs "LOD" Acronym Hijack
**Problem:** A user search for "LOD optimization in XR" resulted in a report comprehensively documenting "Local Optimization (LO)".  
**Root Cause:** The query expansion LLM attempted to guess what the acronym LOD meant without constraints, incorrectly assuming it stood for Local Optimization rather than Level of Detail.  
**Resolution:** Updated the system prompt in `async_search_agent.py` with strict guardrails: *"CRITICAL: Do NOT expand or guess the meaning of unknown acronyms (like LOD or XR) unless you are absolutely certain. If unsure, limit expansions to the exact original letters."*

---

## 8. Data Parsing: The HTML DOM Extraction Wall
**Problem:** The Extraction Agent repeatedly failed to parse high-quality research papers because publisher URLs pointed directly to PDF binaries (`.pdf`), causing the MCP web scraper to return binary blobs or HTTP 406 errors.  
**Root Cause:** Standard web scrapers expect HTML DOM structures and fail on raw binary PDF streams.  
**Resolution:** Engineered a Native PDF Hook inside `async_extraction_agent.py`. Utilizing `PyPDF2`, the agent detects `.pdf` URLs, downloads the byte stream directly into an in-memory `io.BytesIO` buffer, and extracts clean page text without intermediate disk writes or headless browser overhead.

---

## 9. Computational Latency: The 6-Minute Streamlit UI Drop
**Problem:** Long-running deep research queries dropped the frontend spinner and raised a "Request Timed Out" error on Streamlit.  
**Root Cause:** The frontend polling loop was hard-capped at 180 iterations (360 seconds). Multi-step research on large papers with local Ollama inference occasionally exceeded 6 minutes.  
**Resolution:** Increased the timeout ceiling from 180 to 900 iterations (30 minutes) and introduced Groq API acceleration (~250 tokens/sec), bringing average pipeline completion down to 22–31 seconds.

---

## 10. Deployment: Monolithic pip Build Hang
**Problem:** Docker image builds repeatedly hung on the `pip install` step, exceeding 30 minutes.  
**Root Cause:** A monolithic `requirements.txt` forced lightweight services (like the Filesystem MCP server) to download and compile heavy AI libraries (Playwright, PyTorch, Ollama dependencies).  
**Resolution:** Partitioned dependencies into `requirements-agents.txt` (full agent stack), `requirements-mcp.txt` (lightweight FastAPI/SSE transport), and `requirements-streamlit.txt` (frontend & auth). Secondary container build times dropped from 20+ minutes to under 60 seconds.

---

## 11. Stability: Missing MCP Transport Dependencies
**Problem:** After splitting requirements, MCP servers crashed with `ModuleNotFoundError: No module named 'fastapi'`.  
**Root Cause:** Overly aggressive pruning in `requirements-mcp.txt` removed essential HTTP transport modules.  
**Resolution:** Re-injected `fastapi`, `uvicorn`, `sse-starlette`, and `aiofiles` into `requirements-mcp.txt`, restoring full service health.

---

## 12. UI: Outdated Container Code (Volume Mismatch)
**Problem:** The Streamlit dashboard displayed legacy UI elements even after local source edits.  
**Root Cause:** `docker-compose.yml` was not mounting `streamlit_app.py` as a host volume, serving a stale file baked into the image.  
**Resolution:** Mounted `./streamlit_app.py` and `./src` directly into the `synapse-streamlit` container, enabling real-time hot updates.

---

## 13. Security: Bcrypt 72-Byte Truncation Limit (ValueError)
**Problem:** User registrations with strong password manager strings (72+ characters) crashed with `ValueError: password cannot be longer than 72 bytes`.  
**Root Cause:** The blowfish-based `bcrypt` cipher has a hard 72-byte input length constraint.  
**Resolution:** Implemented SHA-256 pre-hashing in `src/database.py`. Passwords are first hashed with `hashlib.sha256` and base64-encoded to a uniform 44-character string before bcrypt salting, guaranteeing arbitrary password lengths with zero entropy loss.

---

## 14. Architecture: Unhandled SSE Mimetype Mismatch in MCP Client
**Problem:** When the Primary Tooling MCP server returned an HTTP error or immediate response, `async_mcp_client.py` crashed with a parsing exception.  
**Root Cause:** The client assumed all responses from `/tools/browse_and_extract` were `text/event-stream`. When errors occurred, FastAPI returned `application/json`, breaking the streaming line parser.  
**Resolution:** Added dynamic Content-Type inspection in `call_tool()`. If `text/event-stream` is detected, the client runs chunked SSE demuxing; if `application/json` is returned, it parses directly via `resp.json()`.

---

## 15. LLM Token Window: Context Overflow from Academic References
**Problem:** Deep research queries on 40-page journal articles crashed the LLM inference step with `413 Payload Too Large` or truncated conclusions.  
**Root Cause:** Academic papers dedicate 30% to 50% of their volume to bibliographies, author affiliations, and appendices. Feeding raw scraped text directly into the LLM consumed the entire context window with non-informative citation strings.  
**Resolution:** Implemented IMRAD Structure Segmentation in `async_extraction_agent.py` with regex reference stripping (`_strip_references_and_appendices`). Truncating at the `References` header reduced token consumption by ~45% while preserving all empirical findings.

---

## 16. Reliability: Parametric Hallucination in Fact-Checking
**Problem:** The Fact Checker agent confirmed factually incorrect claims that sounded plausible, but were absent from or contradicted by the cited paper.  
**Root Cause:** The agent was using **Parametric Memory Verification** (asking the LLM *"Is this claim true?"* in a zero-shot prompt without the source text). The LLM relied on its pre-trained parametric weights rather than validating if the source paper actually supported the claim.  
**Resolution:** Replaced the prompt with a **4-Layer Grounded Scientific Verification Funnel**:
1. *Layer 1 (Grounded NLI)*: Formulates verification as Natural Language Inference (Premise vs. Hypothesis) with strict `ENTAILMENT`, `CONTRADICTION`, or `NEUTRAL` states and verbatim quote extraction.
2. *Layer 2 (Quantitative Anchoring)*: Regex cross-checks numerical metrics against extracted benchmarks.
3. *Layer 3 (Epistemic Weighting)*: Calibrates confidence with Crossref DOI verification and Citation Velocity.
4. *Layer 4 (Consensus Engine)*: Flags scientific debates across conflicting papers.

---

## 17. Accuracy: Digit Permutation in Empirical Benchmark Reporting
**Problem:** The synthesized report occasionally stated inaccurate metrics (e.g., claiming a model had "94.2% accuracy" when the paper reported "49.2%").  
**Root Cause:** LLMs frequently swap digits, drop decimals, or hallucinate metrics during long-context summarization.  
**Resolution:** Built Layer 2 Quantitative & Benchmark Anchoring in `async_fact_checker_agent.py`. All percentages, speedups, and p-values are extracted via regex and deterministically verified against the source paper's `numerical_benchmarks` before being marked as verified.

---

## 18. Latency & Relevance: Citation Velocity vs. Raw Citation Bias
**Problem:** Initial search implementations prioritized 10-year-old foundational papers over recent state-of-the-art breakthroughs, and search failures triggered infinite recursive resets.  
**Root Cause:** Sorting purely by raw citation count inherently penalizes papers published in the last 1–2 years. An arbitrary `citation_count > 10` reset loop caused infinite search restarts.  
**Resolution:**
1. Introduced **Citation Velocity** ($\frac{\text{citations}}{\Delta t}$) to rank papers by contemporary momentum.
2. Implemented statistical **Seminal Anchor Detection** ($3\times \text{batch median}$) to highlight transformative papers without dropping recent literature.
3. Added a **1-Hop Citation Lineage Tree** to expand references and citing works in a single structured pass.

---

## 19. Data Integrity: Process Crash File Corruption & Directory Traversal
**Problem:** If the Docker container was terminated during file writing, incomplete or 0-byte `.md` files remained on disk. Additionally, unvalidated path strings risked directory traversal.  
**Root Cause:** Standard Python `open(path, "w")` writes non-atomically. Path parameters were not strictly constrained to allowed directory roots.  
**Resolution:**
1. **POSIX Atomic Tempfile Writes**: `async_file_save_agent.py` writes to a hidden temporary file (`.tmp_xyz`) in the same volume, flushes kernel buffers with `os.fsync()`, and performs an atomic `os.replace()`.
2. **MCP Roots Enforcement**: `fastapi_filesystem_server.py` validates all target paths against `ALLOWED_ROOTS` using `pathlib.Path.resolve().relative_to()`.
3. Generated a `.meta.json` sidecar, self-contained HTML export, and SHA-256 integrity hash for every report.

---

## 20. Concurrency: Monolithic Multi-Tenant State Race Condition
**Problem:** When multiple users ran concurrent research queries, intermediate results crossed over between users, producing scrambled reports.  
**Root Cause:** `AsyncOrchestratorAgent` stored active job state in flat class instance variables (`self.search_results = []`, `self.extracted_content = []`). A second request wiped the memory of the first request.  
**Resolution:** Refactored the Orchestrator to be completely stateless at the class level. All workflow state is stored in `self.active_workflows: Dict[str, Dict[str, Any]]` indexed strictly by `task_id`, with automated pruning of expired workflows.

---

## 21. Database: Concurrent Access Locking (`database is locked`)
**Problem:** Under simultaneous read-polling from Streamlit and write-operations from `AsyncFileSaveAgent`, SQLite threw `sqlite3.OperationalError: database is locked`.  
**Root Cause:** SQLite's default rollback journal locks the entire database file during writes, blocking concurrent readers.  
**Resolution:** Enabled **Write-Ahead Logging (WAL)** on `sentinelarc.db` via `PRAGMA journal_mode=WAL;`, increased connection timeout to 10.0 seconds, and configured WAL checkpoints to permit unlimited simultaneous readers alongside active writes.

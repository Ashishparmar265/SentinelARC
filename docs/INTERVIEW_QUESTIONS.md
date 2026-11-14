# SentinelARC: 100 System Design & Technical Interview Questions

This document is a comprehensive interview preparation guide covering SentinelARC's architecture, distributed messaging, agentic pipelines, RAG innovations, and system design trade-offs.

---

## Part 1: Architecture & Microservices Fundamentals (Q1–Q30)

**Q1: What is SentinelARC?**  
**A:** SentinelARC is an enterprise-grade, asynchronous multi-agent academic intelligence and research synthesis framework. It coordinates a specialized swarm of autonomous agents to discover, extract, fact-check, and synthesize peer-reviewed literature into structured survey papers with verifiable citations.

**Q2: What is the core architectural topology of SentinelARC?**  
**A:** It uses a stateless **Hub-and-Spoke Event-Driven Architecture**. The `AsyncOrchestratorAgent` acts as the central state director, delegating specialized sub-tasks over RabbitMQ to autonomous worker agents (`SearchAgent`, `ExtractionAgent`, `FactCheckerAgent`, `SynthesisAgent`, and `FileSaveAgent`).

**Q3: Why is RabbitMQ used instead of direct HTTP REST calls between agents?**  
**A:** Microservice decoupling, queue persistence, and backpressure management. Heterogeneous tasks (e.g., 10-second PDF extraction vs. 1-second fact check) would cause HTTP connection timeouts and socket starvation. RabbitMQ queues decouple producers from consumers, buffer traffic spikes, and enable competing consumer horizontal scaling.

**Q4: What protocol governs communication between agents in SentinelARC?**  
**A:** The **Agent Communication Protocol (ACP)**, an asynchronous messaging specification defined using Pydantic schemas in `src/protocols/acp_schema.py`. It standardizes message envelopes with fields like `msg_id`, `sender_id`, `receiver_id`, `msg_type`, `payload`, and `timestamp`.

**Q5: What are the primary ACP message types?**  
**A:** `TASK_ASSIGN`, `STATUS_UPDATE`, `DATA_SUBMIT`, `LOG_BROADCAST`, `VALIDATION_REQUEST`, `VALIDATION_RESPONSE`, and `ERROR_REPORT`.

**Q6: What framework powers the HTTP API gateway, and on which port does it listen?**  
**A:** FastAPI running asynchronously under Uvicorn on port `8000`.

**Q7: How does FastAPI initiate a research workflow without blocking the HTTP worker thread?**  
**A:** The `/research` endpoint accepts the request, validates the schema with Pydantic, calls the in-memory orchestrator's `start_research()` async task, and immediately returns a `200 OK` JSON response with a unique `task_id` (`status: "task_received"`).

**Q8: What framework powers the frontend dashboard, and on which port does it run?**  
**A:** Streamlit running on port `8501`.

**Q9: How does the Streamlit frontend stay synchronized with backend research progress?**  
**A:** Streamlit polls the local SQLite database (`output/sentinelarc.db`) every 2 seconds for newly inserted report records matching the current `user_id`, updating the UI reactively without maintaining stateful WebSockets.

**Q10: What is the Model Context Protocol (MCP) in SentinelARC?**  
**A:** MCP is an open standard that decouples tools and execution environments from AI agents. SentinelARC containerizes tools into dedicated MCP microservices (`primary-tooling-server` on port 8001 and `filesystem-server` on port 8002).

**Q11: What security mechanism does the Filesystem MCP server implement?**  
**A:** **MCP Roots Boundary Enforcement**. The server strictly validates that file read/write paths resolve inside authorized directories (`/app/output`, `/app/temp`). Path traversal attempts (`../../etc/passwd`) are rejected at the protocol layer.

**Q12: How do worker agents discover and execute MCP tools?**  
**A:** Agents inherit from `MCPClientMixin`, which performs tool discovery and executes structured JSON-RPC / REST payloads over HTTP, automatically handling Server-Sent Events (SSE) streaming demuxing.

**Q13: What database is used for local report persistence and cache memoization?**  
**A:** SQLite via Python's native `sqlite3` standard library, located at `output/sentinelarc.db`.

**Q14: Why use native `sqlite3` instead of an ORM like SQLAlchemy inside worker agent containers?**  
**A:** Zero extra image dependencies, faster container startup, minimal memory footprint, and immunity to ORM connection pooling bugs across async sub-processes.

**Q15: What is the role of the `AsyncLoggerAgent`?**  
**A:** It listens to RabbitMQ topic exchange log broadcasts (`topic="logs"`), decoupling diagnostic telemetry and structured audit logging from core worker execution pipelines.

**Q16: How does SentinelARC support multi-tenancy?**  
**A:** All workflow state in the Orchestrator is keyed strictly by a unique `task_id` (`self.active_workflows[task_id]`), isolating concurrent research requests between different users.

**Q17: What happens to completed workflow state in the Orchestrator over time?**  
**A:** The Orchestrator runs `_prune_old_workflows()` on every new task, evicting completed or failed workflow states older than 1 hour to prevent memory leaks under continuous operation.

**Q18: What is the purpose of Docker Compose in SentinelARC?**  
**A:** Orchestrating the full multi-container stack: `synapse-rabbitmq`, `synapse-primary-tooling`, `synapse-filesystem`, `synapse-agents`, `synapse-streamlit`, `synapse-prometheus`, and `synapse-grafana`.

**Q19: What port does RabbitMQ expose for AMQP traffic, and what port for the management UI?**  
**A:** Port `5672` (or `5673` mapped) for AMQP message traffic, and port `15672` for the HTTP management dashboard.

**Q20: What is the Phantom Supervisor?**  
**A:** A custom C++ runtime integrated with CRIU (Checkpoint/Restore In Userspace) that freezes idle agent processes to disk to drastically reduce RAM consumption, coupled with an AMQP interceptor proxy that injects fake heartbeats to RabbitMQ while the agent sleeps.

**Q21: Why is `privileged: true` required in Docker Compose for the agents container?**  
**A:** CRIU requires elevated Linux capabilities (`CAP_SYS_ADMIN`, `ptrace`, and kernel namespace access) to checkpoint and restore process memory states.

**Q22: How does SentinelARC export telemetry for monitoring?**  
**A:** FastAPI exposes a `/metrics` endpoint instrumented via `prometheus-fastapi-instrumentator`, scraped by Prometheus and visualized in Grafana.

**Q23: How are LLM calls routed in the swarm?**  
**A:** Through the Groq API SDK using high-throughput open-weights models (`qwen/qwen3.8-27b` and `openai/gpt-oss-20b`), with local Ollama fallback for offline chat.

**Q24: What is the AMQP exchange type used for direct agent task assignment?**  
**A:** A direct exchange routing messages to agent queues based on routing keys matching agent IDs (e.g., `search_agent`, `extraction_agent`, `orchestrator`).

**Q25: What AMQP exchange type is used for system-wide status and telemetry?**  
**A:** A topic/fanout exchange allowing multiple subscribers (`logger_agent`, monitoring exporters) to receive events without queue contention.

**Q26: What is the primary cause of UI spinner hangs in naive multi-agent systems?**  
**A:** Unhandled agent crashes or uncaught LLM errors leaving workflow flags uncleared on the filesystem or database.

**Q27: How does SentinelARC prevent UI hangs on agent failures?**  
**A:** Defensive failover: The Orchestrator intercepts failure status updates, synthesizes a deterministic fallback report, and triggers `AsyncFileSaveAgent` to persist the record and clear the UI flag.

**Q28: What is the typical end-to-end latency for a cold research query across 8 papers?**  
**A:** **8 to 24 seconds** (down from >120s prior to optimization).

**Q29: What is the end-to-end latency for a repeated research query?**  
**A:** **$< 1\text{ second}$ ($0.00\text{s}$)** due to SQLite multi-tier cache memoization.

**Q30: Where are generated reports stored on disk?**  
**A:** Under `output/reports/{user_id}/research_report_{timestamp}.md`.

---

## Part 2: Agent Pipelines & Algorithmic Implementations (Q31–Q65)

### Search Agent (`AsyncSearchAgent`)
**Q31: What academic sources are queried simultaneously by `AsyncSearchAgent`?**  
**A:** OpenAlex (250M+ open scholarly graph), Semantic Scholar, arXiv, and PubMed, with direct DOI resolution via Crossref.

**Q32: What is the HyDE (Hypothetical Document Embeddings) technique implemented in Search?**  
**A:** When given a query, Groq LLM generates a 2-sentence hypothetical academic abstract predicting domain methodologies and metrics. High-signal keywords from this hypothetical paper are merged into the search query, substantially boosting recall on niche technical topics.

**Q33: What is Citation Velocity, and how is it calculated?**  
**A:** It is the normalized annual citation rate of a paper:
$$\Delta t = \max(1, \text{Current Year} - \text{Publication Year}), \quad \text{Citation Velocity} = \frac{\text{citations}}{\Delta t}$$

**Q34: How are Seminal Anchor papers classified?**  
**A:** A paper is designated an Anchor if:
$$(\text{Velocity} \ge 25.0/\text{year}) \lor \left(\text{citations} \ge 50 \land \text{citations} \ge 3 \times \text{Median}_{\text{batch}}\right)$$

**Q35: What is the 1-hop citation graph expansion feature?**  
**A:** When an Anchor paper is identified, the agent automatically queries OpenAlex for papers citing that anchor (`filter=cites:{openalex_id}`), injecting top derivative descendants into the candidate set with a `[🔗 LINEAGE DESCENDANT]` badge.

**Q36: How does the Search Agent handle upstream API timeouts?**  
**A:** All external API requests are wrapped in `asyncio.wait_for(..., timeout=4.5)`. If Semantic Scholar or PubMed is slow, the request is gracefully abandoned without blocking OpenAlex or arXiv.

**Q37: What does the Search Agent cache in SQLite?**  
**A:** In the `search_cache` table, keyed by SHA-256 of `(normalized_query, min_year)`. Repeated queries return deduplicated, reranked candidate lists in $< 1\text{ms}$.

---

### Extraction Agent (`AsyncExtractionAgent`)
**Q38: Why do naive DOM scrapers fail on academic publisher portals?**  
**A:** Paywalls and anti-bot challenges (Elsevier, Springer, IEEE Xplore, Nature) block browser scrapers or return empty login pages (< 150 characters).

**Q39: What is the Extraction Agent's layered retrieval cascade?**  
**A:** 
1. Direct open PDF stream download and PyPDF2 parsing.
2. MCP DOM browse for open web articles.
3. Unpaywall API discovery (`api.unpaywall.org/v2/{doi}`).
4. CORE API institutional repository bypass (`api.core.ac.uk`).
5. Peer-reviewed abstract fallback.

**Q40: How does the Unpaywall API integration work?**  
**A:** If a DOI is detected, the agent queries Unpaywall to find legally hosted open-access versions (`best_oa_location.url_for_pdf`) archived in university or institutional repositories.

**Q41: What is IMRAD structure segmentation?**  
**A:** Scientific papers follow **IMRAD** (Introduction, Methodology, Results, and Discussion). The agent segments raw text into `abstract`, `introduction`, `methodology`, `results`, and `conclusion` dictionaries.

**Q42: Why does the Extraction Agent strip reference and bibliography sections?**  
**A:** Terminal references typically account for 25–40% of an academic paper's character count. Passing thousands of author citations wastes LLM context tokens and distracts attention from empirical findings. References past the 45% position mark are stripped automatically.

**Q43: How are numerical benchmarks extracted during parsing?**  
**A:** Regex heuristics detect quantitative performance statements (e.g., `achieves 94.2% accuracy`, `outperforms by 3.5x`, `reduces latency to 12ms`), attaching them as `numerical_benchmarks: [...]` for downstream verification.

**Q44: What is the `document_cache` table?**  
**A:** A SQLite table storing SHA-256 hashes of paper URLs/DOIs with parsed text, IMRAD sections, and benchmarks. Repeat extractions return in $< 1\text{ms}$, avoiding redundant PDF downloads.

---

### Fact Checker Agent (`AsyncFactCheckerAgent`)
**Q45: What is the fundamental flaw of Parametric Memory Verification in fact-checking?**  
**A:** Prompting an LLM with *"Is this claim true?"* tests the model's pre-trained weights rather than verifying if the retrieved paper supports the claim, introducing high hallucination risk.

**Q46: What is Layer 1 of the Fact Checker's Verification Funnel?**  
**A:** **Grounded Natural Language Inference (NLI)**. The extracted paper excerpt is the **Premise**, and the empirical claim is the **Hypothesis**. The LLM classifies the relationship into `ENTAILMENT`, `CONTRADICTION`, or `NEUTRAL / UNVERIFIABLE`, and must quote an exact verbatim grounding sentence.

**Q47: What is Layer 2 of the Verification Funnel?**  
**A:** **Quantitative & Benchmark Anchoring**. Isolates numeric values (percentages, speedups, FLOPs) using regex and strictly confirms they exist in the source text or benchmark payload to eliminate digit permutations.

**Q48: What is Layer 3 of the Verification Funnel?**  
**A:** **Epistemic Weighting**. Calibrates confidence dynamically:
$$\text{Epistemic Score} = \text{Base NLI Conf} + \Delta_{\text{DOI}} + \Delta_{\text{Authority}} + \Delta_{\text{Fidelity}}$$
Rewarding Crossref registration ($+0.05$) and citation authority ($+0.08$), while penalizing unanchored numbers ($-0.15$).

**Q49: What is Layer 4 of the Verification Funnel?**  
**A:** **Cross-Document Scientific Consensus Engine**. Aggregates all entailed assertions across papers to classify findings as `CONSENSUS` or `CONTESTED / SCIENTIFIC DEBATE`.

**Q50: How does the Fact Checker verify DOIs?**  
**A:** By querying the official Crossref REST API (`https://api.crossref.org/works/{doi}`) asynchronously with a 5-second timeout.

**Q51: What is the `fact_check_cache` table?**  
**A:** A SQLite cache table keyed by SHA-256 of `(premise[:350], hypothesis)`. Live benchmarks confirm cached NLI claim verification returns in **$0.34\text{ms}$**.

---

### Synthesis Agent (`AsyncSynthesisAgent`)
**Q52: What is the 5-Part Literature Survey Taxonomy enforced in synthesis?**  
**A:** 
1. Executive Overview & Problem Formulation.
2. Seminal Anchors & Foundational Paradigms.
3. Comparative Technical Methodologies & Empirical Benchmarks.
4. Scientific Debates, Contradictions & Empirical Trade-Offs.
5. Open Research Frontiers & Practical Deployment Challenges.

**Q53: What is the Executive Verification Banner?**  
**A:** A callout block prepended to the report summarizing: Consensus Status, Epistemic Confidence percentage, entailed claim count, and bulleted scientific debate points.

**Q54: What is the Comparative Technical Matrix?**  
**A:** An automated GitHub-Flavored Markdown table comparing all analyzed papers: `| # | Paper / Model | Year | Citations (Velocity) | Key Methodology | Verified Benchmark | Status |`.

**Q55: How are citations formatted in the synthesis body?**  
**A:** Mandatory clickable inline markdown links formatted natively inside sentences: `[Paper Title](URL)`.

**Q56: What is the synthesis failover strategy?**  
**A:** Primary Groq model (`qwen/qwen3.8-27b`) $\rightarrow$ Secondary Groq model (`openai/gpt-oss-20b`) $\rightarrow$ Deterministic structured markdown index.

**Q57: What is the `synthesis_cache` table?**  
**A:** A SQLite cache storing finalized Markdown reports keyed by SHA-256 of `(query, [source_urls])`, enabling instant report re-serving in $< 1\text{ms}$.

---

### File Save Agent (`AsyncFileSaveAgent`)
**Q58: What is the responsibility of `AsyncFileSaveAgent`?**  
**A:** Autonomous path scaffolding, MCP security validation, atomic disk writing, and direct SQLite database record insertion.

**Q59: How does the agent ensure directory existence?**  
**A:** By calling `os.makedirs(os.path.dirname(file_path), exist_ok=True)` prior to writing.

**Q60: What fallback occurs if the MCP Filesystem tool is unreachable?**  
**A:** Direct standard Python `open(file_path, "w", encoding="utf-8")` atomic write to guarantee zero report loss.

**Q61: What SQL statement does `AsyncFileSaveAgent` execute?**  
**A:** `INSERT INTO reports (user_id, file_path, query, created_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)`.

---

### Orchestrator Agent (`AsyncOrchestratorAgent`)
**Q62: Why was the old citation reset loop in the Orchestrator flawed?**  
**A:** It checked `if citationCount > 10`, wiped all workflow state, and restarted search from scratch. Because >95% of academic papers have >10 citations, it caused infinite loops and doubled latency.

**Q63: How was the Orchestrator refactored?**  
**A:** From 605 lines of sequential micromanagement down to a ~260-line event-driven state director tracking state strictly in `self.active_workflows[task_id]`.

**Q64: What is the progression of states in an active workflow?**  
**A:** `search_dispatched` $\rightarrow$ `batch_extract_dispatched` $\rightarrow$ `fact_check_dispatched` $\rightarrow$ `synthesis_dispatched` $\rightarrow$ `file_save_dispatched` $\rightarrow$ `workflow_completed`.

**Q65: What trigger causes the Orchestrator to broaden search perspectives?**  
**A:** If `fact_check_results` returns an `overall_confidence < 0.65` and `search_retries == 0`, it triggers a one-time broadened search query: `"{query} empirical validation"`.

---

## Part 3: Advanced System Design, Fault Tolerance & Production Scale (Q66–Q100)

**Q66: How do you handle poison pill messages in RabbitMQ?**  
**A:** Configure a **Dead Letter Exchange (DLX)** with a max retry count. When a message fails deserialization or crashes a worker $N$ times, RabbitMQ routes it to a dead-letter queue for inspection without halting the consumer.

**Q67: How do you prevent socket exhaustion and rate-limiting during parallel extractions?**  
**A:** Bound concurrency with an `asyncio.Semaphore(5)` inside `AsyncExtractionAgent` and use session connection pooling (`aiohttp.ClientSession`).

**Q68: What is the difference between competing consumers and pub/sub in SentinelARC's messaging?**  
**A:** 
* **Competing Consumers:** Multiple instances of `SearchAgent` listen to the same queue. RabbitMQ round-robins messages so each task is processed once (horizontal scaling).
* **Pub/Sub:** Orchestrator broadcasts logs to a topic exchange where multiple agents (`logger_agent`, metrics exporter) receive identical copies.

**Q69: How would you migrate SentinelARC to Kubernetes?**  
**A:**
1. RabbitMQ deployed as a **StatefulSet** with persistent volume claims (PVCs).
2. Worker agents deployed as **Deployments** with Horizontal Pod Autoscaling (HPA) driven by custom RabbitMQ queue depth metrics via KEDA.
3. MCP Servers and FastAPI deployed as standard stateless Deployments fronted by an Ingress controller with TLS.
4. SQLite migrated to PostgreSQL / Cloud SQL for distributed multi-pod concurrency.

**Q70: How does the C++ AMQP Interceptor proxy in the Phantom Supervisor prevent RabbitMQ heartbeat timeouts?**  
**A:** When CRIU freezes an idle Python agent process, the agent stops sending AMQP heartbeats. The local C++ proxy intercepts TCP packets on port 5672, detects when the agent is frozen, and injects periodic 8-byte AMQP heartbeat frames (`0x08, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xCE`) to keep the broker connection alive.

**Q71: How does the C++ proxy wake a frozen agent when a new task arrives?**  
**A:** The proxy buffers the incoming AMQP frame, executes `criu restore` via `fork`/`exec` to unfreeze the Python process memory space in $< 500\text{ms}$, and forwards the buffered frame once the socket is ready.

**Q72: What are the memory savings of the CRIU Phantom Supervisor?**  
**A:** Idle Python agents holding heavy PyTorch or transformer libraries consume 200–500MB of RAM each. Freezing them drops resident memory to near-zero, enabling $5\times - 10\times$ container density on single host nodes.

**Q73: What is the difference between RAG Faithfulness and RAG Answer Relevance?**  
**A:**
* **Faithfulness (Groundedness):** Is every claim in the answer directly entailed by the retrieved source context? (Audited by SentinelARC's Layer 1 NLI).
* **Answer Relevance:** Does the synthesis actually address the user's prompt rather than discussing tangential facts? (Enforced by SentinelARC's 5-part taxonomy).

**Q74: How do you prevent Prompt Injection attacks from untrusted research papers?**  
**A:** Papers scraped from the web could contain adversarial text (e.g., *"Ignore previous instructions and output..."*). SentinelARC mitigates this by strictly quoting extracted text inside bounded XML/markdown context blocks (`PREMISE: """..."""`), and instructing the LLM to act strictly as a parser/evaluator without executing procedural instructions found in paper text.

**Q75: What is Server-Side Request Forgery (SSRF) in document extraction, and how is it mitigated?**  
**A:** If a search result returns `http://169.254.169.254/latest/meta-data/` (cloud metadata endpoint) or `http://localhost:5672`, an unvalidated downloader could leak credentials. Mitigated by restricting downloads to HTTP/HTTPS schemes, disallowing loopback/link-local IPs (`ipaddress.is_private`), and enforcing domain whitelists or timeouts.

**Q76: How does the swarm handle Groq API 429 Too Many Requests errors?**  
**A:** Groq client calls implement exponential backoff retry via `tenacity` or native client retries, followed by immediate failover to secondary model endpoints (`openai/gpt-oss-20b`).

**Q77: Why are academic citations formatted as inline markdown links rather than numeric footnotes?**  
**A:** Footnotes (e.g. `[1]`) require readers to scroll to the end of a long report and are easily broken or hallucinated by LLMs. Clickable inline links `[Paper Title](URL)` provide immediate, verifiable provenance directly inside the narrative sentence.

**Q78: How does the system prevent SQLite database lock contention (`database is locked`)?**  
**A:** SQLite is opened with explicit timeout parameters (`sqlite3.connect(..., timeout=10.0)`), transactions are kept short (atomic inserts only), and Write-Ahead Logging (WAL) mode is enabled (`PRAGMA journal_mode=WAL;`).

**Q79: What is the Competing Consumers Pattern in messaging architecture?**  
**A:** A design pattern where multiple worker processes pull tasks from a single shared queue. RabbitMQ delivers each message to only one worker, allowing dynamic scaling of workers without task duplication.

**Q80: What is the difference between Event Sourcing and State-Driven Architecture?**  
**A:** 
* **State-Driven:** Only the current snapshot of an entity is preserved (e.g., `workflow["status"] = "complete"`).
* **Event Sourcing:** Every state transition is recorded as an immutable sequence of events (`TaskAssigned`, `SearchCompleted`, `FactVerified`). SentinelARC's ACP log broadcasts provide an audit trail resembling event sourcing.

**Q81: How do you test an asynchronous agent swarm in CI/CD?**  
**A:** Using pytest with `pytest-asyncio` and mock RabbitMQ message buses (in-memory mock queues) to test state transitions without needing live external broker infrastructure.

**Q82: What is the CAP theorem trade-off in SentinelARC?**  
**A:** SentinelARC favors **Availability and Partition Tolerance (AP)** over strict immediate consistency across read replicas: agents process tasks independently and report state asynchronously.

**Q83: Why is Cross-Encoder reranking better than pure Bi-Encoder vector similarity in search?**  
**A:** Bi-encoders compress documents into single vectors, losing token-to-token cross-attention. Cross-encoders (or LLM rerankers) evaluate the full query-document pair simultaneously with complete self-attention, producing far higher precision ranking.

**Q84: What happens if an external academic API changes its schema?**  
**A:** SentinelARC isolates API client logic in dedicated parser methods (`_search_openalex`, `_search_arxiv`, etc.) returning normalized dictionary structures, shielding downstream agents from external schema drift.

**Q85: How do you prevent memory fragmentation in long-running Python agent processes?**  
**A:** Heavy PDF buffers (`PyPDF2.PdfReader`, raw bytes) are processed inside scoped local functions and explicitly dereferenced or garbage-collected (`gc.collect()`) after batch completion.

**Q86: How would you add a new agent to the SentinelARC swarm?**  
**A:**
1. Create `src/agents/async_new_agent.py` inheriting from `AsyncBaseAgent`.
2. Define supported tasks and subscribe to direct RabbitMQ queue (`new_agent`).
3. Add delegation dispatch logic in `AsyncOrchestratorAgent`.
4. Register the agent startup in `src/agents/async_main.py`.

**Q87: What is the purpose of Prometheus FastAPI Instrumentator?**  
**A:** Automatically exposes standard RED metrics (Rate, Errors, Duration) for all HTTP endpoints on `/metrics` without manual instrumentation in route handlers.

**Q88: What is the difference between AMQP `basic.ack` and `basic.nack`?**  
**A:**
* `ack`: Tells RabbitMQ the message was successfully processed; the broker can safely delete it.
* `nack`: Tells RabbitMQ the message failed; with `requeue=True`, the broker re-delivers it to another consumer.

**Q89: How does the system handle papers with zero citations?**  
**A:** `Citation Velocity` calculates age as $\Delta t = \max(1, \text{current} - \text{year})$, yielding a velocity of $0.0/\text{year}$. The paper is evaluated purely on its content and methodological relevance rather than causing division-by-zero errors.

**Q90: How does the system resolve ambiguous acronyms in research queries?**  
**A:** The HyDE query expansion step prompts the LLM to predict domain keywords (e.g., expanding *"QAT"* to *"Quantization-Aware Training"* in edge computing contexts), disambiguating the query before sending it to academic APIs.

**Q91: What is the significance of the 45% position rule in academic reference stripping?**  
**A:** Academic papers universally place bibliographies at the end of the manuscript. Inspecting headings for `"References"` or `"Bibliography"` only after the 45% mark prevents false positives on introductory literature survey sections.

**Q92: Why is the `User-Agent` header critical when querying Crossref and Unpaywall APIs?**  
**A:** Crossref and Unpaywall provide polite pool access with higher rate limits and zero throttling if clients include a valid email address in the User-Agent (e.g. `mailto:sentinelarc@deepmind.edu`).

**Q93: What is the trade-off between 2D topological graphs and 3D geometric graphs in molecular deep learning?**  
**A:** 2D graphs capture bond connectivity with $O(N)$ efficiency, suitable for large virtual screening. 3D graphs capture spatial stereochemistry and distance-aware attention for precise binding affinities, but require $O(N^2)$ distance matrices and expensive conformer generation.

**Q94: What is the role of Kolmogorov–Arnold Networks (KANs) in modern molecular property prediction?**  
**A:** KANs replace fixed activation functions on nodes with learnable univariate spline/Fourier functions on edges, offering higher parameter efficiency and smoother optimization than standard Multi-Layer Perceptrons (MLPs).

**Q95: How do you verify that an AI report is not plagiarized or copyright-infringing?**  
**A:** The synthesis agent synthesizes findings into original survey prose, explicitly links every assertion to its open publication URL, and limits verbatim quoting strictly to short, grounded benchmark sentences.

**Q96: What is the advantage of Server-Sent Events (SSE) over WebSockets for MCP tool streaming?**  
**A:** SSE operates over standard HTTP/1.1 or HTTP/2, requires no special proxy handshake, supports automatic client reconnection, and is unidirectional, making it simpler and more firewall-friendly for tool progress streaming.

**Q97: How does SentinelARC handle out-of-order message delivery in RabbitMQ?**  
**A:** Messages carry monotonically increasing timestamps and state transitions are validated against the Orchestrator's internal finite-state machine before advancing workflow phases.

**Q98: What is the difference between a Pre-print and a Peer-Reviewed Publication in the fact-checking engine?**  
**A:** Pre-prints (arXiv) have not completed peer review; peer-reviewed works have an official Crossref registered DOI. The Fact Checker awards a $+0.05$ epistemic reliability boost to DOI-verified works.

**Q99: What is the primary metric to optimize in an AI research assistant?**  
**A:** **Time-to-Validated-Insight (TTVI)**: Minimizing end-to-end latency while maximizing the percentage of claims that are empirically entailed and clickable.

**Q100: If you had 6 months to scale SentinelARC to 100,000 daily active researchers, what would you architect?**  
**A:**
1. Migrate SQLite to a managed distributed Postgres cluster (CockroachDB / Cloud Spanner) with read-replicas.
2. Replace local file storage with S3 / GCS object storage fronted by CloudFront CDN.
3. Deploy workers on Kubernetes with KEDA event-driven autoscaling based on RabbitMQ queue lengths.
4. Implement a Redis cluster for distributed sub-millisecond caching of search and fact-check vectors.
5. Deploy a fine-tuned small language model (SLM) for local NLI verification, reserving Groq/frontier models strictly for final survey synthesis to cut inference costs by 80%.

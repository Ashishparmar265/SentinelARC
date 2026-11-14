# SentinelARC - Future Work & Technical Debt

## High Priority To-Do
- [x] **Concurrent Multi-Tenant Orchestrator Refactoring** (Completed)
  - **Context:** The current `AsyncOrchestratorAgent` uses flat variables (e.g., `self.search_results`, `self.extracted_content`) to track workflow state. While Data output is fully isolated per-user via directory paths, two users triggering standard "Research" queries at the exact same microsecond could overwrite the Orchestrator's flat variables mid-execution.
  - **Implemented Solution:** Refactored `async_orchestrator.py` globally to use a dictionary store tied to `task_id` (`self.active_workflows[task_id]`), isolated per concurrent request with automatic state resolution and cleanup.
- [x] **Swarm Latency Optimization & Multi-Source Agent Delegation** (Completed)
  - **Implemented Solution:** Concurrently gathers from OpenAlex, Semantic Scholar, arXiv, PubMed, and Crossref in `async_search_agent.py`. Integrated dynamic Citation Velocity and Outlier Analysis to replace naive `> 10` reset loops. Added batch extraction with native PDF stream parsing and CORE API open-access paywall bypass in `async_extraction_agent.py`. Automated fact-check claim extraction in `async_fact_checker_agent.py`. Added anchor-prioritized synthesis with inline citations in `async_synthesis_agent.py`. Delegated path formatting and native SQLite persistence to `async_file_save_agent.py`. Reduced end-to-end query latency to ~22–31s.

## General Backlog
- [ ] Integrate Phantom Process Supervisor (CRIU) for optimized socket container states.

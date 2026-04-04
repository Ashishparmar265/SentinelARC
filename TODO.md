# SentinelARC - Future Work & Technical Debt

## High Priority To-Do
- [ ] **Concurrent Multi-Tenant Orchestrator Refactoring**
  - **Context:** The current `AsyncOrchestratorAgent` uses flat variables (e.g., `self.search_results`, `self.extracted_content`) to track workflow state. While Data output is fully isolated per-user via directory paths, two users triggering standard "Research" queries at the exact same microsecond could overwrite the Orchestrator's flat variables mid-execution.
  - **Proposed Solution:** Refactor `async_orchestrator.py` globally to use a dictionary hash-map tied to `task_id` (e.g., `self.active_tasks[task_id]["search_results"]`).
  - **Action Items:**
    - Rewrite all 15+ callback functions (`_handle_extracted_content`, etc.) to lookup state.
    - Ensure all companion agents (`search_agent`, `extraction_agent`) pass the `task_id` or `user_id` identifier back on every `DataSubmitPayload`.

## General Backlog
- [ ] Integrate Phantom Process Supervisor (CRIU) for optimized socket container states.

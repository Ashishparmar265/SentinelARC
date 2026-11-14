# SentinelARC API & Protocols Reference

This document provides a comprehensive reference for SentinelARC's external REST APIs, inter-agent messaging schemas (Agent Communication Protocol - ACP), RabbitMQ topology, and SQLite database schema.

---

## 1. REST API Endpoints (FastAPI :8000)

**Base URL:** `http://localhost:8000`

### 1.1 Health Check
Verifies system health, active agent subscriptions, and orchestrator readiness.

* **Endpoint:** `GET /health`
* **Response:**
  ```json
  {
    "status": "healthy",
    "agents_active": 7,
    "orchestrator_ready": true,
    "version": "2.0.0"
  }
  ```

### 1.2 Start Research Workflow
Dispatches an asynchronous multi-agent research task.

* **Endpoint:** `POST /research`
* **Headers:** `Content-Type: application/json`
* **Request Body:**
  ```json
  {
    "query": "Quantization-Aware Training for Edge Devices",
    "user_id": 1,
    "task_id": "qat_edge_001"
  }
  ```
  *(Note: `task_id` is optional; if omitted, a UUID-based ID is automatically generated).*
* **Response:**
  ```json
  {
    "status": "task_received",
    "task_id": "qat_edge_001",
    "query": "Quantization-Aware Training for Edge Devices"
  }
  ```

### 1.3 General Chat (Streaming)
Provides streaming conversational interactions via the local Ollama LLM proxy.

* **Endpoint:** `POST /general_chat`
* **Headers:** `Content-Type: application/json`
* **Request Body:**
  ```json
  {
    "query": "Explain the difference between pruning and quantization.",
    "model": "llama3",
    "history": [
      {
        "type": "user",
        "content": "Hello!"
      },
      {
        "type": "assistant",
        "content": "Hi! How can I help with your research today?"
      }
    ],
    "user_id": 1
  }
  ```
* **Response:** `text/plain` streaming chunked response.

### 1.4 Prometheus Telemetry
Exposes standard RED metrics for Prometheus scrapers.

* **Endpoint:** `GET /metrics`
* **Response:** Prometheus exposition format text.

---

## 2. Agent Communication Protocol (ACP) Schema

All inter-agent communication across RabbitMQ is strictly governed by Pydantic models defined in `src/protocols/acp_schema.py`.

### 2.1 Message Envelope (`ACPMessage`)
Every message transmitted across AMQP queues uses this standardized JSON envelope:

```json
{
  "msg_id": "msg-8f12a3b0-4c8d-4e9a",
  "sender_id": "orchestrator",
  "receiver_id": "search_agent",
  "topic": null,
  "msg_type": "TASK_ASSIGN",
  "payload": { ... },
  "timestamp": "2026-11-14T13:18:42.120Z",
  "version": "1.0"
}
```

### 2.2 Payload Schemas

#### A. Task Assignment (`TaskAssignPayload`)
```json
{
  "task_type": "web_search",  // "web_search" | "batch_extract" | "fact_check" | "synthesize_research" | "save_file"
  "task_data": {
    "query": "Diffusion Models for Monocular Depth Estimation",
    "task_id": "diff_depth_001",
    "user_id": 1,
    "max_results": 10
  },
  "priority": 1
}
```

#### B. Status Update (`StatusUpdatePayload`)
```json
{
  "status": "batch_extracting: 4/8 complete",
  "progress": 50.0,
  "task_id": "diff_depth_001",
  "timestamp": "2026-11-14T13:18:45.340Z"
}
```

#### C. Data Submission (`DataSubmitPayload`)
```json
{
  "data_type": "fact_check_results",  // "search_results" | "extracted_content_batch" | "fact_check_results" | "synthesis_report" | "file_save_result"
  "data": {
    "claims_processed": [...],
    "consensus": {
      "status": "CONSENSUS",
      "notes": "Empirical findings corroborated across independent scholarly sources."
    },
    "summary": {
      "total_claims": 6,
      "entailed_claims": 5,
      "overall_confidence": 0.88
    }
  },
  "source": "fact_checker",
  "task_id": "diff_depth_001"
}
```

#### D. Agent-to-Agent Peer Validation (`ValidationRequestPayload` & `ValidationResponsePayload`)
```json
// Request
{
  "claim": "Flash attention decreases training latency by 35%.",
  "source_url": "https://arxiv.org/abs/2205.14135",
  "evidence": "In our experiments, the transformer model with flash attention reduced training latency by 35%."
}

// Response
{
  "is_valid": true,
  "confidence": 0.95,
  "evidence": "In our experiments, the transformer model with flash attention reduced training latency by 35% compared to standard attention.",
  "source": "fact_checker_agent"
}
```

#### E. System Telemetry & Logs (`LogBroadcastPayload`)
```json
{
  "level": "INFO",
  "message": "Research synthesis completed: 2062 words generated across 8 sources.",
  "component": "synthesis_agent",
  "timestamp": "2026-11-14T13:25:38.660Z"
}
```

---

## 3. RabbitMQ Topology & Queues

| Queue Name | Routing Key | Exchange | Description |
|:---|:---|:---|:---|
| `orchestrator` | `orchestrator` | `direct` | Ingests data submissions and status updates from worker agents. |
| `search_agent` | `search_agent` | `direct` | Receives academic search and query expansion tasks. |
| `extraction_agent` | `extraction_agent` | `direct` | Receives batch document extraction tasks. |
| `fact_checker_agent` | `fact_checker_agent` | `direct` | Receives 4-layer NLI fact-checking and consensus tasks. |
| `synthesis_agent` | `synthesis_agent` | `direct` | Receives 5-part literature survey synthesis tasks. |
| `file_save_agent` | `file_save_agent` | `direct` | Receives report persistence and database registration tasks. |
| `logger_agent` | `*` | `topic (logs)` | Receives system-wide audit telemetry and log broadcasts. |

---

## 4. SQLite Database Schema (`output/sentinelarc.db`)

SentinelARC uses a local SQLite database for UI state synchronization and swarm memoization:

### 4.1 Reports Table (`reports`)
```sql
CREATE TABLE reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    file_path TEXT NOT NULL,
    query TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 4.2 Multi-Tier Swarm Caching Tables
```sql
-- Search Agent Cache (<1ms)
CREATE TABLE search_cache (
    query_hash TEXT PRIMARY KEY,
    query TEXT,
    min_year INTEGER,
    results_json TEXT,
    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Extraction Agent Document Cache (<1ms)
CREATE TABLE document_cache (
    url_hash TEXT PRIMARY KEY,
    url TEXT,
    title TEXT,
    full_text TEXT,
    sections_json TEXT,
    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Fact Checker NLI & Benchmark Cache (0.34ms)
CREATE TABLE fact_check_cache (
    claim_hash TEXT PRIMARY KEY,
    claim TEXT,
    premise_snippet TEXT,
    nli_verdict TEXT,
    nli_confidence REAL,
    numerical_match INTEGER,
    grounding_quote TEXT,
    epistemic_score REAL,
    reasoning TEXT,
    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Synthesis Agent Survey Cache (<1ms)
CREATE TABLE synthesis_cache (
    query_hash TEXT PRIMARY KEY,
    query TEXT,
    report_content TEXT,
    word_count INTEGER,
    sources_count INTEGER,
    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

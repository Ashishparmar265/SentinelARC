# Agent Communication Protocol (ACP) Specification

> **Specification Version**: 2.1 (Production)  
> **Reference Implementation**: `src/protocols/acp_schema.py` and `src/message_bus/rabbitmq_bus.py`

---

## 1. Overview

The **Agent Communication Protocol (ACP)** is SentinelARC's standardized, type-safe messaging specification. ACP governs all asynchronous inter-agent coordination over AMQP (RabbitMQ), supporting both direct Agent-to-Agent (A2A) tasks and Publish-Subscribe topic broadcasts.

### Core Architectural Principles
1. **Type Safety & Pydantic Validation**: Every message envelope and payload is strictly validated using Pydantic models before serialization to JSON bytes.
2. **Stateless Task Isolation**: All operational payloads carry a mandatory `task_id` UUID to prevent cross-talk between overlapping research workflows.
3. **Decoupled Asynchrony**: Agents communicate non-blockingly over AMQP exchanges, allowing workers to scale horizontally and survive independent restarts.
4. **Observable Event Streams**: Built-in `LOG_BROADCAST` and `STATUS_UPDATE` primitives stream real-time progress to system loggers and UI pollers.

---

## 2. Base Message Envelope

All inter-agent messages are packaged inside the standardized `ACPMessage` envelope:

```python
class ACPMessage(BaseModel):
    sender_id: str              # Unique identifier of sending agent (e.g. "orchestrator")
    receiver_id: Optional[str]  # Target agent identifier (for direct routing)
    topic: Optional[str]        # Broadcast topic name (e.g. "logs", "metrics")
    msg_type: ACPMsgType        # Enumerated protocol action
    payload: Dict[str, Any]     # Type-safe payload serialized as dict
    timestamp: Optional[str]    # ISO-8601 UTC timestamp string
```

### Protocol Message Types (`ACPMsgType`)

| Enum Value | Purpose | Typical Direction | Payload Model |
|---|---|---|---|
| `TASK_ASSIGN` | Delegates an operational task to a worker | Orchestrator → Worker | `TaskAssignPayload` |
| `STATUS_UPDATE` | Reports progress % and state transitions | Worker → Orchestrator | `StatusUpdatePayload` |
| `DATA_SUBMIT` | Returns completed research data artifacts | Worker → Orchestrator | `DataSubmitPayload` |
| `VALIDATION_REQUEST` | Requests peer review / fact checking | Synthesis / Agent → FactChecker | `ValidationRequestPayload` |
| `VALIDATION_RESPONSE` | Returns validation verdict & evidence | FactChecker → Requester | `ValidationResponsePayload` |
| `LOG_BROADCAST` | System-wide event broadcasting | Any Agent → Topic Exchange | `LogBroadcastPayload` |

---

## 3. Communication Patterns

### Pattern 1: Direct Agent-to-Agent (A2A) Routing
Direct messages specify `receiver_id`. The underlying message bus routes the message to the `synapse.direct` AMQP exchange with a routing key equal to `receiver_id`:

```python
# Orchestrator assigning search task
task_message = ACPMessage(
    sender_id="orchestrator",
    receiver_id="search_agent",
    msg_type=ACPMsgType.TASK_ASSIGN,
    payload=TaskAssignPayload(
        task_type="web_search",
        task_data={"query": "Direct Preference Optimization in LLMs", "task_id": "task_9e1b2c3d"},
        priority=1
    ).model_dump()
)
```

### Pattern 2: Publish-Subscribe Topic Broadcasting
Broadcast messages omit `receiver_id` and set `topic`. The message bus routes them to the `synapse.topics` AMQP exchange:

```python
# Extraction Agent broadcasting progress log
log_message = ACPMessage(
    sender_id="extraction_agent",
    topic="logs",
    msg_type=ACPMsgType.LOG_BROADCAST,
    payload=LogBroadcastPayload(
        level="INFO",
        message="Batch extraction complete for 5 open-access PDFs",
        component="extraction_agent"
    ).model_dump()
)
```

### Pattern 3: Request-Response Data Submission
Workers return completed payloads to the Orchestrator via `DATA_SUBMIT`:

```python
# Fact Checker returning 4-layer validation results
submission = ACPMessage(
    sender_id="fact_checker_agent",
    receiver_id="orchestrator",
    msg_type=ACPMsgType.DATA_SUBMIT,
    payload=DataSubmitPayload(
        data_type="fact_check_results",
        data={
            "overall_confidence": 0.92,
            "consensus_status": "SCIENTIFIC CONSENSUS",
            "verified_claims_count": 8,
            "contested_claims_count": 0,
            "verifications": [...]
        },
        task_id="task_9e1b2c3d"
    ).model_dump()
)
```

---

## 4. Detailed Payload Specifications

### 4.1 TaskAssignPayload
```python
class TaskAssignPayload(BaseModel):
    task_type: str                    # Task verb: "web_search", "batch_extract", "fact_check", "synthesize", "save_report"
    task_data: Dict[str, Any]         # Task-specific arguments (query, papers, claims, task_id)
    priority: int = 1                 # Priority tier (1=High, 5=Low)
```

### 4.2 StatusUpdatePayload
```python
class StatusUpdatePayload(BaseModel):
    status: str                       # Current state description (e.g. "parsing_pdf_stream")
    progress: Optional[float] = None  # Progress indicator float (0.0 to 100.0)
    task_id: Optional[str] = None     # Associated workflow UUID
```

### 4.3 DataSubmitPayload
```python
class DataSubmitPayload(BaseModel):
    data_type: str                    # Artifact identifier: "search_results", "extracted_content", "fact_check_results", "synthesis_report", "save_complete"
    data: Any                         # Structured result payload (dict, list, or string)
    source: Optional[str] = None      # Source agent identifier
    task_id: Optional[str] = None     # Mandatory correlation UUID
```

### 4.4 LogBroadcastPayload
```python
class LogBroadcastPayload(BaseModel):
    level: str                        # "DEBUG", "INFO", "WARNING", "ERROR"
    message: str                      # Human-readable log string
    component: Optional[str] = None   # Source micro-agent name
```

### 4.5 ValidationRequestPayload & ValidationResponsePayload
```python
class ValidationRequestPayload(BaseModel):
    claim: str                        # Scientific hypothesis to verify
    source_url: str                   # Primary source URL or DOI
    validation_type: str = "fact_check"

class ValidationResponsePayload(BaseModel):
    is_valid: bool                    # Verification verdict (True if ENTAILED)
    confidence: float                 # Calibrated confidence score (0.0 to 1.0)
    evidence: str                     # 1-sentence verbatim grounding quote from premise
    source: str = "fact_checker_agent"
```

---

## 5. Message Bus Infrastructure (`RabbitMQBus`)

In SentinelARC, the message bus is implemented by [`src/message_bus/rabbitmq_bus.py`](file:///home/iiitl/SentinelARC/src/message_bus/rabbitmq_bus.py) utilizing async AMQP connection adapters.

### Routing Topology
- **Direct Exchange**: `synapse.direct`
  - Routes messages where `receiver_id` matches the queue binding.
  - Queues: `orchestrator`, `search_agent`, `extraction_agent`, `fact_checker_agent`, `synthesis_agent`, `file_save_agent`.
- **Topic Exchange**: `synapse.topics`
  - Routes broadcast events based on topic wildcard routing patterns (e.g., `logs.*`, `metrics.#`).
  - Subscribers: `logger_agent`, Prometheus metrics scrapers.

```python
class RabbitMQBus:
    def __init__(self, rabbitmq_url: str):
        self.rabbitmq_url = rabbitmq_url
        self.direct_exchange = "synapse.direct"
        self.topic_exchange = "synapse.topics"
        self.agent_subscribers: Dict[str, Callable] = {}
        self.topic_subscribers: Dict[str, Set[Callable]] = {}

    async def send_to_agent(self, receiver_id: str, message: ACPMessage):
        """Publishes directly to synapse.direct with routing_key=receiver_id."""
        ...

    async def broadcast(self, topic: str, message: ACPMessage):
        """Publishes to synapse.topics with routing_key=topic."""
        ...
```

---

## 6. End-to-End Hub-and-Spoke Sequence

The following sequence details how ACP messages coordinate the complete research lifecycle:

```
FastAPI           Orchestrator        SearchAgent       ExtractionAgent    FactChecker       SynthesisAgent     FileSaveAgent
   │                   │                   │                   │                │                  │                  │
   ├── start_research ─►                   │                   │                │                  │                  │
   │                   ├── TASK_ASSIGN ───►│                   │                │                  │                  │
   │                   │   (web_search)    │                   │                │                  │                  │
   │                   │◄── DATA_SUBMIT ───┤                   │                │                  │                  │
   │                   │   (papers list)   │                   │                │                  │                  │
   │                   │                                       │                │                  │                  │
   │                   ├── TASK_ASSIGN (batch_extract) ───────►│                │                  │                  │
   │                   │◄── DATA_SUBMIT (clean IMRAD text) ────┤                │                  │                  │
   │                   │                                                        │                  │                  │
   │                   ├── TASK_ASSIGN (4-layer fact-check) ───────────────────►│                  │                  │
   │                   │◄── DATA_SUBMIT (NLI verdicts & consensus) ─────────────┤                  │                  │
   │                   │                                                                           │                  │
   │                   ├── TASK_ASSIGN (synthesize 5-part report) ────────────────────────────────►│                  │
   │                   │◄── DATA_SUBMIT (final markdown survey) ───────────────────────────────────┤                  │
   │                   │                                                                                              │
   │                   ├── TASK_ASSIGN (atomic save & db write) ─────────────────────────────────────────────────────►│
   │                   │◄── DATA_SUBMIT (save_complete & sha256) ─────────────────────────────────────────────────────┤
   │                   │
   ◄── Workflow Done ──┤
```

---

## 7. Strict Task Correlation & Concurrency Control

To guarantee zero cross-talk across concurrent multi-user workloads:
1. Every payload originating from the user request carries `task_id`.
2. Agents must echo the `task_id` in all response payloads (`STATUS_UPDATE`, `DATA_SUBMIT`).
3. The Orchestrator resolves incoming payloads via `self.active_workflows[message.payload["task_id"]]`. Payloads lacking a known `task_id` are rejected with a warning log, ensuring robust multi-tenant operation.

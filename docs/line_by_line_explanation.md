# SentinelARC Line-by-Line Code Explanation

> **Architecture Update Note**: This documentation has been modernized for the SentinelARC platform. Where applicable, assume that agents now run under the Phantom Supervisor (CRIU) runtime and communicate through the C++ AMQP Interceptor.



Because SentinelARC is a vast multi-agent system, this document breaks down the most critical code modules block-by-block (and often line-by-line) to demystify how the asynchronous infrastructure fundamentally operates.

---

## Modue 1: Current State Storage (`src/agents/async_orchestrator.py`)

The `AsyncOrchestrator` is the central brain of SentinelARC. Because it is an asynchronous event-loop driven agent, it cannot rely on procedural "step 1, step 2" code blocks. Instead, it must meticulously track the state of the active payload using class variables so it knows exactly where it is in the lifecycle when a random RabbitMQ message arrives.

### 1.1 Class Initialization
```python
class AsyncOrchestrator(AsyncBaseAgent):
    def __init__(self, agent_id: str, message_bus, mcp_servers: Dict[str, str]):
        super().__init__(agent_id, message_bus, mcp_servers)
        
        # --- State tracking ---
        self.current_task_id = None
        self.current_query = None
        
        # --- Document Stores ---
        self.search_results = []
        self.extracted_content = []
        self.fact_check_results = None
        self.synthesis_report = None
```
**Explanation:**
- `class AsyncOrchestrator(AsyncBaseAgent)`: Inherits from the base RabbitMQ connection class.
- `def __init__`: The constructor. It receives the `agent_id` (usually `"orchestrator"`), the `message_bus` (a RabbitMQ interface), and the URL map to the `mcp_servers`.
- `super().__init__`: Calls the parent class constructor to initialize the RabbitMQ bindings.
- `self.current_task_id`: A UUID string tracking the active user request. If a background message arrives with a different UUID, the orchestrator ignores it (preventing cross-talk between overlapping runs).
- `self.current_query`: Caches the initial user prompt (e.g., "spatial computing in XR").
- `self.search_results = []`: An Array list to catch the outputs dispatched asynchronously by the Search Agent.
- `self.extracted_content = []`: An Array list to catch the web-scraped content dispatched individually by the Extract Agent.

### 1.2 Pipeline Thresholds & Limits
```python
        # --- Operation Threshold parameters ---
        self.extraction_goal = 5       
        self.fact_check_triggered = False 
        self.search_retries = 0        
```
**Explanation:**
- `self.extraction_goal = 5`: Hard-codes the system to pause and wait until exactly 5 web-scraping payloads have returned from the extraction agents before transitioning.
- `self.fact_check_triggered = False`: A critical boolean lock. Because 10 extraction tasks are fired asynchronously, they finish instantly out of order. This lock prevents the Orchestrator from accidentally triggering the Fact-Checker 5 separate times when the 6th, 7th, 8th, 9th, and 10th web pages finish downloading.
- `self.search_retries = 0`: A numerical counter to prevent infinite fallback loops if the Search agent constantly returns 0 results.

---

## Module 2: Inverting Control via Pub-Sub (`src/agents/async_orchestrator.py`)

### 2.1 The Message Handler
```python
    async def handle_message(self, message: ACPMessage):
        """Handle incoming ACP messages sequentially from the message bus."""
        try:
            if message.msg_type == ACPMsgType.TASK_ASSIGN:
                await self._handle_task_assignment(message)
                
            elif message.msg_type == ACPMsgType.STATUS_UPDATE:
                await self._handle_status_update(message)
                
            elif message.msg_type == ACPMsgType.DATA_SUBMIT:
                await self._handle_data_submission(message)
```
**Explanation:**
- `async def handle_message`: This is the _only_ entry point for data. Instead of python calling functions directly, RabbitMQ pushes an `ACPMessage` directly into this function.
- `message.msg_type`: Determines the protocol behavior.
- `ACPMsgType.TASK_ASSIGN`: Generally means Streamlit has asked the Orchestrator to start a new job.
- `ACPMsgType.STATUS_UPDATE`: Agents broadcasting `{"percentage": 80.0, "status": "scraping..."}` to update the UI loop.
- `ACPMsgType.DATA_SUBMIT`: Used when a child agent (like Search or Extract) finishes its job and dumps the actual payload data file back into the Orchestrator. 

### 2.2 Triggering Research
```python
    async def _handle_task_assignment(self, message: ACPMessage):
        payload = TaskAssignPayload(**message.payload)
        
        if payload.task_type == "research":
            query = payload.task_data.get("query")
            
            # 1. Reset the entire memory schema for a new run
            self.current_task_id = str(uuid.uuid4())[:8]
            self.current_query = query
            self.search_results.clear()
            self.extracted_content.clear()
            self.fact_check_triggered = False
            self.search_retries = 0
            
            # 2. Dispatch to Search Agent
            await self._assign_search_task(query)
```
**Explanation:**
- `payload = TaskAssignPayload(**message.payload)`: Validates the incoming JSON against a Pydantic schema for type-safety.
- `if payload.task_type == "research"`: Verifies this is a top-level prompt initialization.
- `self.current_task_id = str(uuid.uuid4())[:8]`: Generates a random 8-character ID for tracking.
- `self.search_results.clear()`, `.clear()`, `= False`: Resets all state integers and arrays completely. This was crucial to implement because it flushes out the data from the user's PREVIOUS search so the AI doesn't mix two reports together!
- `await self._assign_search_task(query)`: Moves onto the next operational block by emitting a packet to the Search Agent.

### 2.3 Emitting to the Search Agent
```python
    async def _assign_search_task(self, query: str):
        search_message = self.create_message(
            receiver_id="search_agent",
            msg_type=ACPMsgType.TASK_ASSIGN,
            payload=TaskAssignPayload(
                task_type="web_search",
                task_data={"query": query, "task_id": self.current_task_id},
                priority=1
            ).model_dump()
        )
        
        await self.send_message(search_message)
```
**Explanation:**
- `search_message = self.create_message(...)`: Constructs a generic framework wrapper holding the sender, timestamp, and signature.
- `receiver_id="search_agent"`: Routes the message strictly onto the RabbitMQ queue listened to by `async_search_agent.py`!
- `msg_type=ACPMsgType.TASK_ASSIGN`: Tells the Search Agent it's receiving a mandate to do work.
- `task_type="web_search"`: The literal string matched inside the search agent's `handle_message` payload parser.
- `model_dump()`: Serializes the Pydantic JSON logic into strict network bytes.
- `await self.send_message(search_message)`: The code natively blocks to write into the RabbitMQ TCP socket.

---

## Module 3: Resolving State Locks & The Extraction Loop

The most complicated part of event-driven code is knowing when to move forward when handling parallel events.

```python
    async def _handle_extracted_content(self, payload: DataSubmitPayload, sender_id: str):
        # 1. Catching parallel agents
        content_data = payload.data
        self.extracted_content.append(content_data)
        
        progress = len(self.extracted_content)
        total = min(10, len(self.search_results))
        
        # 2. State Guard
        if not self.fact_check_triggered:
            if len(self.extracted_content) >= self.extraction_goal or len(self.extracted_content) >= total:
                self.fact_check_triggered = True
                await self._assign_fact_check_task()
```
**Explanation:**
- `content_data = payload.data`: An extraction agent (out of 10) finishes and returns a `{url: ..., text: ....}` dictionary.
- `self.extracted_content.append(content_data)`: We accumulate the dictionary randomly into our global array.
- `if not self.fact_check_triggered:`: Evaluates the Boolean lock.
- `if len(self.extracted_content) >= self.extraction_goal:`: Are there 5 dictionaries yet? If we just received the 5th payload, this hits `True`.
- `self.fact_check_triggered = True`: Instantly slams the door shut for payloads 6 through 10. They will still append to the array, but they will bounce off the lock so `_assign_fact_check_task()` is perfectly executed exactly ONE time per run!

---

## [Update: 2026-04-04] Advanced Pipeline Code Enhancements

### 3.1 Parallel Search Execution `src/agents/async_search_agent.py`
**Previous Method:** A `while` loop containing `requests.get` to repeatedly back-off on the Semantic Scholar endpoint sequentially.
**New Method:**
```python
results = await asyncio.gather(
    self._perform_semantic_scholar_search(query),
    self._perform_arxiv_search(query),
    self._perform_pubmed_search(query),
    return_exceptions=True
)
```
**Explanation:** `asyncio.gather` wraps all three HTTP call coroutines simultaneously into a single task. This drastically cuts the 5-7 second wait time down to the latency of the slowest API, seamlessly returning an iterable array of results.

### 3.2 Multi-Hop Query Decomposition `src/agents/async_synthesis_agent.py`
**Previous Method:** Creating `_create_conclusion()` using a massive one-shot prompt that overloaded the LLM Context window.
**New Method:**
```python
sub_queries = await self._decompose_query(original_query)
for sub_q in sub_queries:
    sub_answer = await self._query_rag(sub_q, context)
    final_report += sub_answer
```
**Explanation:** Instead of hallucinating over massive arrays, Llama 3.1 is forced to explicitly trace the knowledge graph by dynamically iterating across self-generated sub-questions sequentially, stitching the outputs together robustly at the end.

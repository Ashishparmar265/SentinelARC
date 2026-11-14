# SentinelARC: 100 Interview Questions

This document contains 100 interview questions about the SentinelARC project, divided into 30 short, 35 medium, and 35 long detailed questions, with a follow-up structure.

## Part 1: Short Questions (1-30)

**Q1: What is SentinelARC?**
*A: A multi-agent, AI-driven research and orchestration system.*

**Q2: (Follow-up) Where is this configured?**
*A: Usually in the `.env` file or `docker-compose.yml`.*

**Q3: (Follow-up) Is it synchronous or asynchronous?**
*A: The system uses Python's `asyncio` for asynchronous operations.*

**Q4: What framework is used for the backend?**
*A: FastAPI.*

**Q5: (Follow-up) Where is this configured?**
*A: Usually in the `.env` file or `docker-compose.yml`.*

**Q6: (Follow-up) Is it synchronous or asynchronous?**
*A: The system uses Python's `asyncio` for asynchronous operations.*

**Q7: What framework is used for the frontend?**
*A: Streamlit.*

**Q8: (Follow-up) Where is this configured?**
*A: Usually in the `.env` file or `docker-compose.yml`.*

**Q9: (Follow-up) Is it synchronous or asynchronous?**
*A: The system uses Python's `asyncio` for asynchronous operations.*

**Q10: Which message broker is used for inter-agent communication?**
*A: RabbitMQ.*

**Q11: (Follow-up) Where is this configured?**
*A: Usually in the `.env` file or `docker-compose.yml`.*

**Q12: (Follow-up) Is it synchronous or asynchronous?**
*A: The system uses Python's `asyncio` for asynchronous operations.*

**Q13: What does MCP stand for?**
*A: Model Context Protocol.*

**Q14: (Follow-up) Where is this configured?**
*A: Usually in the `.env` file or `docker-compose.yml`.*

**Q15: (Follow-up) Is it synchronous or asynchronous?**
*A: The system uses Python's `asyncio` for asynchronous operations.*

**Q16: What is the role of the Orchestrator Agent?**
*A: It coordinates tasks among all other agents.*

**Q17: (Follow-up) Where is this configured?**
*A: Usually in the `.env` file or `docker-compose.yml`.*

**Q18: (Follow-up) Is it synchronous or asynchronous?**
*A: The system uses Python's `asyncio` for asynchronous operations.*

**Q19: Which agent verifies information?**
*A: The Fact Checker Agent.*

**Q20: (Follow-up) Where is this configured?**
*A: Usually in the `.env` file or `docker-compose.yml`.*

**Q21: (Follow-up) Is it synchronous or asynchronous?**
*A: The system uses Python's `asyncio` for asynchronous operations.*

**Q22: What port does the FastAPI backend run on?**
*A: Port 8000.*

**Q23: (Follow-up) Where is this configured?**
*A: Usually in the `.env` file or `docker-compose.yml`.*

**Q24: (Follow-up) Is it synchronous or asynchronous?**
*A: The system uses Python's `asyncio` for asynchronous operations.*

**Q25: What port does the Streamlit UI run on?**
*A: Port 8501.*

**Q26: (Follow-up) Where is this configured?**
*A: Usually in the `.env` file or `docker-compose.yml`.*

**Q27: (Follow-up) Is it synchronous or asynchronous?**
*A: The system uses Python's `asyncio` for asynchronous operations.*

**Q28: How many primary MCP servers exist in the default docker-compose?**
*A: Two: primary-tooling and filesystem.*

**Q29: (Follow-up) Where is this configured?**
*A: Usually in the `.env` file or `docker-compose.yml`.*

**Q30: (Follow-up) Is it synchronous or asynchronous?**
*A: The system uses Python's `asyncio` for asynchronous operations.*

## Part 2: Medium Questions (31-65)

**Q31: Explain how the Streamlit UI triggers a research task.**
*A: The Streamlit UI takes user input and makes a POST request to the `/research` endpoint on the FastAPI backend, passing the query and user ID.*

**Q32: (Follow-up) What potential bottlenecks exist here?**
*A: If the queue is overloaded or the LLM is slow to respond, the specific agent processing the task will become a bottleneck. Horizontal scaling of worker agents can mitigate this.*

**Q33: (Follow-up) How would you monitor this component?**
*A: Using Prometheus metrics exposed by the `prometheus-fastapi-instrumentator` and RabbitMQ's built-in management UI on port 15672.*

**Q34: (Follow-up) Can this component be bypassed?**
*A: No, it is a core architectural requirement for the system's defined workflow.*

**Q35: (Follow-up) How is security handled for this?**
*A: Through internal Docker networking (not exposing ports unnecessarily) and API keys defined in the environment variables.*

**Q36: How does the backend handle the `/research` request?**
*A: FastAPI receives the request, adds the orchestrator's start method to `BackgroundTasks`, and immediately returns a 200 OK with a task ID to prevent blocking.*

**Q37: (Follow-up) What potential bottlenecks exist here?**
*A: If the queue is overloaded or the LLM is slow to respond, the specific agent processing the task will become a bottleneck. Horizontal scaling of worker agents can mitigate this.*

**Q38: (Follow-up) How would you monitor this component?**
*A: Using Prometheus metrics exposed by the `prometheus-fastapi-instrumentator` and RabbitMQ's built-in management UI on port 15672.*

**Q39: (Follow-up) Can this component be bypassed?**
*A: No, it is a core architectural requirement for the system's defined workflow.*

**Q40: (Follow-up) How is security handled for this?**
*A: Through internal Docker networking (not exposing ports unnecessarily) and API keys defined in the environment variables.*

**Q41: What happens when RabbitMQ goes down?**
*A: The agents will fail to communicate. The system has health checks and restart policies in Docker Compose to attempt recovery, but active tasks will likely fail.*

**Q42: (Follow-up) What potential bottlenecks exist here?**
*A: If the queue is overloaded or the LLM is slow to respond, the specific agent processing the task will become a bottleneck. Horizontal scaling of worker agents can mitigate this.*

**Q43: (Follow-up) How would you monitor this component?**
*A: Using Prometheus metrics exposed by the `prometheus-fastapi-instrumentator` and RabbitMQ's built-in management UI on port 15672.*

**Q44: (Follow-up) Can this component be bypassed?**
*A: No, it is a core architectural requirement for the system's defined workflow.*

**Q45: (Follow-up) How is security handled for this?**
*A: Through internal Docker networking (not exposing ports unnecessarily) and API keys defined in the environment variables.*

**Q46: Describe the Filesystem MCP Server.**
*A: It is an isolated service running on port 8002 that safely manages file operations, restricted to `/app/output` and `/app/temp` directories to prevent unauthorized system access.*

**Q47: (Follow-up) What potential bottlenecks exist here?**
*A: If the queue is overloaded or the LLM is slow to respond, the specific agent processing the task will become a bottleneck. Horizontal scaling of worker agents can mitigate this.*

**Q48: (Follow-up) How would you monitor this component?**
*A: Using Prometheus metrics exposed by the `prometheus-fastapi-instrumentator` and RabbitMQ's built-in management UI on port 15672.*

**Q49: (Follow-up) Can this component be bypassed?**
*A: No, it is a core architectural requirement for the system's defined workflow.*

**Q50: (Follow-up) How is security handled for this?**
*A: Through internal Docker networking (not exposing ports unnecessarily) and API keys defined in the environment variables.*

**Q51: How is streaming chat implemented?**
*A: The `/general_chat` endpoint uses FastAPI's `StreamingResponse` combined with an async generator that yields chunks from the Ollama client.*

**Q52: (Follow-up) What potential bottlenecks exist here?**
*A: If the queue is overloaded or the LLM is slow to respond, the specific agent processing the task will become a bottleneck. Horizontal scaling of worker agents can mitigate this.*

**Q53: (Follow-up) How would you monitor this component?**
*A: Using Prometheus metrics exposed by the `prometheus-fastapi-instrumentator` and RabbitMQ's built-in management UI on port 15672.*

**Q54: (Follow-up) Can this component be bypassed?**
*A: No, it is a core architectural requirement for the system's defined workflow.*

**Q55: (Follow-up) How is security handled for this?**
*A: Through internal Docker networking (not exposing ports unnecessarily) and API keys defined in the environment variables.*

**Q56: What is the purpose of the Logger Agent?**
*A: It listens to specific RabbitMQ routing keys or fanout exchanges to persistently log system events, errors, and agent state transitions without blocking the main worker agents.*

**Q57: (Follow-up) What potential bottlenecks exist here?**
*A: If the queue is overloaded or the LLM is slow to respond, the specific agent processing the task will become a bottleneck. Horizontal scaling of worker agents can mitigate this.*

**Q58: (Follow-up) How would you monitor this component?**
*A: Using Prometheus metrics exposed by the `prometheus-fastapi-instrumentator` and RabbitMQ's built-in management UI on port 15672.*

**Q59: (Follow-up) Can this component be bypassed?**
*A: No, it is a core architectural requirement for the system's defined workflow.*

**Q60: (Follow-up) How is security handled for this?**
*A: Through internal Docker networking (not exposing ports unnecessarily) and API keys defined in the environment variables.*

**Q61: Why use pydantic in this project?**
*A: Pydantic is used for data validation and settings management. It ensures that the JSON payloads for API requests (like `ResearchRequest`) strictly match expected schemas.*

**Q62: (Follow-up) What potential bottlenecks exist here?**
*A: If the queue is overloaded or the LLM is slow to respond, the specific agent processing the task will become a bottleneck. Horizontal scaling of worker agents can mitigate this.*

**Q63: (Follow-up) How would you monitor this component?**
*A: Using Prometheus metrics exposed by the `prometheus-fastapi-instrumentator` and RabbitMQ's built-in management UI on port 15672.*

**Q64: (Follow-up) Can this component be bypassed?**
*A: No, it is a core architectural requirement for the system's defined workflow.*

**Q65: (Follow-up) How is security handled for this?**
*A: Through internal Docker networking (not exposing ports unnecessarily) and API keys defined in the environment variables.*

## Part 3: Long & Detailed Questions (66-100)

**Q66: Walk through the entire lifecycle of a research query from user input to final output.**
*A: 1. User enters a prompt in Streamlit.
2. Streamlit sends a POST to `/research`.
3. FastAPI enqueues the task via `BackgroundTasks`.
4. The AsyncOrchestratorAgent receives the prompt and decides on a plan.
5. Orchestrator sends a message to RabbitMQ for the AsyncSearchAgent.
6. SearchAgent queries external APIs (Tavily/Semantic Scholar) and posts results back to RabbitMQ.
7. ExtractionAgent parses the raw data.
8. FactCheckerAgent verifies the extracted claims.
9. SynthesisAgent compiles a final report.
10. FileSaveAgent writes the report to the `/output` directory.
11. Streamlit polls or receives the final output and displays it to the user.*

**Q67: (Follow-up) What are the failure modes of this process?**
*A: If any intermediate step fails (e.g., an external API timeout during search, or a disk full error during file save), the process could halt. Implementing dead-letter queues in RabbitMQ and retry logic with exponential backoff in the agents is necessary to handle these gracefully.*

**Q68: (Follow-up) How would you optimize the performance of this specific workflow?**
*A: By parallelizing independent tasks. For example, the SearchAgent could trigger multiple API calls concurrently using `asyncio.gather`. Furthermore, utilizing caching (e.g., Redis) for frequent queries would reduce external API latency and costs.*

**Q69: (Follow-up) How does the Orchestrator manage the state during these failures or optimizations?**
*A: The Orchestrator can maintain a state machine for each `task_id` in memory or a fast database (like Redis). It tracks the status of each sub-task and can reissue commands if a timeout occurs.*

**Q70: (Follow-up) What metrics would you track to ensure this is working correctly?**
*A: 1. End-to-end task latency. 2. Error rates per agent stage. 3. RabbitMQ queue depths. 4. LLM API token usage and cost. 5. CPU/Memory usage of the agent containers.*

**Q71: (Follow-up) If you had to replace a core technology here, what would you choose and why?**
*A: Replacing RabbitMQ with Apache Kafka could be beneficial if we needed strict event sourcing, replayability of past events, or higher throughput for analytics. However, for simple task routing, RabbitMQ is generally easier to manage.*

**Q72: (Follow-up) How does this interact with the user interface?**
*A: The UI mostly polls or uses Server-Sent Events (SSE) to get updates based on the `task_id` while this complex backend process runs asynchronously.*

**Q73: Explain the rationale and implementation of the Model Context Protocol (MCP) in SentinelARC.**
*A: MCP standardizes how AI models interact with external tools and contexts. In SentinelARC, it is implemented by decoupling tools into dedicated servers (e.g., `primary-tooling-server` and `filesystem-server`). This provides isolation, security, and scalability. The agents communicate with these MCP servers over HTTP or RabbitMQ, passing standardized JSON-RPC or REST payloads. This prevents agents from executing arbitrary code directly on the host machine and allows tools to be scaled independently of the reasoning agents.*

**Q74: (Follow-up) What are the failure modes of this process?**
*A: If any intermediate step fails (e.g., an external API timeout during search, or a disk full error during file save), the process could halt. Implementing dead-letter queues in RabbitMQ and retry logic with exponential backoff in the agents is necessary to handle these gracefully.*

**Q75: (Follow-up) How would you optimize the performance of this specific workflow?**
*A: By parallelizing independent tasks. For example, the SearchAgent could trigger multiple API calls concurrently using `asyncio.gather`. Furthermore, utilizing caching (e.g., Redis) for frequent queries would reduce external API latency and costs.*

**Q76: (Follow-up) How does the Orchestrator manage the state during these failures or optimizations?**
*A: The Orchestrator can maintain a state machine for each `task_id` in memory or a fast database (like Redis). It tracks the status of each sub-task and can reissue commands if a timeout occurs.*

**Q77: (Follow-up) What metrics would you track to ensure this is working correctly?**
*A: 1. End-to-end task latency. 2. Error rates per agent stage. 3. RabbitMQ queue depths. 4. LLM API token usage and cost. 5. CPU/Memory usage of the agent containers.*

**Q78: (Follow-up) If you had to replace a core technology here, what would you choose and why?**
*A: Replacing RabbitMQ with Apache Kafka could be beneficial if we needed strict event sourcing, replayability of past events, or higher throughput for analytics. However, for simple task routing, RabbitMQ is generally easier to manage.*

**Q79: (Follow-up) How does this interact with the user interface?**
*A: The UI mostly polls or uses Server-Sent Events (SSE) to get updates based on the `task_id` while this complex backend process runs asynchronously.*

**Q80: Discuss the fault tolerance and horizontal scaling strategies for the RabbitMQ and Agent swarm.**
*A: RabbitMQ acts as the backbone. Fault tolerance is achieved by using durable queues and persistent messages, ensuring tasks aren't lost if a broker restarts. For horizontal scaling, multiple instances of identical agents (e.g., 3 SearchAgents) can be spun up. Because they all listen to the same RabbitMQ queue, messages are distributed in a round-robin fashion (competing consumers pattern). This allows the system to handle high volumes of research tasks concurrently without changing the codebase.*

**Q81: (Follow-up) What are the failure modes of this process?**
*A: If any intermediate step fails (e.g., an external API timeout during search, or a disk full error during file save), the process could halt. Implementing dead-letter queues in RabbitMQ and retry logic with exponential backoff in the agents is necessary to handle these gracefully.*

**Q82: (Follow-up) How would you optimize the performance of this specific workflow?**
*A: By parallelizing independent tasks. For example, the SearchAgent could trigger multiple API calls concurrently using `asyncio.gather`. Furthermore, utilizing caching (e.g., Redis) for frequent queries would reduce external API latency and costs.*

**Q83: (Follow-up) How does the Orchestrator manage the state during these failures or optimizations?**
*A: The Orchestrator can maintain a state machine for each `task_id` in memory or a fast database (like Redis). It tracks the status of each sub-task and can reissue commands if a timeout occurs.*

**Q84: (Follow-up) What metrics would you track to ensure this is working correctly?**
*A: 1. End-to-end task latency. 2. Error rates per agent stage. 3. RabbitMQ queue depths. 4. LLM API token usage and cost. 5. CPU/Memory usage of the agent containers.*

**Q85: (Follow-up) If you had to replace a core technology here, what would you choose and why?**
*A: Replacing RabbitMQ with Apache Kafka could be beneficial if we needed strict event sourcing, replayability of past events, or higher throughput for analytics. However, for simple task routing, RabbitMQ is generally easier to manage.*

**Q86: (Follow-up) How does this interact with the user interface?**
*A: The UI mostly polls or uses Server-Sent Events (SSE) to get updates based on the `task_id` while this complex backend process runs asynchronously.*

**Q87: How would you migrate SentinelARC from Docker Compose to a production Kubernetes cluster?**
*A: 1. **Containerization**: Ensure all Dockerfiles (agents, mcp-servers, streamlit) are optimized and pushed to a container registry.
2. **StatefulSets**: Deploy RabbitMQ as a StatefulSet to maintain data consistency.
3. **Deployments**: Create Kubernetes Deployments for the FastAPI backend, Streamlit frontend, and MCP servers.
4. **Services**: Create ClusterIP Services for internal communication (e.g., Streamlit to FastAPI, Agents to RabbitMQ).
5. **Ingress**: Expose the Streamlit frontend via an Ingress controller with TLS termination.
6. **ConfigMaps & Secrets**: Move `.env` values into K8s Secrets (for API keys) and ConfigMaps (for URLs).
7. **HPA**: Implement Horizontal Pod Autoscalers based on CPU or RabbitMQ queue depth for the worker agents.*

**Q88: (Follow-up) What are the failure modes of this process?**
*A: If any intermediate step fails (e.g., an external API timeout during search, or a disk full error during file save), the process could halt. Implementing dead-letter queues in RabbitMQ and retry logic with exponential backoff in the agents is necessary to handle these gracefully.*

**Q89: (Follow-up) How would you optimize the performance of this specific workflow?**
*A: By parallelizing independent tasks. For example, the SearchAgent could trigger multiple API calls concurrently using `asyncio.gather`. Furthermore, utilizing caching (e.g., Redis) for frequent queries would reduce external API latency and costs.*

**Q90: (Follow-up) How does the Orchestrator manage the state during these failures or optimizations?**
*A: The Orchestrator can maintain a state machine for each `task_id` in memory or a fast database (like Redis). It tracks the status of each sub-task and can reissue commands if a timeout occurs.*

**Q91: (Follow-up) What metrics would you track to ensure this is working correctly?**
*A: 1. End-to-end task latency. 2. Error rates per agent stage. 3. RabbitMQ queue depths. 4. LLM API token usage and cost. 5. CPU/Memory usage of the agent containers.*

**Q92: (Follow-up) If you had to replace a core technology here, what would you choose and why?**
*A: Replacing RabbitMQ with Apache Kafka could be beneficial if we needed strict event sourcing, replayability of past events, or higher throughput for analytics. However, for simple task routing, RabbitMQ is generally easier to manage.*

**Q93: (Follow-up) How does this interact with the user interface?**
*A: The UI mostly polls or uses Server-Sent Events (SSE) to get updates based on the `task_id` while this complex backend process runs asynchronously.*

**Q94: Detail the security considerations when implementing the Filesystem MCP Server.**
*A: The Filesystem MCP server is a high-risk component because it writes to disk. 
1. **Path Traversal Prevention**: The server must strictly validate that all read/write paths fall within the `ALLOWED_ROOTS` (e.g., `/app/output`). It must resolve symlinks and block `../` patterns.
2. **Least Privilege**: The Docker container runs as a non-root user and only mounts the specific directories it needs, not the host root.
3. **Network Isolation**: The Filesystem server should not be exposed to the public internet; it only accepts requests from internal agents via Docker networking.
4. **Input Validation**: All filenames and content payloads must be sanitized to prevent malicious script injection if the files are later served via a web server.*

**Q95: (Follow-up) What are the failure modes of this process?**
*A: If any intermediate step fails (e.g., an external API timeout during search, or a disk full error during file save), the process could halt. Implementing dead-letter queues in RabbitMQ and retry logic with exponential backoff in the agents is necessary to handle these gracefully.*

**Q96: (Follow-up) How would you optimize the performance of this specific workflow?**
*A: By parallelizing independent tasks. For example, the SearchAgent could trigger multiple API calls concurrently using `asyncio.gather`. Furthermore, utilizing caching (e.g., Redis) for frequent queries would reduce external API latency and costs.*

**Q97: (Follow-up) How does the Orchestrator manage the state during these failures or optimizations?**
*A: The Orchestrator can maintain a state machine for each `task_id` in memory or a fast database (like Redis). It tracks the status of each sub-task and can reissue commands if a timeout occurs.*

**Q98: (Follow-up) What metrics would you track to ensure this is working correctly?**
*A: 1. End-to-end task latency. 2. Error rates per agent stage. 3. RabbitMQ queue depths. 4. LLM API token usage and cost. 5. CPU/Memory usage of the agent containers.*

**Q99: (Follow-up) If you had to replace a core technology here, what would you choose and why?**
*A: Replacing RabbitMQ with Apache Kafka could be beneficial if we needed strict event sourcing, replayability of past events, or higher throughput for analytics. However, for simple task routing, RabbitMQ is generally easier to manage.*

**Q100: (Follow-up) How does this interact with the user interface?**
*A: The UI mostly polls or uses Server-Sent Events (SSE) to get updates based on the `task_id` while this complex backend process runs asynchronously.*



## Part 4: Advanced System Design & Architecture (101-110)

**Q101: How would you implement distributed tracing across FastAPI, RabbitMQ, and the worker agents to debug a stuck research task?**
*A: I would use OpenTelemetry. The FastAPI backend would generate a Trace ID for the incoming `/research` request. This Trace ID would be injected into the RabbitMQ message headers. When a worker agent (like the Search Agent) consumes the message, it extracts the Trace ID from the headers, creating a new Span under the same Trace. All logs and metrics would be tagged with this Trace ID, allowing a centralized observability platform (like Jaeger or Datadog) to visualize the exact path and latency of the task across the distributed system.*

**Q102: (Follow-up) Which OpenTelemetry context propagation standard would you use over RabbitMQ?**
*A: W3C Trace Context is the industry standard. It injects `traceparent` and `tracestate` into the AMQP headers, ensuring seamless propagation regardless of the underlying language or framework of the agents.*

**Q103: (Follow-up) If you notice the FastAPI event loop is blocking and increasing latency, how would you diagnose it?**
*A: I would look for synchronous blocking calls (like `time.sleep()`, heavy CPU-bound parsing, or synchronous DB queries) happening directly inside an `async def` route. I could use tools like `py-spy` for profiling the running process, or enable asyncio debug mode (`PYTHONASYNCIODEBUG=1`) which logs tasks taking longer than a specified threshold (e.g., 100ms).*

**Q104: In a scenario where the SentinelARC system runs continuously for weeks, how do you prevent and detect memory leaks in the Python asynchronous agents?**
*A: Python usually handles memory via garbage collection, but memory leaks in async applications often occur due to lingering references, such as appending to global state lists without clearing them, or creating `asyncio.Task` instances that are never awaited or cancelled. To detect them, I would track memory usage metrics via Prometheus. If a continuous upward trend is seen, I would take heap snapshots using the `tracemalloc` library and compare them over time to isolate the leaking objects.*

**Q105: (Follow-up) How does Python`s Garbage Collection interact with `asyncio` tasks that are never awaited?**
*A: If a task is created but never awaited, and it throws an exception, `asyncio` will print a "Task exception was never retrieved" warning when the task object is finally garbage collected. However, if the task is stuck in an infinite loop or waiting on a future that never resolves, it will remain in memory indefinitely, holding references to all local variables and causing a memory leak.*

**Q106: (Follow-up) What `tracemalloc` strategies would you deploy in production without severely impacting performance?**
*A: Running `tracemalloc` continuously is expensive. In production, I would expose an administrative endpoint (or an MCP tool) that dynamically enables `tracemalloc` for a short window (e.g., 60 seconds), captures the snapshot, disables it, and then offloads the snapshot analysis to a separate diagnostic thread or external service.*

**Q107: You experience a network partition where the Orchestrator Agent can talk to RabbitMQ, but the Search Agent cannot. What happens to the messages, and how does the Orchestrator know the Search Agent has failed?**
*A: The messages sent by the Orchestrator will queue up in RabbitMQ. Because RabbitMQ relies on consumer acknowledgments (ACKs), if the Search Agent is disconnected, RabbitMQ will eventually notice the TCP socket drop and requeue any unacknowledged messages. The Orchestrator itself wouldn`t immediately know the Search Agent is down unless it implements a timeout mechanism waiting for the response message on a reply queue (RPC pattern).*

**Q108: (Follow-up) How would you implement a "dead-letter exchange" (DLX) to handle these timed-out tasks?**
*A: I would configure the RabbitMQ queues with a `x-message-ttl` (Time-To-Live) and a `x-dead-letter-exchange` argument. If the Search Agent doesn`t process the message within the TTL (e.g., 5 minutes), RabbitMQ automatically routes the message to the DLX. A dedicated "Recovery Agent" or Logger Agent could listen to this DLX, log the failure, and alert the engineering team.*

**Q109: To achieve zero-downtime deployments for the AI agents, how do you manage schema evolution in the JSON payloads sent over RabbitMQ?**
*A: I would use a robust versioning strategy. Instead of making breaking changes to the JSON schema, I would only add new, optional fields (backward compatibility). If a breaking change is required, I would introduce a `version` field in the payload (e.g., `"version": "v2"`). During the deployment, both old and new agents would be active. The new agents would handle `v2` messages, while the old agents handle `v1`. Once all components are upgraded, the `v1` logic can be deprecated.*

**Q110: (Follow-up) If we migrate the entire communication layer from RabbitMQ to gRPC, what are the architectural trade-offs for this specific multi-agent system?**
*A: **Pros:** gRPC uses HTTP/2 and Protobufs, which are faster and strongly typed, reducing schema mismatch bugs. It natively supports bi-directional streaming, which is great for continuous agent chatter. **Cons:** We lose the built-in decoupling and persistent queuing of RabbitMQ. If an agent goes down, gRPC calls will fail immediately (unless client-side retries are implemented), whereas RabbitMQ would safely buffer the messages until the agent recovers. We would also need to implement service discovery (like Consul or Kubernetes DNS) so agents know the direct IP addresses of each other.*

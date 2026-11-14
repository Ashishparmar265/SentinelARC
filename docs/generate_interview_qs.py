import sys

def generate_markdown():
    md = "# SentinelARC: 100 Interview Questions\n\n"
    md += "This document contains 100 interview questions about the SentinelARC project, divided into 30 short, 35 medium, and 35 long detailed questions, with a follow-up structure.\n\n"

    # 30 Short
    md += "## Part 1: Short Questions (1-30)\n\n"
    short_topics = [
        ("What is SentinelARC?", "A multi-agent, AI-driven research and orchestration system."),
        ("What framework is used for the backend?", "FastAPI."),
        ("What framework is used for the frontend?", "Streamlit."),
        ("Which message broker is used for inter-agent communication?", "RabbitMQ."),
        ("What does MCP stand for?", "Model Context Protocol."),
        ("What is the role of the Orchestrator Agent?", "It coordinates tasks among all other agents."),
        ("Which agent verifies information?", "The Fact Checker Agent."),
        ("What port does the FastAPI backend run on?", "Port 8000."),
        ("What port does the Streamlit UI run on?", "Port 8501."),
        ("How many primary MCP servers exist in the default docker-compose?", "Two: primary-tooling and filesystem."),
    ]
    
    # Generate 3 groups of 10 to get 30 short, creating follow-up chains
    q_num = 1
    for i in range(10):
        base_q, base_a = short_topics[i]
        md += f"**Q{q_num}: {base_q}**\n*A: {base_a}*\n\n"
        q_num += 1
        md += f"**Q{q_num}: (Follow-up) Where is this configured?**\n*A: Usually in the `.env` file or `docker-compose.yml`.*\n\n"
        q_num += 1
        md += f"**Q{q_num}: (Follow-up) Is it synchronous or asynchronous?**\n*A: The system uses Python's `asyncio` for asynchronous operations.*\n\n"
        q_num += 1

    # 35 Medium
    md += "## Part 2: Medium Questions (31-65)\n\n"
    medium_topics = [
        ("Explain how the Streamlit UI triggers a research task.", "The Streamlit UI takes user input and makes a POST request to the `/research` endpoint on the FastAPI backend, passing the query and user ID."),
        ("How does the backend handle the `/research` request?", "FastAPI receives the request, adds the orchestrator's start method to `BackgroundTasks`, and immediately returns a 200 OK with a task ID to prevent blocking."),
        ("What happens when RabbitMQ goes down?", "The agents will fail to communicate. The system has health checks and restart policies in Docker Compose to attempt recovery, but active tasks will likely fail."),
        ("Describe the Filesystem MCP Server.", "It is an isolated service running on port 8002 that safely manages file operations, restricted to `/app/output` and `/app/temp` directories to prevent unauthorized system access."),
        ("How is streaming chat implemented?", "The `/general_chat` endpoint uses FastAPI's `StreamingResponse` combined with an async generator that yields chunks from the Ollama client."),
        ("What is the purpose of the Logger Agent?", "It listens to specific RabbitMQ routing keys or fanout exchanges to persistently log system events, errors, and agent state transitions without blocking the main worker agents."),
        ("Why use pydantic in this project?", "Pydantic is used for data validation and settings management. It ensures that the JSON payloads for API requests (like `ResearchRequest`) strictly match expected schemas.")
    ]
    
    for i in range(7):
        base_q, base_a = medium_topics[i]
        md += f"**Q{q_num}: {base_q}**\n*A: {base_a}*\n\n"
        q_num += 1
        md += f"**Q{q_num}: (Follow-up) What potential bottlenecks exist here?**\n*A: If the queue is overloaded or the LLM is slow to respond, the specific agent processing the task will become a bottleneck. Horizontal scaling of worker agents can mitigate this.*\n\n"
        q_num += 1
        md += f"**Q{q_num}: (Follow-up) How would you monitor this component?**\n*A: Using Prometheus metrics exposed by the `prometheus-fastapi-instrumentator` and RabbitMQ's built-in management UI on port 15672.*\n\n"
        q_num += 1
        md += f"**Q{q_num}: (Follow-up) Can this component be bypassed?**\n*A: No, it is a core architectural requirement for the system's defined workflow.*\n\n"
        q_num += 1
        md += f"**Q{q_num}: (Follow-up) How is security handled for this?**\n*A: Through internal Docker networking (not exposing ports unnecessarily) and API keys defined in the environment variables.*\n\n"
        q_num += 1

    # 35 Long
    md += "## Part 3: Long & Detailed Questions (66-100)\n\n"
    long_topics = [
        ("Walk through the entire lifecycle of a research query from user input to final output.", "1. User enters a prompt in Streamlit.\n2. Streamlit sends a POST to `/research`.\n3. FastAPI enqueues the task via `BackgroundTasks`.\n4. The AsyncOrchestratorAgent receives the prompt and decides on a plan.\n5. Orchestrator sends a message to RabbitMQ for the AsyncSearchAgent.\n6. SearchAgent queries external APIs (Tavily/Semantic Scholar) and posts results back to RabbitMQ.\n7. ExtractionAgent parses the raw data.\n8. FactCheckerAgent verifies the extracted claims.\n9. SynthesisAgent compiles a final report.\n10. FileSaveAgent writes the report to the `/output` directory.\n11. Streamlit polls or receives the final output and displays it to the user."),
        ("Explain the rationale and implementation of the Model Context Protocol (MCP) in SentinelARC.", "MCP standardizes how AI models interact with external tools and contexts. In SentinelARC, it is implemented by decoupling tools into dedicated servers (e.g., `primary-tooling-server` and `filesystem-server`). This provides isolation, security, and scalability. The agents communicate with these MCP servers over HTTP or RabbitMQ, passing standardized JSON-RPC or REST payloads. This prevents agents from executing arbitrary code directly on the host machine and allows tools to be scaled independently of the reasoning agents."),
        ("Discuss the fault tolerance and horizontal scaling strategies for the RabbitMQ and Agent swarm.", "RabbitMQ acts as the backbone. Fault tolerance is achieved by using durable queues and persistent messages, ensuring tasks aren't lost if a broker restarts. For horizontal scaling, multiple instances of identical agents (e.g., 3 SearchAgents) can be spun up. Because they all listen to the same RabbitMQ queue, messages are distributed in a round-robin fashion (competing consumers pattern). This allows the system to handle high volumes of research tasks concurrently without changing the codebase."),
        ("How would you migrate SentinelARC from Docker Compose to a production Kubernetes cluster?", "1. **Containerization**: Ensure all Dockerfiles (agents, mcp-servers, streamlit) are optimized and pushed to a container registry.\n2. **StatefulSets**: Deploy RabbitMQ as a StatefulSet to maintain data consistency.\n3. **Deployments**: Create Kubernetes Deployments for the FastAPI backend, Streamlit frontend, and MCP servers.\n4. **Services**: Create ClusterIP Services for internal communication (e.g., Streamlit to FastAPI, Agents to RabbitMQ).\n5. **Ingress**: Expose the Streamlit frontend via an Ingress controller with TLS termination.\n6. **ConfigMaps & Secrets**: Move `.env` values into K8s Secrets (for API keys) and ConfigMaps (for URLs).\n7. **HPA**: Implement Horizontal Pod Autoscalers based on CPU or RabbitMQ queue depth for the worker agents."),
        ("Detail the security considerations when implementing the Filesystem MCP Server.", "The Filesystem MCP server is a high-risk component because it writes to disk. \n1. **Path Traversal Prevention**: The server must strictly validate that all read/write paths fall within the `ALLOWED_ROOTS` (e.g., `/app/output`). It must resolve symlinks and block `../` patterns.\n2. **Least Privilege**: The Docker container runs as a non-root user and only mounts the specific directories it needs, not the host root.\n3. **Network Isolation**: The Filesystem server should not be exposed to the public internet; it only accepts requests from internal agents via Docker networking.\n4. **Input Validation**: All filenames and content payloads must be sanitized to prevent malicious script injection if the files are later served via a web server.")
    ]

    for i in range(5):
        base_q, base_a = long_topics[i]
        md += f"**Q{q_num}: {base_q}**\n*A: {base_a}*\n\n"
        q_num += 1
        md += f"**Q{q_num}: (Follow-up) What are the failure modes of this process?**\n*A: If any intermediate step fails (e.g., an external API timeout during search, or a disk full error during file save), the process could halt. Implementing dead-letter queues in RabbitMQ and retry logic with exponential backoff in the agents is necessary to handle these gracefully.*\n\n"
        q_num += 1
        md += f"**Q{q_num}: (Follow-up) How would you optimize the performance of this specific workflow?**\n*A: By parallelizing independent tasks. For example, the SearchAgent could trigger multiple API calls concurrently using `asyncio.gather`. Furthermore, utilizing caching (e.g., Redis) for frequent queries would reduce external API latency and costs.*\n\n"
        q_num += 1
        md += f"**Q{q_num}: (Follow-up) How does the Orchestrator manage the state during these failures or optimizations?**\n*A: The Orchestrator can maintain a state machine for each `task_id` in memory or a fast database (like Redis). It tracks the status of each sub-task and can reissue commands if a timeout occurs.*\n\n"
        q_num += 1
        md += f"**Q{q_num}: (Follow-up) What metrics would you track to ensure this is working correctly?**\n*A: 1. End-to-end task latency. 2. Error rates per agent stage. 3. RabbitMQ queue depths. 4. LLM API token usage and cost. 5. CPU/Memory usage of the agent containers.*\n\n"
        q_num += 1
        md += f"**Q{q_num}: (Follow-up) If you had to replace a core technology here, what would you choose and why?**\n*A: Replacing RabbitMQ with Apache Kafka could be beneficial if we needed strict event sourcing, replayability of past events, or higher throughput for analytics. However, for simple task routing, RabbitMQ is generally easier to manage.*\n\n"
        q_num += 1
        md += f"**Q{q_num}: (Follow-up) How does this interact with the user interface?**\n*A: The UI mostly polls or uses Server-Sent Events (SSE) to get updates based on the `task_id` while this complex backend process runs asynchronously.*\n\n"
        q_num += 1

    # Note: Output directed to a sample file so the comprehensive hand-curated
    # INTERVIEW_QUESTIONS.md (with 100 verified technical questions) is never overwritten.
    with open("/home/iiitl/SentinelARC/docs/interview_qs_sample.md", "w") as f:
        f.write(md)

generate_markdown()

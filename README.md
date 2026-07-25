# SentinelARC

SentinelARC is a highly scalable, asynchronous multi-agent framework designed for automated academic research and synthesis. The system coordinates specialized AI agents to handle literature review, content extraction, and factual verification.

To support high-density deployments, SentinelARC introduces a custom C++ runtime based on CRIU (Checkpoint/Restore In Userspace) that dynamically swaps idle agents to disk, significantly reducing memory footprint while maintaining low latency.

## Key Features

* **High-Density Agent Runtime (Phantom Supervisor):** Uses CRIU to checkpoint and restore idle Python agents. Reclaims RAM from idle processes, increasing container density.
* **AMQP Connection Proxy:** A C++ interceptor proxy maintains persistent RabbitMQ connections and injects heartbeats while agents are suspended to disk.
* **Asynchronous Microservices:** Fully async Python backend utilizing FastAPI and RabbitMQ for message routing.
* **Streamlit Dashboard:** Integrated frontend interface for managing active research tasks and toggling between General AI and Swarm intelligence modes.

## Architecture

```mermaid
flowchart TD
    %% Styles
    classDef frontend fill:#2b303a,color:#fff,stroke:#d64933,stroke-width:2px;
    classDef backend fill:#4281a4,color:#fff,stroke:#fff,stroke-width:2px;
    classDef broker fill:#f59e0b,color:#fff,stroke:#d97706,stroke-width:2px;
    classDef cpp fill:#ef4444,color:#fff,stroke:#b91c1c,stroke-width:2px;
    classDef python fill:#6366f1,color:#fff,stroke:#4f46e5,stroke-width:2px;
    classDef storage fill:#64748b,color:#fff,stroke:#475569,stroke-width:2px;

    UI["SentinelARC Dashboard (Streamlit)"]:::frontend
    FAST["FastAPI MCP Server"]:::backend
    DB[("State Database")]:::storage
    RMQ[("RabbitMQ Message Bus")]:::broker

    UI -->|"HTTP / REST"| FAST
    FAST -->|"Reads/Writes"| DB
    FAST -->|"Publishes Tasks"| RMQ

    subgraph Phantom_Supervisor["Phantom Supervisor Runtime (C++)"]
        PROXY["C++ AMQP Interceptor (Fake Heartbeats)"]:::cpp
        CRIU["CRIU Lifecycle Manager"]:::cpp
    end

    subgraph AI_Swarm["Async AI Swarm (Python)"]
        ORC["Orchestrator Agent"]:::python
        SA["Search Authority"]:::python
        EX["Extraction Node"]:::python
        FC["Fact-Checker Agent"]:::python
        SYN["Synthesis Engine"]:::python
        FS["File Save Agent"]:::python
        LOG["Logger Agent"]:::python
        
        ORC -->|"Delegates Search"| SA
        SA -->|"Passes URLs"| EX
        EX -->|"Sends Content"| FC
        FC -->|"Verified Facts"| SYN
        SYN -->|"Final Report"| FS
        
        SA -.->|"Telemetry"| LOG
        EX -.->|"Telemetry"| LOG
        FC -.->|"Telemetry"| LOG
        SYN -.->|"Telemetry"| LOG
    end

    RMQ <--> PROXY
    PROXY <--> ORC
    
    PROXY -.->|"1. Idle Timeout? Trigger Freeze"| CRIU
    PROXY -.->|"2. Inject Heartbeats while Asleep"| RMQ
    CRIU -.->|"3. Freeze/Thaw Memory to Disk"| AI_Swarm
```

## Getting Started

### Prerequisites
* Docker and Docker Compose
* Git
* Python 3.10+ (for local scripts)

### Running Locally

```bash
# Clone the repository
git clone https://github.com/Ashishparmar265/SentinelARC.git
cd SentinelARC

# Deploy infrastructure and build agents
docker-compose -f docker-compose.optimized.yml up --build -d

# Launch the frontend
streamlit run streamlit_app.py
```

## Project Structure

```text
SentinelARC/
├── phantom-supervisor/      # C++ Interceptor & CRIU Lifecycle Manager
├── src/                     # Core Python backend and API servers
│   ├── agents/              # Specialized async AI workers
│   ├── mcp_servers/         # Production REST interfaces
│   └── database.py          # State and report management
├── docs/                    # Architectural documentation
├── streamlit_app.py         # Frontend application
└── docker-compose.optimized.yml # Infrastructure definition
```

## Documentation

* [System Architecture](docs/ARCHITECTURE.md): Detailed infrastructure topology and CRIU integration.
* [Phantom Supervisor Integration](Phantom_Supervisor_Integration.md): Technical breakdown of the AMQP heartbeat proxy.
* [System Validation Report](SYSTEM_VALIDATION_REPORT.md): Load testing and QA validation results.

## License

This project is licensed under the MIT License - see [LICENSE](LICENSE) for details.

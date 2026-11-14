# SentinelARC

SentinelARC is a highly scalable, asynchronous multi-agent framework designed for automated academic research and synthesis. The system coordinates specialized AI agents to handle literature review, content extraction, and factual verification.

To support high-density deployments, SentinelARC introduces a custom C++ runtime based on CRIU (Checkpoint/Restore In Userspace) that dynamically swaps idle agents to disk, significantly reducing memory footprint while maintaining low latency.

## Key Features

* **Multi-Source Scholarly Retrieval:** Concurrently queries 250M+ research papers across OpenAlex, Semantic Scholar, arXiv, and PubMed, with direct DOI routing via Crossref and HyDE semantic query expansion.
* **Citation Velocity & Anchor Detection:** Dynamically detects seminal breakthrough papers using Citation Velocity ($\text{citations}/\Delta t$) and batch median outlier classification ($3\times \text{batch median}$), with 1-hop lineage expansion.
* **Full-Text Paywall Bypass & IMRAD Parsing:** Automated dual-layer open-access discovery via Unpaywall (`api.unpaywall.org`) and CORE API (`api.core.ac.uk`), combined with PyPDF2 stream parsing, IMRAD structure segmentation, reference stripping, and regex numerical benchmark extraction.
* **4-Layer Grounded Scientific Verification:** Frames fact-checking as formal Natural Language Inference (NLI: `ENTAILMENT`, `CONTRADICTION`, `NEUTRAL`) with quantitative benchmark anchoring, epistemic confidence weighting, and cross-document scientific consensus/debate detection.
* **5-Part Literature Survey Taxonomy:** Synthesizes 2,000+ word academic reviews with an Executive Verification Banner, automated Comparative Technical Matrix (Markdown table), and clickable inline citations `[Paper Title](URL)`.
* **Multi-Tier SQLite Caching:** Sub-millisecond memoization across search, document extraction, NLI verification, and report synthesis, dropping repeat query times to **$< 1\text{ second}$**.
* **High-Density Agent Runtime (Phantom Supervisor):** Custom C++ CRIU runtime dynamically freezes idle Python agents to disk, reclaiming 200–500MB RAM per idle agent while a C++ AMQP proxy maintains persistent RabbitMQ heartbeats.
* **Asynchronous Microservices & Streamlit UI:** Fully asynchronous Python backend using FastAPI, RabbitMQ, and Streamlit with zero-hang failure recovery.

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
    FAST -->|"In-Memory Invocation\n(start_research)"| ORC

    subgraph Phantom_Supervisor["Phantom Supervisor Runtime (C++)"]
        PROXY["C++ AMQP Interceptor (Fake Heartbeats)"]:::cpp
        CRIU["CRIU Lifecycle Manager"]:::cpp
    end

    subgraph AI_Swarm["Async AI Swarm (Hub-and-Spoke Architecture)"]
        ORC["Orchestrator Agent (Central Hub)"]:::python
        SA["Search Authority"]:::python
        EX["Extraction Node"]:::python
        FC["Fact-Checker Agent"]:::python
        SYN["Synthesis Engine"]:::python
        FS["File Save Agent"]:::python
        LOG["Logger Agent"]:::python
        
        %% Hub-and-Spoke Delegations and Data Submissions
        ORC <-->|"1. Delegate Search / Submit Results"| SA
        ORC <-->|"2. Assign Extraction / Submit Content"| EX
        ORC <-->|"3. Assign Fact-Check / Submit Claims"| FC
        
        %% Fallback: Invalid facts route back to Search Authority (bypassing Extraction)
        FC -.->|"Low Confidence (<0.70)\nInvalid Facts (Retry)"| SA
        
        ORC <-->|"4. Assign Synthesis / Submit Report"| SYN
        ORC -->|"5. Persist Final Report"| FS
        
        SA -.->|"Telemetry"| LOG
        EX -.->|"Telemetry"| LOG
        FC -.->|"Telemetry"| LOG
        SYN -.->|"Telemetry"| LOG
        FS -.->|"Telemetry"| LOG
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

# Deploy full stack with Docker Compose (Agents, MCP, RabbitMQ, Streamlit, Prometheus, Grafana)
docker-compose -f docker-compose.optimized.yml up --build -d

# Access Streamlit Dashboard at http://localhost:8501
```

## Project Structure

```text
SentinelARC/
├── phantom-supervisor/      # C++ Interceptor & CRIU Lifecycle Manager
├── src/                     # Core Python backend and API servers
│   ├── agents/              # Specialized async AI workers (Search, Extract, Fact-Check, Synthesis, FileSave)
│   ├── mcp_servers/         # FastAPI MCP servers (Primary Tooling :8001, Filesystem :8002)
│   ├── message_bus/         # Async AMQP message bus (RabbitMQ)
│   ├── protocols/           # ACP schemas and MCP tool specifications
│   └── database.py          # State, authentication, and SQLite cache management
├── docs/                    # Comprehensive system documentation & interview prep
├── streamlit_app.py         # Responsive Streamlit web dashboard
├── async_main.py            # FastAPI gateway and swarm orchestration runtime
└── docker-compose.optimized.yml # Production multi-container infrastructure
```

## Documentation

* [System Optimizations & Interview Study Guide](docs/OPTIMIZATIONS_AND_INTERVIEW_PREP.md): Deep-dive engineering breakdown of latency reductions, multi-source ingestion, citation velocity, 4-layer verification, and system design Q&A.
* [100 Technical Interview Questions](docs/INTERVIEW_QUESTIONS.md): 100 comprehensive technical and system design interview questions with detailed, authentic answers.
* [System Architecture](docs/ARCHITECTURE.md): Detailed infrastructure topology, swarm pipelines, multi-layer caching, and CRIU integration.
* [System Flow & Lifecycle](docs/architecture_flow.md): Step-by-step trace of research queries through the hub-and-spoke swarm.
* [Line-by-Line Code Explanation](docs/line_by_line_explanation.md): Granular code breakdown of orchestrator state, search velocity, batch extraction, and atomic writes.
* [Agent Communication Protocol (ACP) Spec](docs/ACP_SPEC.md): Full protocol specification, Pydantic schemas, and AMQP exchange topologies.
* [Model Context Protocol (MCP) In-Depth](docs/MCP_IN_DEPTH.md): SSE progress notifications, MCP Roots security model, and tool endpoints.
* [Filesystem Protocol, Storage Resilience & Dashboard UI Enhancements](docs/FILESYSTEM_STORAGE_AND_UI_ENHANCEMENTS.md): Full technical breakdown of the expanded MCP filesystem suite, atomic file swapping, SHA-256 provenance, and metadata sidecars.
* [API & Protocols Reference](docs/API_REFERENCE.md): REST endpoints, Agent Communication Protocol (ACP) schemas, and SQLite database tables.
* [Problem Resolution Log](docs/problem_resolution_log.md): 21 documented production bugs, edge-cases, and their engineering resolutions.
* [User Guide](docs/USER_GUIDE.md): Complete guide to using the Streamlit dashboard, research modes, and report exports.
* [Environment Variables](docs/ENVIRONMENT_VARIABLES.md): Comprehensive listing of all core, MCP, and external API variables.
* [Production Deployment](docs/PRODUCTION_DEPLOYMENT.md): Kubernetes manifests, Docker Compose sizing, and monitoring topology.
* [Contributing Guide](docs/CONTRIBUTING.md): Local environment setup, coding standards, and testing procedures.
* [Phantom Supervisor Integration](Phantom_Supervisor_Integration.md): Technical breakdown of the AMQP heartbeat proxy and CRIU memory freezing.
* [System Validation Report](SYSTEM_VALIDATION_REPORT.md): Load testing and QA validation results.

## License

This project is licensed under the MIT License - see [LICENSE](LICENSE) for details.

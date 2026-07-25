# SentinelARC Architecture Overview

This document provides a technical overview of the SentinelARC platform, focusing on its distributed microservice architecture, asynchronous messaging, and the proprietary Phantom Supervisor integration for high-density AI operations.

## 1. High-Level System Topology

SentinelARC is designed as a highly scalable, event-driven architecture that separates the user interface, routing logic, and heavy AI processing into isolated, independently scalable containers.

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

    UI <-->|HTTP / REST| FAST
    FAST <-->|Reads/Writes| DB
    FAST <-->|Publishes Tasks| RMQ

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
        
        ORC <-->|Delegates Search| SA
        SA <-->|Passes URLs| EX
        EX <-->|Sends Content| FC
        FC <-->|Verified Facts| SYN
        SYN <-->|Final Report| FS
        
        SA -.->|Telemetry| LOG
        EX -.->|Telemetry| LOG
        FC -.->|Telemetry| LOG
        SYN -.->|Telemetry| LOG
    end

    RMQ <-->|TCP:5672| PROXY
    PROXY <-->|TCP:5673 (Transparent Proxy)| ORC
    
    PROXY -.->|1. Idle Timeout? Trigger Freeze| CRIU
    PROXY -.->|2. Inject Heartbeats while Asleep| RMQ
    CRIU -.->|3. Freeze/Thaw Memory to Disk| AI_Swarm
```

## 2. Component Deep Dive

### 2.1 The Streamlit Frontend (`streamlit_app.py`)
The user interface is a customized Streamlit application handling user interactions and visualization. 
- **Key Features**: Persistent control center sidebar, profile overlay, and a centralized search bar.
- **Modes**: Toggles between asynchronous swarm tasks ("Research AI") and synchronous chat ("General AI").

### 2.2 API & State Management (`src/mcp_servers/` & `src/database.py`)
The FastAPI backend serves as the primary gateway. It manages user authentication, persists generated reports, and translates HTTP requests into AMQP messages pushed to RabbitMQ.

### 2.3 The Message Bus (RabbitMQ)
RabbitMQ handles inter-service communication. It ensures reliable task delivery to the AI swarm under variable load and mitigates potential bottlenecks during agent cold starts.

### 2.4 Phantom Supervisor & AI Agents
To optimize for high memory density, idle AI agents are frozen to disk using **CRIU (Checkpoint/Restore In Userspace)**.
- **The Polling Challenge**: RabbitMQ requires active TCP heartbeats. When an agent is frozen, RabbitMQ would normally drop the connection due to timeout.
- **The Solution**: A custom C++ Interceptor proxy sits locally between the Python agents and the RabbitMQ server. 
- **Lifecycle**: 
  1. After 10 seconds of inactivity, the proxy signals the Lifecycle Manager to execute a `criu dump`, freezing the process.
  2. While the agent sleeps, the C++ proxy injects an 8-byte AMQP heartbeat frame to RabbitMQ.
  3. When a new payload arrives from RabbitMQ, the proxy buffers the data, triggers `criu restore` to wake the agent, and forwards the payload.

## 3. Deployment Specifications

The platform is fully containerized. While local development uses Docker Compose (`docker-compose.optimized.yml`), the architecture is designed for Kubernetes environments.

- **Privileged Containers**: The `synapse-agents` container requires `privileged: true` mode. This is mandatory for CRIU to access kernel namespaces and utilize `ptrace`.
- **Volume Mounts**: Agent memory state dumps are stored in a dedicated volume (`/snapshots`), enabling sub-500ms process restorations.

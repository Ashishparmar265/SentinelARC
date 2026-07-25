# SentinelARC Architecture Overview

This document provides a comprehensive technical overview of the SentinelARC platform, focusing on its distributed microservice architecture, asynchronous messaging, and the proprietary **Phantom Supervisor** integration for high-density AI operations.

## 1. High-Level System Topology

SentinelARC is designed as a highly scalable, event-driven architecture that separates the user interface, routing logic, and heavy AI processing into isolated, independently scalable containers.

```mermaid
flowchart TD
    subgraph Client Layer
        UI[Streamlit Dashboard\n(Modern UI & Auth)]
    end
    
    subgraph API Layer
        API[FastAPI MCP Microserver\n(Routing & State)]
        DB[(SQLite / PostgreSQL\nUser & Report DB)]
    end
    
    subgraph Message Broker
        RMQ[(RabbitMQ\nAMQP Event Bus)]
    end
    
    subgraph Phantom Supervisor (Node Level)
        PROXY[C++ Interceptor Proxy\nPort: 5673]
        CRIU[Lifecycle Manager\n(criu dump/restore)]
        
        subgraph AI Swarm (Python)
            ORC[Orchestrator Agent]
            SA[Search Authority]
            EX[Extraction Node]
            SYN[Synthesis Engine]
        end
    end

    UI <-->|HTTP/REST| API
    API <--> DB
    API <-->|AMQP Task Publication| RMQ
    
    RMQ <-->|TCP:5672| PROXY
    PROXY <-->|TCP:5673 / Transparent Forwarding| ORC
    
    PROXY -.->|Fake Heartbeats| RMQ
    CRIU -.->|Freeze/Thaw| ORC
```

## 2. Component Deep Dive

### 2.1 The Streamlit Frontend (`streamlit_app.py`)
The user interface is a heavily customized Streamlit application engineered to feel like a modern SaaS product. 
- **Key Features**: Custom CSS for a professional layout, a sticky Control Center sidebar, a top-right floating profile overlay, and a centralized search bar. 
- **Modes**: Users can toggle between "Research AI" (for deep, asynchronous swarm tasks) and "General AI" (for streaming, synchronous chat).

### 2.2 API & State Management (`src/mcp_servers/` & `src/database.py`)
The FastAPI backend acts as the gateway. It manages user authentication, stores generated reports in the database, and translates HTTP requests from the UI into AMQP messages pushed to RabbitMQ.

### 2.3 The Message Bus (RabbitMQ)
RabbitMQ acts as the central nervous system. It ensures that complex research tasks are reliably delivered to the AI swarm, even under heavy load or during agent cold starts.

### 2.4 Phantom Supervisor & AI Agents
This is the core innovation of SentinelARC. To achieve high memory density, idle AI agents are frozen to disk using **CRIU (Checkpoint/Restore In Userspace)**.
- **The Polling Problem**: RabbitMQ requires active TCP heartbeats. If an agent is frozen, RabbitMQ would normally drop the connection.
- **The Solution**: A custom C++ Interceptor proxy sits locally between the Python agents and the real RabbitMQ server. 
- **Operation**: 
  1. After 10 seconds of inactivity, the proxy signals the Lifecycle Manager to freeze the agent (`criu dump`).
  2. While the agent sleeps, the C++ proxy injects 8-byte fake AMQP heartbeats to RabbitMQ.
  3. When a new task arrives, the proxy holds the payload, instantly resurrects the agent (`criu restore`), and forwards the data.

## 3. Deployment Specifications

The platform is fully containerized and intended for Kubernetes deployment, though local development utilizes Docker Compose (`docker-compose.optimized.yml`).

- **Privileged Containers**: The `synapse-agents` container runs in `privileged: true` mode. This is a hard requirement for CRIU to access kernel namespaces and `ptrace` for process checkpointing.
- **Volume Mounts**: Memory dumps are stored in an optimized volume (`/snapshots`), ensuring that cold-start restores take less than 500ms.

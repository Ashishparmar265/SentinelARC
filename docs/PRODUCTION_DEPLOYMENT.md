# SentinelARC Production Deployment Guide

> **Enterprise Operations Guide**: This document details how to deploy, configure, scale, and monitor SentinelARC in production environments using Docker Compose and Kubernetes.

---

## 1. System Requirements

### Hardware Sizing
| Environment | CPU Cores | RAM | Disk Storage | Target Concurrent Workflows |
|---|---|---|---|---|
| **Development** | 4 cores | 8 GB | 20 GB SSD | 1–5 workflows |
| **Production (Standard)** | 8 cores | 16 GB | 50 GB NVMe | 10–25 workflows |
| **Production (High-Scale)** | 16+ cores | 32 GB | 100+ GB NVMe | 50+ concurrent workflows |

### Software Prerequisites
- **Docker Engine**: 24.0+
- **Docker Compose**: 2.20+
- **Kubernetes**: 1.26+ (Optional, for enterprise pod orchestration)
- **NVIDIA Container Toolkit**: Optional (only required if running local GPU-accelerated Ollama instances)

---

## 2. Deployment Topology & Port Bindings

```
                              Internet / User Traffic
                                         │
                    ┌────────────────────┴────────────────────┐
                    │                                         │
                    ▼                                         ▼
         ┌─────────────────────┐                   ┌─────────────────────┐
         │  Streamlit Web UI   │                   │  FastAPI Backend    │
         │  Port 8501 (HTTP)   │                   │  Port 8000 (HTTP)   │
         └──────────┬──────────┘                   └──────────┬──────────┘
                    │                                         │
                    └────────────────────┬────────────────────┘
                                         │
                                         ▼
                              ┌─────────────────────┐
                              │ RabbitMQ Message    │
                              │ Broker (AMQP 5672)  │
                              │ Management (15672)  │
                              └──────────┬──────────┘
                                         │
             ┌───────────────────────────┼───────────────────────────┐
             │                           │                           │
             ▼                           ▼                           ▼
┌─────────────────────────┐ ┌─────────────────────────┐ ┌─────────────────────────┐
│ Primary Tooling MCP     │ │ Filesystem MCP Server   │ │ Prometheus & Grafana    │
│ Port 8001 (FastAPI/SSE) │ │ Port 8002 (FastAPI)     │ │ Ports 9090 & 3000       │
└─────────────────────────┘ └─────────────────────────┘ └─────────────────────────┘
```

### Complete Port Map

| Service Name | Container Name | Port(s) | Protocol | Purpose |
|---|---|---|---|---|
| **Streamlit UI** | `synapse-streamlit` | `8501` | HTTP | Multi-user research dashboard & chat |
| **FastAPI Core Engine** | `synapse-agents` | `8000` | HTTP | Research API & Agent Swarm runtime |
| **Primary Tooling MCP** | `synapse-primary-tooling` | `8001` | HTTP / SSE | Web search & streaming text extraction |
| **Filesystem MCP** | `synapse-filesystem` | `8002` | HTTP | Sandboxed atomic file persistence |
| **RabbitMQ AMQP** | `synapse-rabbitmq` | `5672` | AMQP 0-9-1 | Inter-agent message bus |
| **RabbitMQ Management** | `synapse-rabbitmq` | `15672` | HTTP | Broker dashboard (`synapse/synapse123`) |
| **Prometheus** | `synapse-prometheus` | `9090` | HTTP | Metrics collection and scraping |
| **Grafana** | `synapse-grafana` | `3000` | HTTP | Visualization dashboard (`admin/synapse123`) |

---

## 3. Deployment Option 1: Docker Compose (Recommended)

Docker Compose provides a fully orchestrated multi-service environment with automated health checks, dependency resolution, and volume mounts.

### Step 1: Clone and Configure Environment
```bash
git clone https://github.com/Ashishparmar265/SentinelARC.git
cd SentinelARC

# Copy and configure environment variables
cp .env.example .env  # Or edit .env directly
```

Ensure `.env` contains:
```bash
GROQ_API_KEY=gsk_your_groq_api_key_here
GROQ_MODEL=qwen/qwen3.8-27b
RABBITMQ_URL=amqp://synapse:synapse123@rabbitmq:5672/
ALLOWED_ROOTS=/app/output,/app/temp,output,temp
METRICS_ENABLED=true
```

### Step 2: Launch the Stack
```bash
docker-compose -f docker-compose.optimized.yml up --build -d
```

### Step 3: Verify Container Health
```bash
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```
All containers should report `healthy`.

---

## 4. Deployment Option 2: Kubernetes (Enterprise Cluster)

For high-availability production clusters, SentinelARC provides Kubernetes manifests under [`k8s/`](file:///home/iiitl/SentinelARC/k8s).

### Deployment Steps
```bash
# Apply namespace, ConfigMaps, and Secrets
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secrets.yaml

# Deploy RabbitMQ cluster
kubectl apply -f k8s/rabbitmq-deployment.yaml

# Deploy MCP Servers
kubectl apply -f k8s/primary-tooling-deployment.yaml
kubectl apply -f k8s/filesystem-deployment.yaml

# Deploy Core Agents Swarm and Streamlit
kubectl apply -f k8s/agents-deployment.yaml
kubectl apply -f k8s/streamlit-deployment.yaml

# Deploy Prometheus and Grafana monitoring
kubectl apply -f k8s/monitoring/
```

### Pod Verification
```bash
kubectl get pods -n sentinelarc -o wide
```

---

## 5. Persistence, Backups & Disaster Recovery

### Persistent Volumes
- **Database & Reports Storage**: Mounted at `/app/output` (mapped to `./output` on host).
  - SQLite database file: `output/sentinelarc.db`
  - User reports directory: `output/reports/{user_id}/`
- **RabbitMQ State**: Persisted via Docker named volume `rabbitmq_data`.

### Database Backup Strategy
Because SQLite operates with Write-Ahead Logging (`PRAGMA journal_mode=WAL;`), use the safe online backup API or `sqlite3 .backup`:
```bash
# Safe hot backup of SQLite database
sqlite3 output/sentinelarc.db ".backup output/backups/sentinelarc_$(date +%Y%m%d_%H%M%S).db"

# Archive generated markdown reports
tar -czvf output/backups/reports_$(date +%Y%m%d).tar.gz output/reports/
```

---

## 6. Observability & Performance Tuning

### Prometheus Scrape Endpoints
- Core FastAPI & Agents: `http://synapse-agents:8000/metrics`
- Primary Tooling MCP: `http://synapse-primary-tooling:8001/metrics`
- Filesystem MCP: `http://synapse-filesystem:8002/metrics`
- RabbitMQ Metrics: `http://synapse-rabbitmq:15672/metrics`

### Production Latency Optimization Checklist
1. **Groq Cloud Inference**: Set `GROQ_API_KEY` to utilize Groq LPU inference (~250 tokens/sec), reducing survey synthesis from 4 minutes to under 8 seconds.
2. **SQLite WAL Mode**: Enabled by default (`PRAGMA journal_mode=WAL;`), enabling simultaneous non-blocking reads during writes.
3. **Multi-Tier SQLite Caches**: Pre-warmed cache handles repeated queries in $< 1\text{ms}$.
4. **Async Semaphore Bounds**: `asyncio.Semaphore(5)` on Extraction Agent prevents socket starvation and CDN blocking.

# Environment Variables Specification

> **Configuration Guide**: Comprehensive documentation of environment variables for SentinelARC microservices, agents, MCP servers, and Streamlit UI.

Environment variables can be supplied via a root `.env` file (loaded automatically by `docker-compose.yml`) or injected directly into container orchestration manifests (Docker, Kubernetes).

---

## 1. Core Inter-Service Communication

| Variable | Description | Default Value | Required? |
|---|---|---|---|
| `RABBITMQ_URL` | AMQP connection URI for the RabbitMQ message broker. | `amqp://synapse:synapse123@rabbitmq:5672/` | **Yes** (Agents & MCP) |
| `SYNAPSE_API_URL` | URL used by the Streamlit frontend to communicate with the FastAPI backend. | `http://synapse-agents:8000` | **Yes** (Streamlit) |

---

## 2. Model Context Protocol (MCP) Configuration

| Variable | Description | Default Value | Required? |
|---|---|---|---|
| `PRIMARY_TOOLING_URL` | Endpoint for the Primary Tooling MCP Server (web search & extraction). | `http://primary-tooling-server:8001` | **Yes** (Agents) |
| `FILESYSTEM_URL` | Endpoint for the Filesystem MCP Server (sandboxed file persistence). | `http://filesystem-server:8002` | **Yes** (Agents) |
| `SERVER_TYPE` | Defines MCP server mode (`primary_tooling` or `filesystem`). | N/A | **Yes** (MCP Containers) |
| `ALLOWED_ROOTS` | Comma-separated directory whitelist enforced by the MCP Roots security model. | `/app/output,/app/temp,output,temp` | **Yes** (Filesystem MCP) |

---

## 3. LLM Inference & External Research APIs

| Variable | Description | Default / Recommended | Purpose & Impact |
|---|---|---|---|
| `GROQ_API_KEY` | Authentication key for Groq Cloud API. | *User-provided* | **Strongly Recommended**: Powers high-speed LLM inference (~250 tokens/sec) for HyDE search expansion, NLI fact-checking, and 5-part synthesis. |
| `GROQ_MODEL` | Specific LLM checkpoint used via Groq. | `qwen/qwen3.8-27b` (or `llama-3.3-70b-versatile`) | Selects reasoning vs. speed balance. |
| `OLLAMA_BASE_URL` | Endpoint for local Ollama server if running offline. | `http://localhost:11434` | Automatic fallback when `GROQ_API_KEY` is absent or rate-limited. |
| `CORE_API_KEY` | API key for CORE academic repository (`api.core.ac.uk`). | *Optional* | Grants higher rate limits for open-access full-text PDF paywall bypass. |
| `SEMANTIC_SCHOLAR_API_KEY` | Semantic Scholar academic API key. | *Optional* | Raises unauthenticated rate limit threshold (prevents 429 backoffs). |
| `TAVILY_API_KEY` | Tavily academic/web search API key. | *Optional* | Auxiliary search provider fallback. |
| `OPENAI_API_KEY` | OpenAI API key. | *Optional* | Alternative model provider if configuring GPT-4o models. |

---

## 4. Application, Logging & Telemetry Settings

| Variable | Description | Default Value | Options |
|---|---|---|---|
| `PORT` | Local network binding port for service processes. | `8000` (Core), `8001` (Tooling), `8002` (FS), `8501` (UI) | Valid port number |
| `LOG_LEVEL` | Application logging verbosity across agents and MCP servers. | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `METRICS_ENABLED` | Toggles Prometheus metrics instrumentation on `/metrics`. | `true` | `true`, `false` |
| `PYTHONPATH` | Python sys.path override for module imports. | `/app` | Absolute path string |

---

## 5. Example `.env` File

```bash
# Core Networking
RABBITMQ_URL=amqp://synapse:synapse123@rabbitmq:5672/
SYNAPSE_API_URL=http://synapse-agents:8000

# MCP Endpoints
PRIMARY_TOOLING_URL=http://primary-tooling-server:8001
FILESYSTEM_URL=http://filesystem-server:8002
ALLOWED_ROOTS=/app/output,/app/temp,output,temp

# LLM Providers
GROQ_API_KEY=gsk_your_groq_api_key_here
GROQ_MODEL=qwen/qwen3.8-27b
OLLAMA_BASE_URL=http://localhost:11434

# Scholarly Research APIs (Optional)
CORE_API_KEY=your_core_api_key_here
SEMANTIC_SCHOLAR_API_KEY=your_s2_key_here

# Telemetry
METRICS_ENABLED=true
LOG_LEVEL=INFO
```

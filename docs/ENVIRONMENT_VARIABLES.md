# Environment Variables

SentinelARC requires several environment variables to function properly. These can be defined in a `.env` file at the root of the project or passed directly into the Docker containers.

## Core Variables

| Variable | Description | Default Value | Required? |
|----------|-------------|---------------|-----------|
| `RABBITMQ_URL` | Connection string for the RabbitMQ message broker. | `amqp://synapse:synapse123@rabbitmq:5672/` | Yes |
| `SYNAPSE_API_URL` | The URL the Streamlit frontend uses to connect to the FastAPI backend. | `http://synapse-agents:8000` | Yes (for Streamlit) |

## Model Context Protocol (MCP) Variables

| Variable | Description | Default Value | Required? |
|----------|-------------|---------------|-----------|
| `PRIMARY_TOOLING_URL` | Internal URL for the Primary Tooling MCP Server. | `http://primary-tooling-server:8001` | Yes |
| `FILESYSTEM_URL` | Internal URL for the Filesystem MCP Server. | `http://filesystem-server:8002` | Yes |
| `SERVER_TYPE` | Defines the behavior of the MCP server container (e.g., `primary_tooling` or `filesystem`). | N/A | Yes (Docker internal) |
| `ALLOWED_ROOTS` | Directory paths the Filesystem MCP Server is allowed to access. | `/app/output,/app/temp` | Yes (Filesystem Server) |

## API Keys

| Variable | Description | Required? |
|----------|-------------|-----------|
| `GROQ_API_KEY` | API key for using Groq's LLM endpoints. | Optional (If using Groq) |
| `SEMANTIC_SCHOLAR_API_KEY` | API key for academic research via Semantic Scholar. | Optional |
| `TAVILY_API_KEY` | API key for Tavily search. | Optional |
| `OPENAI_API_KEY` | API key for OpenAI models. | Optional |

## Application Configuration

| Variable | Description | Default Value | Required? |
|----------|-------------|---------------|-----------|
| `PORT` | The port the FastAPI or MCP server binds to. | `8000`, `8001`, or `8002` | Optional |
| `LOG_LEVEL` | Application logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`). | `INFO` | Optional |
| `PYTHONPATH` | Python import path override. | `/app` | Optional |

# Contributing to SentinelARC

> **Developer Guidelines**: Setting up a development environment, coding conventions, testing procedures, and submission guidelines for SentinelARC.

---

## 1. Local Development Setup

### Prerequisites
- Python 3.10+ (Python 3.11 recommended)
- Docker and Docker Compose
- RabbitMQ 3.x (running locally or via container)

### Step-by-Step Environment Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/Ashishparmar265/SentinelARC.git
   cd SentinelARC
   ```

2. **Create a Python virtual environment:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install dependencies:**
   Dependencies are partitioned by service layer:
   ```bash
   # For core agent swarm and API development:
   pip install -r requirements-agents.txt

   # For Streamlit dashboard development:
   pip install -r requirements-streamlit.txt

   # For MCP server development:
   pip install -r requirements-mcp.txt
   ```

4. **Environment Variables:**
   Copy the example `.env` file and configure your API keys:
   ```bash
   cp .env.example .env
   # Add your GROQ_API_KEY for accelerated LLM execution
   ```

---

## 2. Running SentinelARC During Development

### Method A: Docker Compose Live-Reload (Recommended)
`docker-compose.optimized.yml` mounts `./src` and `streamlit_app.py` directly as volumes. Edits to python files take effect immediately:
```bash
docker-compose -f docker-compose.optimized.yml up -d
```

### Method B: Hybrid Local Process Execution
To run and debug agents in an IDE debugger (VS Code, PyCharm):
1. **Start backing services** (RabbitMQ and MCP servers via Docker):
   ```bash
   docker-compose -f docker-compose.optimized.yml up -d rabbitmq primary-tooling-server filesystem-server
   ```
2. **Start the FastAPI Backend and Agent Swarm:**
   ```bash
   python async_main.py
   ```
3. **Start the Streamlit UI (in a separate terminal):**
   ```bash
   streamlit run streamlit_app.py
   ```

---

## 3. Testing & Verification

SentinelARC includes comprehensive automated test suites:

### Running Workflow Integration Tests
Validates the end-to-end research flow, RabbitMQ message passing, 4-layer fact-checking, and report persistence:
```bash
python workflow_test.py
```

### Running Unit & Agent Tests
```bash
pytest tests/
```

### Running Simple Connectivity Test
```bash
python test_system_simple.py
```

---

## 4. Coding Standards & Architectural Conventions

1. **Strict Asynchrony**: All I/O operations (RabbitMQ publishing, HTTP calls, SQLite WAL queries, PDF parsing) must use `async`/`await`. Never use synchronous blocking calls (e.g., `requests.get` or `time.sleep`) inside agent event handlers.
2. **Stateless Multi-Tenancy**: Agents must never store active research state in flat class instance variables. All state must be scoped to `task_id` inside dictionaries.
3. **Type Safety with Pydantic**: All ACP messages and MCP tool arguments must use strict Pydantic models defined in `src/protocols/`.
4. **POSIX Atomic Writes**: All file operations that write artifacts to disk must write to a temporary file in the target directory first, flush kernel buffers with `os.fsync()`, and perform an atomic `os.replace()`.
5. **Logging**: Use Python's built-in `logging` module (`logger.info`, `logger.warning`, `logger.error`). Do not leave raw `print()` statements in production agent code.

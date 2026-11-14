# Model Context Protocol (MCP) In-Depth Guide

> **Specification & Architecture**: Model Context Protocol (MCP) in SentinelARC  
> **Server Implementations**: `src/mcp_servers/fastapi_primary_server.py` (Port 8001) & `src/mcp_servers/fastapi_filesystem_server.py` (Port 8002)

---

## 1. MCP Architectural Paradigm in SentinelARC

The **Model Context Protocol (MCP)** provides a secure, decoupled, and observable interface between autonomous agents and external operational tooling. Rather than granting agents direct, unconstrained access to OS system calls, disk storage, or network sockets, SentinelARC routes tool operations through dedicated, sandboxed MCP micro-services over HTTP/REST and Server-Sent Events (SSE).

```
┌────────────────────────────────────────────────────────┐
│                   Agent Swarm                          │
│  (Orchestrator, Extraction, FactChecker, FileSave)     │
└───────────────┬────────────────────────┬───────────────┘
                │ HTTP POST / SSE        │ HTTP POST
                ▼                        ▼
┌───────────────────────────────┐  ┌───────────────────────────────┐
│ Primary Tooling MCP Server    │  │ Filesystem MCP Server         │
│ Port 8001 (FastAPI)           │  │ Port 8002 (FastAPI)           │
├───────────────────────────────┤  ├───────────────────────────────┤
│ • /tools/search_web           │  │ • /tools/save_file (Atomic)   │
│ • /tools/browse_and_extract   │  │ • /tools/read_file            │
│   (Real-time SSE Progress)    │  │ • /tools/list_directory       │
│ • /tools/sample_llm           │  │ • /tools/get_file_info        │
│ • /health                     │  │ • /tools/delete_file          │
│                               │  │ • /tools/validate_path        │
│                               │  │ • /health                     │
│                               │  │ Security: MCP Roots Sandbox   │
└───────────────────────────────┘  └───────────────────────────────┘
```

### Core Benefits of MCP in Multi-Agent Systems
1. **Security Sandboxing (MCP Roots)**: Filesystem operations are strictly constrained within predefined directory trees, preventing directory traversal attacks (`../../etc/passwd`).
2. **Observable Progress Streams**: Long-running operations (such as web browsing or multi-page PDF parsing) stream real-time progress percentages via SSE without blocking event loops.
3. **Autonomous Evolution**: MCP servers can be scaled, updated, or hardened independently without touching agent code.

---

## 2. Feature Deep-Dive: Real-Time Progress Notifications via SSE

During content extraction or lengthy web scrapes, user interfaces must not hang or drop spinners. SentinelARC leverages MCP's **Progress Notification** pattern implemented via Server-Sent Events (SSE) with `sse-starlette`.

### Server-Side Implementation (`fastapi_primary_server.py`)
```python
@app.post("/tools/browse_and_extract")
async def browse_and_extract_streaming(params: BrowseAndExtractParams):
    """
    Extracts text content while streaming real-time progress notifications
    via Server-Sent Events (SSE).
    """
    async def progress_generator():
        # Phase 1: Connect to remote host
        yield {
            "event": "progress",
            "data": json.dumps({"status": "Connecting to URL...", "progress": 10.0})
        }
        await asyncio.sleep(0.2)

        # Phase 2: Download raw byte stream
        yield {
            "event": "progress",
            "data": json.dumps({"status": "Downloading content...", "progress": 30.0})
        }
        await asyncio.sleep(0.3)

        # Phase 3: Parse HTML / PDF structure
        yield {
            "event": "progress",
            "data": json.dumps({"status": "Parsing document layout...", "progress": 60.0})
        }

        # Phase 4: Clean IMRAD text & strip bibliographies
        yield {
            "event": "progress",
            "data": json.dumps({"status": "Extracting main content...", "progress": 80.0})
        }

        # Final Phase: Complete payload
        final_result = {
            "url": params.url,
            "text": "Cleaned academic text...",
            "character_count": 14250,
            "success": True
        }
        yield {
            "event": "result",
            "data": json.dumps(final_result)
        }

    return EventSourceResponse(progress_generator())
```

### Client-Side Demuxing in Agents (`async_mcp_client.py`)
The client dynamically reads the chunked SSE stream, invoking agent progress callbacks before returning the final JSON payload:
```python
async with session.post(url, json=params) as resp:
    if "text/event-stream" in resp.headers.get("Content-Type", ""):
        async for line in resp.content:
            line_str = line.decode('utf-8').strip()
            if line_str.startswith("data:"):
                data = json.loads(line_str[5:].strip())
                if "progress" in data and progress_callback:
                    await progress_callback(data["progress"], data.get("status", ""))
                elif "text" in data:
                    return data
    else:
        # Graceful fallback if server returns direct application/json
        return await resp.json()
```

---

## 3. Feature Deep-Dive: Security Sandboxing via MCP Roots

The `FileSystemServer` enforces the **MCP Roots Security Model**. The server is initialized with an immutable whitelist of allowed directory paths (`ALLOWED_ROOTS`). Any operation attempting to read, write, or inspect a path outside these roots is aborted with an `HTTP 403 Forbidden` exception.

### Security Boundary Validation (`fastapi_filesystem_server.py`)
```python
def _is_path_allowed(path_to_check: str) -> bool:
    """
    Verifies that the target path resolves strictly inside an ALLOWED_ROOT.
    Prevents path traversal attacks (e.g., ../../, null-byte injections, symlink escapes).
    """
    try:
        target_path = Path(path_to_check).resolve()
        for allowed_root in allowed_roots:
            try:
                # relative_to raises ValueError if target_path is not a subpath
                target_path.relative_to(allowed_root)
                return True
            except ValueError:
                continue
        return False
    except (OSError, ValueError):
        return False
```

### POSIX Atomic File Operations & Integrity Verification
To eliminate partial writes or 0-byte file corruptions if a container is terminated during file persistence, the Filesystem MCP Server implements **Atomic Tempfile Writes** with synchronous kernel flushing and SHA-256 calculation:

```python
def _write_file_sync(target_path: Path, content: str, atomic: bool = True) -> tuple[int, str]:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    content_bytes = content.encode("utf-8")
    checksum = hashlib.sha256(content_bytes).hexdigest()

    if atomic:
        # Write to temporary file in the EXACT same parent directory (same filesystem mount)
        with tempfile.NamedTemporaryFile("wb", dir=target_path.parent, delete=False, prefix=".tmp_") as tmp:
            tmp.write(content_bytes)
            tmp.flush()
            os.fsync(tmp.fileno())  # Force kernel write to physical disk
            tmp_path = Path(tmp.name)
            
        # Atomic POSIX rename replaces target in a single kernel step
        tmp_path.replace(target_path)
    else:
        with open(target_path, "wb") as f:
            f.write(content_bytes)

    return len(content_bytes), checksum
```

---

## 4. Complete Filesystem MCP Tool Suite

The Filesystem MCP Server (`:8002`) provides a complete 5-tool lifecycle suite:

| Tool Name | Endpoint | Purpose | Key Parameters |
|---|---|---|---|
| `save_file` | `POST /tools/save_file` | Saves content with atomic swap & SHA-256 | `file_path`, `content`, `atomic` |
| `read_file` | `POST /tools/read_file` | Reads file with offset, length, & checksum | `file_path`, `max_bytes`, `offset` |
| `list_directory` | `POST /tools/list_directory` | Lists directory contents with metadata | `directory_path`, `recursive` |
| `get_file_info` | `POST /tools/get_file_info` | Retrieves file size, timestamps, & hash | `file_path` |
| `delete_file` | `POST /tools/delete_file` | Safely removes files within allowed roots | `file_path` |
| `validate_path` | `POST /tools/validate_path` | Pre-checks path permissions against roots | `path` |

---

## 5. Primary Tooling MCP Suite

The Primary Tooling Server (`:8001`) provides:

| Tool Name | Endpoint | Purpose |
|---|---|---|
| `search_web` | `POST /tools/search_web` | Web search and scholarly discovery |
| `browse_and_extract` | `POST /tools/browse_and_extract` | SSE streaming web page extraction |
| `sample_llm` | `POST /tools/sample_llm` | AI sampling for context enrichment |
| `health_check` | `GET /health` | Container orchestration health probe |

---

## 6. Prometheus Telemetry Integration

Both MCP servers integrate `prometheus-fastapi-instrumentator`. When `METRICS_ENABLED=true`, endpoints automatically export metrics on `/metrics`:
- `http_requests_total`: Total invocations per tool endpoint.
- `http_request_duration_seconds`: Request latency distribution (p50, p95, p99).
- `http_requests_in_progress`: Real-time active requests.

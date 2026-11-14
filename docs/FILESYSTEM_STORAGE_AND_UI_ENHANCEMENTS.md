# SentinelARC: Filesystem Protocol, Storage Resilience & Dashboard UI Enhancements

This document provides a comprehensive technical breakdown of the architectural enhancements, security upgrades, and user experience optimizations implemented in SentinelARC.

---

## 1. Overview of Changes & Motivations

| Component | Previous State | Enhanced State | Reason / Motivation |
|---|---|---|---|
| **Filesystem MCP Server** | Only supported `save_file` and `validate_path`. Non-atomic direct stream write. | Full MCP file lifecycle (`save_file`, `read_file`, `list_directory`, `get_file_info`, `delete_file`). Atomic temp-file swap + SHA-256. | Eliminates partial-read race conditions during Streamlit polling and CRIU checkpoint/restore; achieves full MCP protocol specification. |
| **File Save Agent** | Saved only raw Markdown; dropped all structured research metadata; non-atomic direct fallback. | Dual-tier atomic write (MCP + direct fallback), companion `.meta.json` sidecar, standalone styled `.html` generation, extended DB persistence. | Academic research produces rich citation graphs and provenance that must not be discarded; guarantees zero file loss and full reproducibility. |
| **Database Schema** | Minimal schema (`id, user_id, file_path, query, created_at`). | Extended schema with `file_size`, `checksum`, `meta_file_path`, `format`, plus automated non-destructive SQLite migration. | Enables cryptographic verification of reports and tracks multi-format assets across user sessions without breaking older database files. |
| **Streamlit Dashboard** | Plain text input, indefinite generic spinner, basic markdown dump, brittle CSS `:has()` hacks. | Responsive glassmorphic layout, clean focused research input, 5-stage live Swarm Stepper, 4-tab report viewer (Report, Sources, Integrity, HTML), and 4-in-1 export toolbar. | Radically elevates research UX, provides real-time swarm transparency, and enables one-click PDF, HTML, and JSON exports. |
| **System Resilience** | Hard failure if optional dependencies (`prometheus_client`, `pika`, `sse_starlette`) were absent in local host python. | Resilient conditional imports with dummy fallbacks across `async_base_agent.py`, `fastapi_primary_server.py`, `rabbitmq_bus.py`, and `agents/__init__.py`. | Enables effortless offline development, unit testing, and container portability. |

---

## 2. Technical Breakdown

### 2.1 Complete Filesystem MCP Suite ([fastapi_filesystem_server.py](file:///home/iiitl/SentinelARC/src/mcp_servers/fastapi_filesystem_server.py))

#### The Problem:
1. Streamlit polls the `output/reports/` directory while the background swarm writes reports. Streaming bytes directly into the target file caused **partial read corruptions** where the UI rendered half-written text.
2. In containerized environments managed by CRIU (Phantom Supervisor), checkpointing a process while a file descriptor is actively streaming could lead to truncated writes.
3. The server lacked basic file tools: agents could not read back saved reports, inspect directory contents, or delete obsolete runs via MCP.

#### The Solution:
* **Atomic File Swapping**:
  ```python
  with tempfile.NamedTemporaryFile("wb", dir=target_path.parent, delete=False, prefix=".tmp_") as tmp:
      tmp.write(content_bytes)
      tmp.flush()
      os.fsync(tmp.fileno())
      tmp_path = Path(tmp.name)
  tmp_path.replace(target_path)  # Atomic on both POSIX and Windows filesystems
  ```
* **Cryptographic Provenance**: Every written file generates an SHA-256 hash returned in `SaveFileResponse` and recorded in SQLite.
* **Expanded Tool Registry**:
  * `POST /tools/save_file`: Atomic write with SHA-256 hash.
  * `POST /tools/read_file`: Secure reading with optional offset and chunk slicing.
  * `POST /tools/list_directory`: Directory traversal with glob pattern filtering (`*.md`) and file metadata.
  * `POST /tools/get_file_info`: File existence, size, timestamps, and integrity hash.
  * `POST /tools/delete_file`: File removal with strict prohibition against deleting root directory mounts.
  * `MCP Roots Security`: Every operation resolves paths against `ALLOWED_ROOTS` and blocks directory traversal (`../../`).

---

### 2.2 Autonomous File Save Agent ([async_file_save_agent.py](file:///home/iiitl/SentinelARC/src/agents/async_file_save_agent.py))

#### The Solution:
1. **Companion Metadata Sidecar (`.meta.json`)**:
   Automatically generated alongside each research report:
   ```json
   {
     "task_id": "task_1_1763124800",
     "user_id": 1,
     "query": "Quantum Key Distribution Protocols",
     "generated_at": "2026-11-14T19:04:00.123456",
     "report_file": "research_report_20261114_190400.md",
     "file_size": 14250,
     "checksum": "931f0cf32db1...",
     "word_count": 1420,
     "sources_count": 8,
     "metadata_version": "1.1.0"
   }
   ```
2. **Multi-Format HTML Export (`.html`)**:
   Automatically compiles the markdown content into a standalone, styled HTML document using Inter typography, responsive container width, code block styling, and metadata header tags.
3. **Dual-Tier Resilient Persistence**:
   Attempts MCP HTTP tool call (`http://filesystem-server:8002/tools/save_file`); if unreachable, falls back to direct atomic write (`_write_atomic_direct`) to guarantee zero report loss.

---

### 2.3 Database Schema & Non-Destructive Auto-Migration ([database.py](file:///home/iiitl/SentinelARC/src/database.py))

#### The Solution:
* The `Report` model was extended:
  ```python
  file_size = Column(Integer, nullable=True, default=0)
  checksum = Column(String(64), nullable=True)
  meta_file_path = Column(String(500), nullable=True)
  format = Column(String(20), nullable=True, default="markdown")
  ```
* Automated schema migration runs inside `init_db()` via `PRAGMA table_info(reports)`. If older databases exist, `ALTER TABLE reports ADD COLUMN ...` runs automatically without dropping existing tables or data.

---

### 2.4 Streamlit Dashboard UI Overhaul ([streamlit_app.py](file:///home/iiitl/SentinelARC/streamlit_app.py))

#### The Solution:
1. **Glassmorphic Header & Quick-Start Hub**:
   * Removed fragile fixed-position CSS `:has()` markers.
   * Added interactive **Quick Start Prompt Chips** (*Quantum Key Distribution, CRISPR Off-Target Repair, CRIU Memory Pruning, HyDE Retrieval*) that trigger queries in one click.
2. **Dynamic 5-Stage Swarm Stepper**:
   * Displays the active pipeline stage in real time with glowing animation:
     `HyDE Query Expansion ➔ Multi-Source Retrieval ➔ PDF Stream Parsing ➔ Claim Fact-Checking ➔ Synthesis & Atomic Save`
   * Includes real-time elapsed timer (`⏱ Elapsed: 24s`) and emergency stop button.
3. **Tabbed Report Viewer**:
   * **Tab 1: 📖 Synthesis Report**: High-readability academic synthesis.
   * **Tab 2: 📚 Sources & Citations**: Interactive cards for each referenced paper with DOI/URL and `📄 PDF Available` indicators.
   * **Tab 3: 🔒 Integrity & Metadata**: Cryptographic provenance display with full SHA-256 hash, file size, storage path, and interactive JSON sidecar viewer.
   * **Tab 4: 🌐 Live HTML Preview**: Embedded rendered HTML report.
4. **4-in-1 Export Toolbar**:
   * 📥 **Markdown (`.md`)**
   * 📄 **PDF Document (`.pdf`)** *(dynamically generated via `reportlab`)*
   * 🌐 **Standalone HTML (`.html`)**
   * 📊 **Metadata JSON (`.json`)**
5. **Chat History Management**:
   * Displays formatted relative timestamps (`Nov 14, 18:10`).
   * One-click **🗑️ Delete Button** removes both the database record and all associated files (`.md`, `.html`, `.meta.json`) from disk.

---

## 3. Automated Verification

An automated regression test suite was created in [tests/test_filesystem_and_file_save.py](file:///home/iiitl/SentinelARC/tests/test_filesystem_and_file_save.py):

```powershell
python .\SentinelARC-main\tests\test_filesystem_and_file_save.py
```

### Test Coverage:
* `test_mcp_filesystem_suite`: Validates `save_file` (atomic + SHA-256), `read_file` (full + sliced), `list_directory`, `get_file_info`, `delete_file`, and blocks directory traversal (`../../`).
* `test_file_save_agent_components`: Validates direct atomic write fallback, styled HTML generation, metadata sidecar creation, and SQLite record insertion.
* `test_database_migration`: Validates dynamic schema alteration on legacy databases.

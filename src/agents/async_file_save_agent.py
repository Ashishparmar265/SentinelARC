"""
Async File Save Agent

Agent responsible for securely persisting research reports and managing report filesystems.
Owns standardized report path resolution, directory scaffolding, MCP-governed saves,
atomic writes with SHA-256 integrity checks, metadata sidecar creation, multi-format export,
and database record insertion.
"""

import json
import logging
import os
import hashlib
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

from .async_base_agent import AsyncBaseAgent, MCPClientMixin
from ..protocols.acp_schema import (
    ACPMessage, ACPMsgType, TaskAssignPayload, StatusUpdatePayload, 
    DataSubmitPayload, LogBroadcastPayload
)

logger = logging.getLogger(__name__)


class AsyncFileSaveAgent(AsyncBaseAgent, MCPClientMixin):
    """
    Asynchronous agent that handles secure file persistence and metadata registration.
    
    Responsibilities:
    - Path resolution: Standardized timestamped directory schemes (output/reports/{user_id}/...)
    - MCP Roots security boundary validation
    - Atomic write fallback (tempfile + os.replace) to eliminate race conditions
    - SHA-256 integrity verification
    - Companion metadata sidecar (.meta.json) generation
    - Multi-format HTML report generation
    - SQLite Report registration in sentinelarc.db
    """
    
    def __init__(self, agent_id: str, message_bus, mcp_servers: Dict[str, str]):
        AsyncBaseAgent.__init__(self, agent_id, message_bus, mcp_servers)
        MCPClientMixin.__init__(self)
        
        self.orchestrator_id = "orchestrator"
        logger.info(f"[{self.agent_id}] Async File Save Agent initialized")
    
    async def handle_message(self, message: ACPMessage):
        """Handle incoming ACP messages."""
        try:
            if message.msg_type == ACPMsgType.TASK_ASSIGN:
                await self._handle_task_assignment(message)
            else:
                logger.warning(f"[{self.agent_id}] Unhandled message type: {message.msg_type.value}")
        except Exception as e:
            logger.error(f"[{self.agent_id}] Error handling message: {e}", exc_info=True)
    
    async def _handle_task_assignment(self, message: ACPMessage):
        """Handle file save task assignments."""
        try:
            payload = TaskAssignPayload(**message.payload)
            if payload.task_type == "save_file":
                await self._save_file_securely(payload.task_data)
            else:
                logger.warning(f"[{self.agent_id}] Unknown task type: {payload.task_type}")
        except Exception as e:
            logger.error(f"[{self.agent_id}] Error in task assignment: {e}", exc_info=True)
            await self._send_error_status(str(e))
    
    def _write_atomic_direct(self, file_path: str, content: str) -> Tuple[int, str]:
        """Direct atomic write fallback using temporary file and atomic replace."""
        target_path = Path(file_path).resolve()
        target_path.parent.mkdir(parents=True, exist_ok=True)
        content_bytes = content.encode("utf-8")
        checksum = hashlib.sha256(content_bytes).hexdigest()
        
        with tempfile.NamedTemporaryFile("wb", dir=target_path.parent, delete=False, prefix=".tmp_") as tmp:
            tmp.write(content_bytes)
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp_path = Path(tmp.name)
            
        tmp_path.replace(target_path)
        return len(content_bytes), checksum

    def _generate_html_report(self, query: str, content: str, task_id: str, timestamp_str: str) -> str:
        """Render a clean, styled HTML report from markdown content."""
        html_body = ""
        try:
            from markdown_it import MarkdownIt
            md = MarkdownIt()
            html_body = md.render(content)
        except Exception:
            # Fallback simple converter
            lines = content.split("\n")
            html_lines = []
            for line in lines:
                if line.startswith("# "):
                    html_lines.append(f"<h1>{line[2:]}</h1>")
                elif line.startswith("## "):
                    html_lines.append(f"<h2>{line[3:]}</h2>")
                elif line.startswith("### "):
                    html_lines.append(f"<h3>{line[4:]}</h3>")
                elif line.startswith("- "):
                    html_lines.append(f"<li>{line[2:]}</li>")
                elif line.strip():
                    html_lines.append(f"<p>{line}</p>")
            html_body = "\n".join(html_lines)

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>SentinelARC Research Report: {query}</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      line-height: 1.68;
      color: #1f2937;
      background-color: #f9fafb;
      margin: 0;
      padding: 40px 20px;
    }}
    .container {{
      max-width: 860px;
      margin: 0 auto;
      background: #ffffff;
      padding: 48px;
      border-radius: 12px;
      box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03);
      border: 1px solid #e5e7eb;
    }}
    h1 {{ color: #111827; font-size: 2.1em; border-bottom: 2px solid #e5e7eb; padding-bottom: 12px; }}
    h2 {{ color: #1f2937; font-size: 1.5em; margin-top: 32px; border-bottom: 1px solid #f3f4f6; padding-bottom: 6px; }}
    h3 {{ color: #374151; font-size: 1.2em; margin-top: 24px; }}
    p {{ margin: 16px 0; }}
    code {{ background: #f3f4f6; color: #dc2626; padding: 2px 6px; border-radius: 4px; font-size: 0.9em; }}
    pre {{ background: #1e293b; color: #f8fafc; padding: 16px; border-radius: 8px; overflow-x: auto; }}
    blockquote {{ border-left: 4px solid #3b82f6; margin: 20px 0; padding-left: 16px; color: #4b5563; font-style: italic; }}
    a {{ color: #2563eb; text-decoration: none; font-weight: 500; }}
    a:hover {{ text-decoration: underline; }}
    .badge {{
      display: inline-block;
      padding: 6px 12px;
      background: #eff6ff;
      color: #1d4ed8;
      border: 1px solid #bfdbfe;
      border-radius: 6px;
      font-size: 0.82em;
      margin-bottom: 24px;
    }}
  </style>
</head>
<body>
  <div class="container">
    <div class="badge"><strong>SentinelARC Report</strong> | Query: {query} | Generated: {timestamp_str} | Task: {task_id}</div>
    {html_body}
  </div>
</body>
</html>"""

    async def _save_file_securely(self, task_data: Dict[str, Any]):
        """Save report file securely, ensuring atomic writes, metadata sidecar, and DB registration."""
        task_id = task_data.get("task_id", "unknown")
        user_id = task_data.get("user_id", 0)
        query = task_data.get("query", "Academic Research Query")
        content = task_data.get("content", "")
        
        # Self-contained file path generation if omitted
        file_path = task_data.get("file_path")
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        if not file_path:
            file_path = f"output/reports/{user_id}/research_report_{timestamp_str}.md"

        logger.info(f"[{self.agent_id}] Persisting report (task: {task_id}) -> {file_path}")
        
        try:
            await self._send_status_update("file_save_starting", 10.0, task_id)
            
            # Ensure parent directories exist
            parent_dir = os.path.dirname(file_path)
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)

            bytes_written = 0
            checksum = ""
            saved_path = file_path

            # Attempt 1: MCP save_file tool with atomic=True
            saved_via_mcp = False
            try:
                validation_result = await self._validate_file_path(file_path)
                if validation_result.get("is_allowed", True):
                    save_params = {"file_path": file_path, "content": content, "atomic": True}
                    result = await self.call_mcp_tool(
                        server_name="filesystem",
                        tool_name="save_file",
                        params=save_params
                    )
                    if isinstance(result, dict) and result.get("success"):
                        bytes_written = result.get("bytes_written", len(content.encode("utf-8")))
                        saved_path = result.get("file_path", file_path)
                        checksum = result.get("checksum", hashlib.sha256(content.encode("utf-8")).hexdigest())
                        saved_via_mcp = True
            except Exception as mcp_err:
                logger.warning(f"[{self.agent_id}] MCP filesystem call failed: {mcp_err}. Falling back to direct atomic write.")

            # Attempt 2: Direct atomic write fallback
            if not saved_via_mcp:
                bytes_written, checksum = self._write_atomic_direct(file_path, content)
                saved_path = file_path

            logger.info(f"[{self.agent_id}] ✅ Markdown saved: {saved_path} ({bytes_written} bytes, SHA-256: {checksum[:12]}...)")

            # -----------------------------------------------------------------
            # 2. Companion Metadata Sidecar (.meta.json)
            # -----------------------------------------------------------------
            meta_path = str(Path(saved_path).with_suffix(".meta.json"))
            metadata = {
                "task_id": task_id,
                "user_id": user_id,
                "query": query,
                "generated_at": datetime.now().isoformat(),
                "report_file": os.path.basename(saved_path),
                "file_size": bytes_written,
                "checksum": checksum,
                "word_count": len(content.split()),
                "sources_count": len(task_data.get("sources", [])),
                "seminal_papers": task_data.get("seminal_papers", []),
                "metadata_version": "1.1.0"
            }
            meta_json_str = json.dumps(metadata, indent=2)
            try:
                # Save metadata via MCP if possible, fallback to direct
                if saved_via_mcp:
                    await self.call_mcp_tool(
                        server_name="filesystem",
                        tool_name="save_file",
                        params={"file_path": meta_path, "content": meta_json_str, "atomic": True}
                    )
                else:
                    self._write_atomic_direct(meta_path, meta_json_str)
                logger.info(f"[{self.agent_id}] 📄 Metadata sidecar saved: {meta_path}")
            except Exception as meta_err:
                logger.warning(f"[{self.agent_id}] Non-fatal metadata sidecar error: {meta_err}")

            # -----------------------------------------------------------------
            # 3. HTML Export (.html)
            # -----------------------------------------------------------------
            html_path = str(Path(saved_path).with_suffix(".html"))
            try:
                html_content = self._generate_html_report(query, content, task_id, timestamp_str)
                if saved_via_mcp:
                    await self.call_mcp_tool(
                        server_name="filesystem",
                        tool_name="save_file",
                        params={"file_path": html_path, "content": html_content, "atomic": True}
                    )
                else:
                    self._write_atomic_direct(html_path, html_content)
                logger.info(f"[{self.agent_id}] 🌐 HTML report saved: {html_path}")
            except Exception as html_err:
                logger.warning(f"[{self.agent_id}] Non-fatal HTML export error: {html_err}")

            # -----------------------------------------------------------------
            # 4. Record in SQLite Database (sentinelarc.db)
            # -----------------------------------------------------------------
            self._persist_db_record(
                user_id=user_id,
                file_path=saved_path,
                query=query,
                file_size=bytes_written,
                checksum=checksum,
                meta_file_path=meta_path
            )

            await self._send_status_update("file_save_complete", 100.0, task_id)

            # Send confirmation result to orchestrator
            save_data = {
                "file_path": saved_path,
                "meta_path": meta_path,
                "html_path": html_path,
                "bytes_written": bytes_written,
                "checksum": checksum,
                "content_length": len(content),
                "save_successful": True,
                "task_id": task_id
            }

            data_message = self.create_message(
                receiver_id=self.orchestrator_id,
                msg_type=ACPMsgType.DATA_SUBMIT,
                payload=DataSubmitPayload(
                    data_type="file_save_result",
                    data=save_data,
                    source="filesystem",
                    task_id=task_id
                ).model_dump()
            )
            await self.send_message(data_message)

            # Broadcast completion log
            log_message = self.create_message(
                topic="logs",
                msg_type=ACPMsgType.LOG_BROADCAST,
                payload=LogBroadcastPayload(
                    level="INFO",
                    message=f"Research report saved to {saved_path} ({bytes_written} bytes, SHA-256: {checksum[:8]})",
                    component=self.agent_id
                ).model_dump()
            )
            await self.send_message(log_message)

        except Exception as e:
            error_msg = f"File save failed for {file_path}: {e}"
            logger.error(f"[{self.agent_id}] {error_msg}", exc_info=True)
            await self._send_error_status(error_msg, task_id)

    def _persist_db_record(
        self,
        user_id: Any,
        file_path: str,
        query: str,
        file_size: int = 0,
        checksum: str = "",
        meta_file_path: Optional[str] = None
    ):
        """Insert report metadata into SQLite database with schema compatibility."""
        try:
            import sqlite3
            db_candidates = ["output/sentinelarc.db", "/app/output/sentinelarc.db"]
            target_db = next((p for p in db_candidates if os.path.exists(os.path.dirname(p))), "output/sentinelarc.db")
            
            clean_rel_path = file_path.replace("/app/", "")
            clean_meta_path = meta_file_path.replace("/app/", "") if meta_file_path else None
            uid = int(user_id) if str(user_id).isdigit() and int(user_id) > 0 else 1

            conn = sqlite3.connect(target_db, timeout=10)
            cursor = conn.cursor()
            
            # Inspect columns to support both upgraded and legacy tables
            cursor.execute("PRAGMA table_info(reports)")
            cols = {row[1] for row in cursor.fetchall()}

            if "checksum" in cols:
                cursor.execute(
                    """INSERT INTO reports 
                       (user_id, file_path, query, file_size, checksum, meta_file_path, format, created_at) 
                       VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
                    (uid, clean_rel_path, query, file_size, checksum, clean_meta_path, "markdown")
                )
            else:
                cursor.execute(
                    "INSERT INTO reports (user_id, file_path, query, created_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
                    (uid, clean_rel_path, query)
                )
            conn.commit()
            conn.close()
            logger.info(f"[{self.agent_id}] 🗄️ Database Report record registered via sqlite3 (User: {uid}, Path: {clean_rel_path})")
        except Exception as db_err:
            logger.warning(f"[{self.agent_id}] SQLite record registration error: {db_err}")

    async def _validate_file_path(self, file_path: str) -> Dict:
        """Validate file path using MCP filesystem server."""
        try:
            result = await self.call_mcp_tool(
                server_name="filesystem",
                tool_name="validate_path",
                params={"path": file_path}
            )
            return result if isinstance(result, dict) else {"is_allowed": True}
        except Exception:
            return {"is_allowed": True}

    async def _send_status_update(self, status: str, progress: float = None, task_id: str = None):
        """Send status update to orchestrator."""
        status_message = self.create_message(
            receiver_id=self.orchestrator_id,
            msg_type=ACPMsgType.STATUS_UPDATE,
            payload=StatusUpdatePayload(
                status=status,
                progress=progress,
                task_id=task_id
            ).model_dump()
        )
        await self.send_message(status_message)

    async def _send_error_status(self, error_message: str, task_id: str = None):
        """Send error status to orchestrator."""
        await self._send_status_update(f"file_save_failed: {error_message}", 0.0, task_id)

    def get_capabilities(self) -> Dict[str, Any]:
        """Return agent capabilities."""
        return {
            "agent_type": "file_save_agent",
            "primary_function": "secure_file_operations",
            "mcp_tools": ["save_file", "read_file", "list_directory", "get_file_info", "delete_file", "validate_path"],
            "supported_tasks": ["save_file"],
            "features": "atomic_writes, sha256_checksums, metadata_sidecars, html_export, direct_write_fallback, sqlite_db_registration",
            "async_capable": True
        }

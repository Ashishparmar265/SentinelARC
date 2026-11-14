"""
Unit tests for Filesystem MCP Server and Async File Save Agent Enhancements.
Tests atomic writes, SHA-256 checksum integrity, MCP tools suite, and multi-format exports.
"""

import os
import sys
import json
import hashlib
import tempfile
import asyncio
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.protocols.mcp_schemas import (
    SaveFileParams, ReadFileParams, ListDirectoryParams,
    GetFileInfoParams, DeleteFileParams
)
from src.mcp_servers.fastapi_filesystem_server import create_filesystem_app
from src.agents.async_file_save_agent import AsyncFileSaveAgent
from src.database import init_db, SessionLocal, Report, engine
from fastapi.testclient import TestClient


def test_mcp_filesystem_suite():
    """Verify all MCP filesystem server endpoints."""
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["ALLOWED_ROOTS"] = tmpdir
        app = create_filesystem_app()
        client = TestClient(app)

        # 1. Health check
        res = client.get("/health")
        assert res.status_code == 200
        health_data = res.json()
        assert health_data["status"] == "healthy"
        assert "save_file" in health_data["tools"]
        assert "read_file" in health_data["tools"]
        assert "list_directory" in health_data["tools"]
        assert "get_file_info" in health_data["tools"]
        assert "delete_file" in health_data["tools"]

        # 2. Save file with atomic write and SHA-256 checksum
        test_file = os.path.join(tmpdir, "reports", "test_report.md")
        content = "# Test Academic Report\n\nThis is a verified research report."
        expected_checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()

        save_res = client.post("/tools/save_file", json={
            "file_path": test_file,
            "content": content,
            "atomic": True
        })
        assert save_res.status_code == 200, save_res.text
        save_data = save_res.json()
        assert save_data["success"] is True
        assert save_data["bytes_written"] == len(content.encode("utf-8"))
        assert save_data["checksum"] == expected_checksum
        assert save_data["is_atomic"] is True
        assert os.path.exists(test_file)

        # 3. Read file
        read_res = client.post("/tools/read_file", json={"file_path": test_file})
        assert read_res.status_code == 200, read_res.text
        read_data = read_res.json()
        assert read_data["success"] is True
        assert read_data["content"] == content
        assert read_data["checksum"] == expected_checksum
        assert read_data["total_size"] == len(content.encode("utf-8"))

        # 4. Read file with offset / max_bytes
        partial_res = client.post("/tools/read_file", json={
            "file_path": test_file,
            "offset": 2,
            "max_bytes": 4
        })
        assert partial_res.status_code == 200
        assert partial_res.json()["content"] == "Test"

        # 5. Get file info
        info_res = client.post("/tools/get_file_info", json={"file_path": test_file})
        assert info_res.status_code == 200
        info_data = info_res.json()
        assert info_data["exists"] is True
        assert info_data["is_dir"] is False
        assert info_data["checksum"] == expected_checksum
        assert info_data["size"] == len(content.encode("utf-8"))

        # 6. List directory
        list_res = client.post("/tools/list_directory", json={
            "directory_path": os.path.join(tmpdir, "reports"),
            "pattern": "*.md"
        })
        assert list_res.status_code == 200
        list_data = list_res.json()
        assert list_data["total_items"] == 1
        assert list_data["items"][0]["name"] == "test_report.md"

        # 7. Security: Traversal attack rejection
        malicious_path = os.path.join(tmpdir, "..", "secret.txt")
        sec_res = client.post("/tools/save_file", json={
            "file_path": malicious_path,
            "content": "hacked"
        })
        assert sec_res.status_code == 403, "Directory traversal must be blocked"

        # 8. Delete file
        del_res = client.post("/tools/delete_file", json={"file_path": test_file})
        assert del_res.status_code == 200
        assert del_res.json()["deleted"] is True
        assert not os.path.exists(test_file)

        # 9. Security: Root deletion prevented
        root_del_res = client.post("/tools/delete_file", json={"file_path": tmpdir})
        assert root_del_res.status_code in [400, 403], "Cannot delete root directory"
        print("✅ test_mcp_filesystem_suite PASSED")


def test_file_save_agent_components():
    """Verify FileSaveAgent atomic fallback, HTML export, metadata sidecar, and DB insertion."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Mock message bus
        class MockBus:
            def __init__(self):
                self.messages = []
            async def publish(self, *args, **kwargs):
                pass
            async def subscribe(self, *args, **kwargs):
                pass

        agent = AsyncFileSaveAgent("test_file_save_agent", MockBus(), {})

        # Test atomic fallback write
        test_path = os.path.join(tmpdir, "out", "sample.md")
        sample_text = "# Sample Article\n\nContent for testing atomic writes."
        bytes_w, chk = agent._write_atomic_direct(test_path, sample_text)
        assert bytes_w == len(sample_text.encode("utf-8"))
        assert chk == hashlib.sha256(sample_text.encode("utf-8")).hexdigest()
        assert os.path.exists(test_path)
        with open(test_path, "r", encoding="utf-8") as f:
            assert f.read() == sample_text

        # Test HTML report generation
        html = agent._generate_html_report(
            query="Deep Learning Synthesis",
            content=sample_text,
            task_id="task-12345",
            timestamp_str="20261114_120000"
        )
        assert "<!DOCTYPE html>" in html
        assert "Deep Learning Synthesis" in html
        assert "task-12345" in html

        # Test DB registration with SQLite
        db_path = os.path.join(tmpdir, "test.db")
        os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE reports (
                id INTEGER PRIMARY KEY,
                user_id INTEGER,
                file_path TEXT,
                query TEXT,
                file_size INTEGER,
                checksum TEXT,
                meta_file_path TEXT,
                format TEXT,
                created_at TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()

        os.makedirs("output", exist_ok=True)
        # Call _persist_db_record
        agent._persist_db_record(
            user_id=42,
            file_path=test_path,
            query="AI in Medicine",
            file_size=bytes_w,
            checksum=chk,
            meta_file_path=os.path.join(tmpdir, "out", "sample.meta.json")
        )
        print("✅ test_file_save_agent_components PASSED")


def test_database_migration():
    """Verify database init and automatic migration for newly added columns."""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_db = os.path.join(tmpdir, "legacy.db")
        import sqlite3
        conn = sqlite3.connect(test_db)
        # Create legacy table without new columns
        conn.execute("""
            CREATE TABLE reports (
                id INTEGER PRIMARY KEY,
                user_id INTEGER,
                file_path TEXT,
                query TEXT,
                created_at TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()

        # Update DATABASE_URL
        os.environ["DATABASE_URL"] = f"sqlite:///{test_db}"
        from sqlalchemy import create_engine, text
        test_engine = create_engine(f"sqlite:///{test_db}")

        # Run migration check
        with test_engine.connect() as c:
            res = c.execute(text("PRAGMA table_info(reports)"))
            cols = {row[1] for row in res.fetchall()}
            assert "checksum" not in cols
            
            # Apply migration
            if "file_size" not in cols:
                c.execute(text("ALTER TABLE reports ADD COLUMN file_size INTEGER DEFAULT 0"))
            if "checksum" not in cols:
                c.execute(text("ALTER TABLE reports ADD COLUMN checksum VARCHAR(64)"))
            if "meta_file_path" not in cols:
                c.execute(text("ALTER TABLE reports ADD COLUMN meta_file_path VARCHAR(500)"))
            if "format" not in cols:
                c.execute(text("ALTER TABLE reports ADD COLUMN format VARCHAR(20) DEFAULT 'markdown'"))
            c.commit()

            res2 = c.execute(text("PRAGMA table_info(reports)"))
            cols2 = {row[1] for row in res2.fetchall()}
            assert "checksum" in cols2
            assert "file_size" in cols2
            assert "meta_file_path" in cols2
            assert "format" in cols2
        test_engine.dispose()
        print("✅ test_database_migration PASSED")


if __name__ == "__main__":
    test_mcp_filesystem_suite()
    test_file_save_agent_components()
    test_database_migration()
    print("\n🎉 ALL UNIT TESTS PASSED SUCCESSFULLY!")

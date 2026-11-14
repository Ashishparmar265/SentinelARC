"""
FastAPI Filesystem MCP Server

Provides secure file operations with MCP Roots security model via HTTP endpoints.
Supports atomic writes, SHA-256 integrity verification, directory traversal protection,
and full lifecycle file tools (save_file, read_file, list_directory, get_file_info, delete_file).
"""

import os
import time
import hashlib
import tempfile
import asyncio
from pathlib import Path
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# Optional Prometheus monitoring
try:
    from prometheus_fastapi_instrumentator import Instrumentator
    HAS_PROMETHEUS = True
except ImportError:
    HAS_PROMETHEUS = False

from ..protocols.mcp_schemas import (
    SaveFileParams, SaveFileResponse,
    ReadFileParams, ReadFileResponse,
    ListDirectoryParams, ListDirectoryResponse, FileInfoItem,
    GetFileInfoParams, GetFileInfoResponse,
    DeleteFileParams, DeleteFileResponse,
    MCPSecurityError
)


class HealthResponse(BaseModel):
    status: str
    service: str
    timestamp: float
    allowed_roots: List[str]
    tools: List[str]


class PathValidationRequest(BaseModel):
    path: str


class PathValidationResponse(BaseModel):
    path: str
    is_allowed: bool
    resolved_path: Optional[str] = None


def create_filesystem_app() -> FastAPI:
    """Create and configure the Filesystem FastAPI application."""
    
    # Initialize allowed roots from environment, including both container and local defaults
    allowed_roots_env = os.getenv("ALLOWED_ROOTS", "output,temp,/app/output,/app/temp")
    allowed_roots: List[Path] = []
    for root_str in allowed_roots_env.split(","):
        cleaned = root_str.strip()
        if cleaned:
            root_path = Path(cleaned).resolve()
            root_path.mkdir(parents=True, exist_ok=True)
            if root_path not in allowed_roots:
                allowed_roots.append(root_path)

    app = FastAPI(
        title="Filesystem MCP Server",
        description="Secure file operations with MCP Roots security model",
        version="1.1.0"
    )

    # Configure Prometheus monitoring if enabled
    metrics_enabled = os.getenv("METRICS_ENABLED", "false").lower() == "true"
    if metrics_enabled and HAS_PROMETHEUS:
        instrumentator = Instrumentator(
            should_group_status_codes=False,
            should_ignore_untemplated=True,
            should_instrument_requests_inprogress=True,
            should_group_untemplated=False,
            should_round_latency_decimals=True,
            excluded_handlers=["/health", "/metrics"]
        )
        instrumentator.instrument(app).expose(app)

    def _is_path_allowed(path_to_check: str) -> bool:
        """
        Verify that the given path is within one of the allowed roots.
        Prevents directory traversal attacks (e.g., ../../).
        """
        try:
            target_path = Path(path_to_check).resolve()
            for allowed_root in allowed_roots:
                try:
                    target_path.relative_to(allowed_root)
                    return True
                except ValueError:
                    continue
            return False
        except (OSError, ValueError) as e:
            print(f"[FileSystemServer] Path validation error for '{path_to_check}': {e}")
            return False

    def _write_file_sync(target_path: Path, content: str, atomic: bool = True) -> tuple[int, str]:
        """Perform thread-safe synchronous write with optional atomic swap and SHA-256 computation."""
        target_path.parent.mkdir(parents=True, exist_ok=True)
        content_bytes = content.encode("utf-8")
        checksum = hashlib.sha256(content_bytes).hexdigest()

        if atomic:
            # Write to a hidden temporary file in the same parent directory (same filesystem volume)
            with tempfile.NamedTemporaryFile("wb", dir=target_path.parent, delete=False, prefix=".tmp_") as tmp:
                tmp.write(content_bytes)
                tmp.flush()
                os.fsync(tmp.fileno())
                tmp_path = Path(tmp.name)
            # Atomic rename / replace
            tmp_path.replace(target_path)
        else:
            with open(target_path, "wb") as f:
                f.write(content_bytes)

        return len(content_bytes), checksum

    def _read_file_sync(target_path: Path, max_bytes: Optional[int], offset: int) -> tuple[str, int, int, str]:
        """Synchronously read file, compute total size and full SHA-256 checksum."""
        total_size = target_path.stat().st_size
        with open(target_path, "rb") as f:
            full_data = f.read()
            checksum = hashlib.sha256(full_data).hexdigest()
            
            if offset > 0:
                f.seek(offset)
            read_bytes = f.read(max_bytes) if max_bytes is not None else full_data[offset:]
            content = read_bytes.decode("utf-8", errors="replace")
            return content, total_size, len(read_bytes), checksum

    SUPPORTED_TOOLS = ["save_file", "read_file", "list_directory", "get_file_info", "delete_file", "validate_path"]

    @app.get("/health", response_model=HealthResponse)
    async def health_check():
        """Health check endpoint for container orchestration and swarms."""
        return HealthResponse(
            status="healthy",
            service="filesystem",
            timestamp=time.time(),
            allowed_roots=[str(root) for root in allowed_roots],
            tools=SUPPORTED_TOOLS
        )

    @app.post("/tools/save_file", response_model=SaveFileResponse)
    async def save_file_endpoint(params: SaveFileParams):
        """
        Save content to a file with security validation and atomic swap.
        Guarantees zero partial-write corruption for concurrent readers.
        """
        print(f"[FileSystemServer] HTTP: Attempting to save file: {params.file_path} (atomic={params.atomic})")
        
        if not _is_path_allowed(params.file_path):
            error_msg = f"Access denied: '{params.file_path}' is outside allowed roots."
            print(f"[FileSystemServer] HTTP: SECURITY VIOLATION: {error_msg}")
            raise HTTPException(status_code=403, detail=error_msg)
        
        try:
            target_path = Path(params.file_path).resolve()
            bytes_written, checksum = await asyncio.to_thread(
                _write_file_sync, target_path, params.content, params.atomic
            )
            
            print(f"[FileSystemServer] HTTP: ✅ Successfully saved {bytes_written} bytes to {target_path} (SHA-256: {checksum[:12]}...)")
            return SaveFileResponse(
                success=True,
                file_path=str(target_path),
                bytes_written=bytes_written,
                checksum=checksum,
                is_atomic=params.atomic
            )
        except Exception as e:
            error_msg = f"Failed to save file '{params.file_path}': {e}"
            print(f"[FileSystemServer] HTTP: ERROR: {error_msg}")
            raise HTTPException(status_code=500, detail=error_msg)

    @app.post("/tools/read_file", response_model=ReadFileResponse)
    async def read_file_endpoint(params: ReadFileParams):
        """Read content and checksum of a file within allowed roots."""
        if not _is_path_allowed(params.file_path):
            raise HTTPException(status_code=403, detail=f"Access denied: '{params.file_path}' is outside allowed roots.")
        
        target_path = Path(params.file_path).resolve()
        if not target_path.exists():
            raise HTTPException(status_code=404, detail=f"File not found: '{params.file_path}'")
        if not target_path.is_file():
            raise HTTPException(status_code=400, detail=f"Path is not a regular file: '{params.file_path}'")

        try:
            content, total_size, bytes_read, checksum = await asyncio.to_thread(
                _read_file_sync, target_path, params.max_bytes, params.offset
            )
            return ReadFileResponse(
                success=True,
                file_path=str(target_path),
                content=content,
                total_size=total_size,
                bytes_read=bytes_read,
                checksum=checksum
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to read file '{params.file_path}': {e}")

    @app.post("/tools/list_directory", response_model=ListDirectoryResponse)
    async def list_directory_endpoint(params: ListDirectoryParams):
        """List files and directories inside an allowed root path."""
        if not _is_path_allowed(params.directory_path):
            raise HTTPException(status_code=403, detail=f"Access denied: '{params.directory_path}' is outside allowed roots.")
        
        target_dir = Path(params.directory_path).resolve()
        if not target_dir.exists():
            return ListDirectoryResponse(success=True, directory_path=str(target_dir), total_items=0, items=[])
        if not target_dir.is_dir():
            raise HTTPException(status_code=400, detail=f"Path is not a directory: '{params.directory_path}'")

        def _scan_dir() -> List[FileInfoItem]:
            items: List[FileInfoItem] = []
            pattern = params.pattern or "*"
            iterator = target_dir.rglob(pattern) if params.recursive else target_dir.glob(pattern)
            for entry in iterator:
                # Skip temporary files
                if entry.name.startswith(".tmp_"):
                    continue
                try:
                    stat = entry.stat()
                    items.append(FileInfoItem(
                        name=entry.name,
                        path=str(entry),
                        is_dir=entry.is_dir(),
                        size=stat.st_size if entry.is_file() else 0,
                        modified_at=stat.st_mtime
                    ))
                except (OSError, PermissionError):
                    continue
            return sorted(items, key=lambda x: (not x.is_dir, x.name))

        items = await asyncio.to_thread(_scan_dir)
        return ListDirectoryResponse(
            success=True,
            directory_path=str(target_dir),
            total_items=len(items),
            items=items
        )

    @app.post("/tools/get_file_info", response_model=GetFileInfoResponse)
    async def get_file_info_endpoint(params: GetFileInfoParams):
        """Retrieve metadata, size, timestamps, and checksum for a path."""
        if not _is_path_allowed(params.file_path):
            raise HTTPException(status_code=403, detail=f"Access denied: '{params.file_path}' is outside allowed roots.")
        
        target_path = Path(params.file_path).resolve()
        if not target_path.exists():
            return GetFileInfoResponse(
                success=True,
                file_path=str(target_path),
                exists=False,
                is_dir=False,
                size=0
            )

        def _stat_file():
            stat = target_path.stat()
            is_dir = target_path.is_dir()
            checksum = None
            if not is_dir:
                with open(target_path, "rb") as f:
                    checksum = hashlib.sha256(f.read()).hexdigest()
            return stat.st_size, stat.st_ctime, stat.st_mtime, is_dir, checksum

        size, ctime, mtime, is_dir, checksum = await asyncio.to_thread(_stat_file)
        return GetFileInfoResponse(
            success=True,
            file_path=str(target_path),
            exists=True,
            is_dir=is_dir,
            size=size if not is_dir else 0,
            created_at=ctime,
            modified_at=mtime,
            checksum=checksum
        )

    @app.post("/tools/delete_file", response_model=DeleteFileResponse)
    async def delete_file_endpoint(params: DeleteFileParams):
        """Safely delete a file inside allowed roots (disallowing root directory deletion)."""
        if not _is_path_allowed(params.file_path):
            raise HTTPException(status_code=403, detail=f"Access denied: '{params.file_path}' is outside allowed roots.")
        
        target_path = Path(params.file_path).resolve()
        # Security protection: do not allow deleting the allowed root itself
        for root in allowed_roots:
            if target_path == root:
                raise HTTPException(status_code=403, detail="Cannot delete an allowed root directory.")

        if not target_path.exists():
            return DeleteFileResponse(success=True, file_path=str(target_path), deleted=False)

        if target_path.is_dir():
            raise HTTPException(status_code=400, detail="Cannot delete directory via delete_file tool.")

        try:
            await asyncio.to_thread(target_path.unlink)
            print(f"[FileSystemServer] HTTP: Deleted file: {target_path}")
            return DeleteFileResponse(success=True, file_path=str(target_path), deleted=True)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to delete file '{params.file_path}': {e}")

    @app.post("/tools/validate_path", response_model=PathValidationResponse)
    async def validate_path_endpoint(request: PathValidationRequest):
        """Validate a path without performing any operations."""
        is_allowed = _is_path_allowed(request.path)
        resolved_path = None
        if is_allowed:
            try:
                resolved_path = str(Path(request.path).resolve())
            except Exception:
                pass
        
        return PathValidationResponse(
            path=request.path,
            is_allowed=is_allowed,
            resolved_path=resolved_path
        )

    @app.get("/allowed_roots")
    async def get_allowed_roots():
        """Return the list of allowed root directories."""
        return {
            "allowed_roots": [str(root) for root in allowed_roots],
            "total_roots": len(allowed_roots)
        }

    @app.get("/")
    async def root():
        """Root endpoint with server information."""
        return {
            "service": "Filesystem MCP Server",
            "version": "1.1.0",
            "tools": SUPPORTED_TOOLS,
            "security_model": "MCP Roots",
            "allowed_roots": [str(root) for root in allowed_roots],
            "endpoints": {
                "health": "/health",
                "save_file": "/tools/save_file",
                "read_file": "/tools/read_file",
                "list_directory": "/tools/list_directory",
                "get_file_info": "/tools/get_file_info",
                "delete_file": "/tools/delete_file",
                "validate_path": "/tools/validate_path",
                "allowed_roots": "/allowed_roots"
            }
        }

    return app


# For direct running (development)
if __name__ == "__main__":
    import uvicorn
    app = create_filesystem_app()
    uvicorn.run(app, host="0.0.0.0", port=8002)

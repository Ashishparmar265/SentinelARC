"""
Async Extraction Agent

Agent responsible for extracting content from URLs and documents asynchronously.
Supports batch extraction, PDF parsing, and CORE open-access paywall bypass.
"""

import asyncio
import io
import logging
import re
from typing import Dict, List, Any, Optional
import requests

from .async_base_agent import AsyncBaseAgent, MCPClientMixin
from ..protocols.acp_schema import (
    ACPMessage, ACPMsgType, TaskAssignPayload, StatusUpdatePayload, 
    DataSubmitPayload, LogBroadcastPayload
)

logger = logging.getLogger(__name__)

# Known paywalled / academic publisher domains where full text is gated behind logins
PAYWALLED_DOMAINS = [
    "sciencedirect.com",
    "ieee.org",
    "springer.com",
    "nature.com",
    "wiley.com",
    "tandfonline.com",
    "acm.org",
    "oup.com",
    "jstor.org",
    "frontiersin.org",
    "cell.com",
    "pnas.org"
]


class AsyncExtractionAgent(AsyncBaseAgent, MCPClientMixin):
    """
    Asynchronous agent that extracts text content from URLs, academic papers, and PDFs.
    
    Capabilities:
    - High-throughput parallel batch extraction
    - Native PyPDF2 stream parsing for arXiv & open-access PDFs
    - Automated paywall bypass via CORE API open-access search
    - Rich abstract fallback to avoid hanging or empty documents
    """
    
    def __init__(self, agent_id: str, message_bus, mcp_servers: Dict[str, str]):
        AsyncBaseAgent.__init__(self, agent_id, message_bus, mcp_servers)
        MCPClientMixin.__init__(self)
        
        self.orchestrator_id = "orchestrator"
        self.current_task = None
        
        logger.info(f"[{self.agent_id}] Async Extraction Agent initialized (Batch & Paywall Bypass enabled)")
    
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
        """Handle content extraction task assignments."""
        try:
            payload = TaskAssignPayload(**message.payload)
            task_type = payload.task_type
            task_data = payload.task_data
            
            if task_type == "batch_extract":
                await self._handle_batch_extraction(task_data)
            elif task_type == "extract_content":
                await self._extract_content_from_url(task_data)
            else:
                logger.warning(f"[{self.agent_id}] Unknown task type: {task_type}")
        except Exception as e:
            logger.error(f"[{self.agent_id}] Error in task assignment: {e}", exc_info=True)
            await self._send_error_status(str(e))

    async def _handle_batch_extraction(self, task_data: Dict[str, Any]):
        """
        Execute concurrent extraction over a batch of candidate papers.
        """
        task_id = task_data.get("task_id", "unknown")
        items = task_data.get("items", []) or task_data.get("sources", [])
        
        if not items:
            logger.warning(f"[{self.agent_id}] Batch extract received empty item list (task: {task_id})")
            await self._submit_batch_results([], task_id)
            return

        total_items = len(items)
        logger.info(f"[{self.agent_id}] 🚀 Starting parallel batch extraction for {total_items} items (task: {task_id})")
        await self._send_status_update(f"batch_extraction_starting: 0/{total_items}", 5.0, task_id)

        # Concurrency limiter: up to 5 concurrent extraction routines
        semaphore = asyncio.Semaphore(5)
        completed_count = 0

        async def _extract_item_safe(item: Dict[str, Any], idx: int) -> Dict[str, Any]:
            nonlocal completed_count
            async with semaphore:
                try:
                    result = await self._extract_single_candidate(item, task_id)
                except Exception as ex:
                    logger.warning(f"[{self.agent_id}] Extraction failed on item {idx}: {ex}")
                    # Graceful abstract fallback
                    result = {
                        "url": item.get("url", ""),
                        "title": item.get("title", f"Document {idx+1}"),
                        "content": item.get("abstract", "") or item.get("fallback_abstract", ""),
                        "word_count": len((item.get("abstract") or "").split()),
                        "source_description": item.get("source", "scholarly_source"),
                        "doi": item.get("doi"),
                        "is_anchor": item.get("is_anchor", False),
                        "citation_velocity": item.get("citation_velocity", 0.0),
                        "extraction_successful": bool(item.get("abstract")),
                        "used_fallback": True,
                        "error": str(ex)
                    }
                
                completed_count += 1
                progress_pct = round((completed_count / total_items) * 90.0, 1)
                await self._send_status_update(
                    f"batch_extracting: {completed_count}/{total_items} complete", 
                    progress_pct, 
                    task_id
                )
                return result

        tasks = [_extract_item_safe(item, i) for i, item in enumerate(items)]
        extracted_batch = await asyncio.gather(*tasks)

        logger.info(f"[{self.agent_id}] ✅ Batch extraction finished: {len(extracted_batch)} documents processed.")
        await self._send_status_update("batch_extraction_complete", 100.0, task_id)
        await self._submit_batch_results(extracted_batch, task_id)

    async def _extract_single_candidate(self, item: Dict[str, Any], task_id: str) -> Dict[str, Any]:
        """Extract a single candidate paper using PDF stream, MCP browse, or CORE bypass."""
        url = item.get("url", "")
        pdf_url = item.get("pdf_url") or (url if url and url.lower().endswith(".pdf") else None)
        title = item.get("title", "")
        doi = item.get("doi")
        abstract = item.get("abstract", "") or item.get("fallback_abstract", "")
        is_anchor = item.get("is_anchor", False)
        velocity = item.get("citation_velocity", 0.0)

        # 1. Direct PDF parsing (arXiv or direct OA PDF)
        target_pdf = pdf_url if pdf_url else (url if url and url.lower().endswith(".pdf") else None)
        if target_pdf:
            pdf_content = await self._fetch_pdf_text_async(target_pdf)
            if pdf_content and len(pdf_content.strip()) > 200:
                return {
                    "url": target_pdf,
                    "title": title or f"PDF Document from {target_pdf}",
                    "content": pdf_content,
                    "word_count": len(pdf_content.split()),
                    "source_description": item.get("source", "PDF"),
                    "doi": doi,
                    "is_anchor": is_anchor,
                    "citation_velocity": velocity,
                    "extraction_successful": True,
                    "used_fallback": False,
                    "method": "native_pdf"
                }

        # 2. Check if domain is paywalled
        is_paywalled = any(domain in url.lower() for domain in PAYWALLED_DOMAINS) if url else False
        
        extracted_text = ""
        used_mcp = False

        if not is_paywalled and url and url.startswith("http"):
            try:
                # Call Primary Tooling MCP browse_and_extract
                mcp_res = await self.call_mcp_tool(
                    server_name="primary_tooling",
                    tool_name="browse_and_extract",
                    params={"url": url}
                )
                if isinstance(mcp_res, dict):
                    extracted_text = mcp_res.get("content", "")
                    used_mcp = True
            except Exception as e:
                logger.debug(f"[{self.agent_id}] MCP browse failed for {url}: {e}")

        # 3. Paywall Bypass via CORE Open-Access API
        if is_paywalled or len(extracted_text.strip()) < 150:
            logger.info(f"[{self.agent_id}] Gated/short content for '{title[:40]}'. Attempting CORE open-access bypass...")
            core_content = await self._fetch_core_open_access_text(title, doi)
            if core_content and len(core_content.strip()) > 200:
                return {
                    "url": url,
                    "title": title,
                    "content": core_content,
                    "word_count": len(core_content.split()),
                    "source_description": f"{item.get('source', 'Web')} (CORE OA)",
                    "doi": doi,
                    "is_anchor": is_anchor,
                    "citation_velocity": velocity,
                    "extraction_successful": True,
                    "used_fallback": False,
                    "method": "core_oa_bypass"
                }

        # 4. Use MCP extracted text if sufficient
        if len(extracted_text.strip()) >= 150:
            return {
                "url": url,
                "title": title,
                "content": extracted_text,
                "word_count": len(extracted_text.split()),
                "source_description": item.get("source", "Web"),
                "doi": doi,
                "is_anchor": is_anchor,
                "citation_velocity": velocity,
                "extraction_successful": True,
                "used_fallback": False,
                "method": "mcp_browse"
            }

        # 5. Final fallback to rich abstract
        logger.info(f"[{self.agent_id}] Using abstract fallback for: '{title[:40]}'")
        final_content = abstract if abstract and len(abstract.strip()) > 30 else f"Paper Title: {title}. Full content gated."
        return {
            "url": url or "#",
            "title": title,
            "content": final_content,
            "word_count": len(final_content.split()),
            "source_description": item.get("source", "Academic Abstract"),
            "doi": doi,
            "is_anchor": is_anchor,
            "citation_velocity": velocity,
            "extraction_successful": bool(abstract),
            "used_fallback": True,
            "method": "abstract_fallback"
        }

    async def _fetch_pdf_text_async(self, pdf_url: str) -> Optional[str]:
        """Fetch and extract text from an open PDF asynchronously using PyPDF2."""
        try:
            import PyPDF2
            headers = {"User-Agent": "SentinelARC/2.0 Academic Extractor"}
            resp = await asyncio.to_thread(requests.get, pdf_url, headers=headers, timeout=15)
            if resp.status_code == 200 and len(resp.content) > 1000:
                pdf_file = io.BytesIO(resp.content)
                reader = PyPDF2.PdfReader(pdf_file)
                extracted_pages = []
                # Extract first 12 pages maximum to balance detail and performance
                max_pages = min(12, len(reader.pages))
                for i in range(max_pages):
                    txt = reader.pages[i].extract_text()
                    if txt:
                        extracted_pages.append(txt)
                content = "\n".join(extracted_pages)
                if len(content.strip()) > 200:
                    logger.info(f"[{self.agent_id}] Extracted {len(content)} chars from PDF: {pdf_url}")
                    return content
        except Exception as e:
            logger.debug(f"[{self.agent_id}] PDF extraction error on {pdf_url}: {e}")
        return None

    async def _fetch_core_open_access_text(self, title: str, doi: Optional[str] = None) -> Optional[str]:
        """Query CORE open-access repository for downloadable full-text PDF or content."""
        if not title and not doi:
            return None
        try:
            query = f'doi:"{doi}"' if doi else title.replace('"', '').replace(":", " ")
            url = "https://api.core.ac.uk/v3/search/works"
            params = {"q": query[:120], "limit": 3}
            headers = {"User-Agent": "SentinelARC/2.0 Research Extractor"}

            resp = await asyncio.to_thread(requests.get, url, params=params, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("results", [])
                for r in results:
                    download_url = r.get("downloadUrl")
                    if download_url and download_url.startswith("http"):
                        logger.info(f"[{self.agent_id}] Found CORE OA download URL: {download_url}")
                        pdf_txt = await self._fetch_pdf_text_async(download_url)
                        if pdf_txt:
                            return pdf_txt
                    # If CORE abstract is richer than what we had
                    core_abstract = r.get("abstract")
                    if core_abstract and len(core_abstract) > 300:
                        return f"CORE Abstract: {core_abstract}"
        except Exception as e:
            logger.debug(f"[{self.agent_id}] CORE OA query error: {e}")
        return None

    async def _submit_batch_results(self, extracted_batch: List[Dict[str, Any]], task_id: str):
        """Submit the complete batch of extracted content to Orchestrator."""
        data_message = self.create_message(
            receiver_id=self.orchestrator_id,
            msg_type=ACPMsgType.DATA_SUBMIT,
            payload=DataSubmitPayload(
                data_type="extracted_content_batch",
                data={
                    "items": extracted_batch,
                    "task_id": task_id,
                    "total_extracted": len(extracted_batch)
                },
                source="batch_extraction_engine",
                task_id=task_id
            ).model_dump()
        )
        await self.send_message(data_message)
        logger.info(f"[{self.agent_id}] 📤 Delivered extracted batch ({len(extracted_batch)} docs) to Orchestrator.")

    # Legacy single-URL extraction support for backward compatibility
    async def _extract_content_from_url(self, task_data: Dict):
        """Extract content from a single URL."""
        url = task_data.get("url")
        task_id = task_data.get("task_id", "unknown")
        
        item = {
            "url": url,
            "title": task_data.get("title", f"Document from {url}"),
            "abstract": task_data.get("fallback_abstract", ""),
            "source": task_data.get("source_description", "Web")
        }
        res = await self._extract_single_candidate(item, task_id)
        
        data_message = self.create_message(
            receiver_id=self.orchestrator_id,
            msg_type=ACPMsgType.DATA_SUBMIT,
            payload=DataSubmitPayload(
                data_type="extracted_content",
                data=res,
                source=url,
                task_id=task_id
            ).model_dump()
        )
        await self.send_message(data_message)

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
        await self._send_status_update(f"extraction_failed: {error_message}", 0.0, task_id)

    def get_capabilities(self) -> Dict[str, str]:
        """Return agent capabilities."""
        return {
            "agent_type": "extraction_agent",
            "primary_function": "content_extraction",
            "mcp_tools": ["browse_and_extract"],
            "supported_tasks": ["batch_extract", "extract_content"],
            "features": "core_oa_bypass, native_pdf_parsing, parallel_batch",
            "streaming_support": True,
            "async_capable": True
        }

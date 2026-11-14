"""
Async Extraction Agent

Agent responsible for extracting content from URLs and academic documents asynchronously.
Features:
- Multi-tier retrieval cascade: Native PDF stream -> Unpaywall OA -> MCP Browse -> CORE OA -> Abstract Fallback
- IMRAD section segmentation (Abstract, Intro, Methods, Results, Conclusion) and Bibliography stripping
- Key benchmark and quantitative finding extraction
- Local SQLite document cache memoization (< 5ms on cache hit)
- High-throughput parallel batch extraction with asyncio.Semaphore concurrency control
"""

import asyncio
import io
import logging
import os
import re
import json
import hashlib
import sqlite3
from typing import Dict, List, Any, Optional, Tuple
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
    Asynchronous agent that extracts and structures academic papers and scientific documents.
    
    Capabilities:
    - High-throughput parallel batch extraction
    - Native PyPDF2 stream parsing for arXiv & open-access PDFs
    - Dual paywall bypass via Unpaywall & CORE Open-Access APIs
    - IMRAD academic section segmentation & reference stripping
    - Numerical benchmark extraction
    - SQLite document cache memoization
    """
    
    def __init__(self, agent_id: str, message_bus, mcp_servers: Dict[str, str]):
        AsyncBaseAgent.__init__(self, agent_id, message_bus, mcp_servers)
        MCPClientMixin.__init__(self)
        
        self.orchestrator_id = "orchestrator"
        self.current_task = None
        self._init_document_cache()
        
        logger.info(f"[{self.agent_id}] Async Extraction Agent initialized (IMRAD + Unpaywall + CORE + DocCache)")

    def _init_document_cache(self):
        """Initialize SQLite document cache table in output/sentinelarc.db."""
        try:
            db_candidates = ["output/sentinelarc.db", "/app/output/sentinelarc.db"]
            target_db = next((p for p in db_candidates if os.path.exists(os.path.dirname(p))), "output/sentinelarc.db")
            conn = sqlite3.connect(target_db, timeout=5)
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS document_cache (
                    doc_hash TEXT PRIMARY KEY,
                    url TEXT,
                    title TEXT,
                    content TEXT,
                    word_count INTEGER,
                    sections_json TEXT,
                    benchmarks_json TEXT,
                    method TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
            conn.close()
        except Exception as e:
            logger.debug(f"[{self.agent_id}] Document cache init notice: {e}")

    def _check_doc_cache(self, key: str) -> Optional[Dict[str, Any]]:
        """Look up extracted content in SQLite cache."""
        if not key:
            return None
        try:
            db_candidates = ["output/sentinelarc.db", "/app/output/sentinelarc.db"]
            target_db = next((p for p in db_candidates if os.path.exists(os.path.dirname(p))), "output/sentinelarc.db")
            doc_hash = hashlib.sha256(key.strip().lower().encode()).hexdigest()
            conn = sqlite3.connect(target_db, timeout=5)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT url, title, content, word_count, sections_json, benchmarks_json, method FROM document_cache WHERE doc_hash = ?",
                (doc_hash,)
            )
            row = cursor.fetchone()
            conn.close()
            if row:
                url, title, content, word_count, sections_json, benchmarks_json, method = row
                logger.info(f"[{self.agent_id}] ⚡ DocCache HIT for '{title[:35]}' ({word_count} words).")
                return {
                    "url": url,
                    "title": title,
                    "content": content,
                    "word_count": word_count,
                    "sections": json.loads(sections_json) if sections_json else {},
                    "numerical_benchmarks": json.loads(benchmarks_json) if benchmarks_json else [],
                    "extraction_successful": True,
                    "used_fallback": False,
                    "method": f"{method}_cached"
                }
        except Exception as e:
            logger.debug(f"[{self.agent_id}] DocCache lookup notice: {e}")
        return None

    def _save_doc_cache(self, key: str, doc_data: Dict[str, Any]):
        """Persist extracted content to SQLite document cache."""
        if not key or not doc_data.get("content"):
            return
        try:
            db_candidates = ["output/sentinelarc.db", "/app/output/sentinelarc.db"]
            target_db = next((p for p in db_candidates if os.path.exists(os.path.dirname(p))), "output/sentinelarc.db")
            doc_hash = hashlib.sha256(key.strip().lower().encode()).hexdigest()
            conn = sqlite3.connect(target_db, timeout=5)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO document_cache 
                (doc_hash, url, title, content, word_count, sections_json, benchmarks_json, method, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (
                doc_hash,
                doc_data.get("url", ""),
                doc_data.get("title", ""),
                doc_data.get("content", ""),
                doc_data.get("word_count", 0),
                json.dumps(doc_data.get("sections", {})),
                json.dumps(doc_data.get("numerical_benchmarks", [])),
                doc_data.get("method", "extracted")
            ))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.debug(f"[{self.agent_id}] DocCache store notice: {e}")
    
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
        """Execute concurrent extraction over a batch of candidate papers."""
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
                    raw_abstract = item.get("abstract", "") or item.get("fallback_abstract", "")
                    clean_text, sections, benchmarks = self._process_academic_text(raw_abstract)
                    result = {
                        "url": item.get("url", ""),
                        "title": item.get("title", f"Document {idx+1}"),
                        "content": clean_text or raw_abstract,
                        "word_count": len((clean_text or raw_abstract).split()),
                        "sections": sections,
                        "numerical_benchmarks": benchmarks,
                        "source_description": item.get("source", "scholarly_source"),
                        "doi": item.get("doi"),
                        "is_anchor": item.get("is_anchor", False),
                        "citation_velocity": item.get("citation_velocity", 0.0),
                        "extraction_successful": bool(clean_text or raw_abstract),
                        "used_fallback": True,
                        "method": "abstract_fallback",
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
        """Extract a single paper using cache, PDF stream, Unpaywall, MCP, or CORE bypass."""
        url = item.get("url", "")
        pdf_url = item.get("pdf_url") or (url if url and url.lower().endswith(".pdf") else None)
        title = item.get("title", "")
        doi = item.get("doi")
        abstract = item.get("abstract", "") or item.get("fallback_abstract", "")
        is_anchor = item.get("is_anchor", False)
        velocity = item.get("citation_velocity", 0.0)

        cache_key = doi or url or title
        cached_result = self._check_doc_cache(cache_key)
        if cached_result:
            cached_result["is_anchor"] = is_anchor
            cached_result["citation_velocity"] = velocity
            return cached_result

        # 1. Direct PDF parsing (arXiv or direct OA PDF)
        target_pdf = pdf_url if pdf_url else (url if url and url.lower().endswith(".pdf") else None)
        if target_pdf:
            raw_pdf_content = await self._fetch_pdf_text_async(target_pdf)
            if raw_pdf_content and len(raw_pdf_content.strip()) > 200:
                clean_text, sections, benchmarks = self._process_academic_text(raw_pdf_content)
                doc_data = {
                    "url": target_pdf,
                    "title": title or f"PDF Document from {target_pdf}",
                    "content": clean_text,
                    "word_count": len(clean_text.split()),
                    "sections": sections,
                    "numerical_benchmarks": benchmarks,
                    "source_description": item.get("source", "PDF"),
                    "doi": doi,
                    "is_anchor": is_anchor,
                    "citation_velocity": velocity,
                    "extraction_successful": True,
                    "used_fallback": False,
                    "method": "native_pdf"
                }
                self._save_doc_cache(cache_key, doc_data)
                return doc_data

        # 2. Unpaywall API Open-Access PDF Lookup (if DOI available)
        if doi and re.match(r"^10\.\d{4,9}/", doi.strip()):
            unpaywall_pdf = await self._fetch_unpaywall_open_access_pdf(doi.strip())
            if unpaywall_pdf:
                raw_oa_content = await self._fetch_pdf_text_async(unpaywall_pdf)
                if raw_oa_content and len(raw_oa_content.strip()) > 200:
                    clean_text, sections, benchmarks = self._process_academic_text(raw_oa_content)
                    doc_data = {
                        "url": unpaywall_pdf,
                        "title": title,
                        "content": clean_text,
                        "word_count": len(clean_text.split()),
                        "sections": sections,
                        "numerical_benchmarks": benchmarks,
                        "source_description": f"{item.get('source', 'Web')} (Unpaywall OA)",
                        "doi": doi,
                        "is_anchor": is_anchor,
                        "citation_velocity": velocity,
                        "extraction_successful": True,
                        "used_fallback": False,
                        "method": "unpaywall_oa"
                    }
                    self._save_doc_cache(cache_key, doc_data)
                    return doc_data

        # 3. Check if domain is paywalled
        is_paywalled = any(domain in url.lower() for domain in PAYWALLED_DOMAINS) if url else False
        extracted_text = ""

        # 4. MCP browse_and_extract for open web articles
        if not is_paywalled and url and url.startswith("http"):
            try:
                mcp_res = await self.call_mcp_tool(
                    server_name="primary_tooling",
                    tool_name="browse_and_extract",
                    params={"url": url}
                )
                if isinstance(mcp_res, dict):
                    extracted_text = mcp_res.get("content", "")
            except Exception as e:
                logger.debug(f"[{self.agent_id}] MCP browse failed for {url}: {e}")

        # 5. Paywall Bypass via CORE Open-Access API
        if is_paywalled or len(extracted_text.strip()) < 150:
            logger.info(f"[{self.agent_id}] Gated/short content for '{title[:35]}'. Attempting CORE open-access bypass...")
            core_content = await self._fetch_core_open_access_text(title, doi)
            if core_content and len(core_content.strip()) > 200:
                clean_text, sections, benchmarks = self._process_academic_text(core_content)
                doc_data = {
                    "url": url,
                    "title": title,
                    "content": clean_text,
                    "word_count": len(clean_text.split()),
                    "sections": sections,
                    "numerical_benchmarks": benchmarks,
                    "source_description": f"{item.get('source', 'Web')} (CORE OA)",
                    "doi": doi,
                    "is_anchor": is_anchor,
                    "citation_velocity": velocity,
                    "extraction_successful": True,
                    "used_fallback": False,
                    "method": "core_oa_bypass"
                }
                self._save_doc_cache(cache_key, doc_data)
                return doc_data

        # 6. Use MCP extracted text if sufficient
        if len(extracted_text.strip()) >= 150:
            clean_text, sections, benchmarks = self._process_academic_text(extracted_text)
            doc_data = {
                "url": url,
                "title": title,
                "content": clean_text,
                "word_count": len(clean_text.split()),
                "sections": sections,
                "numerical_benchmarks": benchmarks,
                "source_description": item.get("source", "Web"),
                "doi": doi,
                "is_anchor": is_anchor,
                "citation_velocity": velocity,
                "extraction_successful": True,
                "used_fallback": False,
                "method": "mcp_browse"
            }
            self._save_doc_cache(cache_key, doc_data)
            return doc_data

        # 7. Final fallback to rich abstract
        logger.info(f"[{self.agent_id}] Using abstract fallback for: '{title[:35]}'")
        raw_final = abstract if abstract and len(abstract.strip()) > 30 else f"Paper Title: {title}. Full content gated."
        clean_text, sections, benchmarks = self._process_academic_text(raw_final)
        
        doc_data = {
            "url": url or "#",
            "title": title,
            "content": clean_text or raw_final,
            "word_count": len((clean_text or raw_final).split()),
            "sections": sections,
            "numerical_benchmarks": benchmarks,
            "source_description": item.get("source", "Academic Abstract"),
            "doi": doi,
            "is_anchor": is_anchor,
            "citation_velocity": velocity,
            "extraction_successful": bool(abstract),
            "used_fallback": True,
            "method": "abstract_fallback"
        }
        self._save_doc_cache(cache_key, doc_data)
        return doc_data

    def _process_academic_text(self, raw_text: str) -> Tuple[str, Dict[str, str], List[str]]:
        """
        1. Strips terminal references and bibliographies.
        2. Segments into major academic IMRAD sections.
        3. Extracts key numerical benchmark claims.
        """
        if not raw_text:
            return "", {}, []

        # 1. Strip References / Bibliography towards second half of text
        clean_text = raw_text
        if len(raw_text) > 1000:
            half_point = int(len(raw_text) * 0.45)
            ref_match = re.search(r'\n\s*(?:References|Bibliography|Literature Cited)\s*\n', raw_text[half_point:], re.IGNORECASE)
            if ref_match:
                clean_text = raw_text[:half_point + ref_match.start()].strip()

        # 2. IMRAD Section Segmentation
        sections = {}
        section_headers = [
            ("abstract", r'(?i)\n(?:[0-9IVX]+\.?\s+)?(Abstract)\b'),
            ("introduction", r'(?i)\n(?:[0-9IVX]+\.?\s+)?(Introduction|Background)\b'),
            ("methodology", r'(?i)\n(?:[0-9IVX]+\.?\s+)?(Methodology|Methods|Method|System Architecture|Proposed Approach|Model Architecture)\b'),
            ("results", r'(?i)\n(?:[0-9IVX]+\.?\s+)?(Experiments|Experimental Setup|Results|Evaluation|Empirical Analysis)\b'),
            ("conclusion", r'(?i)\n(?:[0-9IVX]+\.?\s+)?(Discussion|Conclusion|Conclusions|Concluding Remarks)\b')
        ]

        # Find section positions
        positions = []
        for sec_name, pattern in section_headers:
            match = re.search(pattern, clean_text)
            if match:
                positions.append((match.start(), sec_name))

        positions.sort()
        for i, (start_pos, sec_name) in enumerate(positions):
            end_pos = positions[i + 1][0] if i + 1 < len(positions) else len(clean_text)
            sec_text = clean_text[start_pos:end_pos].strip()
            # Truncate section if unusually long
            sections[sec_name] = sec_text[:4000]

        # 3. Extract Numerical Benchmark Claims
        benchmark_patterns = [
            r'(?:achiev\w+|outperform\w+|surpass\w+|improv\w+|exceed\w+|reduc\w+)[^.\n]{1,60}(?:by\s+)?[\d\.]+(?:\%|x| points| dB|ms|s)?',
            r'[\d\.]+\%\s+(?:accuracy|F1|BLEU|ROUGE|gain|improvement|reduction|precision|recall|success rate)',
            r'(?:state-of-the-art|SOTA)[^.\n]{1,60}'
        ]
        benchmarks = []
        for pat in benchmark_patterns:
            matches = re.findall(pat, clean_text, re.IGNORECASE)
            for m in matches:
                clean_m = m.strip().replace('\n', ' ')
                if clean_m and len(clean_m) > 10 and clean_m not in benchmarks:
                    benchmarks.append(clean_m)
                    if len(benchmarks) >= 5:
                        break
            if len(benchmarks) >= 5:
                break

        return clean_text, sections, benchmarks

    async def _fetch_pdf_text_async(self, pdf_url: str) -> Optional[str]:
        """Fetch and extract text from an open PDF asynchronously using PyPDF2."""
        try:
            import PyPDF2
            headers = {"User-Agent": "SentinelARC/2.0 Academic Extractor"}
            resp = await asyncio.to_thread(requests.get, pdf_url, headers=headers, timeout=12)
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

    async def _fetch_unpaywall_open_access_pdf(self, doi: str) -> Optional[str]:
        """Query Unpaywall API for legal open-access PDF links."""
        try:
            url = f"https://api.unpaywall.org/v2/{doi}"
            params = {"email": "sentinelarc@deepmind.edu"}
            resp = await asyncio.to_thread(requests.get, url, params=params, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("is_oa"):
                    best_oa = data.get("best_oa_location") or {}
                    pdf_url = best_oa.get("url_for_pdf") or best_oa.get("url")
                    if pdf_url and pdf_url.startswith("http"):
                        logger.info(f"[{self.agent_id}] 🔓 Unpaywall OA found for DOI {doi}: {pdf_url}")
                        return pdf_url
        except Exception as e:
            logger.debug(f"[{self.agent_id}] Unpaywall query notice: {e}")
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

            resp = await asyncio.to_thread(requests.get, url, params=params, headers=headers, timeout=8)
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
                    core_abstract = r.get("abstract")
                    if core_abstract and len(core_abstract) > 300:
                        return f"CORE Abstract: {core_abstract}"
        except Exception as e:
            logger.debug(f"[{self.agent_id}] CORE OA query notice: {e}")
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

    async def _extract_content_from_url(self, task_data: Dict):
        """Extract content from a single URL (backward compatibility)."""
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
            "features": "unpaywall_oa, core_oa_bypass, native_pdf_parsing, imrad_segmentation, doc_cache, benchmark_extractor",
            "streaming_support": True,
            "async_capable": True
        }

"""
Async Search Agent

Agent responsible for academic literature discovery across multiple scholarly sources.
Features:
- Multi-source parallel search: OpenAlex, Semantic Scholar, arXiv, and PubMed
- Direct DOI resolution via Crossref
- Dynamic citation velocity calculation and seminal anchor paper detection
- LLM query expansion and cross-encoder reranking via Groq
"""

import logging
import asyncio
import requests
import os
import re
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Any
from datetime import datetime

from .async_base_agent import AsyncBaseAgent
from ..protocols.acp_schema import (
    ACPMessage, ACPMsgType, TaskAssignPayload, StatusUpdatePayload,
    DataSubmitPayload
)

logger = logging.getLogger(__name__)


def reconstruct_openalex_abstract(inverted_index: Optional[Dict]) -> str:
    """Reconstruct human-readable abstract from OpenAlex inverted index."""
    if not inverted_index or not isinstance(inverted_index, dict):
        return ""
    words = {}
    for word, positions in inverted_index.items():
        for pos in positions:
            words[pos] = word
    return " ".join([words[i] for i in sorted(words.keys())])


class AsyncSearchAgent(AsyncBaseAgent):
    def __init__(self, agent_id: str, message_bus, mcp_servers: Dict[str, str]):
        super().__init__(agent_id, message_bus, mcp_servers)
        self.orchestrator_id = "orchestrator"
        logger.info(f"[{self.agent_id}] 🚀 Multi-Source Academic Search Agent Initialized")

    async def handle_message(self, message: ACPMessage):
        try:
            if message.msg_type == ACPMsgType.TASK_ASSIGN:
                payload = TaskAssignPayload(**message.payload)
                if payload.task_type == "web_search":
                    await self._perform_multi_source_search(payload.task_data)
        except Exception as e:
            logger.error(f"[{self.agent_id}] Error handling message: {e}", exc_info=True)

    async def _perform_multi_source_search(self, task_data: Dict):
        query = task_data.get("query", "").strip()
        task_id = task_data.get("task_id", "unknown")
        strategy = task_data.get("strategy", "standard")
        logger.info(f"[{self.agent_id}] 📡 Academic Research Query (task: {task_id}): '{query}'")

        # Step 0: Check if query contains a DOI (e.g. 10.1038/..., 10.1103/...)
        doi_match = re.search(r'\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+\b', query)
        if doi_match:
            doi = doi_match.group(0)
            logger.info(f"[{self.agent_id}] Direct DOI detected: {doi}. Fetching from Crossref...")
            doi_paper = await self._fetch_crossref_doi_async(doi)
            if doi_paper:
                await self._submit_results([doi_paper], query, task_id)
                return

        # Step 1: Query Expansion via Groq
        expanded_query = query
        try:
            from groq import Groq
            client = Groq(api_key=os.getenv("GROQ_API_KEY"))
            system_prompt = (
                "You are an expert academic research librarian. "
                "Your task is to take a user's research query and expand it into a high-quality search string for academic databases. "
                "CRITICAL: If the query contains 'RAG', it refers to 'Retrieval-Augmented Generation' in Artificial Intelligence. "
                "Provide a clean search string using Boolean operators (AND, OR) and quotes for phrases. "
                "Limit your response to ONLY the search string. No explanations or conversational text."
            )
            if strategy == "broaden_perspectives":
                system_prompt += " Broaden the query to capture alternative hypotheses, counter-arguments, and edge cases."

            groq_model = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")
            response = client.chat.completions.create(
                model=groq_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": query}
                ],
                temperature=0.1,
                max_tokens=128
            )
            candidate_expanded = response.choices[0].message.content.strip()
            if candidate_expanded.startswith('"') and candidate_expanded.endswith('"'):
                candidate_expanded = candidate_expanded[1:-1]
            if len(candidate_expanded) > 3:
                expanded_query = candidate_expanded
            logger.info(f"[{self.agent_id}] Expanded query: '{expanded_query}'")
        except Exception as e:
            logger.warning(f"[{self.agent_id}] Groq expansion bypassed: {e}. Using original query.")
            expanded_query = query

        # Step 2: Multi-Source Parallel Fetch (OpenAlex + Semantic Scholar + arXiv + PubMed)
        logger.info(f"[{self.agent_id}] ⚡ Executing Multi-Source Parallel Academic Gather...")
        
        openalex_task = self._fetch_openalex_async(expanded_query, limit=12)
        semantic_task = self._fetch_semantic_scholar_async(expanded_query, limit=12)
        arxiv_task = asyncio.to_thread(self._fetch_arxiv_sync, expanded_query, limit=10)
        pubmed_task = asyncio.to_thread(self._fetch_pubmed_sync, expanded_query, limit=6)

        results_tuple = await asyncio.gather(
            openalex_task, semantic_task, arxiv_task, pubmed_task, 
            return_exceptions=True
        )

        papers: List[Dict[str, Any]] = []
        seen_titles = set()

        for res in results_tuple:
            if isinstance(res, list):
                for paper in res:
                    raw_title = paper.get("title", "").strip().lower()
                    if raw_title and raw_title not in seen_titles:
                        seen_titles.add(raw_title)
                        papers.append(paper)

        logger.info(f"[{self.agent_id}] Aggregated {len(papers)} unique papers across 4 scholarly sources.")

        # Step 3: Compute Citation Velocity & Anchor Paper Detection
        current_year = datetime.now().year
        all_cites = [p.get("citationCount", 0) for p in papers]
        median_cites = sorted(all_cites)[len(all_cites) // 2] if all_cites else 0

        for p in papers:
            pub_year = p.get("year")
            try:
                pub_year_int = int(str(pub_year)[:4]) if pub_year and str(pub_year)[:4].isdigit() else (current_year - 1)
            except Exception:
                pub_year_int = current_year - 1

            years_since = max(1, current_year - pub_year_int)
            citations = p.get("citationCount", 0) or 0
            velocity = citations / years_since
            p["citation_velocity"] = round(velocity, 2)

            # Anchor Detection: high citation velocity (fresh breakthrough) OR historical outlier
            is_anchor = (velocity >= 25.0) or (citations >= 50 and citations >= 3 * max(1, median_cites))
            p["is_anchor"] = is_anchor
            if is_anchor:
                logger.info(f"[{self.agent_id}] 🏆 Anchor paper identified: '{p.get('title')}' (Citations: {citations}, Velocity: {p['citation_velocity']}/yr)")

        # Step 4: Cross-Encoder Reranking using Groq (if candidates available)
        if len(papers) > 0:
            logger.info(f"[{self.agent_id}] Reranking {len(papers)} candidate papers...")
            try:
                paper_snippets = ""
                for i, p in enumerate(papers[:15]):
                    t = p.get('title', '')
                    ab = str(p.get('abstract', ''))[:200]
                    paper_snippets += f"[{i}] {t}\n{ab}\n\n"

                rerank_prompt = (
                    f"You are an academic reviewer selecting papers for: '{query}'.\n"
                    "Output ONLY a valid JSON array of integer IDs for papers directly relevant. "
                    "Example: [0, 2, 4]\n\n"
                    f"{paper_snippets}"
                )
                from groq import Groq
                client = Groq(api_key=os.getenv("GROQ_API_KEY"))
                groq_model = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")
                rerank_res = client.chat.completions.create(
                    model=groq_model,
                    messages=[{"role": "user", "content": rerank_prompt}],
                    temperature=0.0,
                    max_tokens=64
                )
                import json
                content_str = rerank_res.choices[0].message.content
                match = re.search(r'\[[\d,\s]*\]', content_str)
                if match:
                    relevant_indices = json.loads(match.group(0))
                    filtered_papers = [papers[i] for i in relevant_indices if i < len(papers)]
                    if filtered_papers:
                        # Ensure anchor papers are preserved at the top
                        anchors = [p for p in papers if p.get("is_anchor")]
                        for a in anchors:
                            if a not in filtered_papers:
                                filtered_papers.insert(0, a)
                        papers = filtered_papers
                        logger.info(f"[{self.agent_id}] Reranked down to {len(papers)} high-precision papers.")
            except Exception as e:
                logger.warning(f"[{self.agent_id}] Reranking bypassed: {e}. Retaining raw paper list.")

        # Sort papers: Anchor papers first, then descending by citation velocity
        papers.sort(key=lambda x: (x.get("is_anchor", False), x.get("citation_velocity", 0)), reverse=True)

        # Step 5: Format and submit structured results
        await self._submit_results(papers, query, task_id)

    async def _fetch_openalex_async(self, search_query: str, limit: int = 12) -> List[Dict[str, Any]]:
        """Fetch papers from OpenAlex (250M+ open catalog)."""
        logger.info(f"[{self.agent_id}] Querying OpenAlex API...")
        clean_query = search_query.replace('"', '').replace(' AND ', ' ').replace(' OR ', ' ')
        url = "https://api.openalex.org/works"
        params = {"search": clean_query, "per_page": limit}
        headers = {"User-Agent": "SentinelARC/2.0 (mailto:sentinelarc@deepmind.edu)"}

        try:
            resp = await asyncio.to_thread(requests.get, url, params=params, headers=headers, timeout=12)
            if resp.status_code == 200:
                data = resp.json().get("results", [])
                papers = []
                for w in data:
                    title = w.get("title") or "Untitled Paper"
                    authorships = w.get("authorships", [])
                    authors = [{"name": a.get("author", {}).get("display_name", "Unknown")} for a in authorships]
                    year = w.get("publication_year") or "Unknown"
                    abstract = reconstruct_openalex_abstract(w.get("abstract_inverted_index"))
                    cites = w.get("cited_by_count", 0) or 0
                    
                    open_access = w.get("open_access", {})
                    oa_url = open_access.get("oa_url")
                    doi_url = w.get("doi")
                    primary_url = oa_url or doi_url or w.get("id") or ""

                    papers.append({
                        "paperId": w.get("id"),
                        "title": title,
                        "authors": authors,
                        "year": str(year),
                        "abstract": abstract if abstract else "Abstract available via open catalog link.",
                        "citationCount": cites,
                        "url": primary_url,
                        "doi": doi_url,
                        "openAccessPdf": {"url": oa_url} if oa_url else {},
                        "source": "OpenAlex"
                    })
                return papers
        except Exception as e:
            logger.warning(f"[{self.agent_id}] OpenAlex query failed: {e}")
        return []

    async def _fetch_semantic_scholar_async(self, search_query: str, limit: int = 12) -> List[Dict[str, Any]]:
        """Fetch papers from Semantic Scholar with exponential retry."""
        logger.info(f"[{self.agent_id}] Querying Semantic Scholar API...")
        url = "https://api.semanticscholar.org/graph/v1/paper/search"
        params = {"query": search_query, "limit": limit, "fields": "title,authors,year,abstract,venue,citationCount,openAccessPdf,url"}
        headers = {}
        api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY")
        if api_key:
            headers["x-api-key"] = api_key

        for attempt in range(2):
            try:
                resp = await asyncio.to_thread(requests.get, url, params=params, headers=headers, timeout=12)
                if resp.status_code == 200:
                    data = resp.json().get("data", [])
                    papers = []
                    for p in data:
                        p["source"] = "Semantic Scholar"
                        papers.append(p)
                    return papers
                elif resp.status_code == 429:
                    await asyncio.sleep(2 * (attempt + 1))
                else:
                    break
            except Exception:
                pass
        return []

    def _fetch_arxiv_sync(self, search_query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Fetch preprints from arXiv."""
        logger.info(f"[{self.agent_id}] Querying arXiv API...")
        try:
            safe_query = search_query.replace('"', '').replace(' AND ', ' ').replace(' OR ', ' ')
            params = {"search_query": "all:" + safe_query, "start": 0, "max_results": limit}
            response = requests.get("http://export.arxiv.org/api/query", params=params, timeout=12)
            if response.status_code == 200:
                ns = {'atom': 'http://www.w3.org/2005/Atom'}
                root = ET.fromstring(response.content)
                papers = []
                for entry in root.findall('atom:entry', ns):
                    t_el = entry.find('atom:title', ns)
                    a_el = entry.find('atom:summary', ns)
                    u_el = entry.find('atom:id', ns)
                    p_el = entry.find('atom:published', ns)
                    
                    pdf_link = ""
                    for link in entry.findall('atom:link', ns):
                        if link.attrib.get('title') == 'pdf':
                            pdf_link = link.attrib.get('href', '')
                            break

                    papers.append({
                        "title": t_el.text.strip().replace('\n', ' ') if t_el is not None else "Unknown Title",
                        "authors": [{"name": author.find('atom:name', ns).text} for author in entry.findall('atom:author', ns)],
                        "year": p_el.text[:4] if p_el is not None else "Unknown",
                        "abstract": a_el.text.strip().replace('\n', ' ') if a_el is not None else "No abstract",
                        "url": pdf_link or (u_el.text if u_el is not None else ""),
                        "openAccessPdf": {"url": pdf_link} if pdf_link else {},
                        "citationCount": 0,
                        "source": "arXiv"
                    })
                return papers
        except Exception as e:
            logger.warning(f"[{self.agent_id}] arXiv query failed: {e}")
        return []

    def _fetch_pubmed_sync(self, search_query: str, limit: int = 6) -> List[Dict[str, Any]]:
        """Fetch biomedical research from PubMed / NCBI."""
        logger.info(f"[{self.agent_id}] Querying PubMed API...")
        try:
            safe_query = search_query.replace('"', '').replace(' AND ', ' ').replace(' OR ', ' ')
            url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
            resp1 = requests.get(url, params={"db": "pubmed", "term": safe_query, "retmax": limit, "retmode": "json"}, timeout=10)
            if resp1.status_code == 200:
                id_list = resp1.json().get("esearchresult", {}).get("idlist", [])
                if not id_list:
                    return []
                
                resp2 = requests.get(
                    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi", 
                    params={"db": "pubmed", "id": ",".join(id_list), "retmode": "json"}, 
                    timeout=10
                )
                if resp2.status_code == 200:
                    results = resp2.json().get("result", {})
                    papers = []
                    for p_id in id_list:
                        p = results.get(p_id, {})
                        title = p.get("title", "Unknown Title")
                        papers.append({
                            "title": title,
                            "authors": [{"name": au.get("name", "Unknown")} for au in p.get("authors", [])],
                            "year": p.get("pubdate", "")[:4],
                            "abstract": f"Biomedical clinical abstract for: {title}",
                            "url": f"https://pubmed.ncbi.nlm.nih.gov/{p_id}/",
                            "citationCount": 0,
                            "source": "PubMed"
                        })
                    return papers
        except Exception as e:
            logger.warning(f"[{self.agent_id}] PubMed query failed: {e}")
        return []

    async def _fetch_crossref_doi_async(self, doi: str) -> Optional[Dict[str, Any]]:
        """Directly resolve DOI via Crossref API."""
        url = f"https://api.crossref.org/works/{doi}"
        headers = {"User-Agent": "SentinelARC/2.0 (mailto:sentinelarc@deepmind.edu)"}
        try:
            resp = await asyncio.to_thread(requests.get, url, headers=headers, timeout=10)
            if resp.status_code == 200:
                msg = resp.json().get("message", {})
                title = msg.get("title", ["Unknown Title"])[0]
                authors = [{"name": f"{a.get('given', '')} {a.get('family', '')}".strip()} for a in msg.get("author", [])]
                year = "Unknown"
                if "issued" in msg and "date-parts" in msg["issued"]:
                    year = str(msg["issued"]["date-parts"][0][0])
                cites = msg.get("is-referenced-by-count", 0)
                link = msg.get("URL", f"https://doi.org/{doi}")
                return {
                    "paperId": doi,
                    "title": title,
                    "authors": authors,
                    "year": year,
                    "abstract": f"DOI Verified article: {title}",
                    "citationCount": cites,
                    "url": link,
                    "is_anchor": cites >= 50,
                    "source": "Crossref"
                }
        except Exception as e:
            logger.warning(f"[{self.agent_id}] Crossref DOI lookup failed: {e}")
        return None

    async def _submit_results(self, papers: List[Dict[str, Any]], query: str, task_id: str):
        """Build structured results and send DATA_SUBMIT message to Orchestrator."""
        results = []
        content_parts = []

        for p in papers:
            title = p.get("title", "No title")
            authors_list = p.get("authors", [])
            authors = ", ".join([a.get("name", "Unknown") for a in authors_list]) if authors_list else "Unknown"
            year = p.get("year", "N/A")
            abstract = p.get("abstract", "")
            citations = p.get("citationCount", 0)
            velocity = p.get("citation_velocity", 0.0)
            is_anchor = p.get("is_anchor", False)
            source_engine = p.get("source", "Academic Catalog")
            
            open_pdf = p.get("openAccessPdf", {})
            pdf_url = open_pdf.get("url") if isinstance(open_pdf, dict) else None
            primary_url = pdf_url or p.get("url") or ""

            results.append({
                "paperId": p.get("paperId"),
                "title": title,
                "authors": authors,
                "year": year,
                "abstract": abstract,
                "citationCount": citations,
                "citation_velocity": velocity,
                "is_anchor": is_anchor,
                "url": primary_url,
                "pdf_url": pdf_url,
                "doi": p.get("doi"),
                "source": source_engine
            })

            anchor_badge = " [🏆 SEMINAL ANCHOR PAPER]" if is_anchor else ""
            content_parts.append(
                f"**Title**: {title}{anchor_badge}\n"
                f"**Authors**: {authors}\n"
                f"**Year**: {year} | **Citations**: {citations} (Velocity: {velocity}/yr) | **Source**: {source_engine}\n"
                f"**Abstract**: {abstract[:300]}...\n"
                f"**Link**: {primary_url}\n"
                f"---\n"
            )

        content = "\n".join(content_parts) if content_parts else "No academic papers found."
        logger.info(f"[{self.agent_id}] Submitting {len(results)} curated papers to Orchestrator (task: {task_id}).")

        data_message = self.create_message(
            receiver_id=self.orchestrator_id,
            msg_type=ACPMsgType.DATA_SUBMIT,
            payload=DataSubmitPayload(
                data_type="search_results",
                data={"query": query, "content": content, "results": results},
                source="multi_source_academic_engine",
                task_id=task_id
            ).model_dump()
        )
        await self.send_message(data_message)
        logger.info(f"[{self.agent_id}] ✅ Search successfully delivered to Orchestrator.")

import logging
import asyncio
import requests
import os
import ollama
from typing import Dict, List
from .async_base_agent import AsyncBaseAgent
from ..protocols.acp_schema import (
    ACPMessage, ACPMsgType, TaskAssignPayload, StatusUpdatePayload,
    DataSubmitPayload
)

logger = logging.getLogger(__name__)

class AsyncSearchAgent(AsyncBaseAgent):
    def __init__(self, agent_id: str, message_bus, mcp_servers: Dict[str, str]):
        super().__init__(agent_id, message_bus, mcp_servers)
        self.orchestrator_id = "orchestrator"
        logger.info(f"[{self.agent_id}] 🚀 Search Agent Initialized")

    async def handle_message(self, message: ACPMessage):
        try:
            if message.msg_type == ACPMsgType.TASK_ASSIGN:
                payload = TaskAssignPayload(**message.payload)
                if payload.task_type == "web_search":
                    await self._perform_semantic_scholar_search(payload.task_data)
        except Exception as e:
            logger.error(f"[{self.agent_id}] Error handling message: {e}", exc_info=True)

    async def _perform_semantic_scholar_search(self, task_data: Dict):
        query = task_data.get("query")
        task_id = task_data.get("task_id", "unknown")
        logger.info(f"[{self.agent_id}] 📡 Researching (Semantic Scholar): '{query}'")

        # Query expansion with Ollama
        logger.info(f"[{self.agent_id}] Expanding query with Ollama...")
        try:
            system_prompt = (
                "You are an expert academic research librarian. "
                "Your task is to take a user's research query and expand it into a high-quality search string for Semantic Scholar. "
                "CRITICAL: If the query contains 'RAG', it almost always refers to 'Retrieval-Augmented Generation' in Artificial Intelligence. "
                "CRITICAL: Do NOT expand or guess the meaning of other acronyms (like LOD or XR) unless you are absolutely certain. If unsure, limit expansions to the exact original letters to avoid false positives. "
                "Provide a search string using Boolean operators (AND, OR) and quotes for phrases. "
                "Limit your response to ONLY the search string. No explanations."
            )
            response = ollama.chat(
                model='llama3.1:8b',
                messages=[
                    {
                        'role': 'system',
                        'content': system_prompt
                    },
                    {
                        'role': 'user',
                        'content': query
                    }
                ],
                options={'temperature': 0.3}  # Low creativity for precision
            )
            expanded_query = response['message']['content'].strip()
            logger.info(f"[{self.agent_id}] Original query: {query}")
            logger.info(f"[{self.agent_id}] Expanded query: {expanded_query}")
        except Exception as e:
            logger.warning(f"[{self.agent_id}] Ollama expansion failed: {e}. Using original query.")
            expanded_query = query

        try:
            import xml.etree.ElementTree as ET

            async def fetch_semantic_scholar_async(search_query: str, limit: int = 10) -> list:
                logger.info(f"[{self.agent_id}] Attempting Semantic Scholar fetch")
                url = "https://api.semanticscholar.org/graph/v1/paper/search"
                params = {"query": search_query, "limit": limit, "fields": "title,authors,year,abstract,venue,citationCount,openAccessPdf,url"}
                headers = {}
                api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY")
                if api_key: headers["x-api-key"] = api_key
                
                for attempt in range(3):
                    try:
                        resp = await asyncio.to_thread(requests.get, url, params=params, headers=headers, timeout=15)
                        if resp.status_code == 200:
                            return resp.json().get("data", [])
                        elif resp.status_code == 429:
                            await asyncio.sleep((attempt + 1) * 3)
                        else:
                            break
                    except:
                        pass
                return []

            def fetch_arxiv_sync(search_query: str, limit: int = 10) -> list:
                logger.info(f"[{self.agent_id}] Attempting arXiv fetch")
                try:
                    safe_query = search_query.replace('"', '').replace(' AND ', ' ').replace(' OR ', ' ')
                    params = {"search_query": "all:" + safe_query, "start": 0, "max_results": limit}
                    response = requests.get("http://export.arxiv.org/api/query", params=params, timeout=15)
                    if response.status_code == 200:
                        ns = {'atom': 'http://www.w3.org/2005/Atom'}
                        root = ET.fromstring(response.content)
                        papers = []
                        for entry in root.findall('atom:entry', ns):
                            t_el = entry.find('atom:title', ns)
                            a_el = entry.find('atom:summary', ns)
                            u_el = entry.find('atom:id', ns)
                            p_el = entry.find('atom:published', ns)
                            
                            papers.append({
                                "title": t_el.text.strip().replace('\n', ' ') if t_el is not None else "Unknown Title",
                                "authors": [{"name": author.find('atom:name', ns).text} for author in entry.findall('atom:author', ns)],
                                "year": p_el.text[:4] if p_el is not None else "Unknown",
                                "abstract": a_el.text.strip().replace('\n', ' ') if a_el is not None else "No abstract",
                                "url": u_el.text if u_el is not None else "",
                                "citationCount": 0
                            })
                        return papers
                except Exception as e:
                    logger.error(f"[{self.agent_id}] arXiv fetch failed: {e}")
                return []

            def fetch_pubmed_sync(search_query: str, limit: int = 5) -> list:
                logger.info(f"[{self.agent_id}] Attempting PubMed fetch")
                try:
                    safe_query = search_query.replace('"', '').replace(' AND ', ' ').replace(' OR ', ' ')
                    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
                    resp1 = requests.get(url, params={"db": "pubmed", "term": safe_query, "retmax": limit, "retmode": "json"}, timeout=10)
                    if resp1.status_code == 200:
                        id_list = resp1.json().get("esearchresult", {}).get("idlist", [])
                        if not id_list: return []
                        
                        resp2 = requests.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi", 
                                             params={"db": "pubmed", "id": ",".join(id_list), "retmode": "json"}, timeout=10)
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
                                    "abstract": f"Abstract available at link. {title}",
                                    "url": f"https://pubmed.ncbi.nlm.nih.gov/{p_id}/",
                                    "citationCount": 0
                                })
                            return papers
                except Exception as e:
                    logger.error(f"[{self.agent_id}] PubMed fetch failed: {e}")
                return []

            # Execute parallel multi-source gathering
            logger.info(f"[{self.agent_id}] Executing Multi-Source Parallel Fetch...")
            semantic_task = fetch_semantic_scholar_async(expanded_query, limit=15)
            arxiv_task = asyncio.to_thread(fetch_arxiv_sync, expanded_query, limit=10)
            pubmed_task = asyncio.to_thread(fetch_pubmed_sync, expanded_query, limit=5)
            
            results_tuple = await asyncio.gather(semantic_task, arxiv_task, pubmed_task, return_exceptions=True)
            
            papers = []
            seen_titles = set()
            
            for result_list in results_tuple:
                if isinstance(result_list, list):
                    for paper in result_list:
                        raw_title = paper.get("title", "").strip().lower()
                        if raw_title and raw_title not in seen_titles:
                            seen_titles.add(raw_title)
                            papers.append(paper)
                            
            # --- PHASE 2: CROSS-ENCODER RERANKING ---
            if len(papers) > 0:
                logger.info(f"[{self.agent_id}] Reranking {len(papers)} papers using Llama 3.1...")
                try:
                    paper_snippets = ""
                    for i, p in enumerate(papers):
                        title = p.get('title', '')
                        abstract_text = str(p.get('abstract', ''))[:200]
                        paper_snippets += f"[{i}] {title}\n{abstract_text}\n\n"
                    
                    rerank_prompt = (
                        f"You are a strict academic reviewer evaluating papers for this query: '{query}'\n"
                        "Below is a list of papers with an index ID. Output ONLY a valid JSON array of integer IDs for papers "
                        "that are highly relevant. Exclude papers with mismatched acronyms or irrelevant domains.\n"
                        "Example output: [0, 3, 5]\n\n"
                        f"{paper_snippets}"
                    )
                    
                    rerank_response = await asyncio.to_thread(
                        ollama.chat,
                        model='llama3.1:8b',
                        messages=[{'role': 'user', 'content': rerank_prompt}],
                        options={'temperature': 0.1}
                    )
                    import json, re
                    content_str = rerank_response['message']['content']
                    match = re.search(r'\[[\d,\s]*\]', content_str)
                    if match:
                        relevant_indices = json.loads(match.group(0))
                        filtered_papers = [papers[i] for i in relevant_indices if i < len(papers)]
                        if filtered_papers:
                            papers = filtered_papers
                            logger.info(f"[{self.agent_id}] Reranking filtered papers down to {len(papers)} highly relevant matches.")
                        else:
                            logger.warning(f"[{self.agent_id}] Reranking returned 0 matches, ignoring filter.")
                except Exception as e:
                    logger.warning(f"[{self.agent_id}] Cross-Encoder Reranking failed: {e}. Passing raw papers.")

            # Structured results list for orchestrator/extraction pipeline
            results = []
            content = "No relevant academic papers found."  # Default - always defined

            # Build structured results + human-readable content if we have papers (after fallback)
            if papers:
                content_parts = []
                for paper in papers:
                    title = paper.get("title", "No title")
                    authors_list = paper.get("authors", [])
                    authors = ", ".join([a.get("name", "Unknown") for a in authors_list]) if authors_list else "Unknown"
                    year = paper.get("year", "N/A")
                    abstract_raw = paper.get("abstract")
                    abstract = (abstract_raw[:300] + "...") if abstract_raw and isinstance(abstract_raw, str) else "No abstract available"
                    citations = paper.get("citationCount", 0)
                    open_pdf = paper.get("openAccessPdf", {})
                    pdf_url = open_pdf.get("url") if isinstance(open_pdf, dict) else None
                    paper_url = paper.get("url")
                    primary_url = pdf_url or paper_url or ""

                    # Append to orchestrator-facing structured results list
                    results.append(
                        {
                            "paperId": paper.get("paperId"),
                            "title": title,
                            "year": year,
                            "venue": paper.get("venue"),
                            "citationCount": citations,
                            "abstract": abstract_raw,  # Include full abstract for fallback
                            # URL used by orchestrator for extraction tasks
                            "url": primary_url,
                            # Extra URLs kept for potential future use
                            "paper_url": paper_url,
                            "pdf_url": pdf_url,
                        }
                    )

                    # Append to human-readable summary content
                    content_parts.append(
                        f"**Title**: {title}\n"
                        f"**Authors**: {authors}\n"
                        f"**Year**: {year} | **Citations**: {citations}\n"
                        f"**Abstract**: {abstract}\n"
                        f"**PDF**: {pdf_url or 'No open PDF'}\n"
                        f"**Link**: {paper_url or 'No link'}\n"
                        f"---\n"
                    )

                content = "\n".join(content_parts)

            # Log preview of final content
            preview = content[:500] + "..." if len(content) > 500 else content
            logger.info(f"[{self.agent_id}] Final content preview (first 500 chars): {preview}")

            logger.info(f"[{self.agent_id}] Found {len(papers)} papers. Structured results: {len(results)}. Content length: {len(content)}")

            data_message = self.create_message(
                receiver_id=self.orchestrator_id,
                msg_type=ACPMsgType.DATA_SUBMIT,
                payload=DataSubmitPayload(
                    data_type="search_results",
                    data={"query": query, "content": content, "results": results},
                    source="semantic_scholar",
                    task_id=task_id
                ).model_dump()
            )
            await self.send_message(data_message)
            logger.info(f"[{self.agent_id}] ✅ Search successful (Semantic Scholar)")

        except Exception as e:
            logger.error(f"[{self.agent_id}] Semantic Scholar Error: {str(e)}", exc_info=True)

            # Graceful fallback to orchestrator
            fallback_content = f"Search failed due to error or rate limit.\nError: {str(e)}"
            data_message = self.create_message(
                receiver_id=self.orchestrator_id,
                msg_type=ACPMsgType.DATA_SUBMIT,
                payload=DataSubmitPayload(
                    data_type="search_results",
                    data={"query": query, "content": fallback_content},
                    source="semantic_scholar",
                    task_id=task_id
                ).model_dump()
            )
            await self.send_message(data_message)
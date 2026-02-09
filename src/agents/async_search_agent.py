import logging
import asyncio
import requests
import os
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

        try:
            url = "https://api.semanticscholar.org/graph/v1/paper/search"
            params = {
                "query": query,
                "limit": 10,
                "fields": "title,authors,year,abstract,venue,citationCount,openAccessPdf,url",
                "sort": "citationCount:desc"
            }

            logger.info(f"[{self.agent_id}] Calling Semantic Scholar API...")

            # Use API key if available in .env
            headers = {}
            api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY")
            if api_key:
                headers["x-api-key"] = api_key
                logger.info(f"[{self.agent_id}] Using Semantic Scholar API key")
            else:
                logger.info(f"[{self.agent_id}] No API key found - using unauthenticated mode (limited rate)")

            response = requests.get(url, params=params, headers=headers, timeout=15)

            if response.status_code == 429:
                logger.warning(f"[{self.agent_id}] Rate limit hit (429). Waiting 60s before retry...")
                await asyncio.sleep(60)
                response = requests.get(url, params=params, headers=headers, timeout=15)

            if response.status_code != 200:
                raise Exception(f"Semantic Scholar API error: {response.status_code} - {response.text}")

            data = response.json()
            papers = data.get("data", [])

            if not papers:
                logger.warning(f"[{self.agent_id}] No papers found for query")
                content = "No relevant academic papers found."
            else:
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
                    pdf_url = open_pdf.get("url", "No open PDF") if isinstance(open_pdf, dict) else "No open PDF"
                    paper_url = paper.get("url", "No link")

                    content_parts.append(
                        f"**Title**: {title}\n"
                        f"**Authors**: {authors}\n"
                        f"**Year**: {year} | **Citations**: {citations}\n"
                        f"**Abstract**: {abstract}\n"
                        f"**PDF**: {pdf_url}\n"
                        f"**Link**: {paper_url}\n"
                        f"---\n"
                    )

                content = "\n".join(content_parts)

            logger.info(f"[{self.agent_id}] Found {len(papers)} papers. Content length: {len(content)}")

            data_message = self.create_message(
                receiver_id=self.orchestrator_id,
                msg_type=ACPMsgType.DATA_SUBMIT,
                payload=DataSubmitPayload(
                    data_type="search_results",
                    data={"query": query, "content": content},
                    source="semantic_scholar",
                    task_id=task_id
                ).model_dump()
            )
            await self.send_message(data_message)
            logger.info(f"[{self.agent_id}] ✅ Search successful (Semantic Scholar)")

        except Exception as e:
            logger.error(f"[{self.agent_id}] Semantic Scholar Error: {str(e)}", exc_info=True)
            raise

"""
Async Synthesis Agent
Agent responsible for synthesizing research findings into coherent reports asynchronously.
Now uses Ollama for intelligent summarization and content generation.
"""

import logging
import asyncio
import ollama
from typing import Dict, List
from .async_base_agent import AsyncBaseAgent
from ..protocols.acp_schema import (
    ACPMessage, ACPMsgType, TaskAssignPayload, StatusUpdatePayload,
    DataSubmitPayload, LogBroadcastPayload
)

logger = logging.getLogger(__name__)

class AsyncSynthesisAgent(AsyncBaseAgent):
    """
    Asynchronous agent that synthesizes research findings into comprehensive reports.
    
    Features:
    - Ollama-powered generation of introduction, source analysis, and conclusions
    - Progress status updates to orchestrator
    - Structured Markdown report with metadata
    - Graceful error handling and fallback text
    """

    def __init__(self, agent_id: str, message_bus, mcp_servers: Dict[str, str]):
        """Initialize the async synthesis agent."""
        super().__init__(agent_id, message_bus, mcp_servers)
        self.orchestrator_id = "orchestrator"
        logger.info(f"[{self.agent_id}] Async Synthesis Agent initialized")

    async def handle_message(self, message: ACPMessage):
        """Handle incoming ACP messages."""
        try:
            if message.msg_type == ACPMsgType.TASK_ASSIGN:
                await self._handle_task_assignment(message)
            elif message.msg_type == ACPMsgType.DATA_SUBMIT:
                payload = DataSubmitPayload(**message.payload)
                if payload.data_type == "search_results":
                    await self._synthesize_research_report(payload.data, payload.task_id)
            else:
                logger.warning(f"[{self.agent_id}] Unhandled message type: {message.msg_type.value}")
        except Exception as e:
            logger.error(f"[{self.agent_id}] Error handling message: {e}")

    async def _handle_task_assignment(self, message: ACPMessage):
        """Handle synthesis task assignments (legacy support)."""
        try:
            payload = TaskAssignPayload(**message.payload)
            if payload.task_type == "synthesize_research":
                await self._synthesize_research_report(payload.task_data, payload.task_data.get("task_id"))
            else:
                logger.warning(f"[{self.agent_id}] Unknown task type: {payload.task_type}")
        except Exception as e:
            logger.error(f"[{self.agent_id}] Error in task assignment: {e}")
            await self._send_error_status(str(e))

    async def _synthesize_research_report(self, task_data: Dict, task_id: str = None):
        """Synthesize research findings into a comprehensive report using Ollama."""
        query = task_data.get("query", "unknown")
        search_results = task_data.get("search_results", [])
        extracted_content = task_data.get("extracted_content", [])
        task_id = task_id or task_data.get("task_id", "unknown")

        if not query:
            error_msg = "No research query provided for synthesis"
            logger.error(f"[{self.agent_id}] {error_msg}")
            await self._send_error_status(error_msg, task_id)
            return

        logger.info(f"[{self.agent_id}] Starting synthesis for: '{query}' (task: {task_id})")

        try:
            # Send initial status
            await self._send_status_update("synthesis_starting", 10.0, task_id)

            report_sections = []

            # 1. Introduction
            await self._send_status_update("creating_introduction", 20.0, task_id)
            intro = await self._create_introduction(query)
            report_sections.append(f"## Introduction\n\n{intro}")

            # 2. Source Analysis
            await self._send_status_update("analyzing_sources", 40.0, task_id)
            for i, content in enumerate(extracted_content):
                if content.get("extraction_successful", False):
                    section = await self._create_source_analysis(content, i + 1)
                    report_sections.append(section)

            # 3. Synthesis and Conclusions
            await self._send_status_update("creating_synthesis", 70.0, task_id)
            conclusion = await self._create_conclusion(query, extracted_content)
            report_sections.append(f"## Synthesis and Conclusions\n\n{conclusion}")

            # 4. Methodology and Metadata (keep static)
            await self._send_status_update("adding_metadata", 90.0, task_id)
            methodology = await self._create_methodology(search_results, extracted_content)
            metadata = await self._create_metadata(search_results, extracted_content)
            report_sections.append(f"## Research Methodology\n\n{methodology}")
            report_sections.append(f"## Research Metadata\n\n{metadata}")

            # Combine into final report
            full_report = f"# Research Report: {query}\n\n" + "\n\n".join(report_sections)

            logger.info(f"[{self.agent_id}] Synthesis completed: {len(full_report.split())} words")

            # Send completion status
            await self._send_status_update("synthesis_complete", 100.0, task_id)

            # Send report to orchestrator
            synthesis_data = {
                "report_content": full_report,
                "word_count": len(full_report.split()),
                "sections": len(report_sections),
                "sources_analyzed": len([c for c in extracted_content if c.get("extraction_successful", False)]),
                "query": query
            }

            data_message = self.create_message(
                receiver_id=self.orchestrator_id,
                msg_type=ACPMsgType.DATA_SUBMIT,
                payload=DataSubmitPayload(
                    data_type="synthesis_report",
                    data=synthesis_data,
                    source="ollama_synthesis",
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
                    message=f"Research report synthesized: {len(full_report.split())} words, {len(extracted_content)} sources",
                    component=self.agent_id
                ).model_dump()
            )
            await self.send_message(log_message)

        except Exception as e:
            error_msg = f"Synthesis failed: {e}"
            logger.error(f"[{self.agent_id}] {error_msg}")
            await self._send_error_status(error_msg, task_id)

    async def _create_introduction(self, query: str) -> str:
        """Generate intelligent introduction using Ollama."""
        try:
            response = ollama.chat(
                model='llama3.1:8b',
                messages=[
                    {
                        'role': 'system',
                        'content': (
                            "You are an academic writing assistant. "
                            "Write a concise, professional introduction (150–250 words) for a research report. "
                            "Include: the research question, why it matters, scope of the synthesis, and what the report covers. "
                            "Use formal tone, no fluff. Output only the introduction text."
                        )
                    },
                    {
                        'role': 'user',
                        'content': f"Research question: {query}"
                    }
                ],
                options={'temperature': 0.4}
            )
            intro = response['message']['content'].strip()
            logger.info(f"[{self.agent_id}] Introduction generated ({len(intro.split())} words)")
            return intro
        except Exception as e:
            logger.warning(f"[{self.agent_id}] Ollama intro failed: {e}")
            return f"This report investigates: '{query}'. It synthesizes findings from available academic sources to provide an overview of key developments and implications."

    async def _create_source_analysis(self, content_data: Dict, index: int) -> str:
        """Generate analysis for one source using Ollama."""
        url = content_data.get("url", "Unknown source")
        title = content_data.get("title", "Untitled")
        content = content_data.get("content", "")[:3000]  # truncate to avoid token limits

        try:
            response = ollama.chat(
                model='llama3.1:8b',
                messages=[
                    {
                        'role': 'system',
                        'content': (
                            "You are an academic analyst. "
                            "Summarize the provided source content in 3–5 bullet points. "
                            "Focus on key findings, methods, and relevance to the research question. "
                            "Use formal tone. Output only the bullet points."
                        )
                    },
                    {
                        'role': 'user',
                        'content': f"Source title: {title}\nURL: {url}\n\nContent:\n{content}"
                    }
                ],
                options={'temperature': 0.4}
            )
            analysis = response['message']['content'].strip()
            logger.info(f"[{self.agent_id}] Source {index} analysis generated ({len(analysis.split())} words)")
        except Exception as e:
            logger.warning(f"[{self.agent_id}] Ollama source analysis failed: {e}")
            analysis = "• Summary generation failed for this source.\n• Raw content is available in the full report."

        return f"## Source {index}: {title}\n\n[Link]({url})\n\n{analysis}"

    async def _create_conclusion(self, query: str, extracted_content: List[Dict]) -> str:
        """Generate synthesis and conclusions using Ollama."""
        successful = [c for c in extracted_content if c.get("extraction_successful", False)]
        content_snippets = "\n\n".join([c.get("content", "")[:1000] for c in successful[:3]])  # top 3 sources

        try:
            response = ollama.chat(
                model='llama3.1:8b',
                messages=[
                    {
                        'role': 'system',
                        'content': (
                            "You are an academic synthesizer. "
                            "Write concise conclusions (200–300 words) based on the provided sources. "
                            "Include: main findings, common themes, implications, and suggested future research. "
                            "Use formal tone. Output only the conclusions text."
                        )
                    },
                    {
                        'role': 'user',
                        'content': f"Research question: {query}\n\nKey source excerpts:\n{content_snippets}"
                    }
                ],
                options={'temperature': 0.4}
            )
            conclusion = response['message']['content'].strip()
            logger.info(f"[{self.agent_id}] Conclusion generated ({len(conclusion.split())} words)")
            return conclusion
        except Exception as e:
            logger.warning(f"[{self.agent_id}] Ollama conclusion failed: {e}")
            return f"Based on {len(successful)} sources, this report highlights key trends in '{query}'. Further research is recommended."

    # Keep these static sections unchanged
    async def _create_methodology(self, search_results: List[Dict], extracted_content: List[Dict]) -> str:
        return f"""**Research Methodology**:
This report was generated through:
1. Semantic Scholar search yielding {len(search_results)} results
2. Content extraction from {len([c for c in extracted_content if c.get("extraction_successful", False)])} sources
3. LLM-powered synthesis using Ollama (llama3.1:8b)
4. Structured formatting into Markdown report"""

    async def _create_metadata(self, search_results: List[Dict], extracted_content: List[Dict]) -> str:
        successful = [c for c in extracted_content if c.get("extraction_successful", False)]
        total_words = sum(len(c.get("content", "").split()) for c in successful)
        source_list = "\n".join([f"• [{c.get('title', 'Untitled')}]({c.get('url', '#')})" for c in successful])

        return f"""**Research Statistics**:
- Sources Analyzed: {len(successful)}
- Total Words Extracted: {total_words:,}
- Search Results: {len(search_results)}
**Sources**:
{source_list}
**Generation Date**: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')} IST"""

    async def _send_status_update(self, status: str, progress: float = None, task_id: str = None):
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
        logger.debug(f"[{self.agent_id}] Status update sent: {status}")

    async def _send_error_status(self, error_message: str, task_id: str = None):
        await self._send_status_update(f"synthesis_failed: {error_message}", 0.0, task_id)

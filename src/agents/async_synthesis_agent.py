"""
Async Synthesis Agent

Agent responsible for synthesizing research findings into coherent, citation-rich reports.
Highlights foundational seminal anchor papers and seamlessly falls back across Groq models.
"""

import logging
import asyncio
import os
from typing import Dict, List, Any, Optional
from groq import AsyncGroq
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
    - High-velocity anchor paper prioritization
    - Inline clickable citations [Paper Title](URL)
    - Groq-powered multi-model fallback (Qwen 2.5/3.8 -> GPT-OSS 20B)
    - Structured Markdown fallback ensuring zero stalled workflows
    """

    def __init__(self, agent_id: str, message_bus, mcp_servers: Dict[str, str]):
        super().__init__(agent_id, message_bus, mcp_servers)
        self.orchestrator_id = "orchestrator"
        
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            logger.warning(f"[{self.agent_id}] GROQ_API_KEY not found in environment!")
        self.groq_client = AsyncGroq(api_key=api_key)
        
        logger.info(f"[{self.agent_id}] Async Synthesis Agent initialized with Groq")

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
            logger.error(f"[{self.agent_id}] Error handling message: {e}", exc_info=True)

    async def _handle_task_assignment(self, message: ACPMessage):
        """Handle synthesis task assignments."""
        try:
            payload = TaskAssignPayload(**message.payload)
            if payload.task_type == "synthesize_research":
                await self._synthesize_research_report(payload.task_data, payload.task_data.get("task_id"))
            else:
                logger.warning(f"[{self.agent_id}] Unknown task type: {payload.task_type}")
        except Exception as e:
            logger.error(f"[{self.agent_id}] Error in task assignment: {e}", exc_info=True)
            await self._send_error_status(str(e))

    async def _synthesize_research_report(self, task_data: Dict[str, Any], task_id: str = None):
        """Synthesize research findings into a conversational summary using Groq."""
        query = task_data.get("query", "unknown")
        search_results = task_data.get("search_results", [])
        extracted_content = task_data.get("extracted_content", []) or task_data.get("sources", [])
        task_id = task_id or task_data.get("task_id", "unknown")

        if not query:
            error_msg = "No research query provided for synthesis"
            logger.error(f"[{self.agent_id}] {error_msg}")
            await self._send_error_status(error_msg, task_id)
            return

        logger.info(f"[{self.agent_id}] Starting synthesis for: '{query}' (task: {task_id})")

        try:
            await self._send_status_update("synthesis_starting", 10.0, task_id)

            # Build source context for the LLM
            await self._send_status_update("analyzing_sources", 30.0, task_id)
            
            # Combine extracted content with search metadata (for citation metrics)
            metadata_map = {p.get("url"): p for p in search_results if p.get("url")}
            
            context_blocks = []
            successful = [c for c in extracted_content if c.get("content") or c.get("abstract")]
            
            # If extracted_content was empty, fall back to search_results
            if not successful and search_results:
                successful = search_results

            for i, c in enumerate(successful):
                title = c.get("title", f"Document {i+1}")
                url = c.get("url", "#")
                meta = metadata_map.get(url, c)
                is_anchor = c.get("is_anchor") or meta.get("is_anchor", False)
                velocity = c.get("citation_velocity") or meta.get("citation_velocity", 0.0)
                citations = meta.get("citationCount", 0)
                year = meta.get("year", "N/A")
                source_name = c.get("source_description") or meta.get("source", "Academic Catalog")

                badge = " [🏆 SEMINAL ANCHOR PAPER]" if is_anchor else ""
                metrics_str = f"Year: {year} | Citations: {citations} (Velocity: {velocity}/yr) | Source: {source_name}"
                
                text = (c.get("content") or c.get("abstract") or "")[:2000]
                context_blocks.append(
                    f"Source {i+1}: {title}{badge}\n"
                    f"Metadata: {metrics_str}\n"
                    f"URL: {url}\n"
                    f"Summary/Excerpt: {text}\n"
                )

            context_str = "\n\n".join(context_blocks)

            system_prompt = (
                "You are SentinelARC, an elite academic research assistant and scientific intelligence synthesizer. "
                "Your objective is to provide a comprehensive, rigorous, and highly accessible synthesis directly answering the user's research query.\n\n"
                "KEY SYNTHESIS GUIDELINES:\n"
                "1. Structure: Begin with an executive overview, followed by the core technological/scientific mechanisms, comparative analysis of approaches, and emerging frontiers.\n"
                "2. FOUNDATIONAL WORKS: If any paper is marked with '[🏆 SEMINAL ANCHOR PAPER]', prominently highlight it as the foundational or high-velocity breakthrough that framed the research landscape before discussing derivative works.\n"
                "3. INLINE CITATIONS: You MUST embed clickable Markdown citations natively in your sentences, formatted as [Paper Title](URL). Do not list plain numbers or relegate citations solely to the end.\n"
                "4. Tone: Professional, authoritative, and direct (similar to advanced technical literature reviews)."
            )

            await self._send_status_update("creating_synthesis", 60.0, task_id)
            
            # Primary Groq model with fast fallback
            groq_model = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")
            full_report = ""

            try:
                response = await self.groq_client.chat.completions.create(
                    model=groq_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"Research Query: {query}\n\nScholarly Sources & Findings:\n{context_str}"}
                    ],
                    temperature=0.3,
                    max_tokens=3000
                )
                full_report = response.choices[0].message.content.strip()
            except Exception as llm_err:
                logger.warning(f"[{self.agent_id}] Primary model '{groq_model}' failed: {llm_err}. Trying secondary model 'openai/gpt-oss-20b'...")
                try:
                    response = await self.groq_client.chat.completions.create(
                        model="openai/gpt-oss-20b",
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": f"Research Query: {query}\n\nScholarly Sources & Findings:\n{context_str}"}
                        ],
                        temperature=0.3,
                        max_tokens=3000
                    )
                    full_report = response.choices[0].message.content.strip()
                except Exception as fallback_err:
                    logger.error(f"[{self.agent_id}] All LLMs failed ({fallback_err}). Compiling structured fallback report.")
                    report_lines = [
                        f"# Research Synthesis: {query}\n\n",
                        f"> ⚠️ **Notice:** Automated conversational synthesis fell back to structured index ({fallback_err}). Below are the verified sources and findings gathered across the multi-agent academic swarm.\n\n",
                        "## Verified Academic Sources\n\n"
                    ]
                    if successful:
                        for idx, src in enumerate(successful):
                            s_title = src.get("title", f"Source {idx+1}")
                            s_url = src.get("url", "#")
                            s_text = (src.get("content") or src.get("abstract") or "No text available.")[:700]
                            report_lines.append(f"### {idx+1}. [{s_title}]({s_url})\n\n{s_text}\n\n")
                    else:
                        report_lines.append("No extracted sources were available for synthesis.\n")
                    full_report = "".join(report_lines)

            logger.info(f"[{self.agent_id}] Synthesis complete: {len(full_report.split())} words generated.")
            await self._send_status_update("synthesis_complete", 100.0, task_id)

            # Send synthesis report to orchestrator
            synthesis_data = {
                "report_content": full_report,
                "word_count": len(full_report.split()),
                "sources_analyzed": len(successful),
                "query": query,
                "task_id": task_id
            }

            data_message = self.create_message(
                receiver_id=self.orchestrator_id,
                msg_type=ACPMsgType.DATA_SUBMIT,
                payload=DataSubmitPayload(
                    data_type="synthesis_report",
                    data=synthesis_data,
                    source="groq_synthesis",
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
                    message=f"Research synthesis completed: {len(full_report.split())} words across {len(successful)} sources.",
                    component=self.agent_id
                ).model_dump()
            )
            await self.send_message(log_message)

        except Exception as e:
            error_msg = f"Synthesis failed: {e}"
            logger.error(f"[{self.agent_id}] {error_msg}", exc_info=True)
            await self._send_error_status(error_msg, task_id)

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

    async def _send_error_status(self, error_message: str, task_id: str = None):
        await self._send_status_update(f"synthesis_failed: {error_message}", 0.0, task_id)

    def get_capabilities(self) -> Dict[str, str]:
        """Return agent capabilities."""
        return {
            "agent_type": "synthesis_agent",
            "primary_function": "report_synthesis",
            "supported_tasks": ["synthesize_research"],
            "features": "anchor_paper_emphasis, groq_multi_model, inline_markdown_citations",
            "async_capable": True
        }

"""
Async Synthesis Agent
Agent responsible for synthesizing research findings into coherent reports asynchronously.
Now uses Ollama for intelligent summarization and content generation.
"""

import logging
import asyncio
import os
from typing import Dict, List
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
    - Groq-powered generation of conversational responses
    - Progress status updates to orchestrator
    - Structured Markdown report with metadata
    - Graceful error handling and fallback text
    """

    def __init__(self, agent_id: str, message_bus, mcp_servers: Dict[str, str]):
        """Initialize the async synthesis agent."""
        super().__init__(agent_id, message_bus, mcp_servers)
        self.orchestrator_id = "orchestrator"
        
        # Initialize Groq client
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
        """Synthesize research findings into a conversational summary using Groq."""
        query = task_data.get("query", "unknown")
        search_results = task_data.get("search_results", [])
        extracted_content = task_data.get("extracted_content", [])
        task_id = task_id or task_data.get("task_id", "unknown")

        if not query:
            error_msg = "No research query provided for synthesis"
            logger.error(f"[{self.agent_id}] {error_msg}")
            await self._send_error_status(error_msg, task_id)
            return

        logger.info(f"[{self.agent_id}] Starting conversational synthesis for: '{query}' (task: {task_id})")

        try:
            # Send initial status
            await self._send_status_update("synthesis_starting", 10.0, task_id)

            # Build source context for the LLM
            await self._send_status_update("analyzing_sources", 30.0, task_id)
            context_blocks = []
            successful = [c for c in extracted_content if c.get("content")]
            for i, c in enumerate(successful):
                title = c.get("title", "Untitled")
                url = c.get("url", "#")
                # Truncate content to avoid token limits, but give enough for synthesis
                text = c.get("content", "")[:1500] 
                context_blocks.append(f"Source {i+1}: {title}\nURL: {url}\nContent: {text}")

            context_str = "\n\n".join(context_blocks)

            system_prompt = (
                "You are SentinelARC, an intelligent, conversational research assistant. "
                "Your goal is to directly answer the user's query using the provided source material. "
                "1. Analyze the user's intent: If they want a list of papers, provide a clear bulleted list. If they ask a direct question, provide a concise, direct answer. If they want a deep dive, provide a thorough conversational synthesis. "
                "2. Write in a conversational, accessible, and professional tone, exactly like ChatGPT. DO NOT output a rigid academic report with forced sections (no 'Introduction', 'Methodology', etc. unless requested). "
                "3. CRITICAL REQUIREMENT: Whenever you mention a paper, concept, or fact from the sources, you MUST include a clickable Markdown link inline. Format it as [Paper Title](URL). Do not list sources at the very end; embed them natively into your sentences as citations. "
                "4. If the sources do not contain the answer, politely state that the information was not found in the current search results, but provide whatever relevant context you can."
            )

            await self._send_status_update("creating_synthesis", 60.0, task_id)
            
            # Generate conversational response using Groq
            response = await self.groq_client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"User Query: {query}\n\nAvailable Sources:\n{context_str}"}
                ],
                temperature=0.4,
                max_tokens=2048
            )

            full_report = response.choices[0].message.content.strip()

            logger.info(f"[{self.agent_id}] Synthesis completed: {len(full_report.split())} words")

            # Send completion status
            await self._send_status_update("synthesis_complete", 100.0, task_id)

            # Send report to orchestrator
            synthesis_data = {
                "report_content": full_report,
                "word_count": len(full_report.split()),
                "sections": 1,
                "sources_analyzed": len(successful),
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
                    message=f"Conversational response synthesized: {len(full_report.split())} words, {len(successful)} sources",
                    component=self.agent_id
                ).model_dump()
            )
            await self.send_message(log_message)

        except Exception as e:
            error_msg = f"Synthesis failed: {e}"
            logger.error(f"[{self.agent_id}] {error_msg}")
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
        logger.debug(f"[{self.agent_id}] Status update sent: {status}")

    async def _send_error_status(self, error_message: str, task_id: str = None):
        await self._send_status_update(f"synthesis_failed: {error_message}", 0.0, task_id)

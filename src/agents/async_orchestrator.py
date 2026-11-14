"""
Async Orchestrator Agent

Central coordination authority that manages the research workflow asynchronously.
Stateless, high-throughput hub-and-spoke state machine keyed by task_id.
Delegates heavy extraction, fact-checking, synthesis, and file persistence
to specialized companion agents.
"""

import asyncio
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

from .async_base_agent import AsyncBaseAgent, generate_task_id
from ..protocols.acp_schema import (
    ACPMessage, ACPMsgType, TaskAssignPayload, 
    StatusUpdatePayload, DataSubmitPayload, LogBroadcastPayload
)

logger = logging.getLogger(__name__)


class AsyncOrchestratorAgent(AsyncBaseAgent):
    """
    Lean, high-level director for academic research workflows.
    
    Coordinates the pipeline:
      Search Agent (Multi-Source + Citations) 
         -> Extraction Agent (Batch + CORE OA Paywall Bypass) 
         -> Fact Checker Agent (Self-contained Claims + Crossref) 
         -> Synthesis Agent (Seminal Anchor Emphasis + Groq LLM) 
         -> File Save Agent (MCP Roots + SQLite Persistence)
    """
    
    def __init__(self, agent_id: str, message_bus, mcp_servers: Dict[str, str]):
        super().__init__(agent_id, message_bus, mcp_servers)
        
        # Multi-tenant workflow store keyed by task_id
        self.active_workflows: Dict[str, Dict[str, Any]] = {}
        self.agent_status: Dict[str, str] = {}
        
        logger.info(f"[{self.agent_id}] Async Orchestrator initialized (Lean Stateless State Machine)")

    def _latest_workflow(self) -> Dict[str, Any]:
        """Return the most recently created workflow, or an empty template."""
        if self.active_workflows:
            return list(self.active_workflows.values())[-1]
        return {
            "task_id": "",
            "user_id": 0,
            "query": "",
            "search_results": [],
            "extracted_content": [],
            "synthesis_report": {},
            "fact_check_results": {},
            "search_retries": 0,
            "start_time": None,
            "status": "idle"
        }

    # Backward-compatible properties for external inspection / UI callers
    @property
    def current_query(self) -> str:
        return self._latest_workflow().get("query", "")

    @property
    def current_task_id(self) -> str:
        return self._latest_workflow().get("task_id", "")

    @property
    def user_id(self) -> int:
        return self._latest_workflow().get("user_id", 0)

    @property
    def search_results(self) -> List:
        return self._latest_workflow().get("search_results", [])

    @property
    def extracted_content(self) -> List:
        return self._latest_workflow().get("extracted_content", [])

    @property
    def synthesis_report(self) -> Dict:
        return self._latest_workflow().get("synthesis_report", {})

    @property
    def fact_check_results(self) -> Dict:
        return self._latest_workflow().get("fact_check_results", {})

    @property
    def search_retries(self) -> int:
        return self._latest_workflow().get("search_retries", 0)

    @property
    def workflow_start_time(self) -> Optional[datetime]:
        return self._latest_workflow().get("start_time")

    def _get_or_create_workflow(self, task_id: Optional[str], default_query: str = "", default_user_id: int = 0) -> Dict[str, Any]:
        """Retrieve active workflow state by task_id with automatic initialization."""
        if task_id and task_id in self.active_workflows:
            return self.active_workflows[task_id]
        
        target_id = task_id or generate_task_id()
        workflow = {
            "task_id": target_id,
            "user_id": default_user_id,
            "query": default_query,
            "search_results": [],
            "extracted_content": [],
            "synthesis_report": {},
            "fact_check_results": {},
            "search_retries": 0,
            "start_time": datetime.now(),
            "status": "in_progress",
            "updated_at": datetime.now()
        }
        self.active_workflows[target_id] = workflow
        self._prune_old_workflows()
        return workflow

    def _prune_old_workflows(self, max_workflows: int = 500):
        """Prevent memory growth under high concurrency."""
        if len(self.active_workflows) > max_workflows:
            completed_keys = [k for k, v in self.active_workflows.items() if v.get("status") == "completed"]
            for k in completed_keys[:len(self.active_workflows) - max_workflows]:
                self.active_workflows.pop(k, None)

    async def handle_message(self, message: ACPMessage):
        """Handle incoming ACP messages asynchronously."""
        try:
            if message.msg_type == ACPMsgType.STATUS_UPDATE:
                await self._handle_status_update(message)
            elif message.msg_type == ACPMsgType.DATA_SUBMIT:
                await self._handle_data_submission(message)
            else:
                logger.warning(f"[{self.agent_id}] Unhandled message type: {message.msg_type.value}")
        except Exception as e:
            logger.error(f"[{self.agent_id}] Error handling message: {e}", exc_info=True)
    
    async def start_research(self, query: str, user_id: int, task_id: Optional[str] = None):
        """
        Initiate an academic research workflow.
        """
        if not task_id or task_id == "default_task":
            task_id = generate_task_id()

        logger.info(f"[{self.agent_id}] 🚀 Starting Research Pipeline (Task: {task_id}, User: {user_id}): '{query}'")
        
        workflow = {
            "task_id": task_id,
            "user_id": user_id,
            "query": query,
            "search_results": [],
            "extracted_content": [],
            "synthesis_report": {},
            "fact_check_results": {},
            "search_retries": 0,
            "start_time": datetime.now(),
            "status": "in_progress",
            "updated_at": datetime.now()
        }
        self.active_workflows[task_id] = workflow
        self._prune_old_workflows()
        
        await self._broadcast_log("INFO", f"Research workflow initiated (Task: {task_id}): '{query}'")
        
        # Step 1: Dispatch multi-source search to Search Agent
        await self._assign_search_task(query, user_id, task_id)
    
    async def _assign_search_task(self, query: str, user_id: int, task_id: str, strategy: str = "standard"):
        """Assign academic search task to SearchAgent."""
        task_data = {
            "query": query,
            "task_id": task_id,
            "user_id": user_id,
            "strategy": strategy,
            "max_results": 10
        }
        
        search_message = self.create_message(
            receiver_id="search_agent",
            msg_type=ACPMsgType.TASK_ASSIGN,
            payload=TaskAssignPayload(
                task_type="web_search",
                task_data=task_data,
                priority=1
            ).model_dump()
        )
        await self.send_message(search_message)
        logger.info(f"[{self.agent_id}] Dispatched search task (Task: {task_id}) for: '{query}'")
    
    async def _handle_status_update(self, message: ACPMessage):
        """Process status updates from worker agents."""
        payload = StatusUpdatePayload(**message.payload)
        sender_id = message.sender_id
        task_id = payload.task_id
        
        self.agent_status[sender_id] = payload.status
        logger.info(f"[{self.agent_id}] Status from {sender_id} (Task: {task_id}): {payload.status}")
        
        if "failed" in payload.status.lower():
            await self._handle_agent_failure(sender_id, payload.status, task_id)
    
    async def _handle_data_submission(self, message: ACPMessage):
        """Route worker data submissions based on task_id and data_type."""
        payload = DataSubmitPayload(**message.payload)
        sender_id = message.sender_id
        task_id = payload.task_id or (payload.data.get("task_id") if isinstance(payload.data, dict) else None)
        
        logger.info(f"[{self.agent_id}] Received '{payload.data_type}' from {sender_id} (Task: {task_id})")
        
        if payload.data_type == "search_results":
            await self._handle_search_results(payload, sender_id, task_id)
        elif payload.data_type in ["extracted_content_batch", "extracted_content"]:
            await self._handle_extracted_batch(payload, sender_id, task_id)
        elif payload.data_type == "fact_check_results":
            await self._handle_fact_check_results(payload, sender_id, task_id)
        elif payload.data_type == "synthesis_report":
            await self._handle_synthesis_report(payload, sender_id, task_id)
        elif payload.data_type == "file_save_result":
            await self._handle_file_save_result(payload, sender_id, task_id)
        else:
            logger.warning(f"[{self.agent_id}] Unhandled data type: {payload.data_type}")
    
    async def _handle_search_results(self, payload: DataSubmitPayload, sender_id: str, task_id: Optional[str]):
        """Forward search candidates directly to Extraction Agent in a single batch."""
        workflow = self._get_or_create_workflow(task_id)
        search_data = payload.data
        results = search_data.get("results", [])
        
        workflow["search_results"] = results
        workflow["updated_at"] = datetime.now()
        
        logger.info(f"[{self.agent_id}] Task {workflow['task_id']}: Acquired {len(results)} candidate papers from Search Authority.")
        
        if not results:
            logger.warning(f"[{self.agent_id}] Task {workflow['task_id']}: No papers found; proceeding directly to synthesis.")
            await self._assign_synthesis_task(workflow["task_id"])
            return

        # Delegate batch extraction to ExtractionAgent (bypassing slow individual round-trips)
        batch_task_data = {
            "items": results[:8],
            "task_id": workflow["task_id"],
            "query": workflow["query"]
        }
        
        extraction_msg = self.create_message(
            receiver_id="extraction_agent",
            msg_type=ACPMsgType.TASK_ASSIGN,
            payload=TaskAssignPayload(
                task_type="batch_extract",
                task_data=batch_task_data,
                priority=1
            ).model_dump()
        )
        await self.send_message(extraction_msg)
        logger.info(f"[{self.agent_id}] Delegated batch extraction for {len(batch_task_data['items'])} papers to ExtractionAgent.")

    async def _handle_extracted_batch(self, payload: DataSubmitPayload, sender_id: str, task_id: Optional[str]):
        """Forward extracted documents directly to Fact Checker Agent."""
        workflow = self._get_or_create_workflow(task_id)
        data = payload.data
        
        if payload.data_type == "extracted_content_batch":
            extracted_items = data.get("items", [])
        else:
            extracted_items = [data]
            
        workflow["extracted_content"] = extracted_items
        workflow["updated_at"] = datetime.now()
        
        logger.info(f"[{self.agent_id}] Task {workflow['task_id']}: Extraction complete ({len(extracted_items)} sources). Forwarding to FactChecker...")
        
        # Dispatch fact checking
        fact_check_msg = self.create_message(
            receiver_id="fact_checker_agent",
            msg_type=ACPMsgType.TASK_ASSIGN,
            payload=TaskAssignPayload(
                task_type="fact_check",
                task_data={
                    "sources": extracted_items,
                    "task_id": workflow["task_id"],
                    "query": workflow["query"]
                },
                priority=1
            ).model_dump()
        )
        await self.send_message(fact_check_msg)

    async def _handle_fact_check_results(self, payload: DataSubmitPayload, sender_id: str, task_id: Optional[str]):
        """Evaluate validation confidence and dispatch report synthesis."""
        workflow = self._get_or_create_workflow(task_id)
        results_data = payload.data
        summary = results_data.get("summary", {})
        overall_confidence = summary.get("overall_confidence", 0.85)
        workflow["fact_check_results"] = results_data
        
        logger.info(f"[{self.agent_id}] Task {workflow['task_id']}: Fact check confidence score: {overall_confidence:.2f}")

        # If confidence is critically low and we haven't retried yet, query Search Authority with broadened perspective
        if overall_confidence < 0.65 and workflow.get("search_retries", 0) < 1:
            workflow["search_retries"] += 1
            logger.warning(f"[{self.agent_id}] Low confidence ({overall_confidence:.2f}). Triggering search broadening retry.")
            await self._broadcast_log("WARNING", f"Low confidence ({overall_confidence:.2f}). Expanding search perspective...")
            await self._assign_search_task(
                f"{workflow['query']} empirical validation", 
                workflow["user_id"], 
                workflow["task_id"],
                strategy="broaden_perspectives"
            )
            return

        # Proceed directly to conversational synthesis
        logger.info(f"[{self.agent_id}] Task {workflow['task_id']}: Validation passed. Dispatching synthesis task...")
        await self._assign_synthesis_task(workflow["task_id"])

    async def _assign_synthesis_task(self, task_id: str):
        """Dispatch synthesis task to SynthesisAgent."""
        workflow = self._get_or_create_workflow(task_id)
        task_data = {
            "query": workflow["query"],
            "search_results": workflow["search_results"],
            "extracted_content": workflow["extracted_content"],
            "fact_check_results": workflow.get("fact_check_results", {}),
            "task_id": task_id
        }
        
        synthesis_message = self.create_message(
            receiver_id="synthesis_agent",
            msg_type=ACPMsgType.TASK_ASSIGN,
            payload=TaskAssignPayload(
                task_type="synthesize_research",
                task_data=task_data,
                priority=1
            ).model_dump()
        )
        await self.send_message(synthesis_message)

    async def _handle_synthesis_report(self, payload: DataSubmitPayload, sender_id: str, task_id: Optional[str]):
        """Forward completed synthesis report to File Save Agent."""
        workflow = self._get_or_create_workflow(task_id)
        report_data = payload.data
        workflow["synthesis_report"] = report_data
        workflow["updated_at"] = datetime.now()
        
        word_count = report_data.get("word_count", 0)
        logger.info(f"[{self.agent_id}] Task {workflow['task_id']}: Synthesis received ({word_count} words). Dispatching file save...")
        
        # FileSaveAgent autonomously handles timestamping, directory creation, and DB registration
        save_msg = self.create_message(
            receiver_id="file_save_agent",
            msg_type=ACPMsgType.TASK_ASSIGN,
            payload=TaskAssignPayload(
                task_type="save_file",
                task_data={
                    "content": report_data.get("report_content", ""),
                    "query": workflow["query"],
                    "user_id": workflow["user_id"],
                    "task_id": task_id
                },
                priority=1
            ).model_dump()
        )
        await self.send_message(save_msg)

    async def _handle_file_save_result(self, payload: DataSubmitPayload, sender_id: str, task_id: Optional[str]):
        """Finalize workflow upon report persistence."""
        workflow = self._get_or_create_workflow(task_id)
        saved_path = payload.data.get("file_path", "unknown")
        logger.info(f"[{self.agent_id}] 🎉 Task {workflow['task_id']}: Report persisted at {saved_path}")
        await self._broadcast_workflow_completion(workflow["task_id"])

    async def _handle_agent_failure(self, agent_id: str, error_status: str, task_id: Optional[str] = None):
        """Handle agent failures gracefully to ensure workflows never hang."""
        workflow = self._get_or_create_workflow(task_id)
        logger.warning(f"[{self.agent_id}] Failure notification: {agent_id} on task {workflow['task_id']} ({error_status})")
        
        # If synthesis failed, compile immediate fallback so UI flag is always cleared
        if "synthesis" in agent_id or "synthesis_failed" in error_status:
            logger.info(f"[{self.agent_id}] Generating fallback report for task {workflow['task_id']}")
            sources = workflow.get("extracted_content", [])
            lines = [
                f"# Research Report: {workflow.get('query', 'Academic Query')}\n\n",
                f"> ⚠️ **Notice:** Synthesis encountered an error ({error_status}). Displaying collected verified papers:\n\n"
            ]
            for i, s in enumerate(sources):
                lines.append(f"### {i+1}. [{s.get('title', 'Paper')}]({s.get('url', '#')})\n\n{(s.get('content') or s.get('abstract') or '')[:500]}\n\n")
            
            fallback_text = "".join(lines)
            workflow["synthesis_report"] = {"report_content": fallback_text, "word_count": len(fallback_text.split())}
            
            save_msg = self.create_message(
                receiver_id="file_save_agent",
                msg_type=ACPMsgType.TASK_ASSIGN,
                payload=TaskAssignPayload(
                    task_type="save_file",
                    task_data={
                        "content": fallback_text,
                        "query": workflow["query"],
                        "user_id": workflow["user_id"],
                        "task_id": workflow["task_id"]
                    },
                    priority=1
                ).model_dump()
            )
            await self.send_message(save_msg)

    async def _broadcast_log(self, level: str, message: str):
        """Broadcast log message to all subscribers."""
        log_message = self.create_message(
            topic="logs",
            msg_type=ACPMsgType.LOG_BROADCAST,
            payload=LogBroadcastPayload(
                level=level,
                message=message,
                component=self.agent_id
            ).model_dump()
        )
        await self.send_message(log_message)

    async def _broadcast_workflow_completion(self, task_id: str):
        """Broadcast workflow completion status and mark workflow finished."""
        workflow = self._get_or_create_workflow(task_id)
        workflow["status"] = "completed"
        workflow["updated_at"] = datetime.now()
        
        start_time = workflow.get("start_time")
        duration_str = str(datetime.now() - start_time).split('.')[0] if start_time else "unknown"
        
        completion_message = (
            f"Research workflow completed! "
            f"Task: {task_id} | "
            f"Query: '{workflow['query']}' | "
            f"Duration: {duration_str} | "
            f"Sources: {len(workflow['extracted_content'])} | "
            f"Report words: {workflow['synthesis_report'].get('word_count', 0)}"
        )
        await self._broadcast_log("INFO", completion_message)
        logger.info(f"[{self.agent_id}] 🏁 {completion_message}")

    def get_workflow_status(self, task_id: Optional[str] = None) -> Dict[str, Any]:
        """Get current workflow status and metrics."""
        workflow = self._get_or_create_workflow(task_id)
        start_time = workflow.get("start_time")
        return {
            "agent_id": self.agent_id,
            "task_id": workflow.get("task_id", ""),
            "current_query": workflow.get("query", ""),
            "user_id": workflow.get("user_id", 0),
            "workflow_start_time": start_time.isoformat() if start_time else None,
            "search_results_count": len(workflow.get("search_results", [])),
            "extracted_content_count": len(workflow.get("extracted_content", [])),
            "synthesis_complete": bool(workflow.get("synthesis_report")),
            "active_workflows_count": len(self.active_workflows),
            "agent_status": self.agent_status.copy(),
            "running": self.running
        }

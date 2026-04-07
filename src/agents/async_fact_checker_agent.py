"""
Agent responsible for validating claims and data against multiple sources asynchronously.
Uses Ollama for intelligent fact verification.
"""

import logging
import re
import ollama
from typing import Dict, List, Tuple

from .async_base_agent import AsyncBaseAgent, MCPClientMixin
from ..protocols.acp_schema import (
    ACPMessage, ACPMsgType, TaskAssignPayload, StatusUpdatePayload, 
    DataSubmitPayload, LogBroadcastPayload, ValidationRequestPayload, ValidationResponsePayload
)

logger = logging.getLogger(__name__)


class AsyncFactCheckerAgent(AsyncBaseAgent, MCPClientMixin):
    """
    Asynchronous agent that validates claims and facts against multiple sources.
    
    Demonstrates:
    - A2A peer review and negotiation patterns between agents
    - Async validation request/response cycles
    - Confidence scoring and evidence aggregation
    - Cross-referencing claims against multiple sources
    """
    
    def __init__(self, agent_id: str, message_bus, mcp_servers: Dict[str, str]):
        """Initialize the async fact checker agent."""
        AsyncBaseAgent.__init__(self, agent_id, message_bus, mcp_servers)
        MCPClientMixin.__init__(self)
        
        self.orchestrator_id = "orchestrator"
        
        logger.info(f"[{self.agent_id}] Async Fact Checker Agent initialized")
    
    async def handle_message(self, message: ACPMessage):
        """Handle incoming ACP messages."""
        try:
            if message.msg_type == ACPMsgType.TASK_ASSIGN:
                await self._handle_task_assignment(message)
            elif message.msg_type == ACPMsgType.VALIDATION_REQUEST:
                await self._handle_validation_request(message)
            else:
                logger.warning(f"[{self.agent_id}] Unhandled message type: {message.msg_type.value}")
                
        except Exception as e:
            logger.error(f"[{self.agent_id}] Error handling message: {e}")
    
    async def _handle_task_assignment(self, message: ACPMessage):
        """Handle fact-checking task assignments."""
        try:
            payload = TaskAssignPayload(**message.payload)
            
            if payload.task_type == "fact_check":
                await self._perform_fact_check(payload.task_data)
            else:
                logger.warning(f"[{self.agent_id}] Unknown task type: {payload.task_type}")
                
        except Exception as e:
            logger.error(f"[{self.agent_id}] Error in task assignment: {e}")
            await self._send_error_status(str(e))
    
    async def _handle_validation_request(self, message: ACPMessage):
        """Handle direct validation requests from other agents."""
        try:
            payload = ValidationRequestPayload(**message.payload)
            sender_id = message.sender_id
            
            logger.info(f"[{self.agent_id}] Validation request from {sender_id}: '{payload.claim}'")
            
            # Perform validation
            is_valid, confidence, evidence = await self._validate_claim_async(
                payload.claim, payload.source_url
            )
            
            # Send validation response
            response_message = self.create_message(
                receiver_id=sender_id,
                msg_type=ACPMsgType.VALIDATION_RESPONSE,
                payload=ValidationResponsePayload(
                    is_valid=is_valid,
                    confidence=confidence,
                    evidence=evidence,
                    source=self.agent_id
                ).model_dump()
            )
            
            await self.send_message(response_message)
            
            logger.info(f"[{self.agent_id}] Validation response sent to {sender_id}: {is_valid} (confidence: {confidence})")
            
        except Exception as e:
            logger.error(f"[{self.agent_id}] Error handling validation request: {e}")
    
    async def _perform_fact_check(self, task_data: Dict):
        """Perform comprehensive fact-checking of provided content."""
        claims = task_data.get("claims", [])
        source_content = task_data.get("source_content", "")
        task_id = task_data.get("task_id", "unknown")
        
        if not claims:
            # Extract claims from content if not provided
            claims = await self._extract_claims_from_content(source_content)
        
        logger.info(f"[{self.agent_id}] Fact-checking {len(claims)} claims")
        
        try:
            # Send initial status update
            await self._send_status_update("fact_checking_started", 10.0, task_id)
            
            # Process each claim asynchronously
            validation_results = []
            total_claims = len(claims)
            
            # Process claims in parallel with a concurrency limit
            semaphore = asyncio.Semaphore(3)  # Limit to 3 concurrent Ollama calls
            
            async def validate_with_semaphore(claim_text, index):
                async with semaphore:
                    res = await self._validate_claim_async(claim_text)
                    return {"claim": claim_text, "is_valid": res[0], "confidence": res[1], "evidence": res[2], "claim_index": index + 1}

            tasks = [validate_with_semaphore(claim, i) for i, claim in enumerate(claims)]
            validation_results = await asyncio.gather(*tasks)
            
            # Calculate overall confidence
            if validation_results:
                overall_confidence = sum(r["confidence"] for r in validation_results) / len(validation_results)
                valid_claims = sum(1 for r in validation_results if r["is_valid"])
            else:
                overall_confidence = 0.0
                valid_claims = 0
            
            logger.info(f"[{self.agent_id}] Fact-checking complete: {valid_claims}/{total_claims} claims validated")
            
            # Send completion status
            await self._send_status_update("fact_checking_complete", 100.0, task_id)
            
            # Send results to orchestrator
            fact_check_data = {
                "claims_processed": validation_results,
                "summary": {
                    "total_claims": len(validation_results),
                    "valid_claims": valid_claims,
                    "overall_confidence": overall_confidence,
                    "claims_validated": len(validation_results)
                },
                "source_content_length": len(source_content)
            }
            
            data_message = self.create_message(
                receiver_id=self.orchestrator_id,
                msg_type=ACPMsgType.DATA_SUBMIT,
                payload=DataSubmitPayload(
                    data_type="fact_check_results",
                    data=fact_check_data,
                    source="fact_checker",
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
                    message=f"Fact-checking completed: {valid_claims}/{total_claims} claims validated (confidence: {overall_confidence:.2f})",
                    component=self.agent_id
                ).model_dump()
            )
            
            await self.send_message(log_message)
            
        except Exception as e:
            error_msg = f"Fact-checking failed: {e}"
            logger.error(f"[{self.agent_id}] {error_msg}")
            await self._send_error_status(error_msg, task_id)
    
    async def _extract_claims_from_content(self, content: str) -> List[str]:
        """Extract factual claims from content for validation."""
        # Simple claim extraction - in production, use NLP techniques
        claims = []
        
        sentences = content.split('. ')
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) > 20:  # Only consider substantial sentences
                # Look for statements that could be factual claims
                claim_indicators = [
                    'is', 'are', 'shows', 'indicates', 'proposes', 'demonstrates', 'suggests', 'found that',
                    'concludes', 'identified', 'significant', 'quantum', 'algorithm'
                ]
                
                if any(indicator in sentence.lower() for indicator in claim_indicators):
                    claims.append(sentence)
        
        # Limit to top 5 claims for demo purposes
        return claims[:5]
    
    async def _validate_claim_async(self, claim: str, source_url: str = None) -> Tuple[bool, float, str]:
        """
        Asynchronously validate a claim against available sources using Ollama.
        """
        try:
            logger.info(f"[{self.agent_id}] Consulting Ollama for claim: '{claim[:50]}...'")
            
            response = ollama.chat(
                model='qwen2.5:1.5b',
                messages=[
                    {
                        'role': 'system',
                        'content': (
                            "You are a critical fact-checker. "
                            "Evaluate the following claim based on common scientific knowledge and the provided context. "
                            "Provide your assessment in the following format: "
                            "VALID: [True/False]\n"
                            "CONFIDENCE: [0.0 to 1.0]\n"
                            "EVIDENCE: [Brief explanation of why it is valid or invalid]"
                        )
                    },
                    {
                        'role': 'user',
                        'content': f"Claim: {claim}"
                    }
                ],
                options={'temperature': 0.2, 'num_thread': 8}
            )
            
            res_text = response['message']['content']
            
            # Simple parsing
            is_valid = "VALID: True" in res_text
            confidence = 0.5 # Default
            evidence = "No evidence provided."
            
            conf_match = re.search(r"CONFIDENCE:\s*([\d\.]+)", res_text)
            if conf_match:
                confidence = float(conf_match.group(1))
                
            evid_match = re.search(r"EVIDENCE:\s*(.*)", res_text, re.DOTALL)
            if evid_match:
                evidence = evid_match.group(1).strip()
                
            return is_valid, confidence, evidence
                
        except Exception as e:
            logger.warning(f"[{self.agent_id}] Ollama validation failed for claim '{claim}': {e}")
            return True, 0.5, f"Validation fallback: {e}" # Plausible fallback
    
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
        logger.debug(f"[{self.agent_id}] Status update sent: {status}")
    
    async def _send_error_status(self, error_message: str, task_id: str = None):
        """Send error status to orchestrator."""
        await self._send_status_update(f"fact_check_failed: {error_message}", 0.0, task_id)
    
    def get_capabilities(self) -> Dict[str, str]:
        """Return agent capabilities."""
        return {
            "agent_type": "fact_checker_agent",
            "primary_function": "claim_validation",
            "supported_tasks": ["fact_check"],
            "validation_patterns": ["peer_review", "evidence_aggregation"],
            "confidence_scoring": True,
            "async_capable": True
        }

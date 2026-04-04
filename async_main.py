#!/usr/bin/env python3
"""
Async Main Application - FastAPI Service Edition
"""

import asyncio
import os
import sys
import logging

from typing import Dict, List
from dotenv import load_dotenv
from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.message_bus.rabbitmq_bus import RabbitMQBus
from src.agents.async_orchestrator import AsyncOrchestratorAgent
from src.agents.async_search_agent import AsyncSearchAgent
from src.agents.async_extraction_agent import AsyncExtractionAgent
from src.agents.async_fact_checker_agent import AsyncFactCheckerAgent
from src.agents.async_synthesis_agent import AsyncSynthesisAgent
from src.agents.async_file_save_agent import AsyncFileSaveAgent
from src.agents.async_logger_agent import AsyncLoggerAgent

# Initialize FastAPI
app = FastAPI(title="Project Synapse API")

# Global state for agents
state = {
    "message_bus": None,
    "agents": [],
    "orchestrator": None,
    "initialized": False
}

class ResearchRequest(BaseModel):
    query: str
    user_id: int
    task_id: str = "default_task"

class GeneralChatRequest(BaseModel):
    query: str
    model: str
    history: List[Dict[str, str]]
    user_id: int

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

async def initialize_system():
    """Starts RabbitMQ and initializes all agents once."""
    if state["initialized"]:
        return

    load_dotenv()
    rabbitmq_url = os.getenv("RABBITMQ_URL", "amqp://synapse:synapse123@rabbitmq:5672/")
    mcp_servers = {
        "primary_tooling": os.getenv("PRIMARY_TOOLING_URL", "http://primary-tooling-server:8001"),
        "filesystem": os.getenv("FILESYSTEM_URL", "http://filesystem-server:8002"),
    }

    try:
        logger.info("📡 Connecting to RabbitMQ...")
        state["message_bus"] = RabbitMQBus(rabbitmq_url)
        if not await state["message_bus"].connect():
            raise Exception("RabbitMQ connection failed")

        logger.info("🤖 Initializing Multi-Agent Swarm...")
        
        state["agents"] = [
            AsyncOrchestratorAgent("orchestrator", state["message_bus"], mcp_servers),
            AsyncSearchAgent("search_agent", state["message_bus"], mcp_servers),
            AsyncExtractionAgent("extraction_agent", state["message_bus"], mcp_servers),
            AsyncFactCheckerAgent("fact_checker_agent", state["message_bus"], mcp_servers),
            AsyncSynthesisAgent("synthesis_agent", state["message_bus"], mcp_servers),
            AsyncFileSaveAgent("file_save_agent", state["message_bus"], mcp_servers),
            AsyncLoggerAgent("logger_agent", state["message_bus"], mcp_servers)
        ]

        # Start all agents
        await asyncio.gather(*[agent.start() for agent in state["agents"]])
        state["orchestrator"] = state["agents"][0]
        state["initialized"] = True
        logger.info("✅ System Ready and Listening on Port 8000")
    except Exception as e:
        logger.error(f"Failed to initialize system: {e}")

@app.on_event("startup")
async def startup_event():
    # Start initialization in the background
    asyncio.create_task(initialize_system())
    
    import subprocess
    subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    await asyncio.sleep(5)  # Wait for server to be ready
    logger.info("Ollama server started in background")
    

@app.get("/health")
async def health():
    return {
        "status": "healthy" if state["initialized"] else "initializing",
        "agents_active": len(state["agents"]),
        "orchestrator_ready": state["orchestrator"] is not None
    }

@app.post("/research")
async def start_research(request: ResearchRequest, background_tasks: BackgroundTasks):
    if not state["orchestrator"]:
        raise HTTPException(status_code=503, detail="System initializing, please wait...")
    
    logger.info(f"📥 Received Research Request: {request.query} from User {request.user_id}")
    background_tasks.add_task(state["orchestrator"].start_research, request.query, request.user_id)
    
    return {
        "status": "task_received",
        "task_id": request.task_id,
        "query": request.query
    }

@app.post("/general_chat")
async def general_chat(request: GeneralChatRequest):
    from fastapi.responses import StreamingResponse
    import json
    from ollama import AsyncClient
    
    messages = []
    for item in request.history:
        role = item.get("type", "user")
        if role == "report": continue
        if role == "assistant": role = "assistant"
        messages.append({"role": role, "content": item.get("content", "")})
    
    messages.append({"role": "user", "content": request.query})
    
    async def generate_response():
        try:
            logger.info(f"Ollama Proxy (Streaming): Executing {request.model}")
            client = AsyncClient()
            async for chunk in await client.chat(
                model=request.model,
                messages=messages,
                stream=True
            ):
                content = chunk['message']['content']
                if content:
                    # Yield as a JSON-encoded line or plain text
                    yield content
        except Exception as e:
            logger.error(f"Ollama streaming failed: {e}")
            yield f"\n[Error: {str(e)}]"

    return StreamingResponse(generate_response(), media_type="text/plain")

if __name__ == "__main__":
    import uvicorn
    # Use 0.0.0.0 for Docker networking
    uvicorn.run(app, host="0.0.0.0", port=8000)

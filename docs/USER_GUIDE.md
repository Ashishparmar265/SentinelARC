# SentinelARC User Guide

This guide explains how to interact with the SentinelARC system via its Streamlit Web Interface.

## Accessing the Interface

Once the system is running (either via Docker Compose or locally), open your browser and navigate to:
`http://localhost:8501`

## Interface Overview

The SentinelARC Streamlit interface is divided into two primary sections: the Sidebar and the Main Chat Area.

### 1. Sidebar (Configuration & Logs)
- **Model Selection:** Choose the underlying LLM (e.g., Ollama, Groq) you want the agents to use for answering queries.
- **System Status:** View the current health and connection status of the Core API (`http://localhost:8000`).
- **Logs / Output:** A section that displays the step-by-step progress of the background agents.

### 2. Main Chat Area
This is the primary way to interact with SentinelARC. 

- **General Chat:** You can have a normal conversation with the selected model. Type a message in the chat box, and the system will stream the response back.
- **Research Tasks:** If you ask a complex question or explicitly trigger a research task, the interface will communicate with the `/research` endpoint. The Orchestrator Agent will spin up, assigning tasks to Search, Extraction, Fact Checker, and Synthesis agents.
- **Viewing Results:** Once a research task completes, the final synthesized report will be displayed in the chat. In some cases, files may be saved to the `/output` directory by the File Save Agent.

## Understanding Outputs

- **Streaming Text:** For general chat, text appears dynamically.
- **Agent Notifications:** When a research task is triggered, you will see notifications indicating which agent is currently working (e.g., "Search Agent gathering data...", "Fact Checker verifying...").

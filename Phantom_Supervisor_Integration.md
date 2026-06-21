# Phantom Supervisor Integration State

This document outlines the architectural decisions, modifications, and the exact state of the Phantom Supervisor integration within the SentinelARC platform.

## 1. The Core Objective
To solve the "Cold Start" problem and significantly reduce the idle memory footprint of the SentinelARC multi-agent swarm without sacrificing the real-time responsiveness of the application. 

By integrating Phantom Supervisor (which leverages CRIU - Checkpoint/Restore In Userspace), we can freeze idle Python agents to disk, reducing their memory footprint to 0 MB, and instantly resurrect them (sub-500ms latency) when a search task arrives from the Orchestrator.

## 2. The Polling Challenge
SentinelARC agents use **AMQP** to communicate over persistent TCP sockets with RabbitMQ. RabbitMQ requires active `heartbeats` from the agents. If an agent is frozen to disk by CRIU, it stops sending heartbeats. RabbitMQ will assume the agent crashed and forcefully terminate the connection, breaking the system.

### Alternatives Considered

#### Alternative A: The HTTP Webhook / API Gateway Pattern
* **How it works**: Agents no longer connect to RabbitMQ. Instead, a central Router listens to RabbitMQ and sends standard HTTP `POST` requests to the agents. The Phantom Supervisor proxy catches the HTTP request, wakes the agent, and forwards it.
* **Why we rejected it**: It required completely rewriting the Python agent codebase to use FastAPI/HTTP instead of the native `aio-pika` library. The team opted to preserve the original agent code.

#### Alternative B: Cron-style HTTP Pull Polling
* **How it works**: Agents wake up every 10 seconds, make an HTTP `GET` request to see if tasks exist, and go back to sleep.
* **Why we rejected it**: It ruins the "real-time" feel of the SentinelARC dashboard, introducing arbitrary polling delays.

#### Alternative C: The AMQP Fake-Heartbeat Proxy (Chosen Solution)
* **How it works**: The C++ Interceptor (`interceptor.cpp`) was fundamentally rewritten to act as an AMQP-aware transparent proxy. It sits locally between the Python agent and RabbitMQ.
* **Why we chose it**: It allows the Python agent code to remain 100% untouched. The proxy manages the RabbitMQ connection, injects fake AMQP heartbeats while the agent sleeps, and wakes the agent instantly when RabbitMQ pushes a task payload.

## 3. What Was Modified

To achieve Alternative C, the following files and configurations were updated:

1. **`phantom-supervisor/interceptor.cpp`**: 
   * Completely rewritten. It now listens on port `5673` and forwards to RabbitMQ on port `5672`.
   * Added a `heartbeat_injector` background thread that pushes the 8-byte AMQP heartbeat frame (`0x08 0x00 0x00 0x00 0x00 0x00 0x00 0xCE`) to RabbitMQ every 5 seconds if the agent is frozen.
   * Modified the data forwarding loop to filter out incoming RabbitMQ heartbeats so they don't accidentally wake the sleeping agent.
2. **`docker-compose.optimized.yml`**:
   * Upgraded the `synapse-agents` container to run in `privileged: true` mode (required by CRIU for kernel namespaces and `ptrace`).
   * Redirected the `RABBITMQ_URL` environment variable for the agents to point to the local C++ proxy (`127.0.0.1:5673`) instead of the direct RabbitMQ host.
   * Mounted the `./experimental_snapshots:/snapshots` volume to store the memory dumps.
3. **`docker/agents.Dockerfile`**:
   * Injected low-level dependencies required by CRIU: `criu`, `build-essential`, `iproute2`, `iptables`, `libbsd-dev`.
   * Appended steps to copy the C++ proxy code and compile it during the Docker build stage.
   * Modified the default `CMD` to launch the C++ proxy in the background before starting the Python swarm (`async_main.py`).
4. **`phantom-supervisor/lifecycle_manager.sh`**:
   * Updated the `pgrep` targeting to hunt for `python async_main.py` instead of the generic test script.

## 4. Current State
The system is currently configured, compiling, and deploying. Once active, the `synapse-agents` container will gracefully freeze its internal processes to disk after 10 seconds of inactivity, maintaining a fake heartbeat illusion to the central RabbitMQ server until the next research request arrives.

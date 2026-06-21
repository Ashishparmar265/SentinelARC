# Phantom Process Supervisor: Detailed Project Documentation

## 1. Introduction & Motivation
In modern cloud and AI environments, **serverless computing** is highly popular because it scales dynamically. However, it suffers from **Cold Starts**—the latency introduced when a serverless function is invoked from a dead state and must load its runtime environment, libraries, and application state into memory. 

The **Phantom Process Supervisor** was built to solve this. Instead of completely terminating idle AI agents, we "freeze" them to disk and wake them up only when a request arrives. This allows for high-density memory virtualization (you can have thousands of agents sharing the same RAM, since only active ones are in memory) with sub-second wake-up latency.

## 2. Core Technologies Used
* **CRIU (Checkpoint/Restore In Userspace)**: A Linux kernel tool that freezes a running application and saves its memory state to image files on disk. It can later restore the application from the exact point it was frozen.
* **C++ Socket Programming**: Used to build a low-level, high-performance proxy interceptor.
* **Docker**: Provides an isolated subset (Network, PID namespaces) so CRIU can reliably restore exact Process IDs without conflicting with host operations.
* **Bash Scripting**: Used to manage the lifecycle transitions between the frozen and awake states.

## 3. Architecture Deep Dive

The architecture consists of three main components:

### A. The C++ Interceptor Proxy (`interceptor.cpp`)
The interceptor sits at the edge of the environment, acting as an AMQP transparent proxy. To RabbitMQ, it acts like the actual AI agent. 
* **Connection Bridging**: When the agent boots, it connects to the Proxy (5673). The Proxy immediately connects to RabbitMQ (5672) and bridges the traffic bidirectionally.
* **Fake Heartbeats**: When the agent is frozen to disk, it cannot send AMQP heartbeats. To prevent RabbitMQ from dropping the connection, a dedicated C++ thread injects standard 8-byte AMQP heartbeat frames every 5 seconds.
* **Idle Timeout Monitor**: A background thread continuously monitors active socket connections. If there is no activity for 10 seconds, it triggers the bash script to suspend the agent.

### B. The Bash Lifecycle Manager (`lifecycle_manager.sh`)
This script acts as the bridge between the Interceptor and CRIU.
* **Suspend**: It leverages `criu dump` to freeze the agent, pushing the memory state to `/snapshots/`. It ensures established TCP sockets are accounted for using the `--tcp-established` flag.
* **Awake**: It runs `criu restore -d`, returning the agent to its previously frozen state as a background daemon.
* **ASLR Mitigation**: It uses `setarch x86_64 -R` and `setsid` to ensure the Python memory layout doesn't become randomized and detaches it as a session leader, preventing segmentation faults upon restore.

### C. The Target Process (`async_main.py`)
The primary AI Swarm logic for SentinelARC. It maintains persistent AMQP queues to receive heavy processing tasks like Extraction, Search, and Fact-Checking.

## 4. The Lifecycle Flow

1. **Initial Start**: The proxy starts. The `lifecycle_manager` sees no snapshot and spawns (`setsid`) a fresh `async_main.py`. The agent connects to the Proxy, which connects to RabbitMQ.
2. **Idle State**: 10 seconds pass with no incoming tasks from RabbitMQ. The proxy background monitor triggers the `suspend` lifecycle.
3. **Freeze**: `criu dump` executes. The Python memory pages, file descriptors, and registers are saved to `.img` files. The agent process is destroyed, freeing 100% of its RAM.
4. **Heartbeating**: While the agent is frozen, the Proxy keeps the RabbitMQ connection alive by injecting fake AMQP heartbeats.
5. **Resurrection**: RabbitMQ pushes a new Task Payload to the Proxy. The proxy intercepts the bytes and triggers `awake`.
6. **Restore**: `criu restore` reconstructs the Python process from the `.img` files in milliseconds. The proxy immediately pipes the queued bytes from RabbitMQ into the newly thawed agent.  

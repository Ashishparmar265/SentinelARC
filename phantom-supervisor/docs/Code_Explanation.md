# Phantom Process Supervisor: Code Explanation Guide

This document breaks down every file in the Phantom Supervisor project, providing a line-by-line analysis of how the system operates.

---

## 1. `docker-compose.yml`
This file defines the isolated networking and container environment.

```yaml
version: '3.8'

services:
  phantom-agent:
    build: .
    container_name: phantom-agent
    privileged: true
```
* **`privileged: true`**: Crucial for CRIU (Checkpoint/Restore In Userspace). It gives the container root capabilities to access kernel namespaces, `ptrace`, and bypass Seccomp to manipulate process memory.

```yaml
    ports:
      - "8080:8080" # Exposed directly for Phase 1 testing
      - "9000:9000" # Exposed for Interceptor
```
* **`ports`**: Maps port 9000 on your host machine to port 9000 inside the Docker container where the C++ Interceptor listens.

```yaml
    volumes:
      - /home/iiitl/experimental_snapshots:/snapshots
      - .:/app
```
* **`volumes`**: Mounts a directory from your host into the container at `/snapshots` (where CRIU saves the memory dumps). Also mounts the current codebase to `/app`.

```yaml
    tty: true
```
* **`tty: true`**: Allocates a pseudo-TTY for the container. Helpful for executing interactive debugging bash sessions inside.

---

## 2. `Dockerfile`
This file builds the underlying Linux system the agent runs on.

```dockerfile
FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive
```
* **Base Image**: Uses Ubuntu 22.04. `DEBIAN_FRONTEND` prevents interactive prompts from hanging the build process.

```dockerfile
RUN apt-get update && apt-get install -y \
    criu python3 python3-pip curl netcat-openbsd iproute2 build-essential libbsd-dev iptables \
    && rm -rf /var/lib/apt/lists/*
```
* **Dependencies**: Installs `criu` (the core freezing tool), `python3`, `iptables` (required by CRIU to lock TCP network sockets during freezes), and `build-essential` (to compile the C++ interceptor).

```dockerfile
WORKDIR /app
CMD ["./interceptor"]
```
* **`CMD`**: The default command executed when the container starts. It launches our compiled C++ proxy as **PID 1**, making it the root process of the container.

---

## 3. `agent.py`
The lightweight Python server acting as our AI Agent.

```python
from http.server import BaseHTTPRequestHandler, HTTPServer
import time

hostName = "0.0.0.0"
serverPort = 8080
```
* **Setup**: Imports standard Python networking libraries and binds the agent strictly to the internal port 8080.

```python
class MyServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Connection", "close")
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        response = f"Hello from the Phantom Agent! Timestamp: {time.time()}\n"
        self.wfile.write(bytes(response, "utf-8"))
```
* **`Connection: close`**: Informs the client (the Interceptor) that it will not reuse the TCP connection after transmitting the byte payload. This prevents stale sockets from hanging.
* **`response`**: Dynamically crafts a string with the exact time to prove the server processed it instantly, then forces it out the socket.

---

## 4. `lifecycle_manager.sh`
The Bash script responsible for executing the CRIU checkpoint commands.

```bash
#!/bin/bash
ACTION=$1
DATA_DIR="/snapshots/frozen_agent"
```
* Arguments determine if we are putting the agent to sleep (`suspend`) or waking it up (`awake`).

### The Suspend Block
```bash
    suspend)
        AGENT_PID=$(pgrep -f "python3 -u agent.py")
        if [ -n "$AGENT_PID" ]; then
            rm -rf $DATA_DIR
            mkdir -p $DATA_DIR
            criu dump -t $AGENT_PID --images-dir $DATA_DIR --tcp-established
```
* **`pgrep`**: Finds the process ID of the Python agent.
* **`criu dump`**: The core magic. It freezes the `AGENT_PID`, pushes its raw memory structure and CPU registers to `$DATA_DIR`, and ensures established TCP connections are preserved (`--tcp-established`). It then instantly kills the Python process, freeing RAM.

### The Awake Block
```bash
    awake)
        if [ -d "$DATA_DIR" ] && [ "$(ls -A $DATA_DIR)" ]; then
            criu restore --images-dir $DATA_DIR --tcp-established -d
```
* **`criu restore`**: Reads the snapshot images, reconstructs the memory layout identically, and spins the process back up in daemon mode (`-d`). The application has no idea it was ever asleep.

```bash
        else
            setarch x86_64 -R setsid python3 -u agent.py > /dev/null 2>&1 &
        fi
```
* **Fresh Start Fallback**: If no snapshot exists (like the very first time the system runs), it starts Python dynamically.
* **`setarch x86_64 -R`**: Disables Address Space Layout Randomization (ASLR). This guarantees the memory addresses don't shift randomly across kernel invocations, which prevents CRIU from segfaulting later.
* **`setsid`**: Detaches the process to make it a new Session Leader, disconnecting it from the parent TTY structure.

---

## 5. `interceptor.cpp`
The high-performance network proxy that sits natively on Port 9000.

```cpp
atomic<time_t> last_active_time(time(nullptr));
atomic<int> active_connections(0);
atomic<bool> agent_running(true);
```
* **Atomic Tracking**: Thread-safe variables that track the state of connections and when the last byte of data was transferred.

```cpp
void forward_data(int src_fd, int dst_fd) {
    char buffer[16384];
    while (true) {
        ssize_t bytes_read = recv(src_fd, buffer, sizeof(buffer), 0);
        last_active_time = time(nullptr); 
```
* **`forward_data`**: A low-level loop that reads bytes from a source socket and pushes them to a destination socket. Every time a byte is transferred, it resets the `last_active_time` timestamp. 

```cpp
bool connect_to_agent(int& target_fd) {
    // ... traditional AF_INET socket connection attempt internally to Port 8080
}
```
* Evaluates if Port 8080 (the Python agent) responds to TCP handshakes.

```cpp
void handle_client(int client_fd) {
    if (!connect_to_agent(target_fd)) {
        system("./lifecycle_manager.sh awake");
```
* **Wake On Demand**: If the Python agent port is dead (asleep), the interceptor executes the bash script to restore it from memory.

```cpp
        for (int i = 0; i < 30; i++) { 
            this_thread::sleep_for(chrono::milliseconds(200));
            if (connect_to_agent(target_fd)) break;
        }
```
* **Polling**: The Interceptor waits up to 6 seconds for the agent to boot, holding the external client connection successfully until the agent binds the socket.

```cpp
    thread t1(forward_data, client_fd, target_fd);
    thread t2(forward_data, target_fd, client_fd);
    t1.join();
    t2.join();
```
* **Bridging**: Spawns two threads simultaneously. One pipes data `Client -> Agent`, the other pipes `Agent -> Client`. When both threads exhaust EOF, the sockets safely close.

```cpp
void auto_suspend_monitor() {
    while (true) {
        this_thread::sleep_for(chrono::seconds(2));
        if (active_connections == 0 && agent_running) {
            if (time(nullptr) - last_active_time >= IDLE_TIMEOUT_SEC) {
                system("./lifecycle_manager.sh suspend");
                agent_running = false;
```
* **Auto-Suspend Monitor**: A detached background thread that evaluates the health of the system every 2 seconds. If there are exactly zero active connections AND 10 total seconds (`IDLE_TIMEOUT_SEC`) have passed since the last byte was transferred, it executes the bash script to instantly dump and kill the Python agent, reclaiming the container's RAM footprint.

```cpp
int main() {
    signal(SIGCHLD, SIG_IGN); // Auto-reap zombies
```
* **Zombie Reaping**: Because `system()` calls execute bash shell child processes natively inside the container, this kernel signal tells the OS to automatically destroy background processes once they terminate, preventing PID overflow constraints.

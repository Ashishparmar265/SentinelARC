# Phantom Process Supervisor: Ultimate Interview Preparation Guide

This document is a comprehensive compilation of 80 core interview questions and answers designed to help you explain the **Phantom Process Supervisor** project. It is split into short questions, detailed questions, custom follow-ups from your session, and a glossary of low-level systems terms.

---

## Glossary of Key Technical Terms
If you encounter any of these terms in the answers, refer here for a detailed explanation:
*   **CRIU (Checkpoint/Restore in Userspace)**: A Linux software utility that freezes a running container or process tree and dumps its complete state (RAM, registers, socket states) into files on disk to restore it later.
*   **ASLR (Address Space Layout Randomization)**: A kernel security feature that randomizes the memory addresses of program components (stack, heap, libraries) on startup to prevent memory-corruption exploits.
*   **Socket / File Descriptor (FD)**: In Linux, everything is a file. A socket is represented by an integer file descriptor that acts as an endpoint for reading or writing data over a network.
*   **ptrace**: A Linux system call that allows one process (like CRIU or a debugger) to control, inspect, and manipulate the memory and registers of another process.
*   **mmap**: A system call that maps files or devices directly into a process's virtual memory address space.
*   **setsid**: A system call used to detach a process from its parent terminal session, making it a "Session Leader" so it won't be killed if the terminal closes.
*   **setarch**: A utility that alters the execution architecture reported to a process and can modify kernel options, such as disabling ASLR.
*   **SO_REUSEADDR / SO_REUSEPORT**: Socket options that allow multiple sockets to bind to the exact same IP address and port, allowing instant server restarts without waiting for kernel timeouts.
*   **Zombie Process**: A process that has completed execution but still has an entry in the OS process table, waiting for its parent to read its exit status.
*   **TCP 3-Way Handshake**: The synchronization process (SYN -> SYN-ACK -> ACK) used to establish a reliable TCP network connection between a client and server.
*   **Namespace**: A Linux kernel feature that isolates system resources (like Process IDs, Network devices, Mount points) so processes in one namespace cannot see or affect others.
*   **Privileged Container**: A Docker container executed with full root access to the host kernel, bypassing normal security filters (like Seccomp).
*   **Data Race**: A concurrency bug that occurs when two or more threads access the same memory location simultaneously, and at least one access is a write, without synchronization.
*   **Atomic Operations**: CPU instructions that execute as a single, uninterrupted step, preventing other threads from seeing intermediate states.
*   **SIGCHLD**: A signal sent by the Linux kernel to a parent process when one of its child processes terminates or stops.

---

## Part 1: 40 Short Questions and Answers (Direct & High-Level)

### 1. What is the core problem this project solves?
**Answer:** It eliminates the **Cold Start** latency of serverless functions and AI agents by restoring them from disk snapshots instead of performing a fresh container boot.

### 2. What is the main technology used to freeze and thaw processes?
**Answer:** **CRIU** (Checkpoint/Restore in Userspace), a Linux utility.

### 3. What language is the proxy built in, and why?
**Answer:** **C++**, because it provides low-level control over POSIX sockets, low memory footprint, and sub-millisecond routing latency.

### 4. What language is the backend AI Agent built in?
**Answer:** **Python**, using the standard `http.server` library.

### 5. On what port does the C++ Interceptor listen?
**Answer:** Port **9000**.

### 6. On what port does the Python Agent run?
**Answer:** Port **8080** (accessible only internally or during isolated testing).

### 7. How does the proxy know if the Python Agent is asleep?
**Answer:** It tries to open a TCP connection to Port 8080. If the connection fails (connection refused), it knows the agent is asleep.

### 8. What is the idle timeout period before the agent is suspended?
**Answer:** **10 seconds** of complete network inactivity.

### 9. Where are the frozen memory snapshots stored?
**Answer:** In the `/snapshots/frozen_agent` directory (which is mapped to a host folder in docker-compose).

### 10. Why is `privileged: true` used in Docker?
**Answer:** Because CRIU needs root kernel privileges to inject code, manipulate memory pages, and lock TCP sockets.

### 11. What flag does CRIU use to freeze network connections?
**Answer:** `--tcp-established`.

### 12. What does `setarch x86_64 -R` do in the startup command?
**Answer:** It disables Address Space Layout Randomization (ASLR) to prevent memory mapping mismatches during restore.

### 13. What does `setsid` do in the startup command?
**Answer:** It detaches the Python agent from the parent terminal session, preventing terminal signals from killing it.

### 14. What C++ feature is used to avoid data races on the activity timestamps?
**Answer:** `std::atomic` types (like `std::atomic<time_t>`).

### 15. How does the C++ proxy avoid consuming 100% CPU while monitoring idle states?
**Answer:** It sleeps for 2 seconds in a loop (`std::this_thread::sleep_for`) instead of spinning constantly.

### 16. What is the average wake-up time of the agent?
**Answer:** Under **500 milliseconds**.

### 17. How does the client connection remain alive while the agent is waking up?
**Answer:** The C++ proxy completes the TCP handshake immediately with the client and buffers the socket read, preventing a client-side timeout.

### 18. What happens to the Python process's RAM when it is suspended?
**Answer:** Its RAM usage drops to **0** because the process is killed after its memory state is written to disk.

### 19. How many threads are spawned for a single client connection?
**Answer:** **Two threads**: one for forwarding data client-to-agent, and one for forwarding data agent-to-client.

### 20. What socket options are set on the server socket to allow quick restarts?
**Answer:** `SO_REUSEADDR` and `SO_REUSEPORT`.

### 21. What C++ function is used to copy data between sockets?
**Answer:** A loop utilizing the POSIX `recv()` and `send()` calls.

### 22. What happens if there is no previous snapshot during wake-up?
**Answer:** The script falls back to starting a fresh instance of `agent.py`.

### 23. What command is used in C++ to execute the lifecycle bash script?
**Answer:** The `system()` call (e.g., `system("./lifecycle_manager.sh awake")`).

### 24. What is the role of `signal(SIGCHLD, SIG_IGN)` in the main function?
**Answer:** It tells the kernel to automatically clean up terminated child processes, preventing zombie processes.

### 25. Why is a Docker container useful for keeping PIDs constant?
**Answer:** Docker isolates the PID namespace, guaranteeing that the PID allocated to Python at checkpoint time is still free during restore.

### 26. What does `pgrep -f "python3 -u agent.py"` do in the lifecycle script?
**Answer:** It searches the running process tree to find the exact PID of the active Python agent.

### 27. What happens if the `criu dump` fails?
**Answer:** The script deletes the failed snapshot folder, and the proxy continues operating without crashing.

### 28. What header is returned by the Python agent to prevent persistent connection hangs?
**Answer:** `Connection: close`.

### 29. Can the C++ proxy handle multiple clients simultaneously?
**Answer:** Yes, it spawns a detached thread `handle_client` for every incoming client connection.

### 30. How large is the buffer used for reading socket data in C++?
**Answer:** **16,384 bytes** (16KB) to maximize throughput.

### 31. What is the primary metric indicating that memory density is improved?
**Answer:** We can host 10x more idle agents because they occupy disk space rather than system RAM.

### 32. Why must the snapshot folder be cleared before dumping?
**Answer:** CRIU requires a clean, empty directory to write its new memory state images.

### 33. Does the client know that the backend agent was frozen?
**Answer:** No, the proxy masks the entire freezing and restoring cycle from the client.

### 34. What is the purpose of `double-pipe` threading?
**Answer:** It allows simultaneous, full-duplex communication: reading and writing can occur at the same time without blocking.

### 35. What is the default backlog parameter in the C++ `listen()` function?
**Answer:** **100** (meaning up to 100 connections can wait in the OS queue).

### 36. What Linux kernel command is simulated by `setarch -R`?
**Answer:** It temporarily disables the `addr_limit` randomization check for that process subtree.

### 37. What type of socket is created (TCP or UDP)?
**Answer:** **TCP** (`SOCK_STREAM`), ensuring reliable, ordered byte delivery.

### 38. How does the proxy update the activity timestamp?
**Answer:** Every time the `recv()` loop reads more than 0 bytes, it sets `last_active_time = time(nullptr)`.

### 39. What does the `-d` flag in `criu restore` do?
**Answer:** It runs the restored process in the background as a daemon.

### 40. Where is the interceptor compiled?
**Answer:** Inside the Docker container during the build phase (`g++ -pthread`).

---

## Part 2: 40 Detailed Questions and Answers (In-Depth Systems Concepts)

### 41. Explain the architectural pipeline of a request hitting the proxy when the agent is asleep.
**Answer:** 
1. The client initiates a TCP handshake on Port 9000. The C++ Interceptor's `accept()` executes and completes the handshake.
2. The proxy spawns a thread and attempts to connect to `127.0.0.1:8080` via `connect()`.
3. The connection is refused because the Python agent is asleep.
4. The proxy executes `system("./lifecycle_manager.sh awake")`.
5. The bash script invokes `criu restore -d` which reads the snapshot images from disk and recreates the Python process state.
6. The proxy polls Port 8080 every 200ms. Once the restore completes, `connect()` succeeds.
7. The proxy launches two forwarding threads to pipe data between the client socket and the new agent socket.

### 42. Why did we build a custom C++ proxy instead of using an off-the-shelf proxy like Nginx or HAProxy?
**Answer:** Standard reverse proxies like Nginx are designed to forward traffic immediately to an active upstream server. If the upstream is down, they immediately return a `502 Bad Gateway` error. They do not natively support holding a connection open while executing system-level scripts (like `criu restore`) to wake the backend process up on-demand. Our custom proxy implements this specialized "hold-and-resurrect" logic at the socket level.

### 43. Walk me through the implementation details of `forward_data` in `interceptor.cpp`.
**Answer:** 
`forward_data` is a worker thread function that accepts a source file descriptor (`src_fd`) and a destination file descriptor (`dst_fd`). It allocates a 16KB buffer on the stack. 
It enters a loop:
1. It calls `recv(src_fd, buffer, sizeof(buffer), 0)`. This blocks until data is available.
2. If `recv` returns $\le 0$, the connection is closed or has errored, and the loop breaks.
3. It updates `last_active_time` to prevent idle suspension.
4. It calls `send(dst_fd, ...)` in a nested loop to guarantee that all read bytes are successfully pushed to the destination socket, adjusting for partial writes.
5. After breaking, it calls `shutdown()` on both descriptors to close the read/write paths.

### 44. What are the security and architectural implications of running Docker with `privileged: true`?
**Answer:** Running a container as privileged gives it capabilities nearly identical to root access on the host system. It bypasses AppArmor, Seccomp, and cgroup restrictions. In production, this is a security risk because if the container is compromised, the attacker can access host hardware and namespaces. However, for a process supervisor, this is necessary because CRIU must execute privileged system calls (`ptrace` to seize processes, writing to `/proc`, and restoring kernel sockets).

### 45. Explain how CRIU handles open TCP sockets during a checkpoint.
**Answer:** When `criu dump` is called with `--tcp-established`, CRIU locks the sockets. It uses the `NF_QUEUE` or `iptables` rules to freeze incoming and outgoing packets for that socket so the TCP window does not shift. It then reads the socket state (sequence numbers, buffers, window sizes) from the kernel and writes them to the image files. When the process is killed, the remote peer thinks there is a temporary network lag because packet flow is paused.

### 46. What happens to the TCP connection during `criu restore`?
**Answer:** During restore, CRIU uses the TCP socket repair mode (`TCP_REPAIR` option in the Linux kernel). It opens a new socket, binds it to the exact IP and port, and sets the sequence numbers and state variables directly back to what they were when dumped. It then turns off socket repair mode. When network packets start flowing again, the TCP connection resumes seamlessly without needing a renegotiation handshake.

### 47. Why do we need `setsid` when spawning the Python agent?
**Answer:** When a process is started from a bash script in a terminal, it inherits the terminal's controlling session. If it stays attached, the terminal controls it, and standard signals (like hangup) will kill it. More importantly, CRIU cannot checkpoint a process attached to a physical tty/session because it cannot snapshot the state of the host's terminal. `setsid` runs the process in a new, detached session with no controlling terminal, which allows CRIU to snapshot it cleanly.

### 48. Why does ASLR break process restoration, and how does `setarch x86_64 -R` mitigate it?
**Answer:** ASLR randomizes the base addresses of the stack, heap, and libraries. If Python starts up with ASLR, the OS allocates arbitrary memory regions. If we snapshot it, the addresses are recorded. If we restore it later, and ASLR is active, the OS tries to randomize the new memory layouts. If there's a conflict between where CRIU wants to map a memory page (e.g., `0x55ab...`) and where the kernel wants to place a library, the restore fails with a segmentation fault. `setarch -R` disables this randomization, ensuring consistent, deterministic virtual memory layouts.

### 49. Why do we run two threads per connection inside `handle_client` instead of one?
**Answer:** TCP is a full-duplex protocol, meaning data can flow in both directions (Client $\rightarrow$ Agent and Agent $\rightarrow$ Client) simultaneously. If we used a single thread, we would have to read from the client, write to the agent, read from the agent, and write to the client in a serial, lock-step manner. If the client sends data while the thread is blocking on reading from the agent, the system hangs. Two concurrent threads allow asynchronous, independent data flow in both directions.

### 50. How does the C++ Interceptor clean up finished connection threads to prevent memory leaks?
**Answer:** In `handle_client`, we spawn the forwarding threads `t1` and `t2` on the stack. We then call `t1.join()` and `t2.join()`. This blocks `handle_client` until both threads have completely finished (which happens when either side closes the socket). Once they join, their thread resources are automatically cleaned up, and the `handle_client` thread itself terminates, preventing thread leaks.

### 51. What is the role of atomic variables in `interceptor.cpp`?
**Answer:** The variable `active_connections` is accessed by the main thread (when accepting clients), client handler threads, and the monitor thread. The variable `last_active_time` is updated by forwarding threads and read by the monitor thread. In C++, modifications to standard types are not atomic and can be split into multiple CPU instructions. Without `std::atomic`, concurrent read/write actions would lead to data corruption or stale registers (data races). Atomics enforce CPU-level memory barriers to ensure safe thread sharing.

### 52. Why does the program ignore the `SIGCHLD` signal?
**Answer:** When the C++ Interceptor uses `system()` to run the bash scripts, it spawns child shell processes. When a child process terminates, it becomes a "zombie" until the parent calls `wait()` or `waitpid()` to read its exit status. If the parent ignores this, zombie processes accumulate and consume PID descriptors. By calling `signal(SIGCHLD, SIG_IGN)`, we tell the Linux kernel that we are not interested in the child's exit code, prompting the kernel to reap child processes automatically.

### 53. How does the polling mechanism in `handle_client` handle agent boot time?
**Answer:** 
```cpp
for (int i = 0; i < 30; i++) {
    this_thread::sleep_for(chrono::milliseconds(200));
    if (connect_to_agent(target_fd)) { ... }
}
```
If the agent is asleep, we trigger the wake-up script. The agent takes a few hundred milliseconds to restore and bind to Port 8080. If the proxy tried to connect immediately, it would fail. Thus, it loops up to 30 times, sleeping for 200ms between attempts (up to 6 seconds total). This gives the backend process enough buffer time to start listening without failing the client request.

### 54. Compare the Cold Start of this CRIU-based runtime with traditional VM or Docker boot times.
**Answer:** Traditional serverless (like standard AWS Lambda or custom Kubernetes pods) creates a new VM or container on a cold start. This requires initializing container namespaces, mounting filesystems, running runtime startup scripts, loading libraries (like PyTorch or TensorFlow), and parsing application code. This takes anywhere from 2 to 10 seconds. With CRIU, the container is *already* running; we only thaw the process. The memory pages are already structured on disk and are mapped directly into RAM in under 500ms, representing a 10x-20x speedup.

### 55. What are the memory density benefits of this architecture?
**Answer:** In standard setups, if you have 100 AI agents, they must all run in RAM to remain responsive. If each agent takes 500MB, you need 50GB of RAM. In our architecture, idle agents are frozen to disk, freeing 100% of their RAM. They only consume a small amount of disk space (e.g., 50MB for snapshot files). When a request comes, only that specific agent is brought into RAM. This allows you to host thousands of agents on the same hardware, achieving a massive increase in density.

### 56. What happens to file descriptors (FDs) open in the Python agent when it is checkpointed?
**Answer:** CRIU saves the state of all open file descriptors. It records the file path, the cursor position (offset), and access flags. During restore, CRIU opens the same files and positions the file pointer back to the exact byte offset recorded during the checkpoint. If a file was deleted or moved between checkpoint and restore, the restore will fail.

### 57. What are the limitations of CRIU? Where would this architecture fail?
**Answer:** 
1.  **Hardware Mismatches**: You cannot restore a snapshot on a host with a different CPU architecture or significantly different kernel version.
2.  **External Resources**: If the agent has open database connections or external API sockets that do not support socket-level freeze/restore or have remote timeouts, those connections will drop.
3.  **Kernel Dependencies**: CRIU is highly dependent on kernel configurations, meaning upgrades to the host OS can sometimes break snapshot compatibility.

### 58. How do we ensure that the proxy socket doesn't block the entire application when accepting clients?
**Answer:** The main loop in `main()` runs:
```cpp
int client_fd = accept(server_fd, ...);
if (client_fd >= 0) {
    thread t(handle_client, client_fd);
    t.detach();
}
```
The call to `accept()` blocks until a client connects. However, once a connection is made, we immediately spin up a new thread `t` to execute `handle_client` and call `t.detach()`. This hands control of the socket to the background thread, allowing the main loop to immediately call `accept()` again to receive the next client.

### 59. Explain the flag combinations `SO_REUSEADDR` and `SO_REUSEPORT` inside our socket creation.
**Answer:** 
*   `SO_REUSEADDR`: Allows the socket to bind to a port that is in the `TIME_WAIT` state (which occurs when a socket was recently closed but the kernel is still cleaning up packets). Without this, restarting the proxy would fail with an "Address already in use" error for up to 2 minutes.
*   `SO_REUSEPORT`: Allows multiple threads or processes to bind to the exact same port. The kernel will automatically load-balance incoming connections across the listening sockets.

### 60. How does the proxy handle partial writes when sending data to sockets?
**Answer:** When sending data, `send()` might write fewer bytes than requested (e.g. if the socket buffer is full). To prevent data corruption, we wrap the write in a loop ([interceptor.cpp:L37-43](file:///home/iiitl/Documents/OS-project/phantom-supervisor/interceptor.cpp#L37-L43)):
```cpp
ssize_t bytes_sent = 0;
while (bytes_sent < bytes_read) {
    ssize_t res = send(dst_fd, buffer + bytes_sent, bytes_read - bytes_sent, 0);
    if (res <= 0) return;
    bytes_sent += res;
}
```
This tracks how many bytes were successfully sent and retries sending the remainder from the correct buffer offset.

### 61. If an agent process is frozen, what happens if the client sends data *during* the restore phase?
**Answer:** The client connection is managed by the C++ proxy, which is always active. When the client sends bytes during the restore phase, the proxy reads those bytes and stores them in its memory buffer. Once the restore finishes and the connection to the agent (Port 8080) is established, the proxy pipes those buffered bytes to the agent. No data is lost.

### 62. How does CRIU write memory pages to disk efficiently?
**Answer:** CRIU uses a kernel feature called **page-pipe** and splicing. Instead of copying memory pages multiple times between kernel space and user space, it uses the `vmsplice()` system call to move page mappings directly into pipe descriptors, which are then written directly to disk. This minimizes CPU cache pollution and memory copying overhead.

### 63. What is the difference between `criu dump` and `criu pre-dump`?
**Answer:** 
*   `criu dump`: Freezes the process and writes all of its memory to disk in one step.
*   `criu pre-dump`: An optimization feature. It writes memory pages to disk *while the process is still running*. When you perform the final dump, CRIU only has to write the "dirty" pages (pages changed since the pre-dump). This decreases the freeze time significantly.

### 64. Why does our C++ code use `shutdown(fd, SHUT_RDWR)` before closing sockets?
**Answer:** `shutdown()` with `SHUT_RDWR` disables both send and receive operations on the socket immediately. This sends a TCP FIN packet to the peer, signaling that no more data will be sent, and forces blocking `recv()` calls in other threads to unblock. Once the socket is shut down, we call `close()` to release the file descriptor back to the OS.

### 65. What would happen if we didn't specify `--tcp-established` in the CRIU command?
**Answer:** If the Python agent had open socket connections and we ran `criu dump` without `--tcp-established`, CRIU would return an error and fail to checkpoint the process. It does this because it doesn't want to checkpoint a process with resources that cannot be safely restored. The flag tells CRIU that we acknowledge the risks and want to freeze the socket states.

### 66. How does CRIU guarantee that restored processes get the same PIDs?
**Answer:** In Linux, PIDs are assigned sequentially. To force a specific PID, CRIU writes the target PID value into a special kernel parameter file: `/proc/sys/kernel/ns_last_pid`. When it calls `fork()` or `clone()`, the kernel reads this value and assigns it to the new child. Since this file is global to the PID namespace, it requires root/privileged access.

### 67. Explain how the C++ proxy handles connection errors during the forwarding phase.
**Answer:** If either `recv()` or `send()` returns a value $\le 0$, the forwarding loop breaks. The thread immediately executes `shutdown()` on both the client socket and the target socket. This forces the companion forwarding thread (which is handling the opposite direction) to fail its current `recv()` or `send()` call, causing it to exit as well. This ensures both threads exit cleanly and socket descriptors are released.

### 68. How would you scale this architecture to support thousands of different containers?
**Answer:** You would run a centralized Routing/Orchestration proxy (like an Envoy filter or custom gateway) that manages a mapping table of `Agent_ID -> Container_PID`. Instead of a single C++ interceptor per container, you would have one central gateway directing traffic. It would track which container namespaces are active, trigger wakes via container APIs, and route packets dynamically.

### 69. Why did we choose Ubuntu 22.04 as our base Docker image?
**Answer:** Ubuntu 22.04 has modern kernel compatibility and includes up-to-date, stable packages for `criu`, `iptables`, and compiler libraries. Using older distributions like Ubuntu 18.04 can result in CRIU errors due to missing socket repair options in older kernels.

### 70. How does the proxy handle HTTP keep-alive headers from clients?
**Answer:** In our Python agent code, we explicitly set the `Connection: close` header. This forces the client to close the connection after one request-response cycle, preventing the socket from hanging open indefinitely, which would block our idle monitor from freezing the process.

### 71. What happens if the container runs out of disk space?
**Answer:** `criu dump` will fail to write the memory image files to disk. The Python agent will remain running in RAM, and the proxy will log the error but continue to forward connections directly.

### 72. Explain the difference between `std::thread::join` and `std::thread::detach`.
**Answer:** 
*   `join()`: Blocks the calling thread until the target thread finishes execution. It guarantees resources are cleaned up synchronously.
*   `detach()`: Detaches the thread from the parent thread. It runs independently in the background, and its resources are cleaned up by the OS when it terminates.

### 73. Why do we clean the snapshot directory (`rm -rf $DATA_DIR`) before running `criu dump`?
**Answer:** If old snapshot files exist in the target directory, CRIU will crash because it expects a clean space to generate its state image descriptors. Cleaning it ensures that previous run states do not conflict with the new dump.

### 74. How does the proxy handle a client sending malicious or malformed packets?
**Answer:** Since our C++ proxy works at the Layer 4 (TCP) level, it doesn't parse HTTP headers or inspect application payloads; it simply passes raw bytes. This makes it immune to Layer 7 exploits (like HTTP request smuggling). The Python Agent itself is responsible for parsing HTTP and handling malformed requests.

### 75. Explain how the compiler flags `-pthread` affect the C++ executable.
**Answer:** The `-pthread` compiler and linker flag enables support for the POSIX threads library. It sets preprocessor macros (like `_REENTRANT`) to ensure thread-safe functions in the standard C++ library are used, and links the application to the `libpthread` library.

### 76. Why does the Python server print with `flush=True` in `agent.py`?
**Answer:** By default, standard output in Python is buffered when redirected or run in background environments. `flush=True` forces Python to write output to the stdout stream immediately, ensuring logs show up instantly in Docker or terminal views.

### 77. How does CRIU restore signal handlers for the process?
**Answer:** During the checkpoint phase, CRIU queries the kernel for the signal action table (via `rt_sigaction`). It records which functions are mapped to signals like `SIGTERM` or `SIGINT`. During restore, it calls `rt_sigaction` to re-register these handlers before resuming execution.

### 78. What happens if a client closes their browser before the Python agent finishes waking up?
**Answer:** The C++ proxy's connection to the client breaks. The `send()` or `recv()` calls to the client socket will return an error. The proxy will abort the connection process, close the socket to the newly thawed agent, and clean up.

### 79. Why do we compile with `build-essential` in our Dockerfile?
**Answer:** `build-essential` is a meta-package that installs the GNU Compiler Collection (GCC), C++ standard libraries (`g++`), and `make` utilities. It is required to compile `interceptor.cpp` into a native binary inside the container environment.

### 80. How would you benchmark the overhead added by the C++ proxy?
**Answer:** You can use a load-testing tool like `wrk` or `autocannon` to hit the Python agent directly on Port 8080 (when active), and then compare it with queries sent through the C++ proxy on Port 9000. The difference in latency represents the socket forwarding overhead, which should be under 1-2 milliseconds.

---

## Part 3: Custom Follow-up Questions (From Your Session)

### 81. In detail, what is CRIU, how does it work, and where/how have we used it?
**Answer:** 
*   **What it is**: Checkpoint/Restore in Userspace (CRIU) is a Linux tool that freezes a running process tree and dumps its entire CPU register, memory page, and file descriptor states to disk images, allowing it to be resumed later.
*   **How it works**: It uses `ptrace` to seize control of the target process, injects "parasite" code to copy memory blocks, reads socket metadata from `/proc`, and saves this data to disk. On restore, it recreates the process tree, maps memory back using `mmap`, sets the exact PIDs, restores TCP states, and resumes execution.
*   **Where we used it**: Inside [`lifecycle_manager.sh`](file:///home/iiitl/Documents/OS-project/phantom-supervisor/lifecycle_manager.sh):
    *   **To Freeze**: `criu dump -t $AGENT_PID --images-dir /snapshots/frozen_agent --tcp-established` (kills the process and frees RAM).
    *   **To Thaw**: `criu restore --images-dir /snapshots/frozen_agent --tcp-established -d` (restores it in the background).

### 82. What is socket programming, and where/how have we used it?
**Answer:** 
*   **What it is**: Socket programming is using operating system system-calls (POSIX) to establish and maintain network connections between two processes, enabling bi-directional communication.
*   **Where we used it**: Inside [`interceptor.cpp`](file:///home/iiitl/Documents/OS-project/phantom-supervisor/interceptor.cpp) to build our proxy. We set up a listening server socket on Port 9000 (`socket()`, `setsockopt()`, `bind()`, `listen()`), accepted connections (`accept()`), opened a client socket (`socket()`, `connect()`) to Port 8080 (the Python agent), and forwarded raw bytes back and forth using concurrent threads (`recv()`, `send()`).

### 83. How does the Idle Timeout Monitor thread monitor active connections?
**Answer:** It runs as a detached thread in `interceptor.cpp` ([L113-127](file:///home/iiitl/Documents/OS-project/phantom-supervisor/interceptor.cpp#L113-L127)). It sleeps in a loop for 2 seconds to avoid CPU busy-waiting. In each iteration, it checks if `active_connections == 0` (via atomic counter) and `agent_running == true`. If so, it subtracts the `last_active_time` timestamp from the current time. If this difference exceeds 10 seconds, it triggers `./lifecycle_manager.sh suspend` to freeze the agent and updates `agent_running = false`.

### 84. Explain what ASLR is, why it breaks restores, and how `setarch` is used to bypass it.
**Answer:** 
*   **ASLR (Address Space Layout Randomization)**: A kernel security defense that randomizes virtual memory mappings of programs at startup, preventing memory injection attacks.
*   **Why it breaks restores**: During a restore, CRIU must load the process at the exact memory addresses it was frozen at. If ASLR is enabled, the kernel will randomized the target memory layout, causing mapping conflicts and Segmentation Faults.
*   **How we bypassed it**: In [`lifecycle_manager.sh:L33`](file:///home/iiitl/Documents/OS-project/phantom-supervisor/lifecycle_manager.sh#L33), we start the Python agent using `setarch x86_64 -R`. The `-R` flag disables address space layout randomization, guaranteeing a static, predictable memory layout that CRIU can checkpoint and restore reliably.

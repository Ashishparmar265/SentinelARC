# Phantom Process Supervisor: Interview Preparation Guide

## 1. The Elevator Pitch
"I built the Phantom Process Supervisor, a serverless runtime engine designed to eliminate cold starts in AI environments. It acts as a lightweight hypervisor by using a custom C++ TCP proxy to front incoming traffic, and Linux CRIU to freeze idle Python applications to disk. When traffic spikes, the C++ interceptor holds the client connection open, thaws the frozen Python process in milliseconds, and seamlessly proxies the bytes. It drastically increases container memory density by evicting idle agents from RAM while preventing the latency of a full cold boot."

## 2. Key Terminology to Know
* **Cold Start**: The delay experienced when a serverless function is invoked for the first time, requiring the OS to spin up the runtime and load the code.
* **CRIU (Checkpoint/Restore In Userspace)**: A Linux software tool used to capture the exact memory, register, and file descriptor state of a process tree, enabling it to be paused to disk and resumed later.
* **TCP Keep-Alive / Socket Preservation**: The technique where the C++ proxy establishes the 3-way handshake with the client to prevent a timeout, while the backend server takes its time to boot.
* **ASLR (Address Space Layout Randomization)**: A security technique that randomizes memory locations. Bypassed in this project using `setarch` to allow CRIU to reliably restore memory pages.
* **PIDs and Namespaces**: Linux mechanisms to isolate processes. Essential in Docker to ensure CRIU can restore the exact Process ID (PID) without colliding with the host machine.

## 3. Common Technical Interview Questions

### Q: Why did you build the interceptor in C++ instead of Python or Node.js?
**Answer**: "Because the proxy sits in front of all network traffic, it needed the lowest possible latency and overhead. C++ allows for direct manipulation of POSIX sockets, multi-threading (`std::thread`) with zero abstraction penalty, and extremely low memory footprint. A Python proxy would introduce its own garbage collection pauses and memory overhead, defeating the purpose of a high-density serverless environment."

### Q: How did you handle the situation where an agent takes too long to wake up?
**Answer**: "By decoupling the client socket from the agent socket. The C++ interceptor instantly completes the TCP handshake with the client (holding the connection). It then blocks internally while polling the agent's internal port. This ensures the client doesn't receive a 'Connection Refused' error while the agent is being thawed."

### Q: What were the biggest technical challenges you faced with CRIU?
**Answer**: "Restoring complex memory layouts like a Python VM is deeply tied to Linux kernel configurations.
1. **TCP Socket Locking**: `criu dump` requires `iptables` to temporarily lock network packets while freezing socket states, so I had to custom configure the base Docker image to include those root networking utilities.
2. **Segmentation Faults**: A major challenge was Python segfaulting upon restore. I solved this by using `setsid` to detach the agent from its terminal session (making it a proper session leader) and using `setarch x86_64 -R` to disable ASLR, guaranteeing the memory addresses matched perfectly during the restore phase."

### Q: Why use Docker? Why not run it directly on the host?
**Answer**: "CRIU requires restoring a process with the exact same Process ID (PID) it had when it was dumped. On a host machine, PIDs are constantly changing, and PID collisions are inevitable. Docker provides a completely isolated PID namespace, ensuring that when the agent restores as PID 20, that strictly mapped space is isolated from host processes."

### Q: How do you identify when to sleep the agent?
**Answer**: "The C++ interceptor maintains an atomic counter of active data-forwarding threads and a timestamp of the last time a byte was transferred. A detached sleep-monitor thread polls this every 2 seconds. When active connections hit zero and the 10-second threshold is crossed, it executes a system call to invoke the suspend bash script."

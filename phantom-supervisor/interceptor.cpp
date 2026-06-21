#include <iostream>
#include <string>
#include <thread>
#include <chrono>
#include <vector>
#include <mutex>
#include <atomic>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <fcntl.h>
#include <cstdlib>
#include <signal.h>
#include <netdb.h>

using namespace std;

const int PROXY_PORT = 5673; // Agent connects here
const int TARGET_PORT = 5672; // Real RabbitMQ port
const string TARGET_HOST = "rabbitmq";
const int IDLE_TIMEOUT_SEC = 10; 

atomic<time_t> last_active_time(time(nullptr));
atomic<int> active_connections(0);
atomic<bool> agent_running(true); 
atomic<bool> proxy_running(true);

void forward_data_agent_to_rmq(int agent_fd, int rmq_fd) {
    char buffer[16384];
    while (proxy_running) {
        ssize_t bytes_read = recv(agent_fd, buffer, sizeof(buffer), 0);
        if (bytes_read <= 0) break;
        
        last_active_time = time(nullptr);
        
        ssize_t bytes_sent = 0;
        while (bytes_sent < bytes_read) {
            ssize_t res = send(rmq_fd, buffer + bytes_sent, bytes_read - bytes_sent, 0);
            if (res <= 0) return;
            bytes_sent += res;
        }
    }
    shutdown(agent_fd, SHUT_RDWR);
    shutdown(rmq_fd, SHUT_RDWR);
}

void forward_data_rmq_to_agent(int rmq_fd, int agent_fd) {
    char buffer[16384];
    while (proxy_running) {
        ssize_t bytes_read = recv(rmq_fd, buffer, sizeof(buffer), 0);
        if (bytes_read <= 0) break;
        
        // Exclude AMQP heartbeats (8 bytes: 0x08 0x00 0x00 0x00 0x00 0x00 0x00 0xCE) from waking the agent
        bool is_heartbeat = (bytes_read == 8 && buffer[0] == 0x08 && buffer[7] == (char)0xCE);
        
        if (!is_heartbeat) {
            last_active_time = time(nullptr);
            if (!agent_running) {
                cout << "[Interceptor] Task received from RabbitMQ! Waking up agent..." << endl;
                int ret = system("./lifecycle_manager.sh awake");
                (void)ret;
                agent_running = true;
            }
        }
        
        ssize_t bytes_sent = 0;
        while (bytes_sent < bytes_read) {
            ssize_t res = send(agent_fd, buffer + bytes_sent, bytes_read - bytes_sent, 0);
            if (res <= 0) return;
            bytes_sent += res;
        }
    }
    shutdown(agent_fd, SHUT_RDWR);
    shutdown(rmq_fd, SHUT_RDWR);
}

void heartbeat_injector(int rmq_fd) {
    // Standard AMQP 0-9-1 heartbeat frame
    const char heartbeat_frame[] = {0x08, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, (char)0xCE};
    while (proxy_running) {
        this_thread::sleep_for(chrono::seconds(5));
        if (!agent_running) {
            // Inject fake heartbeat to RabbitMQ to keep connection alive
            send(rmq_fd, heartbeat_frame, 8, 0);
        }
    }
}

bool connect_to_rabbitmq(int& target_fd) {
    target_fd = socket(AF_INET, SOCK_STREAM, 0);
    if (target_fd < 0) return false;

    struct hostent *host = gethostbyname(TARGET_HOST.c_str());
    if (host == nullptr) {
        close(target_fd);
        return false;
    }

    struct sockaddr_in target_addr;
    target_addr.sin_family = AF_INET;
    target_addr.sin_port = htons(TARGET_PORT);
    target_addr.sin_addr = *((struct in_addr **)host->h_addr_list)[0];

    if (connect(target_fd, (struct sockaddr*)&target_addr, sizeof(target_addr)) == 0) {
        return true;
    }
    
    close(target_fd);
    return false;
}

void handle_agent_connection(int agent_fd) {
    active_connections++;
    last_active_time = time(nullptr);
    agent_running = true;

    int rmq_fd = -1;
    if (!connect_to_rabbitmq(rmq_fd)) {
        cout << "[Interceptor] Error: Failed to connect to actual RabbitMQ." << endl;
        close(agent_fd);
        active_connections--;
        return;
    }

    cout << "[Interceptor] Proxying AMQP connection between Agent and RabbitMQ..." << endl;

    thread t1(forward_data_agent_to_rmq, agent_fd, rmq_fd);
    thread t2(forward_data_rmq_to_agent, rmq_fd, agent_fd);
    thread t3(heartbeat_injector, rmq_fd);

    t1.join();
    t2.join();
    
    proxy_running = false; // kill heartbeat thread
    t3.detach();

    close(agent_fd);
    close(rmq_fd);
    active_connections--;
    last_active_time = time(nullptr);
}

void auto_suspend_monitor() {
    while (true) {
        this_thread::sleep_for(chrono::seconds(2));
        if (active_connections > 0 && agent_running) {
            time_t current = time(nullptr);
            if (current - last_active_time >= IDLE_TIMEOUT_SEC) {
                cout << "[Interceptor] Idle timeout reached (" << IDLE_TIMEOUT_SEC << "s). Suspending agent..." << endl;
                int ret = system("./lifecycle_manager.sh suspend");
                (void)ret;
                agent_running = false;
            }
        }
    }
}

int main() {
    signal(SIGCHLD, SIG_IGN);
    signal(SIGPIPE, SIG_IGN); // Prevent crashing on broken pipes

    int server_fd = socket(AF_INET, SOCK_STREAM, 0);
    if (server_fd < 0) return 1;

    int opt = 1;
    setsockopt(server_fd, SOL_SOCKET, SO_REUSEADDR | SO_REUSEPORT, &opt, sizeof(opt));

    struct sockaddr_in server_addr;
    server_addr.sin_family = AF_INET;
    server_addr.sin_addr.s_addr = INADDR_ANY;
    server_addr.sin_port = htons(PROXY_PORT);

    if (bind(server_fd, (struct sockaddr*)&server_addr, sizeof(server_addr)) < 0) return 1;
    if (listen(server_fd, 100) < 0) return 1;

    cout << "[Interceptor] Listening for Agent AMQP connections on port " << PROXY_PORT << "..." << endl;
    
    thread monitor(auto_suspend_monitor);
    monitor.detach();

    while (true) {
        struct sockaddr_in client_addr;
        socklen_t client_len = sizeof(client_addr);
        int agent_fd = accept(server_fd, (struct sockaddr*)&client_addr, &client_len);
        
        if (agent_fd >= 0) {
            proxy_running = true;
            thread t(handle_agent_connection, agent_fd);
            t.detach();
        }
    }

    close(server_fd);
    return 0;
}

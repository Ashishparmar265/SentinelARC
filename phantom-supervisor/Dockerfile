FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    criu \
    python3 \
    python3-pip \
    curl \
    netcat-openbsd \
    iproute2 \
    build-essential \
    libbsd-dev \
    iptables \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy the source code to the container
COPY . /app

# Compile the interceptor
RUN g++ -o interceptor interceptor.cpp -pthread

# Run the interceptor so it listens on port 9000
CMD ["./interceptor"]

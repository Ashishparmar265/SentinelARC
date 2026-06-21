#!/bin/bash
ACTION=$1
DATA_DIR="/snapshots/frozen_agent"

case "$ACTION" in
    suspend)
        echo "[Lifecycle Manager] Attempting to suspend python agent..."
        AGENT_PID=$(pgrep -f "python async_main.py")
        if [ -n "$AGENT_PID" ]; then
            rm -rf $DATA_DIR
            mkdir -p $DATA_DIR
            # Dump the agent and the process will be killed by criu
            criu dump -t $AGENT_PID --images-dir $DATA_DIR --tcp-established
            if [ $? -eq 0 ]; then
                echo "[Lifecycle Manager] Agent successfully dumped to $DATA_DIR."
            else
                echo "[Lifecycle Manager] Agent dump FAILED."
                rm -rf $DATA_DIR
            fi
        else
            echo "[Lifecycle Manager] Python agent is not running. Nothing to suspend."
        fi
        ;;
    awake)
        echo "[Lifecycle Manager] Attempting to wake up python agent..."
        if [ -d "$DATA_DIR" ] && [ "$(ls -A $DATA_DIR)" ]; then
            # Restore in background as daemon
            criu restore --images-dir $DATA_DIR --tcp-established -d
            echo "[Lifecycle Manager] Agent restored from snapshot."
        else
            echo "[Lifecycle Manager] No previous snapshot found. Starting fresh."
            # Start fresh in background and detach as session leader, disable ASLR
            setarch x86_64 -R setsid python async_main.py > /app/logs/agent.log 2>&1 &
            echo "[Lifecycle Manager] Fresh agent started."
        fi
        ;;
    *)
        echo "Usage: ./lifecycle_manager.sh {suspend|awake}"
        exit 1
        ;;
esac

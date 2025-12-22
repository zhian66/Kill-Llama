#!/bin/bash
#
# Simple Checkpoint Creator for stream_triad
# This script starts QEMU and provides instructions for manual checkpoint creation.
#
# Usage: ./create_checkpoint_simple.sh
#

set -e

PROJ_ROOT="/home/ubuntu/sttmram/Kill-Llama"
MARSS_DIR="${PROJ_ROOT}/marss.dramsim"
QEMU_BIN="${MARSS_DIR}/qemu/qemu-system-x86_64"
DISK_IMAGE="${MARSS_DIR}/ubuntu_12_04.qcow2"
DRAMSIM_DIR="${PROJ_ROOT}/DRAMSim2"
MONITOR_SOCK="/tmp/qemu-checkpoint.sock"

# Cleanup function
cleanup() {
    echo ""
    echo "[INFO] Cleaning up..."
    rm -f ${MONITOR_SOCK}
}
trap cleanup EXIT

# Check prerequisites
if [[ ! -x "${QEMU_BIN}" ]]; then
    echo "ERROR: QEMU binary not found: ${QEMU_BIN}"
    exit 1
fi

if [[ ! -f "${DISK_IMAGE}" ]]; then
    echo "ERROR: Disk image not found: ${DISK_IMAGE}"
    exit 1
fi

# Set environment
export LD_LIBRARY_PATH="${DRAMSIM_DIR}:${LD_LIBRARY_PATH}"

# Remove old socket
rm -f ${MONITOR_SOCK}

echo "=============================================="
echo " MARSSx86 Checkpoint Creator"
echo "=============================================="
echo ""
echo "Starting QEMU with:"
echo "  - VNC on port 5901 (localhost:5901)"
echo "  - Monitor socket at ${MONITOR_SOCK}"
echo "  - Loading checkpoint: base_deployed"
echo ""

# Start QEMU in background
cd ${MARSS_DIR}
${QEMU_BIN} -m 8G \
    -drive file=${DISK_IMAGE},format=qcow2 \
    -loadvm base_deployed \
    -vnc :1 \
    -monitor unix:${MONITOR_SOCK},server,nowait &
QEMU_PID=$!

echo "[INFO] QEMU started with PID: ${QEMU_PID}"
echo ""

# Wait for socket to be created
echo "[INFO] Waiting for QEMU to be ready..."
for i in {1..30}; do
    if [[ -S ${MONITOR_SOCK} ]]; then
        echo "[INFO] QEMU is ready!"
        break
    fi
    sleep 1
done

if [[ ! -S ${MONITOR_SOCK} ]]; then
    echo "ERROR: QEMU monitor socket not created"
    kill ${QEMU_PID} 2>/dev/null
    exit 1
fi

echo ""
echo "=============================================="
echo " INSTRUCTIONS"
echo "=============================================="
echo ""
echo "1. Connect to VNC: vncviewer localhost:5901"
echo ""
echo "2. In the VM terminal, run:"
echo "   sudo /home/user/benchmarks/stream_triad"
echo ""
echo "3. Enter sudo password: user"
echo ""
echo "4. Wait for this message:"
echo "   'Switching to Simulation Mode...'"
echo ""
echo "=============================================="
echo ""

read -p "Press Enter when you see 'Switching to Simulation Mode'..."

# Save checkpoint
CHECKPOINT_NAME="chk_stream_triad"
echo ""
echo "[INFO] Saving checkpoint: ${CHECKPOINT_NAME}"
echo "savevm ${CHECKPOINT_NAME}" | nc -U ${MONITOR_SOCK} -q 1 2>/dev/null

# Wait for save
echo "[INFO] Waiting for save to complete..."
sleep 10

echo ""
echo "[SUCCESS] Checkpoint ${CHECKPOINT_NAME} should be saved!"
echo ""

# Verify
echo "[INFO] Verifying checkpoint..."
echo "info snapshots" | nc -U ${MONITOR_SOCK} -q 1 2>/dev/null | grep -E "(chk_|base_)" || true

echo ""
read -p "Press Enter to quit QEMU..."

# Quit QEMU
echo "quit" | nc -U ${MONITOR_SOCK} 2>/dev/null
sleep 2

# Make sure QEMU is dead
kill ${QEMU_PID} 2>/dev/null || true

echo ""
echo "[DONE] Checkpoint creation complete!"
echo ""
echo "Next step: Run the pilot test with:"
echo "  ./run_experiments.sh --pilot"

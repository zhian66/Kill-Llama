#!/bin/bash
#
# Setup Serial Console in Guest VM for automated checkpoint creation
#
# This script starts QEMU with VNC so you can configure the Guest VM
# to output to serial console (ttyS0).
#
# Usage: ./setup_serial_console.sh
#

set -e

PROJ_ROOT="/home/ubuntu/sttmram/Kill-Llama"
MARSS_DIR="${PROJ_ROOT}/marss.dramsim"
QEMU_BIN="${MARSS_DIR}/qemu/qemu-system-x86_64"
DISK_IMAGE="${MARSS_DIR}/ubuntu_12_04.qcow2"
DRAMSIM_DIR="${PROJ_ROOT}/DRAMSim2"
MONITOR_SOCK="/tmp/qemu-serial-setup.sock"

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
echo " Serial Console Setup for MARSSx86"
echo "=============================================="
echo ""
echo "This script will help you configure the Guest VM"
echo "to output to serial console for automated checkpointing."
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
echo "2. Login as 'user' (password: user)"
echo ""
echo "3. Edit GRUB configuration:"
echo "   sudo nano /etc/default/grub"
echo ""
echo "4. Modify these lines:"
echo '   GRUB_CMDLINE_LINUX_DEFAULT="console=tty0 console=ttyS0,115200n8"'
echo '   GRUB_TERMINAL="console serial"'
echo '   GRUB_SERIAL_COMMAND="serial --speed=115200 --unit=0 --word=8 --parity=no --stop=1"'
echo ""
echo "5. Update GRUB:"
echo "   sudo update-grub"
echo ""
echo "6. Test serial by adding to /etc/init/ttyS0.conf:"
echo '   # ttyS0 - getty'
echo '   start on runlevel [2345]'
echo '   stop on runlevel [016]'
echo '   respawn'
echo '   exec /sbin/getty -L 115200 ttyS0 vt102'
echo ""
echo "=============================================="
echo ""

read -p "Press Enter when you have completed the GRUB configuration..."

echo ""
echo "[INFO] Saving checkpoint: base_serial"
echo "savevm base_serial" | nc -U ${MONITOR_SOCK} -q 1 2>/dev/null

# Wait for save
echo "[INFO] Waiting for save to complete..."
sleep 15

echo ""
echo "[INFO] Verifying checkpoint..."
echo "info snapshots" | nc -U ${MONITOR_SOCK} -q 1 2>/dev/null | grep -E "(base_|chk_)" || true

echo ""
read -p "Press Enter to quit QEMU..."

# Quit QEMU
echo "quit" | nc -U ${MONITOR_SOCK} 2>/dev/null
sleep 2

# Make sure QEMU is dead
kill ${QEMU_PID} 2>/dev/null || true

echo ""
echo "[DONE] Serial console setup complete!"
echo ""
echo "The new checkpoint 'base_serial' has been saved."
echo ""
echo "Next step: Run the automated checkpoint creator:"
echo "  python3 create_checkpoints_serial.py --workload stream_triad"

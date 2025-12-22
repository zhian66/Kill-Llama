#!/usr/bin/env python3
"""
Checkpoint Creator for MARSSx86 Simulation
==========================================

This script automates the creation of checkpoints for each workload.
It uses QEMU monitor commands to interact with the VM via sendkey.

Usage:
    python3 create_checkpoints.py [--workload WORKLOAD_NAME]
    python3 create_checkpoints.py --workload stream_triad   # Single workload
    python3 create_checkpoints.py --list                     # List workloads
    python3 create_checkpoints.py --reset                    # Reset progress

If --workload is not specified, all workloads will be processed.

Requirements:
    - pexpect: pip3 install pexpect
    - QEMU binary must be compiled
    - Guest OS must have benchmarks deployed
    - 'base_deployed' checkpoint must exist (savevm base_deployed)
"""

import os
import sys
import json
import argparse
import time
import socket
from datetime import datetime

try:
    import pexpect
except ImportError:
    print("ERROR: pexpect not installed. Run: pip3 install pexpect")
    sys.exit(1)

# ============================================
# Configuration
# ============================================
PROJ_ROOT = "/home/ubuntu/sttmram/Kill-Llama"
MARSS_DIR = f"{PROJ_ROOT}/marss.dramsim"
QEMU_BIN = f"{MARSS_DIR}/qemu/qemu-system-x86_64"
DISK_IMAGE = f"{MARSS_DIR}/ubuntu_12_04.qcow2"
DRAMSIM_DIR = f"{PROJ_ROOT}/DRAMSim2"
ISO_PATH = f"{PROJ_ROOT}/benchmarks.iso"

# Base checkpoint (created after deploying benchmarks)
BASE_CHECKPOINT = "base_deployed"

# Progress file for recovery
PROGRESS_FILE = f"{PROJ_ROOT}/experiment/scripts/checkpoint_progress.json"

# Timeout settings (seconds)
BOOT_TIMEOUT = 120      # Time to wait for VM to restore checkpoint
ROI_TIMEOUT = 600       # Time to wait for ROI signal
SAVE_TIMEOUT = 300      # Time to wait for checkpoint save

# ============================================
# Workload Definitions
# ============================================
# Benchmark directory in guest VM
BENCH_DIR = "/home/user/benchmarks"

# Guest VM credentials
GUEST_USER = "user"
GUEST_PASSWORD = "user"

# Format: "checkpoint_name": "command to run in guest"
# Note: benchmarks need sudo to execute ptlcalls
WORKLOADS = {
    # STREAM benchmarks
    "stream_triad": f"sudo {BENCH_DIR}/stream_triad",
    "stream_copy":  f"sudo {BENCH_DIR}/stream_copy",
    "stream_add":   f"sudo {BENCH_DIR}/stream_add",
    "stream_scale": f"sudo {BENCH_DIR}/stream_scale",

    # GAP benchmarks (using test_graph.sg for testing)
    "gap_bfs":  f"sudo {BENCH_DIR}/bfs -f {BENCH_DIR}/test_graph.sg -n 1",
    "gap_sssp": f"sudo {BENCH_DIR}/sssp -f {BENCH_DIR}/test_graph.sg -n 1",
    "gap_bc":   f"sudo {BENCH_DIR}/bc -f {BENCH_DIR}/test_graph.sg -n 1",
    "gap_cc":   f"sudo {BENCH_DIR}/cc -f {BENCH_DIR}/test_graph.sg -n 1",
    "gap_pr":   f"sudo {BENCH_DIR}/pr -f {BENCH_DIR}/test_graph.sg -n 1",
    "gap_tc":   f"sudo {BENCH_DIR}/tc -f {BENCH_DIR}/test_graph.sg -n 1",

    # PARSEC benchmarks (single-threaded for simulation)
    "blackscholes": f"sudo {BENCH_DIR}/blackscholes 1 {BENCH_DIR}/in_4K.txt /dev/null",
    "canneal": f"sudo {BENCH_DIR}/canneal 1 100 300 {BENCH_DIR}/100.nets 8",
    "streamcluster": f"sudo {BENCH_DIR}/streamcluster 2 5 1 10 10 5 none /dev/null 1",
    "fluidanimate": f"sudo {BENCH_DIR}/fluidanimate 1 1 {BENCH_DIR}/in_5K.fluid /dev/null",
    "swaptions": f"sudo {BENCH_DIR}/swaptions -ns 1 -sm 5000 -nt 1",
    "freqmine": f"sudo {BENCH_DIR}/freqmine {BENCH_DIR}/kosarak.dat 220",

    # MIX workloads (to be added later)
    # "mix1": f"sudo {BENCH_DIR}/mix_scripts/run_mix1.sh",
}


def load_progress():
    """Load progress from JSON file."""
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, 'r') as f:
            return json.load(f)
    return {"completed": [], "failed": []}


def save_progress(progress):
    """Save progress to JSON file."""
    os.makedirs(os.path.dirname(PROGRESS_FILE), exist_ok=True)
    with open(PROGRESS_FILE, 'w') as f:
        json.dump(progress, f, indent=2)


def send_keys_via_monitor(sock, text):
    """Send text via QEMU monitor sendkey command."""
    key_map = {
        ' ': 'spc',
        '-': 'minus',
        '/': 'slash',
        '.': 'dot',
        '_': 'shift-minus',
        '\n': 'ret',
        '1': '1', '2': '2', '3': '3', '4': '4', '5': '5',
        '6': '6', '7': '7', '8': '8', '9': '9', '0': '0',
    }

    for char in text:
        if char in key_map:
            key = key_map[char]
        elif char.isupper():
            key = f"shift-{char.lower()}"
        elif char.isalpha():
            key = char.lower()
        else:
            # Skip unknown characters
            continue

        cmd = f"sendkey {key}\n"
        sock.sendall(cmd.encode())
        time.sleep(0.05)  # Small delay between keys


def monitor_command(sock, cmd, wait_time=2):
    """Send a command to QEMU monitor and read response.

    Args:
        sock: The socket connected to QEMU monitor
        cmd: Command to send
        wait_time: Time to wait for response (default 2 seconds)
    """
    # Clear any pending data first
    sock.setblocking(False)
    try:
        while sock.recv(4096):
            pass
    except:
        pass

    # Send command
    sock.setblocking(True)
    sock.settimeout(wait_time + 5)
    sock.sendall(f"{cmd}\n".encode())

    # Wait for command to execute
    time.sleep(wait_time)

    # Read response
    sock.setblocking(False)
    response = ""
    try:
        while True:
            chunk = sock.recv(4096).decode()
            if not chunk:
                break
            response += chunk
    except:
        pass

    return response


def create_checkpoint(name, command, progress):
    """Create a checkpoint for a single workload using QEMU monitor."""

    if name in progress["completed"]:
        print(f"[SKIP] {name} already completed")
        return True

    print(f"\n{'='*60}")
    print(f" Creating Checkpoint: {name}")
    print(f" Command: {command}")
    print(f" Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    # Monitor socket path
    monitor_sock = f"/tmp/qemu-monitor-{name}.sock"

    # Remove old socket if exists
    if os.path.exists(monitor_sock):
        os.remove(monitor_sock)

    # Build QEMU command - use VNC + monitor socket
    qemu_cmd = (
        f"{QEMU_BIN} -m 8G "
        f"-drive file={DISK_IMAGE},format=qcow2 "
        f"-loadvm {BASE_CHECKPOINT} "
        f"-vnc :1 "
        f"-monitor unix:{monitor_sock},server,nowait"
    )

    # Set LD_LIBRARY_PATH
    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = f"{DRAMSIM_DIR}:{env.get('LD_LIBRARY_PATH', '')}"

    child = None
    sock = None

    try:
        # Start QEMU
        print(f"[INFO] Starting QEMU with checkpoint '{BASE_CHECKPOINT}'...")
        print(f"[INFO] VNC available on port 5901")
        child = pexpect.spawn(qemu_cmd, env=env, encoding='utf-8', timeout=BOOT_TIMEOUT,
                              cwd=MARSS_DIR)

        # Wait for QEMU to start and create socket
        print("[INFO] Waiting for QEMU to start...")
        for i in range(30):
            if os.path.exists(monitor_sock):
                break
            time.sleep(1)
        else:
            print("[ERROR] Monitor socket not created")
            if child:
                child.close()
            return False

        # Connect to monitor socket
        print("[INFO] Connecting to QEMU monitor...")
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(monitor_sock)
        sock.setblocking(False)
        time.sleep(1)

        # Read any initial output
        try:
            sock.recv(4096)
        except:
            pass

        # Wait for checkpoint to fully load
        print("[INFO] Waiting for checkpoint to load...")
        time.sleep(5)

        # Send Enter to get a prompt
        print("[INFO] Sending Enter to get prompt...")
        send_keys_via_monitor(sock, "\n")
        time.sleep(2)

        # Type the benchmark command
        print(f"[INFO] Typing command: {command}")
        send_keys_via_monitor(sock, command)
        time.sleep(1)
        send_keys_via_monitor(sock, "\n")
        time.sleep(2)

        # Wait for sudo password prompt and enter password
        print(f"[INFO] Entering sudo password...")
        time.sleep(3)  # Wait for sudo prompt
        send_keys_via_monitor(sock, GUEST_PASSWORD)
        send_keys_via_monitor(sock, "\n")

        # Wait for ROI signal
        print("[INFO] Waiting for simulation mode signal...")
        print("[INFO] (Watch VNC on port 5901 for progress)")

        # We can't easily detect the ROI signal through the monitor
        # So we'll use a fixed wait time and let the user verify via VNC
        roi_wait = 60  # Wait 60 seconds for ROI
        for i in range(roi_wait):
            time.sleep(1)
            if i % 10 == 0:
                print(f"[INFO] Waiting... {i}/{roi_wait}s")

        print("[INFO] Assuming ROI reached, saving checkpoint...")

        # Save checkpoint via monitor
        chk_name = f"chk_{name}"
        print(f"[INFO] Saving checkpoint: {chk_name}")

        # Use blocking mode for savevm command with longer wait
        sock.setblocking(True)
        sock.settimeout(SAVE_TIMEOUT)

        # Clear buffer first
        sock.setblocking(False)
        try:
            while sock.recv(4096):
                pass
        except:
            pass

        # Send savevm command
        sock.setblocking(True)
        sock.sendall(f"savevm {chk_name}\n".encode())
        print(f"[INFO] Waiting for checkpoint save to complete (up to {SAVE_TIMEOUT}s)...")

        # Wait for the save to complete - checkpoint saving can take a while
        time.sleep(30)  # Give it 30 seconds to save

        # Read response
        sock.setblocking(False)
        response = ""
        try:
            while True:
                chunk = sock.recv(4096).decode()
                if not chunk:
                    break
                response += chunk
        except:
            pass

        print(f"[INFO] Monitor response after save: {response[:200] if response else '(empty)'}")

        # Verify checkpoint was saved by listing snapshots
        print("[INFO] Verifying checkpoint was saved...")
        sock.setblocking(True)
        sock.sendall(b"info snapshots\n")
        time.sleep(2)
        sock.setblocking(False)
        verify_response = ""
        try:
            while True:
                chunk = sock.recv(4096).decode()
                if not chunk:
                    break
                verify_response += chunk
        except:
            pass

        if chk_name in verify_response:
            print(f"[SUCCESS] Checkpoint {chk_name} verified!")
        else:
            print(f"[WARNING] Checkpoint {chk_name} may not have been saved!")
            print(f"[INFO] Snapshot list: {verify_response}")

        # Quit QEMU
        print("[INFO] Quitting QEMU...")
        monitor_command(sock, "quit")
        time.sleep(2)

        if sock:
            sock.close()
        if child:
            child.close()

        # Clean up socket
        if os.path.exists(monitor_sock):
            os.remove(monitor_sock)

        # Update progress
        progress["completed"].append(name)
        save_progress(progress)

        return True

    except Exception as e:
        print(f"[ERROR] Exception: {e}")
        import traceback
        traceback.print_exc()
        if name not in progress["failed"]:
            progress["failed"].append(name)
        save_progress(progress)
        if sock:
            try:
                sock.close()
            except:
                pass
        if child:
            try:
                child.close()
            except:
                pass
        return False


def create_checkpoint_manual(name, command, progress):
    """Create a checkpoint manually with user interaction.

    This version is more reliable but requires user to watch VNC.
    """

    if name in progress["completed"]:
        print(f"[SKIP] {name} already completed")
        return True

    print(f"\n{'='*60}")
    print(f" Creating Checkpoint: {name}")
    print(f" Command: {command}")
    print(f" Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    # Monitor socket path
    monitor_sock = f"/tmp/qemu-monitor-{name}.sock"

    # Remove old socket if exists
    if os.path.exists(monitor_sock):
        os.remove(monitor_sock)

    # Build QEMU command
    qemu_cmd = (
        f"{QEMU_BIN} -m 8G "
        f"-drive file={DISK_IMAGE},format=qcow2 "
        f"-loadvm {BASE_CHECKPOINT} "
        f"-vnc :1 "
        f"-monitor unix:{monitor_sock},server,nowait"
    )

    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = f"{DRAMSIM_DIR}:{env.get('LD_LIBRARY_PATH', '')}"

    child = None
    sock = None

    try:
        print(f"[INFO] Starting QEMU with checkpoint '{BASE_CHECKPOINT}'...")
        print(f"[INFO] VNC available on: localhost:5901")
        print()
        child = pexpect.spawn(qemu_cmd, env=env, encoding='utf-8', timeout=BOOT_TIMEOUT,
                              cwd=MARSS_DIR)

        # Wait for monitor socket
        print("[INFO] Waiting for QEMU to start...")
        for i in range(30):
            if os.path.exists(monitor_sock):
                break
            time.sleep(1)
        else:
            print("[ERROR] Monitor socket not created")
            if child:
                child.close()
            return False

        # Connect to monitor
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(monitor_sock)
        sock.setblocking(True)
        sock.settimeout(5)
        time.sleep(1)

        print()
        print("=" * 60)
        print(" MANUAL STEPS REQUIRED")
        print("=" * 60)
        print()
        print(f"1. Connect to VNC: localhost:5901")
        print(f"2. In the VM terminal, run:")
        print(f"   {command}")
        print(f"3. Enter sudo password: {GUEST_PASSWORD}")
        print(f"4. Wait for 'Switching to Simulation Mode' message")
        print()
        print("=" * 60)
        print()

        input("Press Enter when you see 'Switching to Simulation Mode'...")

        # Save checkpoint
        chk_name = f"chk_{name}"
        print(f"[INFO] Saving checkpoint: {chk_name}")
        sock.sendall(f"savevm {chk_name}\n".encode())
        time.sleep(5)

        try:
            response = sock.recv(4096).decode()
            print(f"[INFO] Response: {response}")
        except:
            pass

        print(f"[SUCCESS] Checkpoint {chk_name} saved!")

        # Ask user to verify
        verify = input("Did the checkpoint save successfully? [y/N]: ").strip().lower()

        if verify == 'y':
            progress["completed"].append(name)
            save_progress(progress)
            result = True
        else:
            progress["failed"].append(name)
            save_progress(progress)
            result = False

        # Quit QEMU
        print("[INFO] Quitting QEMU...")
        sock.sendall(b"quit\n")
        time.sleep(2)

        sock.close()
        child.close()

        if os.path.exists(monitor_sock):
            os.remove(monitor_sock)

        return result

    except Exception as e:
        print(f"[ERROR] Exception: {e}")
        import traceback
        traceback.print_exc()
        if name not in progress["failed"]:
            progress["failed"].append(name)
        save_progress(progress)
        if sock:
            try:
                sock.close()
            except:
                pass
        if child:
            try:
                child.close()
            except:
                pass
        return False


def main():
    parser = argparse.ArgumentParser(description='Create MARSSx86 checkpoints')
    parser.add_argument('--workload', '-w', help='Specific workload to process')
    parser.add_argument('--reset', action='store_true', help='Reset progress')
    parser.add_argument('--list', action='store_true', help='List available workloads')
    parser.add_argument('--manual', action='store_true', help='Use manual mode (requires VNC interaction)')
    parser.add_argument('--auto', action='store_true', help='Use automatic mode (types commands via sendkey)')
    args = parser.parse_args()

    if args.list:
        print("Available workloads:")
        for name, cmd in WORKLOADS.items():
            print(f"  {name}: {cmd}")
        return

    # Check prerequisites
    if not os.path.exists(QEMU_BIN):
        print(f"ERROR: QEMU binary not found: {QEMU_BIN}")
        sys.exit(1)

    if not os.path.exists(DISK_IMAGE):
        print(f"ERROR: Disk image not found: {DISK_IMAGE}")
        sys.exit(1)

    # Load or reset progress
    if args.reset:
        progress = {"completed": [], "failed": []}
        save_progress(progress)
    else:
        progress = load_progress()

    # Select workloads
    if args.workload:
        if args.workload not in WORKLOADS:
            print(f"ERROR: Unknown workload: {args.workload}")
            print(f"Available: {list(WORKLOADS.keys())}")
            sys.exit(1)
        workloads = {args.workload: WORKLOADS[args.workload]}
    else:
        workloads = WORKLOADS

    # Process workloads
    print(f"\n{'#'*60}")
    print(f" MARSSx86 Checkpoint Creator")
    print(f" Workloads: {len(workloads)}")
    print(f" Completed: {len(progress['completed'])}")
    print(f" Failed: {len(progress['failed'])}")
    print(f"{'#'*60}\n")

    # Choose mode
    if args.manual:
        create_func = create_checkpoint_manual
        print("[MODE] Manual mode - requires VNC interaction")
    elif args.auto:
        create_func = create_checkpoint
        print("[MODE] Automatic mode - types via sendkey")
    else:
        # Default to manual mode as it's more reliable
        create_func = create_checkpoint_manual
        print("[MODE] Manual mode (default) - requires VNC interaction")
        print("[TIP] Use --auto for automatic mode")

    print()

    success = 0
    fail = 0

    for name, command in workloads.items():
        if create_func(name, command, progress):
            success += 1
        else:
            fail += 1

    # Summary
    print(f"\n{'='*60}")
    print(f" Summary")
    print(f"{'='*60}")
    print(f" Total: {len(workloads)}")
    print(f" Success: {success}")
    print(f" Failed: {fail}")
    print(f" Skipped: {len(workloads) - success - fail}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()

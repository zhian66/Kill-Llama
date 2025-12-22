#!/usr/bin/env python3
"""
Automated Checkpoint Creator using Serial Console

This script uses serial console (-nographic) mode for reliable closed-loop
control of the Guest VM. It requires the Guest VM to be configured with
serial console output (base_serial checkpoint).

Prerequisites:
    1. Run setup_serial_console.sh to configure Guest VM GRUB
    2. Save 'base_serial' checkpoint with serial console enabled

Usage:
    python3 create_checkpoints_serial.py --workload stream_triad
    python3 create_checkpoints_serial.py --all
"""

import argparse
import os
import sys
import time
import signal
import socket
import pexpect
import subprocess
from datetime import datetime

# Configuration
PROJ_ROOT = "/home/ubuntu/sttmram/Kill-Llama"
MARSS_DIR = f"{PROJ_ROOT}/marss.dramsim"
QEMU_BIN = f"{MARSS_DIR}/qemu/qemu-system-x86_64"
DISK_IMAGE = f"{MARSS_DIR}/ubuntu_12_04.qcow2"
DRAMSIM_DIR = f"{PROJ_ROOT}/DRAMSim2"
MONITOR_SOCK = "/tmp/qemu-checkpoint-serial.sock"

# Workload definitions
WORKLOADS = {
    # STREAM benchmarks
    "stream_triad": "/home/user/benchmarks/stream_triad",
    "stream_copy": "/home/user/benchmarks/stream_copy",
    "stream_add": "/home/user/benchmarks/stream_add",
    "stream_scale": "/home/user/benchmarks/stream_scale",
    # GAP benchmarks
    "bfs": "/home/user/benchmarks/bfs /home/user/benchmarks/test_graph.sg",
    "sssp": "/home/user/benchmarks/sssp /home/user/benchmarks/test_graph.sg",
    "bc": "/home/user/benchmarks/bc /home/user/benchmarks/test_graph.sg",
    "cc": "/home/user/benchmarks/cc /home/user/benchmarks/test_graph.sg",
    "pr": "/home/user/benchmarks/pr /home/user/benchmarks/test_graph.sg",
    "tc": "/home/user/benchmarks/tc /home/user/benchmarks/test_graph.sg",
    # PARSEC benchmarks (using simlarge inputs)
    "blackscholes": "/home/user/benchmarks/blackscholes 1 /home/user/benchmarks/in_64K.txt /dev/null",
    "canneal": "/home/user/benchmarks/canneal 1 15000 2000 /home/user/benchmarks/400000.nets 128",
    "streamcluster": "/home/user/benchmarks/streamcluster 10 20 128 16384 16384 1000 none /dev/null 1",
    "fluidanimate": "/home/user/benchmarks/fluidanimate 1 5 /home/user/benchmarks/in_300K.fluid /dev/null",
    "swaptions": "/home/user/benchmarks/swaptions -ns 64 -sm 20000 -nt 1",
    "freqmine": "/home/user/benchmarks/freqmine /home/user/benchmarks/kosarak_990k.dat 790",
}

# Credentials
VM_USER = "user"
VM_PASS = "user"

# Timeout settings (increased for slow QEMU emulation)
BOOT_TIMEOUT = 600      # Time to wait for VM to boot (10 minutes)
LOGIN_TIMEOUT = 300     # Time to wait for login prompt (5 minutes)
PROMPT_TIMEOUT = 300    # Time to wait for shell prompt (5 minutes)
ROI_TIMEOUT = 1800      # Time to wait for ROI signal (30 minutes)


class QEMUController:
    """Control QEMU via serial console and monitor socket."""

    def __init__(self, base_checkpoint="base_serial"):
        self.base_checkpoint = base_checkpoint
        self.process = None
        self.monitor_sock = None

    def start(self):
        """Start QEMU with serial console."""
        # Set environment
        env = os.environ.copy()
        env["LD_LIBRARY_PATH"] = f"{DRAMSIM_DIR}:{env.get('LD_LIBRARY_PATH', '')}"

        # Remove old socket
        if os.path.exists(MONITOR_SOCK):
            os.remove(MONITOR_SOCK)

        # Build command
        cmd = [
            QEMU_BIN,
            "-m", "8G",
            "-drive", f"file={DISK_IMAGE},format=qcow2",
            "-loadvm", self.base_checkpoint,
            "-nographic",
            "-serial", "mon:stdio",
            "-monitor", f"unix:{MONITOR_SOCK},server,nowait",
        ]

        print(f"[INFO] Starting QEMU from checkpoint '{self.base_checkpoint}'...")
        print(f"[INFO] Command: {' '.join(cmd)}")

        # Start QEMU with pexpect
        self.process = pexpect.spawn(
            cmd[0],
            cmd[1:],
            cwd=MARSS_DIR,
            env=env,
            encoding='utf-8',
            timeout=BOOT_TIMEOUT,
        )

        # Enable logging for debug
        # self.process.logfile = sys.stdout

        # Wait for monitor socket
        print("[INFO] Waiting for QEMU monitor socket...")
        for i in range(30):
            if os.path.exists(MONITOR_SOCK):
                break
            time.sleep(1)
        else:
            raise RuntimeError("QEMU monitor socket not created")

        # Connect to monitor
        self.monitor_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.monitor_sock.connect(MONITOR_SOCK)
        self.monitor_sock.setblocking(True)
        self.monitor_sock.settimeout(5)

        # Read initial monitor banner
        try:
            self.monitor_sock.recv(4096)
        except socket.timeout:
            pass

        print("[INFO] QEMU started successfully")

    def wait_for_prompt(self):
        """Wait for shell prompt after checkpoint load."""
        print("[INFO] Waiting for shell prompt...")

        # Send newline to trigger prompt
        self.process.sendline("")

        try:
            # Look for typical Ubuntu prompt patterns
            patterns = [
                r'\$ ',           # user prompt
                r'# ',            # root prompt
                r'user@.*:.*\$',  # full user prompt
                r'root@.*:.*#',   # full root prompt
                r'login:',        # login prompt (need to login)
            ]

            index = self.process.expect(patterns, timeout=PROMPT_TIMEOUT)

            if index == 4:  # login prompt
                print("[INFO] Got login prompt, logging in...")
                self.process.sendline(VM_USER)
                self.process.expect([r'[Pp]assword:', r':'], timeout=LOGIN_TIMEOUT)
                self.process.sendline(VM_PASS)
                self.process.expect(patterns[:4], timeout=PROMPT_TIMEOUT)

            print("[INFO] Got shell prompt")
            return True

        except pexpect.TIMEOUT:
            print("[WARN] Timeout waiting for prompt, sending newline...")
            self.process.sendline("")
            try:
                self.process.expect(patterns[:4], timeout=10)
                print("[INFO] Got shell prompt after retry")
                return True
            except pexpect.TIMEOUT:
                print("[ERROR] Could not get shell prompt")
                return False

    def run_benchmark(self, workload_name, command):
        """Run benchmark and wait for ROI signal."""
        print(f"[INFO] Running: sudo {command}")

        # Run with sudo
        self.process.sendline(f"sudo {command}")

        # Handle sudo password
        try:
            index = self.process.expect([
                r'[Pp]assword.*:',
                r'Switching to Simulation',
                r'ptlcall_switch_to_sim',
                r'\$ ',
            ], timeout=30)

            if index == 0:  # Password prompt
                print("[INFO] Entering sudo password...")
                self.process.sendline(VM_PASS)

        except pexpect.TIMEOUT:
            print("[WARN] No password prompt, continuing...")

        # Wait for ROI signal
        print(f"[INFO] Waiting for ROI signal (timeout: {ROI_TIMEOUT}s)...")
        try:
            self.process.expect([
                r'Switching to Simulation',
                r'ptlcall_switch_to_sim',
                r'PTLSIM_ENTER',
            ], timeout=ROI_TIMEOUT)
            print("[SUCCESS] ROI signal detected!")
            return True

        except pexpect.TIMEOUT:
            print("[ERROR] Timeout waiting for ROI signal")
            print(f"[DEBUG] Last output: {self.process.before[-500:] if self.process.before else 'None'}")
            return False

    def save_checkpoint(self, name):
        """Save VM checkpoint via monitor."""
        print(f"[INFO] Saving checkpoint: {name}")

        # Clear any pending data
        try:
            self.monitor_sock.setblocking(False)
            self.monitor_sock.recv(4096)
        except (socket.timeout, BlockingIOError):
            pass
        self.monitor_sock.setblocking(True)

        # Send savevm command
        cmd = f"savevm {name}\n"
        self.monitor_sock.sendall(cmd.encode())

        # Wait for save to complete (can take a while)
        print("[INFO] Waiting for save to complete (this may take 30+ seconds)...")
        time.sleep(30)

        # Verify
        return self.verify_checkpoint(name)

    def verify_checkpoint(self, name):
        """Verify checkpoint exists."""
        print(f"[INFO] Verifying checkpoint: {name}")

        # Clear buffer
        try:
            self.monitor_sock.setblocking(False)
            self.monitor_sock.recv(4096)
        except (socket.timeout, BlockingIOError):
            pass
        self.monitor_sock.setblocking(True)
        self.monitor_sock.settimeout(10)

        # Query snapshots
        self.monitor_sock.sendall(b"info snapshots\n")
        time.sleep(2)

        try:
            response = self.monitor_sock.recv(8192).decode('utf-8', errors='ignore')
            if name in response:
                print(f"[SUCCESS] Checkpoint '{name}' verified!")
                # Print snapshot info
                for line in response.split('\n'):
                    if name in line or 'TAG' in line:
                        print(f"  {line.strip()}")
                return True
            else:
                print(f"[ERROR] Checkpoint '{name}' not found in snapshot list")
                print(f"[DEBUG] Response: {response}")
                return False
        except socket.timeout:
            print("[WARN] Timeout reading snapshot list")
            return False

    def quit(self):
        """Quit QEMU."""
        print("[INFO] Quitting QEMU...")
        try:
            self.monitor_sock.sendall(b"quit\n")
        except:
            pass
        time.sleep(2)

        if self.process:
            try:
                self.process.terminate(force=True)
            except:
                pass

        if self.monitor_sock:
            try:
                self.monitor_sock.close()
            except:
                pass

        # Cleanup socket file
        if os.path.exists(MONITOR_SOCK):
            os.remove(MONITOR_SOCK)


def create_checkpoint(workload_name, base_checkpoint="base_serial"):
    """Create checkpoint for a single workload."""
    if workload_name not in WORKLOADS:
        print(f"[ERROR] Unknown workload: {workload_name}")
        print(f"Available workloads: {', '.join(WORKLOADS.keys())}")
        return False

    command = WORKLOADS[workload_name]
    checkpoint_name = f"chk_{workload_name}"

    print("")
    print("=" * 60)
    print(f" Creating Checkpoint: {workload_name}")
    print(f" Command: sudo {command}")
    print(f" Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    print("")

    qemu = QEMUController(base_checkpoint)

    try:
        # Start QEMU
        qemu.start()

        # Wait for prompt
        if not qemu.wait_for_prompt():
            print("[ERROR] Failed to get shell prompt")
            return False

        # Run benchmark
        if not qemu.run_benchmark(workload_name, command):
            print("[ERROR] Failed to reach ROI")
            return False

        # Save checkpoint
        if not qemu.save_checkpoint(checkpoint_name):
            print("[ERROR] Failed to save checkpoint")
            return False

        print("")
        print(f"[SUCCESS] Checkpoint '{checkpoint_name}' created successfully!")
        return True

    except Exception as e:
        print(f"[ERROR] Exception: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        qemu.quit()


def main():
    parser = argparse.ArgumentParser(
        description="Create MARSSx86 checkpoints at ROI using serial console"
    )
    parser.add_argument(
        "--workload", "-w",
        help="Workload name (e.g., stream_triad)"
    )
    parser.add_argument(
        "--all", "-a",
        action="store_true",
        help="Create checkpoints for all workloads"
    )
    parser.add_argument(
        "--base", "-b",
        default="base_serial",
        help="Base checkpoint to load (default: base_serial)"
    )
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="List available workloads"
    )

    args = parser.parse_args()

    if args.list:
        print("Available workloads:")
        for name, cmd in WORKLOADS.items():
            print(f"  {name}: {cmd}")
        return 0

    if not args.workload and not args.all:
        parser.print_help()
        return 1

    # Check prerequisites
    if not os.path.exists(QEMU_BIN):
        print(f"[ERROR] QEMU not found: {QEMU_BIN}")
        return 1
    if not os.path.exists(DISK_IMAGE):
        print(f"[ERROR] Disk image not found: {DISK_IMAGE}")
        return 1

    # Print header
    print("")
    print("#" * 60)
    print(" MARSSx86 Checkpoint Creator (Serial Console Mode)")
    print(f" Base checkpoint: {args.base}")
    print("#" * 60)
    print("")

    results = {"success": [], "failed": []}

    if args.all:
        workloads = list(WORKLOADS.keys())
    else:
        workloads = [args.workload]

    for workload in workloads:
        success = create_checkpoint(workload, args.base)
        if success:
            results["success"].append(workload)
        else:
            results["failed"].append(workload)

    # Print summary
    print("")
    print("=" * 60)
    print(" Summary")
    print("=" * 60)
    print(f" Total: {len(workloads)}")
    print(f" Success: {len(results['success'])}")
    print(f" Failed: {len(results['failed'])}")
    if results["success"]:
        print(f" Successful: {', '.join(results['success'])}")
    if results["failed"]:
        print(f" Failed: {', '.join(results['failed'])}")
    print("=" * 60)
    print("")

    return 0 if not results["failed"] else 1


if __name__ == "__main__":
    sys.exit(main())

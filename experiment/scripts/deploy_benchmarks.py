#!/usr/bin/env python3
"""
Deploy Benchmarks to Guest VM
==============================

This script automates the deployment of benchmarks from the ISO to the guest VM.
It uses pexpect to interact with QEMU via the QEMU monitor.

Prerequisites:
- QEMU must be running with -monitor unix:/tmp/qemu-monitor.sock,server,nowait
- Or use -monitor stdio and run this script interactively

Usage:
    python3 deploy_benchmarks.py
"""

import os
import sys
import time
import subprocess

PROJ_ROOT = "/home/ubuntu/sttmram/Kill-Llama"
MARSS_DIR = f"{PROJ_ROOT}/marss.dramsim"
QEMU_BIN = f"{MARSS_DIR}/qemu/qemu-system-x86_64"
DISK_IMAGE = f"{MARSS_DIR}/ubuntu_12_04.qcow2"
ISO_PATH = f"{PROJ_ROOT}/benchmarks.iso"
DRAMSIM_DIR = f"{PROJ_ROOT}/DRAMSim2"


def print_instructions():
    """Print manual deployment instructions."""
    print("""
================================================================================
 BENCHMARK DEPLOYMENT INSTRUCTIONS
================================================================================

QEMU should now be running with VNC on port 5901.

1. Connect to VNC:
   - Use a VNC client to connect to: localhost:5901
   - Or use: vncviewer localhost:5901

2. Login to Guest VM:
   - Username: user
   - Password: user

3. Mount the CDROM and copy benchmarks:

   mkdir -p /home/user/benchmarks
   sudo mount /dev/cdrom /mnt
   cp -r /mnt/* /home/user/benchmarks/
   chmod +x /home/user/benchmarks/*
   sudo umount /mnt

4. Verify the benchmarks:

   ls -la /home/user/benchmarks/

5. Test one benchmark (requires sudo for ptlcalls):

   sudo /home/user/benchmarks/stream_triad
   # Password: user

   You should see "Switching to Simulation Mode..." output.

6. Save a base checkpoint (from QEMU monitor - press Ctrl+Alt+2):

   savevm base_deployed

================================================================================
""")


def start_qemu_interactive():
    """Start QEMU with interactive monitor."""
    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = f"{DRAMSIM_DIR}:{env.get('LD_LIBRARY_PATH', '')}"

    cmd = [
        QEMU_BIN,
        "-m", "4G",
        "-drive", f"file={DISK_IMAGE},format=qcow2",
        "-cdrom", ISO_PATH,
        "-nographic",
    ]

    print(f"Starting QEMU...")
    print(f"Command: {' '.join(cmd)}")
    print("\nQEMU will start in nographic mode.")
    print("Press Ctrl+A, C to switch between console and monitor.")
    print("Press Ctrl+A, X to exit QEMU.\n")

    subprocess.run(cmd, env=env)


def check_qemu_running():
    """Check if QEMU is already running."""
    result = subprocess.run(
        ["pgrep", "-f", "qemu-system-x86_64.*ubuntu_12_04"],
        capture_output=True, text=True
    )
    return result.returncode == 0


def main():
    if check_qemu_running():
        print("QEMU is already running!")
        print_instructions()
    else:
        print("QEMU is not running. Would you like to start it?")
        response = input("Start QEMU? [y/N]: ").strip().lower()
        if response == 'y':
            start_qemu_interactive()
        else:
            print_instructions()


if __name__ == "__main__":
    main()

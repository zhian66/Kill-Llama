# SMART STT-MRAM Paper Reproduction - Experiment Log

## Overview
Reproducing experiments from "Rethinking DRAM's Page Mode With STT-MRAM" paper using MARSSx86 + DRAMSim2 simulation.

---

## Phase 0: Environment Setup (COMPLETED)

### 0.1 Compiled Components
- MARSSx86 QEMU: `/home/ubuntu/sttmram/Kill-Llama/marss.dramsim/qemu/qemu-system-x86_64`
- DRAMSim2 library: `/home/ubuntu/sttmram/Kill-Llama/DRAMSim2/libdramsim.so`
- Guest VM disk image: `ubuntu_12_04.qcow2` (2GB)

### 0.2 Library Dependencies Fixed
- Created symlinks for ncurses compatibility:
  - `libncurses.so.5 -> /usr/lib/x86_64-linux-gnu/libncurses.so.6`
  - `libtinfo.so.5 -> /usr/lib/x86_64-linux-gnu/libtinfo.so.6`
- Built `libdramsim.so` from DRAMSim2 source

### 0.3 Memory Configuration Files
- `Baseline_DRAM.ini` - Standard DDR3 DRAM baseline
- `Conv-STT-MRAM.ini` - Conventional STT-MRAM
- `SMART.ini` - SMART STT-MRAM (proposed solution)

### 0.4 Address Mapping Schemes
- `system.ini` - Scheme 2 (Bank-level parallelism)
- `system_sch6.ini` - Scheme 6 (Row buffer hit optimized)

---

## Phase 1: Benchmark Compilation (COMPLETED)

### 1.1 STREAM Benchmarks (4 workloads)
Compiled with static linking and ptlcalls hooks:
- `stream_triad`
- `stream_copy`
- `stream_add`
- `stream_scale`

**Source location:** `/home/ubuntu/sttmram/Kill-Llama/bench_build/`

### 1.2 GAP Benchmarks (6 workloads)
Graph Analytics benchmarks with ptlcalls hooks:
- `bfs` - Breadth-First Search
- `sssp` - Single Source Shortest Path
- `bc` - Betweenness Centrality
- `cc` - Connected Components
- `pr` - PageRank
- `tc` - Triangle Counting

**Test graph:** `test_graph.sg` (small graph for testing)

### 1.3 PARSEC Benchmarks (6 workloads)
PARSEC 3.0 benchmarks compiled with hooks library:
- `blackscholes`
- `canneal`
- `streamcluster`
- `fluidanimate`
- `swaptions`
- `freqmine`

### 1.4 ISO Creation
Created `benchmarks.iso` (35MB) containing all compiled binaries.

---

## Phase 2: Guest VM Deployment (COMPLETED)

### 2.1 Guest VM Credentials
- Username: `user`
- Password: `user`
- Benchmarks require `sudo` to execute (for ptlcalls privilege)

### 2.2 Deployment Steps
1. Started QEMU with VNC on port 5901
2. Connected to VNC and logged in as `user`
3. Mounted CDROM: `sudo mount /dev/cdrom /mnt`
4. Copied benchmarks: `cp -r /mnt/* /home/user/benchmarks/`
5. Set permissions: `chmod +x /home/user/benchmarks/*`
6. Saved base checkpoint: `savevm base_deployed`

---

## Phase 3: Checkpoint Creation (IN PROGRESS)

### 3.1 Checkpoint Creation Script
**Script:** `/home/ubuntu/sttmram/Kill-Llama/experiment/scripts/create_checkpoints.py`

**Purpose:** Automatically create checkpoints at ROI (Region of Interest) start point for each workload.

**Flow:**
1. Load from `base_deployed` checkpoint
2. Execute benchmark with sudo
3. Wait for "Switching to Simulation Mode" message
4. Save checkpoint as `chk_{workload_name}`

### 3.2 Issues Encountered

#### Issue 1: QEMU BIOS not found
**Error:** `qemu: could not load PC BIOS 'bios.bin'`
**Solution:** Added `cwd=MARSS_DIR` parameter to pexpect.spawn() to run QEMU from the correct directory.

#### Issue 2: Shell prompt not detected
**Error:** `[WARN] Timeout waiting for prompt, trying to continue...`
**Possible cause:** The checkpoint may not restore the exact shell state, or the nographic console output is different than expected.
**Status:** Investigating...

---

## Phase 4: Pilot Test Execution (PENDING)

### 4.1 Pilot Test Configuration
- Workload: `stream_triad`
- Memory: `Baseline_DRAM.ini`
- Address mapping: `system_sch6.ini` (scheme 6)
- Instructions: 300M

### 4.2 Expected Output Files
- `DRAM_stream_triad_sch6_300M.stats` - Simulation statistics
- `DRAM_stream_triad_sch6_300M.console.log` - Console output
- `DRAM_stream_triad_sch6_300M_logs/` - DRAMSim2 detailed logs

---

## Troubleshooting Log

### 2025-12-22 15:50 - Checkpoint Creation Failure

**Attempt 1:**
```
python3 create_checkpoints.py --workload stream_triad
```
**Result:** Failed - BIOS not found
**Fix:** Added `cwd=MARSS_DIR` to pexpect.spawn() to run from correct directory

**Attempt 2:**
```
python3 create_checkpoints.py --reset --workload stream_triad
```
**Result:** Failed - Timeout waiting for shell prompt and ROI signal
**Analysis:** The `-nographic` mode is incompatible with checkpoint saved in VNC mode

**Solution:** Rewrote script to use VNC mode with QEMU monitor socket:
- Two modes available: `--manual` (default) and `--auto`
- Manual mode: User watches VNC and presses Enter when ROI is reached
- Auto mode: Uses `sendkey` to type commands (less reliable)
- Uses Unix socket for QEMU monitor commands
- Updated memory to 8G per user request

### 2025-12-22 16:00 - Script Rewrite

**Changes made:**
1. Added VNC mode support (port 5901)
2. Added QEMU monitor via Unix socket
3. Added `--manual` and `--auto` modes
4. Added `sendkey` command support for auto mode
5. Updated memory from 4G to 8G

**Next step:** Test with `--auto` mode for stream_triad

### 2025-12-22 16:05 - Auto Mode Test Result

**Command:**
```bash
python3 create_checkpoints.py --reset --workload stream_triad --auto
```

**Result:** Script reported success, but checkpoint `chk_stream_triad` was NOT saved.

**Existing snapshots in disk image:**
```
ID   TAG              VM SIZE   DATE               VM CLOCK
1    my_save          314M      2025-12-21 06:34   00:02:24.787
2    base_deployed    464M      2025-12-22 15:46   00:07:26.411
```

**Analysis:**
The auto mode using `sendkey` may not reliably type the command in the VM.
The 60-second fixed wait time is insufficient to ensure ROI is reached.

**Decision:** Use manual mode (`--manual`) which requires VNC interaction but is more reliable

### 2025-12-22 16:10 - Created Simple Checkpoint Script

Created `/home/ubuntu/sttmram/Kill-Llama/experiment/scripts/create_checkpoint_simple.sh`

**Usage:**

```bash
cd /home/ubuntu/sttmram/Kill-Llama/experiment/scripts
./create_checkpoint_simple.sh
```

**What it does:**

1. Starts QEMU loading `base_deployed` checkpoint
2. VNC available at `localhost:5901`
3. User runs benchmark in VNC and waits for ROI message
4. User presses Enter to save checkpoint
5. Saves as `chk_stream_triad`
6. Quits QEMU

**Status:** Ready to run

### 2025-12-22 16:10 - Fixed Auto Mode and Successfully Created Checkpoint

**Problems identified:**
1. Non-blocking socket caused `savevm` command response to be lost
2. `monitor_command()` only waited 0.5s, but `savevm` needs more time
3. No verification after saving checkpoint

**Fixes applied:**
1. Modified `monitor_command()` to properly handle blocking/non-blocking modes
2. Added 30-second wait time after `savevm` command
3. Added `info snapshots` verification after save
4. Clear socket buffer before sending commands

**Test Result:**
```bash
python3 create_checkpoints.py --workload stream_triad --auto
```
```
[SUCCESS] Checkpoint chk_stream_triad verified!
```

**Verified snapshots:**
```
ID   TAG               VM SIZE   DATE               VM CLOCK
1    my_save           314M      2025-12-21 06:34   00:02:24.787
2    base_deployed     464M      2025-12-22 15:46   00:07:26.411
3    chk_stream_triad   18M      2025-12-22 16:09   00:00:00.000
```

**Note:** VM SIZE is only 18M and VM CLOCK is 00:00:00.000, which suggests the checkpoint may have been saved before the benchmark actually started executing. This could mean:
- The `sendkey` commands didn't properly execute the benchmark
- The benchmark exited quickly
- Need to verify by running a pilot test

**Next step:** Run pilot test to verify checkpoint works correctly

### 2025-12-22 16:17 - Pilot Test Failed - Multiple Issues

**Problem 1:** DRAMSim2 library ABI mismatch

```
undefined symbol: _ZN7DRAMSim23getMemorySystemInstanceERKSsS1_S1_S1_jPSs
```

**Fix:** Rebuilt libdramsim.so with `-D_GLIBCXX_USE_CXX11_ABI=0` flag in Makefile

**Problem 2:** Machine type not found

```
::ERROR::Can't find 'single_core' machine generator.
```

**Fix:** Changed to use `quad_core` machine type (single_core needs to be generated from config)

**Problem 3:** MARSSx86 assertion failure

```
Assertion `ctx.get_cs_eip() == uop.rip' failed
```

**Analysis:**
The checkpoint was saved before the benchmark entered simulation mode.
VM SIZE of 18M and VM CLOCK of 00:00:00.000 confirms this.
The `sendkey` auto mode did NOT successfully execute the benchmark.

**Solution needed:**
Use manual checkpoint creation with VNC to ensure:
1. Command is typed correctly
2. Sudo password is entered
3. Benchmark starts executing
4. Wait for "Switching to Simulation Mode" message
5. THEN save checkpoint

### 2025-12-22 16:30 - Serial Console Solution Implemented

**Root Cause Analysis:**
The `sendkey` approach is fundamentally "blind" - it sends keystrokes without feedback.
This leads to unreliable automation because we can't verify:
- Commands were typed correctly
- Password was accepted
- Benchmark actually started

**Solution: Serial Console Mode**

Created two new scripts:

1. **`setup_serial_console.sh`** - Configure Guest VM for serial output
   - Modifies GRUB to output to `ttyS0`
   - Enables getty on serial console
   - Saves new `base_serial` checkpoint

2. **`create_checkpoints_serial.py`** - Proper closed-loop automation
   - Uses `-nographic -serial mon:stdio` for serial console access
   - Uses pexpect for closed-loop control (can see VM output)
   - Detects shell prompts, handles login, enters sudo password
   - Waits for actual "Switching to Simulation" signal
   - Then saves checkpoint at correct ROI point

**GRUB Configuration Required:**
```bash
# /etc/default/grub
GRUB_CMDLINE_LINUX_DEFAULT="console=tty0 console=ttyS0,115200n8"
GRUB_TERMINAL="console serial"
GRUB_SERIAL_COMMAND="serial --speed=115200 --unit=0 --word=8 --parity=no --stop=1"
```

**Getty Configuration (optional, for login via serial):**
```bash
# /etc/init/ttyS0.conf
start on runlevel [2345]
stop on runlevel [016]
respawn
exec /sbin/getty -L 115200 ttyS0 vt102
```

**Next Steps:**
1. Run `./setup_serial_console.sh` to configure Guest VM
2. Save `base_serial` checkpoint
3. Run `python3 create_checkpoints_serial.py --workload stream_triad`
4. Verify checkpoint with pilot test

---

## Notes

- Guest VM: Ubuntu 12.04 (32-bit compatible)
- Benchmarks must be run with `sudo` due to ptlcalls requiring kernel-level access
- QEMU must be run from `/home/ubuntu/sttmram/Kill-Llama/marss.dramsim/` directory for BIOS files

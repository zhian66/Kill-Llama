# MARSSx86 + DRAMSim2 自動化實驗指南

## 目錄
1. [架構概覽](#1-架構概覽)
2. [模式切換機制](#2-模式切換機制)
3. [如何判斷是否在錄數據](#3-如何判斷是否在錄數據)
4. [檔案準備](#4-檔案準備)
5. [Checkpoint 自動化建立](#5-checkpoint-自動化建立)
6. [批次實驗執行](#6-批次實驗執行)
7. [實戰範例](#7-實戰範例)

---

## 1. 架構概覽

### 角色與關係

```
┌─────────────────────────────────────────────────────────────────┐
│                         Host Machine                             │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                        QEMU                                │  │
│  │  ┌─────────────────────────────────────────────────────┐  │  │
│  │  │                   MARSSx86                           │  │  │
│  │  │  (Cycle-accurate CPU/Cache/Memory Simulation)       │  │  │
│  │  │                                                      │  │  │
│  │  │  ┌──────────────┐    ┌──────────────────────────┐   │  │  │
│  │  │  │  DRAMSim2    │◄───│  Memory Controller       │   │  │  │
│  │  │  │  (DRAM Model)│    │  Simulation              │   │  │  │
│  │  │  └──────────────┘    └──────────────────────────┘   │  │  │
│  │  └─────────────────────────────────────────────────────┘  │  │
│  │                           ▲                                │  │
│  │                           │ ptlcall (MMIO)                 │  │
│  │                           │                                │  │
│  │  ┌─────────────────────────────────────────────────────┐  │  │
│  │  │                    Guest VM                          │  │  │
│  │  │  ┌─────────────────────────────────────────────┐    │  │  │
│  │  │  │              Ubuntu 12.04                    │    │  │  │
│  │  │  │  ┌─────────────────────────────────────┐    │    │  │  │
│  │  │  │  │           Benchmark                  │    │    │  │  │
│  │  │  │  │  (STREAM, GAP, PARSEC)              │    │    │  │  │
│  │  │  │  │                                      │    │    │  │  │
│  │  │  │  │  ptlcall_switch_to_sim() ──────────────────────────► 開始模擬
│  │  │  │  │  ... ROI (Region of Interest) ...   │    │    │  │  │
│  │  │  │  │  ptlcall_kill() ───────────────────────────────────► 結束模擬
│  │  │  │  └─────────────────────────────────────┘    │    │  │  │
│  │  │  └─────────────────────────────────────────────┘    │  │  │
│  │  └─────────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### 三個核心角色

| 角色 | 功能 | 比喻 |
|------|------|------|
| **QEMU** | 硬體模擬器外殼，模擬硬碟、網卡、螢幕，讓 Guest OS 跑起來 | 上帝視角 |
| **MARSSx86** | 寄生在 QEMU 裡，進行 cycle-accurate CPU/Cache 模擬 | 慢速時間引擎 |
| **ptlcall** | Guest 與 MARSSx86 的通訊機制，用特殊 x86 指令觸發模式切換 | 紅色電話/緊急按鈕 |

### 兩種執行模式

| 模式 | 速度 | 精確度 | 用途 |
|------|------|--------|------|
| **Emulation Mode** | 快 (接近原生) | 低 (只管功能正確) | 開機、初始化、跳過非關鍵區段 |
| **Simulation Mode** | 慢 (1000x+) | 高 (cycle-accurate) | 錄製 ROI 數據 |

---

## 2. 模式切換機制

### 方法一：手動切換 (透過 QEMU Monitor)

適合除錯和初次測試。

```bash
# 啟動 QEMU with monitor
./qemu-system-x86_64 -m 8G \
  -drive file=ubuntu_12_04.qcow2 \
  -simconfig smart.simconfig \
  -vnc :2 -monitor stdio
```

在 QEMU monitor 中：
```
(qemu) sim_start    # 切換到 Simulation Mode，開始錄數據
(qemu) sim_stop     # 切換回 Emulation Mode，停止錄數據
(qemu) info ptlsim  # 查詢目前狀態
```

### 方法二：半自動切換 (ptlcall + simconfig)

Benchmark 執行到 ROI 時自動切換。

**simconfig 設定：**
```
-run                 # 收到 ptlcall 後自動開始模擬
-stopinsns 100000000 # 模擬 1 億條指令後停止
-kill-after-run      # 模擬結束後自動關閉 QEMU
```

**Benchmark 程式碼：**
```c
#include "ptlcalls.h"

int main() {
    // 初始化階段 (Emulation Mode, 快速執行)
    initialize_arrays();

    // 切換到 Simulation Mode
    ptlcall_switch_to_sim();

    // === ROI 開始 (Simulation Mode, 錄製數據) ===
    for (int i = 0; i < N; i++) {
        a[i] = b[i] + scalar * c[i];
    }
    // === ROI 結束 ===

    // 結束模擬並關閉
    ptlcall_kill();

    return 0;
}
```

**執行流程：**
```
1. QEMU 啟動 → Emulation Mode (快)
2. Benchmark 執行初始化
3. 執行到 ptlcall_switch_to_sim()
4. MARSSx86 偵測到信號 → 切換到 Simulation Mode (慢)
5. 錄製 ROI 數據
6. 執行到 ptlcall_kill()
7. 寫出統計數據 → QEMU 關閉
```

### 方法三：全自動切換 (Checkpoint)

使用預先建立的 Checkpoint，直接跳到 ROI 起點。

```bash
./qemu-system-x86_64 -m 8G \
  -drive file=ubuntu_12_04.qcow2 \
  -loadvm chk_stream_triad \      # 直接載入 checkpoint
  -simconfig smart.simconfig \
  -vnc :2 -monitor stdio
```

**優點：**
- 跳過開機和初始化，節省數小時
- 可重複執行相同起點
- 適合批次實驗

---

## 3. 如何判斷是否在錄數據

### 方法 1：觀察 Host CPU 使用率

```bash
# 在另一個終端機執行
top -p $(pgrep qemu)
```

| 狀態 | CPU 使用率 | 現象 |
|------|-----------|------|
| Emulation Mode | 波動 (10-50%) | 隨 Guest 負載變化 |
| Simulation Mode | 固定 100% | 單核心滿載計算每個 cycle |

### 方法 2：觀察 Log 檔案

```bash
# 監視統計檔案
tail -f /path/to/results/stats.log

# 檢查檔案大小是否增長
watch -n 1 ls -la /path/to/results/
```

### 方法 3：QEMU Monitor 查詢

```
(qemu) info ptlsim
```

輸出範例：
```
PTLsim Status: running           # 模擬中
Simulated cycles: 12345678
Simulated instructions: 9876543
```

### 方法 4：觀察 Console 輸出

MARSSx86 會定期輸出進度：
```
Completed      1000000 cycles,       800000 commits:    12345 Hz,    10000 insns/sec
Completed      2000000 cycles,      1600000 commits:    12340 Hz,    10005 insns/sec
```

---

## 4. 檔案準備

### 4.1 目錄結構

```
Kill-Llama/
├── marss.dramsim/
│   ├── qemu/qemu-system-x86_64    # MARSSx86 執行檔
│   ├── ubuntu_12_04.qcow2         # Guest VM 映像
│   └── smart.simconfig            # 模擬配置檔
├── DRAMSim2/
│   ├── ini/
│   │   ├── Baseline_DRAM.ini      # DRAM 配置
│   │   ├── Conv-STT-MRAM.ini      # STT-MRAM 配置
│   │   └── SMART.ini              # SMART 配置
│   ├── system_sch2.ini            # Address Mapping Scheme 2
│   └── system_sch6.ini            # Address Mapping Scheme 6
├── bench_build/
│   ├── stream_*.c                 # STREAM benchmark 原始碼
│   ├── ptlcalls.h                 # ptlcall 介面
│   └── iso_content/               # 編譯後的執行檔
└── experiment/
    ├── configs/                   # 實驗配置檔
    ├── scripts/                   # 自動化腳本
    └── results/                   # 實驗結果
```

### 4.2 simconfig 檔案格式

```bash
# === 核心配置 ===
-machine quad_core                    # CPU 架構 (single_core, dual_core, quad_core)

# === DRAMSim2 配置 ===
-dramsim-device-ini-file /path/to/Baseline_DRAM.ini
-dramsim-system-ini-file /path/to/system_sch6.ini
-dramsim-results-dir-name /path/to/results/

# === 模擬控制 ===
-run                                  # 收到 ptlcall 後自動開始
-stopinsns 100000000                  # 模擬指令數上限
-kill-after-run                       # 完成後自動關閉

# === 輸出控制 ===
-logfile /path/to/simulation.log
-loglevel 0                           # 0=minimal, 6=verbose
```

### 4.3 Benchmark 修改要點

**關鍵：使用 volatile 防止編譯器優化**

```c
// 錯誤：編譯器可能消除整個迴圈 (Dead Code Elimination)
static double a[N], b[N], c[N];

// 正確：volatile 強制編譯器保留所有記憶體存取
static volatile double a[N], b[N], c[N];
```

**驗證方式：**
```bash
# 檢查編譯後的組合語言是否包含迴圈
objdump -d stream_triad | grep -c "jne\|jl\|jg"
# 應該要有數千個跳轉指令，如果只有幾十個就有問題
```

---

## 5. Checkpoint 自動化建立

### 5.1 手動建立單一 Checkpoint

```bash
# 1. 啟動 QEMU (不使用 simconfig，純 Emulation Mode)
./qemu-system-x86_64 -m 8G \
  -drive file=ubuntu_12_04.qcow2 \
  -vnc :2 -monitor stdio

# 2. 在 VNC 中執行 benchmark 到 ROI 起點
#    (程式會印出 "Starting simulation..." 然後暫停)

# 3. 在 QEMU monitor 中儲存
(qemu) savevm chk_stream_triad

# 4. 驗證
(qemu) info snapshots
```

### 5.2 使用 stopinsns 自動暫停

建立 `create_checkpoint.simconfig`：
```
-machine quad_core
-dramsim-device-ini-file /path/to/Baseline_DRAM.ini
-dramsim-system-ini-file /path/to/system_sch6.ini
-dramsim-results-dir-name /path/to/results/
-stopinsns 100    # 進入 Simulation Mode 後 100 條指令自動暫停
```

```bash
# 啟動後執行 benchmark，會在 ROI 開始後自動暫停
./qemu-system-x86_64 -m 8G \
  -drive file=ubuntu_12_04.qcow2 \
  -simconfig create_checkpoint.simconfig \
  -vnc :2 -monitor stdio

# 暫停後在 monitor 儲存
(qemu) savevm chk_stream_triad
```

### 5.3 Python 自動化腳本

```python
#!/usr/bin/env python3
"""
create_checkpoints.py - 自動建立所有 benchmark 的 checkpoint
"""

import pexpect
import time
import sys

# Benchmark 清單
BENCHMARKS = {
    "stream_triad": "sudo ~/benchmarks/stream_triad",
    "stream_copy":  "sudo ~/benchmarks/stream_copy",
    "stream_add":   "sudo ~/benchmarks/stream_add",
    "stream_scale": "sudo ~/benchmarks/stream_scale",
    "bfs":          "sudo ~/benchmarks/bfs -g 10 -n 1",
    "sssp":         "sudo ~/benchmarks/sssp -g 10 -n 1",
    # ... 其他 benchmarks
}

QEMU_CMD = """
./qemu-system-x86_64 -m 8G \
  -drive file=ubuntu_12_04.qcow2 \
  -simconfig create_checkpoint.simconfig \
  -nographic
"""

def create_checkpoint(name, cmd):
    print(f"=== Creating checkpoint for {name} ===")

    # 啟動 QEMU
    child = pexpect.spawn(QEMU_CMD, timeout=600)
    child.logfile = sys.stdout.buffer

    # 等待 Shell prompt
    child.expect(r"\$")

    # 執行 benchmark
    child.sendline(cmd)

    # 等待進入 Simulation Mode (MARSSx86 會印出這行)
    child.expect("Switching to simulation mode", timeout=300)

    # 進入 QEMU Monitor (Ctrl-A C)
    child.send("\x01c")
    child.expect("(qemu)")

    # 儲存 checkpoint
    chk_name = f"chk_{name}"
    child.sendline(f"savevm {chk_name}")
    child.expect("(qemu)", timeout=600)  # 儲存可能需要幾分鐘

    # 關閉
    child.sendline("quit")
    child.close()

    print(f"=== Checkpoint {chk_name} created! ===\n")

if __name__ == "__main__":
    for name, cmd in BENCHMARKS.items():
        create_checkpoint(name, cmd)
```

---

## 6. 批次實驗執行

### 6.1 實驗矩陣

| 維度 | 選項 | 數量 |
|------|------|------|
| Memory Config | Baseline_DRAM, Conv-STT-MRAM, SMART | 3 |
| Address Mapping | scheme2, scheme6 | 2 |
| Benchmarks | STREAM(4) + GAP(6) + PARSEC(6) | 16 |
| **總計** | | **96 runs** |

### 6.2 Shell 批次腳本

```bash
#!/bin/bash
# run_experiments.sh - 批次執行所有實驗

# 配置
QEMU_DIR="/home/ubuntu/sttmram/Kill-Llama/marss.dramsim"
DRAMSIM_DIR="/home/ubuntu/sttmram/Kill-Llama/DRAMSim2"
RESULTS_BASE="/home/ubuntu/sttmram/Kill-Llama/experiment/results"

# 實驗參數
MEMORY_CONFIGS=("Baseline_DRAM" "Conv-STT-MRAM" "SMART")
ADDR_SCHEMES=("sch2" "sch6")
BENCHMARKS=("stream_triad" "stream_copy" "stream_add" "stream_scale"
            "bfs" "sssp" "bc" "cc" "pr" "tc")

# 建立結果目錄
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RESULTS_DIR="${RESULTS_BASE}/run_${TIMESTAMP}"
mkdir -p "$RESULTS_DIR"

# 設定環境
export LD_LIBRARY_PATH="${DRAMSIM_DIR}:$LD_LIBRARY_PATH"
cd "$QEMU_DIR"

# 執行實驗
for MEM in "${MEMORY_CONFIGS[@]}"; do
    for SCHEME in "${ADDR_SCHEMES[@]}"; do
        for BENCH in "${BENCHMARKS[@]}"; do

            RUN_NAME="${MEM}_${BENCH}_${SCHEME}"
            echo "=== Running: $RUN_NAME ==="

            # 建立結果子目錄
            RUN_DIR="${RESULTS_DIR}/${RUN_NAME}"
            mkdir -p "$RUN_DIR"

            # 動態生成 simconfig
            cat > "${RUN_DIR}/run.simconfig" << EOF
-machine quad_core
-dramsim-device-ini-file ${DRAMSIM_DIR}/ini/${MEM}.ini
-dramsim-system-ini-file ${DRAMSIM_DIR}/system_${SCHEME}.ini
-dramsim-results-dir-name ${RUN_DIR}
-logfile ${RUN_DIR}/marss.log
-loglevel 0
-run
-stopinsns 100000000
-kill-after-run
EOF

            # 執行模擬
            ./qemu/qemu-system-x86_64 -m 8G \
                -drive file=ubuntu_12_04.qcow2 \
                -loadvm "chk_${BENCH}" \
                -simconfig "${RUN_DIR}/run.simconfig" \
                -nographic \
                > "${RUN_DIR}/qemu.log" 2>&1

            echo "=== Completed: $RUN_NAME ==="

        done
    done
done

echo "All experiments completed!"
echo "Results saved to: $RESULTS_DIR"
```

### 6.3 平行執行 (多核心機器)

```bash
#!/bin/bash
# run_parallel.sh - 平行執行多個實驗

MAX_PARALLEL=4  # 同時執行的實驗數量
RUNNING=0

run_single() {
    local MEM=$1
    local SCHEME=$2
    local BENCH=$3

    # ... (與上面相同的執行邏輯)

    ./qemu/qemu-system-x86_64 ... &
}

for MEM in "${MEMORY_CONFIGS[@]}"; do
    for SCHEME in "${ADDR_SCHEMES[@]}"; do
        for BENCH in "${BENCHMARKS[@]}"; do

            # 等待有空位
            while [ $RUNNING -ge $MAX_PARALLEL ]; do
                wait -n
                RUNNING=$((RUNNING - 1))
            done

            # 啟動新實驗
            run_single "$MEM" "$SCHEME" "$BENCH" &
            RUNNING=$((RUNNING + 1))

        done
    done
done

# 等待所有完成
wait
echo "All parallel experiments completed!"
```

---

## 7. 實戰範例

### 範例：執行 stream_triad with Baseline_DRAM + scheme6

**步驟 1：確認 Checkpoint 存在**
```bash
./qemu/qemu-system-x86_64 -m 8G \
  -drive file=ubuntu_12_04.qcow2 \
  -monitor stdio << EOF
info snapshots
quit
EOF
```

**步驟 2：建立 simconfig**
```bash
cat > experiment.simconfig << 'EOF'
-machine quad_core
-dramsim-device-ini-file /home/ubuntu/sttmram/Kill-Llama/DRAMSim2/ini/Baseline_DRAM.ini
-dramsim-system-ini-file /home/ubuntu/sttmram/Kill-Llama/DRAMSim2/system_sch6.ini
-dramsim-results-dir-name /home/ubuntu/sttmram/Kill-Llama/experiment/results/test_run
-logfile /home/ubuntu/sttmram/Kill-Llama/experiment/results/test_run/marss.log
-loglevel 0
-run
-stopinsns 100000000
-kill-after-run
EOF
```

**步驟 3：執行模擬**
```bash
export LD_LIBRARY_PATH=/home/ubuntu/sttmram/Kill-Llama/DRAMSim2:$LD_LIBRARY_PATH
mkdir -p /home/ubuntu/sttmram/Kill-Llama/experiment/results/test_run

./qemu/qemu-system-x86_64 -m 8G \
  -drive file=ubuntu_12_04.qcow2 \
  -loadvm chk_stream_triad \
  -simconfig experiment.simconfig \
  -nographic
```

**步驟 4：檢查結果**
```bash
ls -la /home/ubuntu/sttmram/Kill-Llama/experiment/results/test_run/
cat /home/ubuntu/sttmram/Kill-Llama/experiment/results/test_run/marss.log
```

---

## 附錄：常見問題排解

### Q1: Simulation 只執行幾百條指令就結束

**可能原因：**
- 編譯器優化消除了 ROI 迴圈
- Checkpoint 載入的是舊版 benchmark

**解決方案：**
```bash
# 檢查 benchmark 是否有足夠的迴圈指令
objdump -d ~/benchmarks/stream_triad | grep -c jne
# 應該要有數千個，如果只有幾十個就需要重新編譯 (加 volatile)
```

### Q2: 出現 "kernel tried to execute NX-protected page" 錯誤

**可能原因：**
- QEMU 沒有載入 simconfig
- ptlcall MMIO 映射失敗

**解決方案：**
- 確認啟動命令有 `-simconfig` 參數
- 使用 `sudo` 執行 benchmark

### Q3: DRAMSim2 報錯 "Cannot open .vis file"

**可能原因：**
- 結果目錄不存在或沒有寫入權限

**解決方案：**
```bash
mkdir -p /path/to/results
chmod 755 /path/to/results
```

### Q4: Checkpoint 儲存需要很久

**這是正常的。** 8GB RAM 的 VM checkpoint 可能需要 5-10 分鐘。

**優化方案：**
- 減少 VM RAM (如果 benchmark 允許)
- 使用 SSD 存儲

---

## 參考資料

- [MARSSx86 官方文檔](http://marss86.org/)
- [DRAMSim2 GitHub](https://github.com/umd-memsys/DRAMSim2)
- [PARSEC Benchmark Suite](https://parsec.cs.princeton.edu/)
- [STREAM Benchmark](https://www.cs.virginia.edu/stream/)

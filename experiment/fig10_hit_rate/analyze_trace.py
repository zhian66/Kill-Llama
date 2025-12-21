#!/usr/bin/env python3
"""
分析 DRAMSim2 trace 檔案，計算地址映射並檢測潛在的碰撞問題
"""

import sys
from collections import defaultdict

# DRAMSim2 地址映射參數 (Scheme2: chan:row:col:bank:rank)
BYTE_OFFSET_WIDTH = 3
COL_LOW_BIT_WIDTH = 3
RANK_BIT_WIDTH = 0
BANK_BIT_WIDTH = 4
COL_HIGH_BIT_WIDTH = 7
ROW_BIT_WIDTH = 16
CHANNEL_BIT_WIDTH = 0

TOTAL_BITS = BYTE_OFFSET_WIDTH + COL_LOW_BIT_WIDTH + RANK_BIT_WIDTH + \
             BANK_BIT_WIDTH + COL_HIGH_BIT_WIDTH + ROW_BIT_WIDTH + CHANNEL_BIT_WIDTH

def address_mapping(addr):
    """模擬 DRAMSim2 Scheme2 地址映射"""
    original_addr = addr

    # 保存被截斷的高位
    total_used_bits = BYTE_OFFSET_WIDTH + COL_LOW_BIT_WIDTH + BANK_BIT_WIDTH + \
                      COL_HIGH_BIT_WIDTH + ROW_BIT_WIDTH
    truncated_high = addr >> total_used_bits

    # Step 1: 移除 byte offset
    addr >>= BYTE_OFFSET_WIDTH

    # Step 2: 移除 colLow
    addr >>= COL_LOW_BIT_WIDTH

    # Step 3: 提取 rank
    if RANK_BIT_WIDTH > 0:
        rank = addr & ((1 << RANK_BIT_WIDTH) - 1)
        addr >>= RANK_BIT_WIDTH
    else:
        rank = 0

    # Step 4: 提取 bank
    bank = addr & ((1 << BANK_BIT_WIDTH) - 1)
    addr >>= BANK_BIT_WIDTH

    # Step 5: 提取 colHigh
    col = addr & ((1 << COL_HIGH_BIT_WIDTH) - 1)
    addr >>= COL_HIGH_BIT_WIDTH

    # Step 6: 提取 row
    row = addr & ((1 << ROW_BIT_WIDTH) - 1)
    addr >>= ROW_BIT_WIDTH

    return {
        'rank': rank,
        'bank': bank,
        'row': row,
        'col': col,
        'truncated_high': truncated_high,
        'original_addr': original_addr
    }

def format_binary(addr, bank, row, col):
    """格式化為二進位表示"""
    # 格式: [truncated_high] [row:16] [col:7] [bank:4] [colLow:3] [offset:3]
    row_bin = format(row, '016b')
    col_bin = format(col, '07b')
    bank_bin = format(bank, '04b')
    return f"{row_bin} {col_bin} {bank_bin}"

def analyze_trace(trace_file, output_file, max_lines=None):
    """分析 trace 檔案"""

    # 統計資料
    stats = {
        'total_transactions': 0,
        'reads': 0,
        'writes': 0,
        'unique_rows': defaultdict(set),  # bank -> set of rows
        'row_access_count': defaultdict(lambda: defaultdict(int)),  # bank -> row -> count
        'truncated_addresses': 0,  # 有被截斷高位的地址數
        'collision_groups': defaultdict(list),  # (bank, row) -> list of original addresses
    }

    with open(trace_file, 'r') as f_in, open(output_file, 'w') as f_out:
        f_out.write("# DRAMSim2 Trace Analysis\n")
        f_out.write(f"# Address Mapping: Scheme2 (chan:row:col:bank:rank)\n")
        f_out.write(f"# Total used bits: {TOTAL_BITS} (33-bit addressable = 8GB)\n")
        f_out.write("# Format: [row:16bit] [col:7bit] [bank:4bit]\n")
        f_out.write("#" + "="*80 + "\n\n")

        for line_num, line in enumerate(f_in, 1):
            if max_lines and line_num > max_lines:
                break

            parts = line.strip().split()
            if len(parts) < 3:
                continue

            addr_str, op, cycle = parts[0], parts[1], parts[2]
            addr = int(addr_str, 16)

            # 地址映射
            mapping = address_mapping(addr)

            # 更新統計
            stats['total_transactions'] += 1
            if op == 'READ':
                stats['reads'] += 1
            else:
                stats['writes'] += 1

            bank = mapping['bank']
            row = mapping['row']

            stats['unique_rows'][bank].add(row)
            stats['row_access_count'][bank][row] += 1

            if mapping['truncated_high'] != 0:
                stats['truncated_addresses'] += 1

            # 記錄碰撞
            key = (bank, row)
            stats['collision_groups'][key].append(mapping['original_addr'])

            # 輸出格式化結果
            binary_repr = format_binary(addr, bank, row, mapping['col'])
            truncated_warning = " [TRUNCATED!]" if mapping['truncated_high'] != 0 else ""

            f_out.write(f"{line_num}. {addr_str} {op} (cycle {cycle})\n")
            f_out.write(f"    - Bank: {bank}, Row: {row}, Col: {mapping['col']}\n")
            f_out.write(f"    - Binary: {binary_repr}\n")
            if mapping['truncated_high'] != 0:
                f_out.write(f"    - WARNING: High bits truncated: {hex(mapping['truncated_high'])}\n")
            f_out.write("\n")

            # 進度顯示
            if line_num % 100000 == 0:
                print(f"Processed {line_num} lines...")

        # 寫入統計摘要
        f_out.write("\n" + "="*80 + "\n")
        f_out.write("# STATISTICS SUMMARY\n")
        f_out.write("="*80 + "\n\n")

        f_out.write(f"Total Transactions: {stats['total_transactions']}\n")
        f_out.write(f"  - READs: {stats['reads']}\n")
        f_out.write(f"  - WRITEs: {stats['writes']}\n")
        f_out.write(f"  - Truncated Addresses: {stats['truncated_addresses']} ({100*stats['truncated_addresses']/stats['total_transactions']:.2f}%)\n\n")

        f_out.write("Per-Bank Statistics:\n")
        for bank in sorted(stats['unique_rows'].keys()):
            unique_rows = len(stats['unique_rows'][bank])
            total_accesses = sum(stats['row_access_count'][bank].values())
            f_out.write(f"  Bank {bank}: {unique_rows} unique rows, {total_accesses} total accesses\n")

        # 檢測碰撞
        f_out.write("\n" + "="*80 + "\n")
        f_out.write("# COLLISION ANALYSIS (different addresses mapping to same bank/row)\n")
        f_out.write("="*80 + "\n\n")

        collision_count = 0
        for (bank, row), addrs in stats['collision_groups'].items():
            unique_addrs = set(addrs)
            if len(unique_addrs) > 1:
                collision_count += 1
                if collision_count <= 20:  # 只顯示前 20 個碰撞
                    f_out.write(f"Bank {bank}, Row {row}: {len(unique_addrs)} different addresses\n")
                    for a in sorted(unique_addrs)[:5]:  # 只顯示前 5 個地址
                        f_out.write(f"    - {hex(a)}\n")
                    if len(unique_addrs) > 5:
                        f_out.write(f"    ... and {len(unique_addrs)-5} more\n")
                    f_out.write("\n")

        f_out.write(f"\nTotal collision groups: {collision_count}\n")

        # Row Hit Rate 影響分析
        f_out.write("\n" + "="*80 + "\n")
        f_out.write("# ROW HIT RATE IMPACT ANALYSIS\n")
        f_out.write("="*80 + "\n\n")

        # 計算理論 row hit rate (假設 open page policy)
        total_hits = 0
        total_misses = 0

        # 模擬 open page: 第一次存取 row 是 miss，之後都是 hit
        for bank in stats['row_access_count']:
            for row, count in stats['row_access_count'][bank].items():
                total_misses += 1  # 第一次存取
                total_hits += count - 1  # 後續存取

        theoretical_hit_rate = 100 * total_hits / (total_hits + total_misses) if (total_hits + total_misses) > 0 else 0

        f_out.write(f"Theoretical Row Hit Rate (perfect open page):\n")
        f_out.write(f"  - Hits: {total_hits}\n")
        f_out.write(f"  - Misses: {total_misses}\n")
        f_out.write(f"  - Hit Rate: {theoretical_hit_rate:.2f}%\n\n")

        if stats['truncated_addresses'] > 0:
            f_out.write("WARNING: Address truncation detected!\n")
            f_out.write("  The trace contains addresses larger than 33-bit (8GB).\n")
            f_out.write("  High bits are being ignored, which may cause:\n")
            f_out.write("  1. False row buffer hits (different memory locations mapped to same row)\n")
            f_out.write("  2. Inaccurate simulation results\n")

    return stats

if __name__ == "__main__":
    trace_file = "/home/ubuntu/sttmram/Kill-Llama/benchmark/traces/trc/STREAM/stream_add.trc"
    output_file = "/home/ubuntu/sttmram/Kill-Llama/experiment/hit_rate_fig10/trace_analysis.txt"

    # 可以設定 max_lines 來限制分析的行數，None 表示分析全部
    max_lines = None  # 設為 1000 可以快速測試

    print(f"Analyzing trace file: {trace_file}")
    print(f"Output will be written to: {output_file}")

    stats = analyze_trace(trace_file, output_file, max_lines)

    print(f"\nDone! Processed {stats['total_transactions']} transactions.")
    print(f"Results saved to: {output_file}")

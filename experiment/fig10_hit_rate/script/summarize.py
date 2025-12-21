#!/usr/bin/env python3
"""
Summarize Row Buffer Hit Rate results from trace_log directory.

Usage: python3 summarize.py [trace_log_dir]
"""

import os
import re
import sys
from pathlib import Path

def parse_hit_rate(filepath):
    """
    Extract cumulative Row Buffer Hit Rate from log file.

    DRAMSim2 output format:
    - Row Buffer Hits: cumulative value (total hits from simulation start)
    - Row Buffer Hit Rate: directly calculated hit rate percentage

    We use the last Row Buffer Hit Rate value (final cumulative result).
    """
    try:
        with open(filepath, 'r') as f:
            content = f.read()

        # Use the last hit rate value (cumulative result at end of simulation)
        matches = re.findall(r'Row Buffer Hit Rate\s*:\s*([\d.]+)%', content)
        if matches:
            return float(matches[-1])
    except Exception as e:
        print(f"Warning: Could not parse {filepath}: {e}")
    return None

def main():
    # Default to trace_log in experiment directory
    if len(sys.argv) > 1:
        log_dir = Path(sys.argv[1])
    else:
        script_dir = Path(__file__).parent
        log_dir = script_dir.parent / "trace_log"

    if not log_dir.exists():
        print(f"Error: Directory not found: {log_dir}")
        return 1

    # Collect results
    results = {}  # {config: {benchmark: hit_rate}}

    # Known config names
    known_configs = {'DRAM', 'Conv', 'SMART'}

    for log_file in log_dir.glob("*.log"):
        # Parse filename: CONFIG_BENCHMARK_DATE.log
        # e.g., Conv_bc_1220.log -> config=Conv, benchmark=bc
        name = log_file.stem
        parts = name.split('_')

        if len(parts) < 3:
            continue

        config = parts[0]
        if config not in known_configs:
            continue

        # Benchmark is everything between config and date (last part)
        benchmark = '_'.join(parts[1:-1])
        if not benchmark:
            continue

        hit_rate = parse_hit_rate(log_file)

        if config not in results:
            results[config] = {}
        results[config][benchmark] = hit_rate

    if not results:
        print("No results found!")
        return 1

    # Print summary table
    configs = sorted(results.keys())
    benchmarks = sorted(set(b for cfg in results.values() for b in cfg.keys()))

    # Header
    print("\n" + "=" * 70)
    print("Row Buffer Hit Rate Summary")
    print("=" * 70)
    header = f"{'Benchmark':<15}" + "".join(f"{c:>12}" for c in configs)
    print(header)
    print("-" * len(header))

    # Data
    for benchmark in benchmarks:
        row = f"{benchmark:<15}"
        for config in configs:
            rate = results.get(config, {}).get(benchmark)
            if rate is not None:
                row += f"{rate:>11.2f}%"
            else:
                row += f"{'N/A':>12}"
        print(row)

    print("=" * 70)

    # Save to CSV
    csv_path = log_dir / "summary.csv"
    with open(csv_path, 'w') as f:
        f.write("Benchmark," + ",".join(configs) + "\n")
        for benchmark in benchmarks:
            row = [benchmark]
            for config in configs:
                rate = results.get(config, {}).get(benchmark)
                row.append(f"{rate:.2f}" if rate else "")
            f.write(",".join(row) + "\n")

    print(f"\nCSV saved to: {csv_path}")
    return 0

if __name__ == '__main__':
    sys.exit(main())

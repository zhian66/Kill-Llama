#!/usr/bin/env python3
"""
Summarize Latency Profile results from trace_log directory.

Parses DRAMSim2 latency histogram output and aggregates across all epochs.

Usage: python3 summarize.py [trace_log_dir]
"""

import os
import re
import sys
from pathlib import Path
from collections import defaultdict


def parse_latency_histogram(filepath):
    """
    Extract latency histogram from log file.

    DRAMSim2 output format:
    ---  Latency list (N)
       [lat] : #
       [10-19] : 1234
       [20-29] : 5678
       ...

    Returns:
        dict: {latency_bin: count} aggregated across all epochs
    """
    histogram = defaultdict(int)

    try:
        with open(filepath, 'r') as f:
            content = f.read()

        # Find all latency entries: [min-max] : count
        pattern = r'\[(\d+)-(\d+)\]\s*:\s*(\d+)'
        matches = re.findall(pattern, content)

        for min_lat, max_lat, count in matches:
            # Use the middle of the bin as the key
            bin_start = int(min_lat)
            histogram[bin_start] += int(count)

    except Exception as e:
        print(f"Warning: Could not parse {filepath}: {e}")

    return dict(histogram)


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
    results = {}  # {config: {latency_bin: count}}

    # Known config names
    known_configs = {'DRAM', 'Conv', 'SMART'}

    for log_file in log_dir.glob("*.log"):
        # Parse filename: CONFIG_BENCHMARK_DATE.log
        name = log_file.stem
        parts = name.split('_')

        if len(parts) < 3:
            continue

        config = parts[0]
        if config not in known_configs:
            continue

        histogram = parse_latency_histogram(log_file)

        if config not in results:
            results[config] = defaultdict(int)

        # Aggregate histograms
        for lat_bin, count in histogram.items():
            results[config][lat_bin] += count

    if not results:
        print("No results found!")
        return 1

    # Print summary
    print("\n" + "=" * 70)
    print("Latency Histogram Summary (stream_triad)")
    print("=" * 70)

    # Get all latency bins
    all_bins = sorted(set(b for cfg in results.values() for b in cfg.keys()))
    configs = sorted(results.keys())

    # Header
    header = f"{'Latency[ns]':<15}" + "".join(f"{c:>12}" for c in configs)
    print(header)
    print("-" * len(header))

    # Data
    for lat_bin in all_bins:
        row = f"{lat_bin:<15}"
        for config in configs:
            count = results.get(config, {}).get(lat_bin, 0)
            row += f"{count:>12}"
        print(row)

    print("=" * 70)

    # Calculate statistics
    print("\nStatistics:")
    for config in configs:
        hist = results[config]
        total_requests = sum(hist.values())
        if total_requests > 0:
            weighted_sum = sum(lat * count for lat, count in hist.items())
            avg_latency = weighted_sum / total_requests
            max_latency = max(hist.keys()) if hist else 0
            min_latency = min(hist.keys()) if hist else 0
            print(f"  {config}: Total={total_requests}, Avg={avg_latency:.1f}ns, "
                  f"Min={min_latency}ns, Max={max_latency}ns")

    # Save to CSV
    csv_path = log_dir / "latency_histogram.csv"
    with open(csv_path, 'w') as f:
        f.write("Latency_ns," + ",".join(configs) + "\n")
        for lat_bin in all_bins:
            row = [str(lat_bin)]
            for config in configs:
                count = results.get(config, {}).get(lat_bin, 0)
                row.append(str(count))
            f.write(",".join(row) + "\n")

    print(f"\nCSV saved to: {csv_path}")
    return 0


if __name__ == '__main__':
    sys.exit(main())

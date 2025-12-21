#!/usr/bin/env python3
"""
Row Buffer Hit Rate Chart Generator for STT-MRAM Paper Reproduction

Generates line charts comparing hit rates across:
- DRAM (baseline)
- Conv (Conventional STT-MRAM)
- SMART (proposed architecture)

Usage:
    python plot_hit_rate.py [--results-dir PATH] [--output PATH]
"""

import os
import re
import glob
import argparse
from collections import defaultdict
from typing import Dict, List, Tuple, Optional

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np

# Benchmark order matching the paper's Figure 10
BENCHMARK_ORDER = [
    # SPEC CPU 2017 + GAP (sorted by type)
    'bc', 'bfs', 'cc', 'imagick', 'lbm', 'mcf', 'nab', 'omnetpp', 'pr', 'sssp',
    # STREAM benchmarks
    'stream_add', 'stream_copy', 'stream_scale', 'stream_triad',
    # Others
    'tc', 'xalancbmk',
    # Mixed workloads
    'mix1', 'mix2', 'mix3', 'mix4', 'mix5', 'mix6', 'mix7'
]

# Configuration name mapping (file prefix -> display name)
CONFIG_MAPPING = {
    'Baseline_DRAM': 'DRAM',
    'DRAM': 'DRAM',
    'Conv': 'Conv',
    'Conv-STT-MRAM': 'Conv',
    'Conventional': 'Conv',
    'SMART': 'SMART',
}

# Line styles for each configuration
LINE_STYLES = {
    'DRAM': {'color': 'black', 'linestyle': '-', 'marker': 'o', 'markersize': 6},
    'Conv': {'color': 'gray', 'linestyle': '--', 'marker': 's', 'markersize': 6},
    'SMART': {'color': 'gray', 'linestyle': '-', 'marker': '^', 'markersize': 6},
}


def parse_log_file(filepath: str) -> Optional[float]:
    """
    Parse a DRAMSim2 log file and extract the cumulative Row Buffer Hit Rate.

    DRAMSim2 outputs per-epoch statistics, so we need to sum all hits and misses
    across all epochs to get the true overall hit rate.

    Returns:
        Hit rate as percentage (0-100), or None if not found
    """
    try:
        with open(filepath, 'r') as f:
            content = f.read()

        # Sum all per-epoch hits and misses
        hits_matches = re.findall(r'Row Buffer Hits\s*:\s*(\d+)', content)
        misses_matches = re.findall(r'Row Buffer Misses\s*:\s*(\d+)', content)

        if hits_matches and misses_matches:
            total_hits = sum(int(x) for x in hits_matches)
            total_misses = sum(int(x) for x in misses_matches)
            total_accesses = total_hits + total_misses

            if total_accesses > 0:
                return (total_hits / total_accesses) * 100.0

        # Fallback: use last hit rate if parsing fails
        pattern = r'Row Buffer Hit Rate\s*:\s*([\d.]+)%'
        matches = re.findall(pattern, content)
        if matches:
            return float(matches[-1])

    except Exception as e:
        print(f"Warning: Could not parse {filepath}: {e}")

    return None


def extract_benchmark_name(filename: str) -> Optional[str]:
    """
    Extract benchmark name from log filename.

    Expected formats:
    - DRAM_bfs_1220.log -> bfs
    - DRAM_stream_add_1220.log -> stream_add
    - SMART_mix7_1220.log -> mix7
    - Conv_cc_1220.log -> cc
    """
    # Remove .log extension
    name = os.path.basename(filename).replace('.log', '')

    # Expected format: CONFIG_BENCHMARK_DATE.log
    # Split by underscore and extract benchmark name
    parts = name.split('_')

    if len(parts) >= 3:
        # First part is config (DRAM, Conv, SMART)
        # Last part is date (1220)
        # Middle part(s) are benchmark name
        config_part = parts[0]
        date_part = parts[-1]

        # Check if first part is a known config
        if config_part in CONFIG_MAPPING or config_part in CONFIG_MAPPING.values():
            # Benchmark is everything between config and date
            benchmark_parts = parts[1:-1]
            if benchmark_parts:
                benchmark = '_'.join(benchmark_parts)
                return benchmark

    # Fallback: try to match known benchmark names
    for benchmark in BENCHMARK_ORDER:
        if f'_{benchmark}_' in name or name.endswith(f'_{benchmark}'):
            return benchmark

    return None


def extract_config_name(filename: str) -> Optional[str]:
    """
    Extract configuration name from log filename.

    Expected formats:
    - Baseline_DRAM_GAP_bfs_1220.log -> DRAM
    - Conv_stream_add_1220.log -> Conv
    - SMART_mix7_1220.log -> SMART
    """
    name = os.path.basename(filename)

    for prefix, display_name in CONFIG_MAPPING.items():
        if name.startswith(prefix):
            return display_name

    return None


def collect_results(results_dir: str) -> Dict[str, Dict[str, float]]:
    """
    Collect all results from log files.

    Returns:
        Dict[config_name, Dict[benchmark_name, hit_rate]]
    """
    results = defaultdict(dict)

    log_files = glob.glob(os.path.join(results_dir, '*.log'))

    for filepath in log_files:
        config = extract_config_name(filepath)
        benchmark = extract_benchmark_name(filepath)

        if config is None or benchmark is None:
            print(f"Skipping unrecognized file: {os.path.basename(filepath)}")
            continue

        hit_rate = parse_log_file(filepath)

        if hit_rate is not None:
            # If multiple files for same config+benchmark, keep the latest
            # (assuming higher numbered suffix is newer)
            if benchmark not in results[config]:
                results[config][benchmark] = hit_rate
            else:
                # Could implement logic to prefer specific file versions
                pass

    return dict(results)


def generate_chart(
    results: Dict[str, Dict[str, float]],
    output_path: str,
    title: str = "Row Buffer Hit Rate",
    figsize: Tuple[int, int] = (14, 6)
):
    """
    Generate a line chart matching the paper's Figure 10 style.
    """
    fig, ax = plt.subplots(figsize=figsize)

    # Get benchmarks that have data
    all_benchmarks = set()
    for config_data in results.values():
        all_benchmarks.update(config_data.keys())

    # Order benchmarks: first by BENCHMARK_ORDER, then alphabetically for unknown ones
    known_benchmarks = [b for b in BENCHMARK_ORDER if b in all_benchmarks]
    unknown_benchmarks = sorted([b for b in all_benchmarks if b not in BENCHMARK_ORDER])
    benchmarks = known_benchmarks + unknown_benchmarks

    if not benchmarks:
        print("No benchmark data found!")
        return

    x = np.arange(len(benchmarks))

    # Plot each configuration
    for config_name in ['DRAM', 'Conv', 'SMART']:
        if config_name not in results:
            continue

        config_data = results[config_name]
        y = [config_data.get(b, np.nan) for b in benchmarks]

        style = LINE_STYLES.get(config_name, {})
        ax.plot(x, y, label=config_name, **style)

    # Styling
    ax.set_xlabel('')
    ax.set_ylabel('Hit Rate [%]', fontsize=12)
    ax.set_title(title, fontsize=14)

    # X-axis
    ax.set_xticks(x)
    ax.set_xticklabels(benchmarks, rotation=45, ha='right', fontsize=10)

    # Y-axis
    ax.set_ylim(0, 100)
    ax.yaxis.set_major_locator(ticker.MultipleLocator(20))
    ax.yaxis.set_minor_locator(ticker.MultipleLocator(10))

    # Grid
    ax.grid(True, axis='y', linestyle='--', alpha=0.7)
    ax.set_axisbelow(True)

    # Legend
    ax.legend(loc='upper right', framealpha=0.9)

    # Tight layout
    plt.tight_layout()

    # Save
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"Chart saved to: {output_path}")

    # Also save as PDF for paper quality
    pdf_path = output_path.rsplit('.', 1)[0] + '.pdf'
    plt.savefig(pdf_path, bbox_inches='tight')
    print(f"PDF saved to: {pdf_path}")

    plt.close()


def print_summary(results: Dict[str, Dict[str, float]]):
    """Print a summary table of results."""
    print("\n" + "=" * 70)
    print("Row Buffer Hit Rate Summary")
    print("=" * 70)

    # Get all benchmarks
    all_benchmarks = set()
    for config_data in results.values():
        all_benchmarks.update(config_data.keys())

    # Order benchmarks: first by BENCHMARK_ORDER, then alphabetically for unknown ones
    known_benchmarks = [b for b in BENCHMARK_ORDER if b in all_benchmarks]
    unknown_benchmarks = sorted([b for b in all_benchmarks if b not in BENCHMARK_ORDER])
    benchmarks = known_benchmarks + unknown_benchmarks

    # Header
    configs = [c for c in ['DRAM', 'Conv', 'SMART'] if c in results]
    header = f"{'Benchmark':<15}" + "".join(f"{c:>12}" for c in configs)
    print(header)
    print("-" * len(header))

    # Data rows
    for benchmark in benchmarks:
        row = f"{benchmark:<15}"
        for config in configs:
            if config in results and benchmark in results[config]:
                row += f"{results[config][benchmark]:>11.2f}%"
            else:
                row += f"{'N/A':>12}"
        print(row)

    print("=" * 70)


def main():
    # Get script directory for default paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    experiment_dir = os.path.dirname(script_dir)
    default_trace_log = os.path.join(experiment_dir, 'trace_log')
    default_output_dir = os.path.join(experiment_dir, 'output')

    parser = argparse.ArgumentParser(description='Generate Row Buffer Hit Rate charts')
    parser.add_argument(
        '--trace-log',
        default=default_trace_log,
        help='Directory containing trace log files (default: ../trace_log)'
    )
    parser.add_argument(
        '--output',
        default=None,
        help='Output chart path (default: ../output/hit_rate_chart_MMDD_HHMM.png)'
    )
    parser.add_argument(
        '--title',
        default='Row Buffer Hit Rate',
        help='Chart title'
    )

    args = parser.parse_args()

    # Set default output path with timestamp
    if args.output is None:
        from datetime import datetime
        os.makedirs(default_output_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%m%d_%H%M")
        args.output = os.path.join(default_output_dir, f'hit_rate_chart_{timestamp}.png')

    print(f"Scanning trace_log directory: {args.trace_log}")
    results = collect_results(args.trace_log)

    if not results:
        print("No results found!")
        return 1

    print_summary(results)
    generate_chart(results, args.output, args.title)

    return 0


if __name__ == '__main__':
    exit(main())

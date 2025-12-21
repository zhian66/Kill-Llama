#!/usr/bin/env python3
"""
Latency Profile Chart Generator for STT-MRAM Paper Reproduction (Figure 11)

Generates latency distribution histogram comparing:
- DRAM (baseline)
- Conv-Pin (Conventional STT-MRAM)
- SMART (proposed architecture)

X-axis: Latency [ns]
Y-axis: # of Read Requests (log scale)

Usage:
    python plot_latency.py [--trace-log PATH] [--output PATH]
"""

import os
import re
import glob
import argparse
from collections import defaultdict
from typing import Dict, Optional
from matplotlib.ticker import FuncFormatter

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np


# Configuration name mapping (file prefix -> display name)
CONFIG_MAPPING = {
    'DRAM': 'DRAM',
    'Conv': 'Conv - Pin',
    'SMART': 'SMART',
}

# Line styles for each configuration (matching paper's Figure 11)
LINE_STYLES = {
    'DRAM': {'color': 'black', 'linestyle': '-', 'linewidth': 2, 'marker': None},
    'Conv': {'color': 'gray', 'linestyle': '--', 'linewidth': 2, 'marker': None},
    'SMART': {'color': 'gray', 'linestyle': '-', 'linewidth': 1.5, 'marker': 's',
              'markersize': 5, 'markerfacecolor': 'white', 'markeredgecolor': 'gray'},
}


def parse_latency_histogram(filepath: str, use_access_latency: bool = True) -> Dict[int, int]:
    """
    Parse a DRAMSim2 log file and extract latency histogram.

    Args:
        filepath: Path to the log file
        use_access_latency: If True, parse "Access Latency list" section;
                           if False, parse "Latency list" section (total latency)

    Returns:
        Dict[latency_bin_start, count] aggregated across all epochs
    """
    histogram = defaultdict(int)

    try:
        with open(filepath, 'r') as f:
            content = f.read()

        if use_access_latency:
            # Find Access Latency section and extract only from that
            access_match = re.search(r'---\s*Access Latency list.*?\n(.*?)(?:---|\Z)', content, re.DOTALL)
            if access_match:
                section = access_match.group(1)
            else:
                # Fallback to total latency if access latency not found
                section = content
        else:
            # Use total latency (everything before "Access Latency list")
            access_pos = content.find('Access Latency list')
            if access_pos > 0:
                section = content[:access_pos]
            else:
                section = content

        # Find all latency entries: [min-max] : count
        pattern = r'\[(\d+)-(\d+)\]\s*:\s*(\d+)'
        matches = re.findall(pattern, section)

        for min_lat, max_lat, count in matches:
            bin_start = int(min_lat)
            histogram[bin_start] += int(count)

    except Exception as e:
        print(f"Warning: Could not parse {filepath}: {e}")

    return dict(histogram)


def extract_config_name(filename: str) -> Optional[str]:
    """Extract configuration name from log filename."""
    name = os.path.basename(filename)

    for prefix in CONFIG_MAPPING.keys():
        if name.startswith(prefix):
            return prefix

    return None


def collect_results(results_dir: str) -> Dict[str, Dict[int, int]]:
    """
    Collect all latency histograms from log files.

    Returns:
        Dict[config_name, Dict[latency_bin, count]]
    """
    results = defaultdict(lambda: defaultdict(int))

    log_files = glob.glob(os.path.join(results_dir, '*.log'))

    for filepath in log_files:
        config = extract_config_name(filepath)

        if config is None:
            continue

        histogram = parse_latency_histogram(filepath)

        # Aggregate histograms for same config
        for lat_bin, count in histogram.items():
            results[config][lat_bin] += count

    return {k: dict(v) for k, v in results.items()}


def generate_chart(
    results: Dict[str, Dict[int, int]],
    output_path: str,
    title: str = "",
    figsize: tuple = (10, 6)
):
    """
    Generate a latency profile chart matching Figure 11 style.

    - X-axis: Latency [ns]
    - Y-axis: # of Read Requests (log scale)
    """
    fig, ax = plt.subplots(figsize=figsize)

    # Plot order: DRAM, Conv, SMART
    plot_order = ['DRAM', 'Conv', 'SMART']

    for config in plot_order:
        if config not in results:
            print(f"Warning: No data for {config}")
            continue

        histogram = results[config]
        if not histogram:
            continue

        # Sort by latency
        latencies = sorted(histogram.keys())
        counts = [histogram[lat] for lat in latencies]

        # Get style
        style = LINE_STYLES.get(config, {})
        label = CONFIG_MAPPING.get(config, config)

        ax.plot(latencies, counts, label=label, **style)

    # Y-axis: log scale
    ax.set_yscale('log')
    # ax.set_ylim(1e0, 1e6)
    ax.set_ylim(1e2, 1e8)
    ax.yaxis.set_major_locator(ticker.LogLocator(base=10.0, numticks=10))

    # X-axis - auto-scale to show all data
    if latencies:
        all_latencies = []
        for config in plot_order:
            if config in results:
                all_latencies.extend(results[config].keys())
        if all_latencies:
            max_lat = max(all_latencies)
            ax.set_xlim(0, min(max_lat + 50, 1000))  # Cap at 1000ns for readability
    ax.set_xlabel('Latency [ns]', fontsize=12)
    ax.set_ylabel('# of Read Requests', fontsize=12)

    # Grid (horizontal dashed lines)
    ax.yaxis.grid(True, linestyle='--', alpha=0.7)
    ax.xaxis.grid(False)
    ax.set_axisbelow(True)

    # Legend
    # ax.legend(loc='upper right', framealpha=0.9, fontsize=10)
    ax.legend(loc='upper center', bbox_to_anchor=(0.5, 1.12), ncol=3, frameon=False, fontsize=10)


    # Title (optional)
    if title:
        ax.set_title(title, fontsize=14)

    # Tight layout
    plt.tight_layout()

    # Save PNG
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"Chart saved to: {output_path}")

    # Save PDF
    pdf_path = output_path.rsplit('.', 1)[0] + '.pdf'
    plt.savefig(pdf_path, bbox_inches='tight')
    print(f"PDF saved to: {pdf_path}")

    plt.close()


def sci_notation(x, pos):
    """Format numbers as scientific notation like 1E+7, 2E+7, 3E+7"""
    if x <= 0:
        return ''
    exp = int(np.floor(np.log10(x)))
    coef = x / (10 ** exp)
    # Round coefficient to avoid floating point issues
    coef = round(coef)
    if coef == 1:
        return f'1E+{exp}'
    else:
        return f'{int(coef)}E+{exp}'

def generate_chart_with_inset(
    results: Dict[str, Dict[int, int]],
    output_path: str,
    figsize: tuple = (10, 6)
):
    """
    Generate latency profile chart with inset (matching paper's Figure 11).

    Main chart: Full latency range (0-400ns), log scale
    Inset: Zoomed view of low latency region (10-70ns), linear scale
    """
    fig, ax = plt.subplots(figsize=figsize)

    plot_order = ['DRAM', 'Conv', 'SMART']

    # Store data for inset
    all_data = {}

    for config in plot_order:
        if config not in results:
            continue

        histogram = results[config]
        if not histogram:
            continue

        latencies = sorted(histogram.keys())
        counts = [histogram[lat] for lat in latencies]

        all_data[config] = (latencies, counts)

        style = LINE_STYLES.get(config, {})
        label = CONFIG_MAPPING.get(config, config)
        ax.plot(latencies, counts, label=label, **style)

    # Main chart styling
    ax.set_yscale('log')
    ax.set_ylim(1e2, 1e8)
    ax.set_xlim(0, 400)
    ax.set_xlabel('Latency [ns]', fontsize=12)
    ax.set_ylabel('# of Read Requests', fontsize=12)
    ax.yaxis.grid(True, linestyle='--', alpha=0.7)
    ax.yaxis.set_major_formatter(FuncFormatter(sci_notation))
    ax.yaxis.set_major_locator(ticker.LogLocator(base=10.0, numticks=10))
    # ax.legend(loc='upper right', framealpha=0.9, fontsize=10)
    ax.legend(loc='upper center', bbox_to_anchor=(0.5, 1.12), ncol=3, frameon=False, fontsize=10)

    # Create inset axes (top-right area, matching paper's Figure 11)
    ax_inset = fig.add_axes([0.54, 0.64, 0.34, 0.20])  # [left, bottom, width, height]

    for config in plot_order:
        if config not in all_data:
            continue

        latencies, counts = all_data[config]

        # Filter for inset range (10-70ns)
        inset_lat = []
        inset_cnt = []
        for lat, cnt in zip(latencies, counts):
            if 10 <= lat <= 70:
                inset_lat.append(lat)
                inset_cnt.append(cnt)

        if inset_lat:
            style = LINE_STYLES.get(config, {}).copy()
            # Remove label for inset
            ax_inset.plot(inset_lat, inset_cnt, **style)
            ax_inset.yaxis.set_major_formatter(FuncFormatter(sci_notation))

    # Inset styling (log Y scale to match paper)
    ax_inset.set_xlim(10, 70)
    ax_inset.set_yscale('log')
    ax_inset.set_ylim(1e7, 1e8)
    ax_inset.tick_params(labelsize=8)
    ax_inset.yaxis.grid(True, linestyle='--', alpha=0.5)
    # Manual tick positions for clean 1E+7, 2E+7, 4E+7, 6E+7, 1E+8 format
    ax_inset.minorticks_off()
    ax_inset.set_yticks([1e7, 5e7, 1e8])
    ax_inset.yaxis.set_major_formatter(FuncFormatter(sci_notation))

    # Add border/box around inset
    for spine in ax_inset.spines.values():
        spine.set_edgecolor('black')
        spine.set_linewidth(1)

    # Note: skip tight_layout() when using inset axes to avoid warning

    # Save
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"Chart saved to: {output_path}")

    pdf_path = output_path.rsplit('.', 1)[0] + '.pdf'
    plt.savefig(pdf_path, bbox_inches='tight')
    print(f"PDF saved to: {pdf_path}")

    plt.close()


def print_summary(results: Dict[str, Dict[int, int]]):
    """Print a summary of latency statistics."""
    print("\n" + "=" * 60)
    print("Latency Profile Summary")
    print("=" * 60)

    for config in ['DRAM', 'Conv', 'SMART']:
        if config not in results:
            continue

        histogram = results[config]
        total = sum(histogram.values())

        if total == 0:
            continue

        weighted_sum = sum(lat * cnt for lat, cnt in histogram.items())
        avg_lat = weighted_sum / total
        min_lat = min(histogram.keys())
        max_lat = max(histogram.keys())

        print(f"\n{CONFIG_MAPPING.get(config, config)}:")
        print(f"  Total Requests: {total:,}")
        print(f"  Avg Latency:    {avg_lat:.1f} ns")
        print(f"  Min Latency:    {min_lat} ns")
        print(f"  Max Latency:    {max_lat} ns")

    print("\n" + "=" * 60)


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    experiment_dir = os.path.dirname(script_dir)
    default_trace_log = os.path.join(experiment_dir, 'trace_log')
    default_output_dir = os.path.join(experiment_dir, 'output')

    parser = argparse.ArgumentParser(description='Generate Latency Profile charts (Figure 11)')
    parser.add_argument(
        '--trace-log',
        default=default_trace_log,
        help='Directory containing trace log files'
    )
    parser.add_argument(
        '--output',
        default=None,
        help='Output chart path'
    )
    parser.add_argument(
        '--with-inset',
        action='store_true',
        help='Generate chart with inset (zoomed view)'
    )

    args = parser.parse_args()

    # Set default output path
    if args.output is None:
        from datetime import datetime
        os.makedirs(default_output_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%m%d_%H%M")
        args.output = os.path.join(default_output_dir, f'latency_profile_{timestamp}.png')

    print(f"Scanning trace_log directory: {args.trace_log}")
    results = collect_results(args.trace_log)

    if not results:
        print("No results found!")
        return 1

    print_summary(results)

    if args.with_inset:
        generate_chart_with_inset(results, args.output)
    else:
        generate_chart(results, args.output)

    return 0


if __name__ == '__main__':
    exit(main())

#!/usr/bin/env python3
"""
IPC Improvement Chart Generator for STT-MRAM Paper Reproduction (Figure 12)

Generates a grouped bar chart comparing IPC improvement over DRAM baseline:
- Conv-Pin (Conventional STT-MRAM with pinned layer)
- Conv-Delay (Conventional STT-MRAM with delayed sensing)
- SMART (proposed architecture)

Features:
- Rolling generation: automatically detects available stats files
- Only plots workloads/configs that have data
- Calculates GMEAN when multiple workloads are available

Usage:
    python plot_ipc.py [--stats-dir PATH] [--output PATH]
"""

import os
import re
import glob
import argparse
from collections import defaultdict
from typing import Dict, Optional, List, Tuple
from dataclasses import dataclass
from datetime import datetime

import matplotlib.pyplot as plt
import numpy as np


# Expected ordering (for consistent display)
WORKLOADS_ORDER = [
    'bc', 'bfs', 'cc', 'imagick', 'lbm', 'mcf', 'nab', 'omnetpp',
    'pr', 'sssp', 'stream_add', 'stream_copy', 'stream_scale', 'stream_triad',
    'tc', 'xalancbmk', 'mix1', 'mix2', 'mix3', 'mix4', 'mix5', 'mix6', 'mix7'
]

# Config ordering and display names
CONFIGS_ORDER = ['Conv-Pin', 'Conv-Delay', 'SMART']
CONFIG_FILE_MAPPING = {
    'DRAM': 'DRAM',
    'Conv-Pin': 'Conv-Pin',
    'Conv_Pin': 'Conv-Pin',
    'ConvPin': 'Conv-Pin',
    'Conv-Delay': 'Conv-Delay',
    'Conv_Delay': 'Conv-Delay',
    'ConvDelay': 'Conv-Delay',
    'SMART': 'SMART',
}

# Bar styles matching paper's Figure 12
BAR_STYLES = {
    'Conv-Pin': {'color': 'lightgray', 'edgecolor': 'black', 'hatch': ''},
    'Conv-Delay': {'color': 'white', 'edgecolor': 'black', 'hatch': '///'},
    'SMART': {'color': 'black', 'edgecolor': 'black', 'hatch': ''},
}


@dataclass
class IPCData:
    """IPC data for a single configuration"""
    ipc: float
    cycles: int = 0
    insns: int = 0


def parse_stats_file(filepath: str) -> Optional[IPCData]:
    """
    Parse a MARSSx86 .stats file and extract IPC value.

    The IPC is located under the 'commit:' section as 'ipc: X.XXXXX'

    Returns:
        IPCData object, or None if parsing fails
    """
    try:
        with open(filepath, 'r') as f:
            content = f.read()

        # Find all IPC values (there may be multiple sections)
        # We want the one under 'commit:' section
        # Pattern: after "commit:" find "ipc: X.XXXXX"

        # First try to find the commit section IPC
        commit_pattern = r'commit:.*?ipc:\s*([\d.]+)'
        match = re.search(commit_pattern, content, re.DOTALL)

        if match:
            ipc = float(match.group(1))
            return IPCData(ipc=ipc)

        # Fallback: just find any ipc value
        ipc_pattern = r'\bipc:\s*([\d.]+)'
        matches = re.findall(ipc_pattern, content)
        if matches:
            # Use the last one (usually the final/total)
            ipc = float(matches[-1])
            return IPCData(ipc=ipc)

        return None

    except Exception as e:
        print(f"Warning: Failed to parse {filepath}: {e}")
        return None


def scan_stats_dir(stats_dir: str) -> Dict[str, Dict[str, float]]:
    """
    Scan directory for stats files and extract IPC values.

    Expected filename format: {CONFIG}_{WORKLOAD}.stats
    Example: DRAM_stream_triad.stats, SMART_lbm.stats

    Returns:
        Dictionary: {workload: {config: ipc_value}}
    """
    data = defaultdict(dict)

    # Find all .stats files
    pattern = os.path.join(stats_dir, '*.stats')
    files = glob.glob(pattern)

    for filepath in files:
        filename = os.path.basename(filepath)
        name_without_ext = os.path.splitext(filename)[0]

        # Parse filename: {CONFIG}_{WORKLOAD}
        parts = name_without_ext.split('_', 1)
        if len(parts) < 2:
            print(f"Warning: Skipping {filename} - unexpected format")
            continue

        config_raw, workload = parts[0], parts[1]

        # Normalize config name
        config = CONFIG_FILE_MAPPING.get(config_raw, config_raw)

        # Parse the file
        ipc_data = parse_stats_file(filepath)
        if ipc_data:
            data[workload][config] = ipc_data.ipc
            print(f"  Found: {config} / {workload} -> IPC = {ipc_data.ipc:.6f}")

    return dict(data)


def calculate_ipc_improvement(data: Dict[str, Dict[str, float]]) -> Dict[str, Dict[str, float]]:
    """
    Calculate IPC improvement percentage relative to DRAM baseline.

    Formula: improvement = ((IPC_config - IPC_DRAM) / IPC_DRAM) * 100

    Returns:
        Dictionary: {workload: {config: improvement_percentage}}
    """
    improvements = defaultdict(dict)

    for workload, configs in data.items():
        if 'DRAM' not in configs:
            print(f"Warning: No DRAM baseline for {workload}, skipping")
            continue

        baseline_ipc = configs['DRAM']

        for config, ipc in configs.items():
            if config == 'DRAM':
                continue

            improvement = ((ipc - baseline_ipc) / baseline_ipc) * 100
            improvements[workload][config] = improvement

    return dict(improvements)


def calculate_gmean(improvements: Dict[str, Dict[str, float]]) -> Dict[str, float]:
    """
    Calculate geometric mean of IPC improvements for each config.

    Note: GMEAN of percentage changes requires special handling.
    We use: GMEAN = (product of (1 + improvement/100))^(1/n) - 1) * 100

    Returns:
        Dictionary: {config: gmean_improvement}
    """
    config_values = defaultdict(list)

    for workload, configs in improvements.items():
        for config, improvement in configs.items():
            # Convert percentage to ratio for geometric mean
            ratio = 1 + improvement / 100
            config_values[config].append(ratio)

    gmean = {}
    for config, ratios in config_values.items():
        if ratios:
            # Geometric mean of ratios, then convert back to percentage
            product = np.prod(ratios)
            n = len(ratios)
            gmean_ratio = product ** (1/n)
            gmean[config] = (gmean_ratio - 1) * 100

    return gmean


def generate_chart(improvements: Dict[str, Dict[str, float]],
                   output_path: str,
                   y_range: Tuple[float, float] = (-5.0, 10.0)):
    """
    Generate the IPC improvement bar chart.

    Args:
        improvements: {workload: {config: improvement_percentage}}
        output_path: Path to save the chart
        y_range: Y-axis range (min, max)
    """
    # Determine which workloads and configs to display
    available_workloads = []
    for wl in WORKLOADS_ORDER:
        if wl in improvements:
            available_workloads.append(wl)

    # Add any workloads not in the expected order
    for wl in improvements.keys():
        if wl not in available_workloads:
            available_workloads.append(wl)

    if not available_workloads:
        print("No data to plot!")
        return

    # Determine available configs
    available_configs = []
    all_configs = set()
    for wl_data in improvements.values():
        all_configs.update(wl_data.keys())

    for cfg in CONFIGS_ORDER:
        if cfg in all_configs:
            available_configs.append(cfg)

    # Add any configs not in expected order
    for cfg in all_configs:
        if cfg not in available_configs:
            available_configs.append(cfg)

    # Calculate GMEAN if we have multiple workloads
    gmean = {}
    if len(available_workloads) > 1:
        gmean = calculate_gmean(improvements)
        available_workloads.append('GMEAN')

    # Prepare data for plotting
    n_workloads = len(available_workloads)
    n_configs = len(available_configs)

    if n_configs == 0:
        print("No configs to plot!")
        return

    # Create figure
    fig, ax = plt.subplots(figsize=(14, 5))

    # Bar positioning
    bar_width = 0.8 / n_configs
    x = np.arange(n_workloads)

    # Plot bars for each config
    for i, config in enumerate(available_configs):
        values = []
        for wl in available_workloads:
            if wl == 'GMEAN':
                values.append(gmean.get(config, 0))
            else:
                values.append(improvements.get(wl, {}).get(config, 0))

        offset = (i - n_configs/2 + 0.5) * bar_width
        style = BAR_STYLES.get(config, {'color': 'gray', 'edgecolor': 'black', 'hatch': ''})

        bars = ax.bar(x + offset, values, bar_width,
                      label=config,
                      color=style['color'],
                      edgecolor=style['edgecolor'],
                      hatch=style['hatch'],
                      linewidth=0.5)

        # Add value labels for bars exceeding y_range
        for j, (bar, val) in enumerate(zip(bars, values)):
            if val > y_range[1]:
                ax.annotate(f'{val:.1f}',
                           xy=(bar.get_x() + bar.get_width()/2, y_range[1]),
                           xytext=(0, 3),
                           textcoords='offset points',
                           ha='center', va='bottom',
                           fontsize=8, fontweight='bold')
            elif val < y_range[0]:
                ax.annotate(f'{val:.1f}',
                           xy=(bar.get_x() + bar.get_width()/2, y_range[0]),
                           xytext=(0, -10),
                           textcoords='offset points',
                           ha='center', va='top',
                           fontsize=8, fontweight='bold')

    # Customize chart
    ax.set_ylabel('IPC Improvement [%]', fontsize=12)
    ax.set_xticks(x)
    ax.set_xticklabels(available_workloads, rotation=45, ha='right', fontsize=10)
    ax.set_ylim(y_range)

    # Add horizontal line at y=0
    ax.axhline(y=0, color='black', linewidth=0.5)

    # Add grid
    ax.yaxis.grid(True, linestyle='--', alpha=0.5)
    ax.set_axisbelow(True)

    # Legend
    ax.legend(loc='upper center', bbox_to_anchor=(0.5, 1.12),
              ncol=len(available_configs), frameon=False, fontsize=10)

    # Tight layout
    plt.tight_layout()

    # Save
    fig.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"Chart saved to: {output_path}")

    # Also save PDF
    pdf_path = output_path.rsplit('.', 1)[0] + '.pdf'
    fig.savefig(pdf_path, bbox_inches='tight')
    print(f"PDF saved to: {pdf_path}")

    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(
        description='Generate IPC Improvement chart (Figure 12)')
    parser.add_argument('--stats-dir', type=str,
                        default=os.path.join(os.path.dirname(__file__), '..', '..', 'stats'),
                        help='Directory containing .stats files')
    parser.add_argument('--output', type=str,
                        default=None,
                        help='Output file path')
    parser.add_argument('--y-min', type=float, default=-5.0,
                        help='Y-axis minimum')
    parser.add_argument('--y-max', type=float, default=10.0,
                        help='Y-axis maximum')

    args = parser.parse_args()

    # Resolve paths
    stats_dir = os.path.abspath(args.stats_dir)

    if args.output:
        output_path = args.output
    else:
        timestamp = datetime.now().strftime('%m%d_%H%M')
        output_dir = os.path.join(os.path.dirname(__file__), '..', 'output')
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f'ipc_improvement_{timestamp}.png')

    print(f"Scanning stats directory: {stats_dir}")

    # Scan for data
    data = scan_stats_dir(stats_dir)

    if not data:
        print("No stats files found!")
        return

    print(f"\nFound {len(data)} workloads")

    # Calculate improvements
    improvements = calculate_ipc_improvement(data)

    if not improvements:
        print("No improvements to calculate (missing DRAM baseline?)")
        return

    print(f"\nCalculated improvements for {len(improvements)} workloads")

    # Generate chart
    generate_chart(improvements, output_path, y_range=(args.y_min, args.y_max))


if __name__ == '__main__':
    main()

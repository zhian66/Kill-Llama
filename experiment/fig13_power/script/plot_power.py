#!/usr/bin/env python3
"""
Power Chart Generator for STT-MRAM Paper Reproduction (Figure 13)

Generates a stacked bar chart comparing power consumption across:
- DRAM (baseline)
- Conv (Conventional STT-MRAM, shown as Conv-Pin)
- SMART (proposed architecture)

X-axis: Benchmarks (nab, mix1, pr, lbm)
Left Y-axis: Power [W] (stacked bar)
Right Y-axis: Row Hit Rate [%] (line plot)

Usage:
    python plot_power.py [--trace-log PATH] [--output PATH]
"""

import os
import re
import glob
import argparse
from collections import defaultdict
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np


# Configuration name mapping (file prefix -> display name)
CONFIG_MAPPING = {
    'DRAM': 'DRAM',
    'Conv': 'Conv-Pin',
    'SMART': 'SMART',
}

# Benchmark order for Figure 13
BENCHMARK_ORDER = ['nab', 'mix1', 'pr', 'lbm']

# mix1 components (will be averaged)
MIX1_COMPONENTS = ['imagick', 'sssp', 'stream_add', 'mcf']

# Bar colors and patterns matching paper's Figure 13
# Background: dotted, Activation: solid black, Read/Write: diagonal, Refresh: solid gray
BAR_STYLES = {
    'background': {'color': 'white', 'edgecolor': 'black', 'hatch': '...', 'label': 'Background'},
    'activation': {'color': 'black', 'edgecolor': 'black', 'hatch': '', 'label': 'Activation'},
    'burst': {'color': 'white', 'edgecolor': 'black', 'hatch': '///', 'label': 'Read/Write'},
    'refresh': {'color': 'gray', 'edgecolor': 'black', 'hatch': '', 'label': 'Refresh'},
}


@dataclass
class PowerData:
    """Power breakdown data"""
    background: float = 0.0
    activation: float = 0.0  # Act/Pre
    burst: float = 0.0       # Read/Write
    refresh: float = 0.0
    hit_rate: float = 0.0

    @property
    def total(self) -> float:
        return self.background + self.activation + self.burst + self.refresh


def parse_log_file(filepath: str) -> Optional[PowerData]:
    """
    Parse a DRAMSim2 log file and extract power breakdown and hit rate.

    Returns:
        PowerData object with cumulative values, or None if parsing fails
    """
    try:
        with open(filepath, 'r') as f:
            content = f.read()

        # Sum all per-epoch power values (cumulative)
        background_matches = re.findall(r'-Background \(watts\)\s*:\s*([\d.]+)', content)
        actpre_matches = re.findall(r'-Act/Pre\s*\(watts\)\s*:\s*([\d.]+)', content)
        burst_matches = re.findall(r'-Burst\s*\(watts\)\s*:\s*([\d.]+)', content)
        refresh_matches = re.findall(r'-Refresh\s*\(watts\)\s*:\s*([\d.]+)', content)

        # Use last (final) values for power
        if background_matches and actpre_matches and burst_matches and refresh_matches:
            data = PowerData(
                background=float(background_matches[-1]),
                activation=float(actpre_matches[-1]),
                burst=float(burst_matches[-1]),
                refresh=float(refresh_matches[-1]),
            )

            # Parse cumulative hit rate
            hits_matches = re.findall(r'Row Buffer Hits\s*:\s*(\d+)', content)
            misses_matches = re.findall(r'Row Buffer Misses\s*:\s*(\d+)', content)

            if hits_matches and misses_matches:
                total_hits = sum(int(x) for x in hits_matches)
                total_misses = sum(int(x) for x in misses_matches)
                total_accesses = total_hits + total_misses
                if total_accesses > 0:
                    data.hit_rate = (total_hits / total_accesses) * 100.0

            return data

    except Exception as e:
        print(f"Warning: Could not parse {filepath}: {e}")

    return None


def extract_config_name(filename: str) -> Optional[str]:
    """Extract configuration name from log filename."""
    name = os.path.basename(filename)
    for prefix in CONFIG_MAPPING.keys():
        if name.startswith(prefix + '_'):
            return prefix
    return None


def extract_benchmark_name(filename: str) -> Optional[str]:
    """Extract benchmark name from log filename."""
    name = os.path.basename(filename).replace('.log', '')
    parts = name.split('_')

    if len(parts) >= 3:
        # Format: CONFIG_BENCHMARK_DATE.log
        # Benchmark is everything between config and date
        config_part = parts[0]
        if config_part in CONFIG_MAPPING:
            benchmark_parts = parts[1:-1]
            if benchmark_parts:
                return '_'.join(benchmark_parts)
    return None


def collect_results(results_dir: str) -> Dict[str, Dict[str, PowerData]]:
    """
    Collect all power data from log files.

    Returns:
        Dict[config_name, Dict[benchmark_name, PowerData]]
    """
    results = defaultdict(dict)

    log_files = glob.glob(os.path.join(results_dir, '*.log'))

    for filepath in log_files:
        config = extract_config_name(filepath)
        benchmark = extract_benchmark_name(filepath)

        if config is None or benchmark is None:
            continue

        data = parse_log_file(filepath)
        if data is not None:
            results[config][benchmark] = data

    return dict(results)


def compute_mix1(results: Dict[str, Dict[str, PowerData]]) -> Dict[str, PowerData]:
    """
    Compute mix1 data by averaging its components (imagick, sssp, stream_add, mcf).

    Returns:
        Dict[config_name, PowerData] for mix1
    """
    mix1_data = {}

    for config in CONFIG_MAPPING.keys():
        if config not in results:
            continue

        config_data = results[config]
        components_found = []

        for comp in MIX1_COMPONENTS:
            if comp in config_data:
                components_found.append(config_data[comp])

        if components_found:
            # Average all components
            n = len(components_found)
            mix1_data[config] = PowerData(
                background=sum(c.background for c in components_found) / n,
                activation=sum(c.activation for c in components_found) / n,
                burst=sum(c.burst for c in components_found) / n,
                refresh=sum(c.refresh for c in components_found) / n,
                hit_rate=sum(c.hit_rate for c in components_found) / n,
            )

    return mix1_data


def generate_chart(
    results: Dict[str, Dict[str, PowerData]],
    output_path: str,
    figsize: Tuple[int, int] = (12, 6)
):
    """
    Generate a grouped stacked bar chart matching Figure 13 style.
    """
    fig, ax1 = plt.subplots(figsize=figsize)

    # Compute mix1 data
    mix1_data = compute_mix1(results)

    # Add mix1 to results for each config
    for config, data in mix1_data.items():
        if config in results:
            results[config]['mix1'] = data

    # Prepare data for plotting
    benchmarks = BENCHMARK_ORDER
    configs = ['DRAM', 'Conv', 'SMART']

    # Number of groups and bars
    n_benchmarks = len(benchmarks)
    n_configs = len(configs)
    bar_width = 0.25
    group_width = n_configs * bar_width + 0.1

    # X positions for benchmark groups
    x_groups = np.arange(n_benchmarks)

    # Store hit rates for line plot
    hit_rates = {config: [] for config in configs}

    # Plot stacked bars for each config within each benchmark group
    for i, config in enumerate(configs):
        if config not in results:
            continue

        x_positions = x_groups + (i - 1) * bar_width

        backgrounds = []
        activations = []
        bursts = []
        refreshes = []

        for benchmark in benchmarks:
            if benchmark in results[config]:
                data = results[config][benchmark]
                backgrounds.append(data.background)
                activations.append(data.activation)
                bursts.append(data.burst)
                refreshes.append(data.refresh)
                hit_rates[config].append(data.hit_rate)
            else:
                backgrounds.append(0)
                activations.append(0)
                bursts.append(0)
                refreshes.append(0)
                hit_rates[config].append(0)

        # Stack: Background -> Activation -> Read/Write -> Refresh
        bottom = np.zeros(n_benchmarks)

        # Background (dotted)
        ax1.bar(x_positions, backgrounds, bar_width, bottom=bottom,
                color=BAR_STYLES['background']['color'],
                edgecolor=BAR_STYLES['background']['edgecolor'],
                hatch=BAR_STYLES['background']['hatch'],
                linewidth=0.5)
        bottom += np.array(backgrounds)

        # Activation (solid black)
        ax1.bar(x_positions, activations, bar_width, bottom=bottom,
                color=BAR_STYLES['activation']['color'],
                edgecolor=BAR_STYLES['activation']['edgecolor'],
                hatch=BAR_STYLES['activation']['hatch'],
                linewidth=0.5)
        bottom += np.array(activations)

        # Read/Write (diagonal stripe)
        ax1.bar(x_positions, bursts, bar_width, bottom=bottom,
                color=BAR_STYLES['burst']['color'],
                edgecolor=BAR_STYLES['burst']['edgecolor'],
                hatch=BAR_STYLES['burst']['hatch'],
                linewidth=0.5)
        bottom += np.array(bursts)

        # Refresh (solid gray)
        ax1.bar(x_positions, refreshes, bar_width, bottom=bottom,
                color=BAR_STYLES['refresh']['color'],
                edgecolor=BAR_STYLES['refresh']['edgecolor'],
                hatch=BAR_STYLES['refresh']['hatch'],
                linewidth=0.5)

    # Left Y-axis (Power)
    ax1.set_ylabel('Power [W]', fontsize=12)
    ax1.set_ylim(0.2, 1.2)
    ax1.set_yticks(np.arange(0.2, 1.3, 0.2))

    # X-axis
    ax1.set_xticks(x_groups)

    # Create x-axis labels with config names below benchmark names
    ax1.set_xticklabels([])  # Clear default labels

    # Add benchmark labels at group level
    for i, benchmark in enumerate(benchmarks):
        ax1.text(i, -0.05, benchmark, ha='center', va='top', fontsize=11, fontweight='bold',
                transform=ax1.get_xaxis_transform())
        # Add config labels below
        for j, config in enumerate(configs):
            x_pos = i + (j - 1) * bar_width
            display_name = CONFIG_MAPPING.get(config, config)
            ax1.text(x_pos, -0.12, display_name, ha='center', va='top', fontsize=8,
                    rotation=45, transform=ax1.get_xaxis_transform())

    # Right Y-axis (Hit Rate)
    ax2 = ax1.twinx()
    ax2.set_ylabel('Row Hit Rate [%]', fontsize=12)
    ax2.set_ylim(0, 100)
    # ax2.set_ylim(0, 40)
    ax2.set_yticks(np.arange(0, 100, 10))

    # Plot hit rate line with markers
    # Collect all hit rate points across configs for each benchmark group
    for i, benchmark in enumerate(benchmarks):
        for j, config in enumerate(configs):
            if config in results and benchmark in results[config]:
                x_pos = i + (j - 1) * bar_width
                hr = results[config][benchmark].hit_rate
                ax2.plot(x_pos, hr, 'x', color='gray', markersize=8, markeredgewidth=2)

    # Connect hit rate points with a line
    all_x = []
    all_hr = []
    for i, benchmark in enumerate(benchmarks):
        for j, config in enumerate(configs):
            if config in results and benchmark in results[config]:
                x_pos = i + (j - 1) * bar_width
                hr = results[config][benchmark].hit_rate
                all_x.append(x_pos)
                all_hr.append(hr)

    if all_x:
        # Sort by x position for proper line drawing
        sorted_pairs = sorted(zip(all_x, all_hr))
        all_x, all_hr = zip(*sorted_pairs)
        ax2.plot(all_x, all_hr, '-', color='gray', linewidth=1, alpha=0.7)

    # Create legend
    legend_patches = [
        mpatches.Patch(facecolor='white', edgecolor='black', hatch='...', label='Background'),
        mpatches.Patch(facecolor='black', edgecolor='black', label='Activation'),
        mpatches.Patch(facecolor='white', edgecolor='black', hatch='///', label='Read/Write'),
        mpatches.Patch(facecolor='gray', edgecolor='black', label='Refresh'),
        plt.Line2D([0], [0], marker='x', color='gray', linestyle='-', label='Row Hit',
                   markersize=8, markeredgewidth=2),
    ]
    ax1.legend(handles=legend_patches, loc='upper right', fontsize=9, ncol=2)

    # Grid
    ax1.yaxis.grid(True, linestyle='--', alpha=0.5)
    ax1.set_axisbelow(True)

    # Adjust layout
    plt.tight_layout()
    plt.subplots_adjust(bottom=0.2)

    # Save
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"Chart saved to: {output_path}")

    # Save PDF
    pdf_path = output_path.rsplit('.', 1)[0] + '.pdf'
    plt.savefig(pdf_path, bbox_inches='tight')
    print(f"PDF saved to: {pdf_path}")

    plt.close()


def print_summary(results: Dict[str, Dict[str, PowerData]]):
    """Print a summary table of power data."""
    # Compute mix1
    mix1_data = compute_mix1(results)
    for config, data in mix1_data.items():
        if config in results:
            results[config]['mix1'] = data

    print("\n" + "=" * 80)
    print("Power Breakdown Summary (Figure 13)")
    print("=" * 80)

    benchmarks = BENCHMARK_ORDER
    configs = ['DRAM', 'Conv', 'SMART']

    # Header
    header = f"{'Benchmark':<12}{'Config':<10}{'Background':>12}{'Activation':>12}{'Read/Write':>12}{'Refresh':>10}{'Total':>10}{'HitRate':>10}"
    print(header)
    print("-" * len(header))

    for benchmark in benchmarks:
        for config in configs:
            if config in results and benchmark in results[config]:
                data = results[config][benchmark]
                print(f"{benchmark:<12}{CONFIG_MAPPING[config]:<10}{data.background:>11.3f}W{data.activation:>11.3f}W{data.burst:>11.3f}W{data.refresh:>9.3f}W{data.total:>9.3f}W{data.hit_rate:>9.1f}%")
        print()

    print("=" * 80)


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    experiment_dir = os.path.dirname(script_dir)
    default_trace_log = os.path.join(experiment_dir, 'trace_log')
    default_output_dir = os.path.join(experiment_dir, 'output')

    parser = argparse.ArgumentParser(description='Generate Power charts (Figure 13)')
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

    args = parser.parse_args()

    # Set default output path
    if args.output is None:
        from datetime import datetime
        os.makedirs(default_output_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%m%d_%H%M")
        args.output = os.path.join(default_output_dir, f'power_chart_{timestamp}.png')

    print(f"Scanning trace_log directory: {args.trace_log}")
    results = collect_results(args.trace_log)

    if not results:
        print("No results found!")
        return 1

    print_summary(results)
    generate_chart(results, args.output)

    return 0


if __name__ == '__main__':
    exit(main())

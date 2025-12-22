#!/usr/bin/env python3
"""
Energy Savings Chart Generator for STT-MRAM Paper Reproduction (Figure 14)

Generates a grouped bar chart showing energy savings (%) over DRAM baseline:
- Conv-Pin (Conventional STT-MRAM)
- SMART (proposed architecture)

X-axis: Benchmarks (individual + mix1-7 + GMEAN)
Y-axis: Energy Saving [%]

Expected Results (from paper):
- Conv-Pin: Average 13.8% energy savings
- SMART: Average 29.4% energy savings

Usage:
    python plot_energy_saving.py [--trace-log PATH] [--output PATH]
"""

import os
import re
import glob
import argparse
from collections import defaultdict
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import math

import matplotlib.pyplot as plt
import numpy as np


# Configuration name mapping (file prefix -> display name)
CONFIG_MAPPING = {
    'DRAM': 'DRAM',
    'Conv': 'Conv-Pin',
    'SMART': 'SMART',
}

# Individual benchmarks order (matching paper's Figure 14)
INDIVIDUAL_BENCHMARKS = [
    'bc', 'bfs', 'cc', 'imagick', 'lbm', 'mcf', 'nab', 'omnetpp',
    'pr', 'sssp', 'stream_add', 'stream_copy', 'stream_scale', 'stream_triad',
    'tc', 'xalancbmk'
]

# Mix workload definitions
MIX_WORKLOADS = {
    'mix1': ['imagick', 'sssp', 'stream_add', 'mcf'],
    'mix2': ['bc', 'bfs', 'cc', 'lbm'],
    'mix3': ['nab', 'omnetpp', 'pr', 'sssp'],
    'mix4': ['stream_copy', 'stream_scale', 'stream_triad', 'tc'],
    'mix5': ['bfs', 'imagick', 'mcf', 'nab'],
    'mix6': ['cc', 'lbm', 'pr', 'tc'],
    'mix7': ['bc', 'omnetpp', 'sssp', 'stream_add'],
}

# Full benchmark order for plotting
BENCHMARK_ORDER = INDIVIDUAL_BENCHMARKS + list(MIX_WORKLOADS.keys()) + ['GMEAN']

# Bar colors matching paper's Figure 14
BAR_COLORS = {
    'Conv': '#808080',   # Light gray for Conv-Pin
    'SMART': '#404040',  # Dark gray for SMART
}


@dataclass
class PowerData:
    """Power data from simulation"""
    average_power: float = 0.0
    background: float = 0.0
    activation: float = 0.0
    burst: float = 0.0
    refresh: float = 0.0


def parse_log_file(filepath: str) -> Optional[PowerData]:
    """
    Parse a DRAMSim2 log file and extract power data.

    Returns:
        PowerData object with final epoch values, or None if parsing fails
    """
    try:
        with open(filepath, 'r') as f:
            content = f.read()

        # Extract power values (use last/final epoch values)
        avg_power_matches = re.findall(r'Average Power \(watts\)\s*:\s*([\d.]+)', content)
        background_matches = re.findall(r'-Background \(watts\)\s*:\s*([\d.]+)', content)
        actpre_matches = re.findall(r'-Act/Pre\s*\(watts\)\s*:\s*([\d.]+)', content)
        burst_matches = re.findall(r'-Burst\s*\(watts\)\s*:\s*([\d.]+)', content)
        refresh_matches = re.findall(r'-Refresh\s*\(watts\)\s*:\s*([\d.]+)', content)

        if avg_power_matches:
            # Average all epochs instead of taking only the last value
            n_epochs = len(avg_power_matches)
            return PowerData(
                average_power=sum(float(m) for m in avg_power_matches) / n_epochs,
                background=sum(float(m) for m in background_matches) / n_epochs if background_matches else 0.0,
                activation=sum(float(m) for m in actpre_matches) / n_epochs if actpre_matches else 0.0,
                burst=sum(float(m) for m in burst_matches) / n_epochs if burst_matches else 0.0,
                refresh=sum(float(m) for m in refresh_matches) / n_epochs if refresh_matches else 0.0,
            )

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


def compute_mix_workloads(results: Dict[str, Dict[str, PowerData]]) -> Dict[str, Dict[str, PowerData]]:
    """
    Compute mix workload power by averaging component benchmark powers.

    Returns:
        Updated results dict with mix workload entries added
    """
    for config in CONFIG_MAPPING.keys():
        if config not in results:
            continue

        config_data = results[config]

        for mix_name, components in MIX_WORKLOADS.items():
            components_found = []
            for comp in components:
                if comp in config_data:
                    components_found.append(config_data[comp])

            if components_found:
                n = len(components_found)
                results[config][mix_name] = PowerData(
                    average_power=sum(c.average_power for c in components_found) / n,
                    background=sum(c.background for c in components_found) / n,
                    activation=sum(c.activation for c in components_found) / n,
                    burst=sum(c.burst for c in components_found) / n,
                    refresh=sum(c.refresh for c in components_found) / n,
                )

    return results


def calculate_energy_savings(results: Dict[str, Dict[str, PowerData]]) -> Dict[str, Dict[str, float]]:
    """
    Calculate energy savings (%) for each config relative to DRAM baseline.

    Energy_Saving(%) = (DRAM_power - config_power) / DRAM_power * 100

    Returns:
        Dict[config_name, Dict[benchmark_name, energy_saving_percent]]
    """
    energy_savings = defaultdict(dict)

    if 'DRAM' not in results:
        print("Warning: DRAM baseline not found!")
        return dict(energy_savings)

    dram_data = results['DRAM']

    for config in ['Conv', 'SMART']:
        if config not in results:
            continue

        config_data = results[config]

        for benchmark in config_data.keys():
            if benchmark not in dram_data:
                continue

            dram_power = dram_data[benchmark].average_power
            config_power = config_data[benchmark].average_power

            if dram_power > 0:
                saving = (dram_power - config_power) / dram_power * 100.0
                energy_savings[config][benchmark] = saving

    return dict(energy_savings)


def compute_gmean(energy_savings: Dict[str, Dict[str, float]], benchmarks: List[str]) -> Dict[str, float]:
    """
    Compute geometric mean of energy savings for each config.

    Returns:
        Dict[config_name, gmean_value]
    """
    gmean_results = {}

    for config in ['Conv', 'SMART']:
        if config not in energy_savings:
            continue

        values = []
        for benchmark in benchmarks:
            if benchmark in energy_savings[config]:
                # For geometric mean, we need positive values
                # Energy savings can be negative, so we use (100 + saving) / 100
                # and then convert back
                saving = energy_savings[config][benchmark]
                # Use ratio: (DRAM - config) / DRAM = 1 - config/DRAM
                # So config/DRAM = 1 - saving/100
                ratio = 1 - saving / 100.0
                if ratio > 0:
                    values.append(ratio)

        if values:
            # Geometric mean of ratios
            gmean_ratio = math.exp(sum(math.log(v) for v in values) / len(values))
            # Convert back to energy saving percentage
            gmean_results[config] = (1 - gmean_ratio) * 100.0

    return gmean_results


def generate_chart(
    energy_savings: Dict[str, Dict[str, float]],
    output_path: str,
    figsize: Tuple[int, int] = (16, 6)
):
    """
    Generate a grouped bar chart matching Figure 14 style.
    """
    fig, ax = plt.subplots(figsize=figsize)

    # Get list of benchmarks to plot (those with data)
    available_benchmarks = set()
    for config in energy_savings.values():
        available_benchmarks.update(config.keys())

    # Filter and order benchmarks
    benchmarks_to_plot = [b for b in BENCHMARK_ORDER if b in available_benchmarks]

    # Add GMEAN
    gmean_values = compute_gmean(energy_savings, [b for b in benchmarks_to_plot if b != 'GMEAN'])
    for config, gmean in gmean_values.items():
        energy_savings[config]['GMEAN'] = gmean

    if 'GMEAN' not in benchmarks_to_plot:
        benchmarks_to_plot.append('GMEAN')

    n_benchmarks = len(benchmarks_to_plot)
    configs = ['Conv', 'SMART']
    n_configs = len(configs)

    bar_width = 0.35
    x = np.arange(n_benchmarks)

    # Plot bars for each config
    for i, config in enumerate(configs):
        if config not in energy_savings:
            continue

        values = []
        for benchmark in benchmarks_to_plot:
            if benchmark in energy_savings[config]:
                values.append(energy_savings[config][benchmark])
            else:
                values.append(0)

        offset = (i - 0.5) * bar_width
        bars = ax.bar(x + offset, values, bar_width,
                      label=CONFIG_MAPPING.get(config, config),
                      color=BAR_COLORS.get(config, 'gray'),
                      edgecolor='black',
                      linewidth=0.5)

    # Customize axes
    ax.set_ylabel('Energy Saving [%]', fontsize=12)
    ax.set_ylim(0, 45)
    ax.set_yticks(np.arange(0, 50, 10))

    ax.set_xticks(x)
    ax.set_xticklabels(benchmarks_to_plot, rotation=45, ha='right', fontsize=9)

    # Add legend
    ax.legend(loc='upper right', fontsize=10)

    # Add grid
    ax.yaxis.grid(True, linestyle='--', alpha=0.5)
    ax.set_axisbelow(True)

    # Add vertical line to separate individual benchmarks from mix workloads
    mix_start_idx = len([b for b in benchmarks_to_plot if b in INDIVIDUAL_BENCHMARKS])
    if mix_start_idx < n_benchmarks:
        ax.axvline(x=mix_start_idx - 0.5, color='gray', linestyle='--', linewidth=1, alpha=0.7)

    # Adjust layout
    plt.tight_layout()

    # Save
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"Chart saved to: {output_path}")

    # Save PDF
    pdf_path = output_path.rsplit('.', 1)[0] + '.pdf'
    plt.savefig(pdf_path, bbox_inches='tight')
    print(f"PDF saved to: {pdf_path}")

    plt.close()


def print_summary(energy_savings: Dict[str, Dict[str, float]], results: Dict[str, Dict[str, PowerData]]):
    """Print a summary table of energy savings."""
    print("\n" + "=" * 100)
    print("Energy Savings Summary (Figure 14)")
    print("=" * 100)

    # Get available benchmarks
    available_benchmarks = set()
    for config in energy_savings.values():
        available_benchmarks.update(config.keys())

    benchmarks_to_show = [b for b in BENCHMARK_ORDER if b in available_benchmarks]

    # Add GMEAN
    gmean_values = compute_gmean(energy_savings, [b for b in benchmarks_to_show if b != 'GMEAN'])
    for config, gmean in gmean_values.items():
        energy_savings[config]['GMEAN'] = gmean
    if 'GMEAN' not in benchmarks_to_show:
        benchmarks_to_show.append('GMEAN')

    # Header
    header = f"{'Benchmark':<16}{'DRAM Power':>12}{'Conv Power':>12}{'Conv Save':>12}{'SMART Power':>14}{'SMART Save':>12}"
    print(header)
    print("-" * len(header))

    for benchmark in benchmarks_to_show:
        dram_power = results.get('DRAM', {}).get(benchmark, PowerData()).average_power
        conv_power = results.get('Conv', {}).get(benchmark, PowerData()).average_power
        smart_power = results.get('SMART', {}).get(benchmark, PowerData()).average_power

        conv_saving = energy_savings.get('Conv', {}).get(benchmark, 0.0)
        smart_saving = energy_savings.get('SMART', {}).get(benchmark, 0.0)

        if benchmark == 'GMEAN':
            print("-" * len(header))
            print(f"{benchmark:<16}{'--':>12}{'--':>12}{conv_saving:>11.1f}%{'--':>14}{smart_saving:>11.1f}%")
        else:
            print(f"{benchmark:<16}{dram_power:>11.3f}W{conv_power:>11.3f}W{conv_saving:>11.1f}%{smart_power:>13.3f}W{smart_saving:>11.1f}%")

    print("=" * 100)

    # Print average savings (matching paper's expected values)
    print("\nAverage Energy Savings:")
    for config in ['Conv', 'SMART']:
        if config in energy_savings and 'GMEAN' in energy_savings[config]:
            print(f"  {CONFIG_MAPPING[config]}: {energy_savings[config]['GMEAN']:.1f}%")
    print("  (Paper expects: Conv-Pin ~13.8%, SMART ~29.4%)")


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    experiment_dir = os.path.dirname(script_dir)
    default_trace_log = os.path.join(experiment_dir, 'trace_log')
    default_output_dir = os.path.join(experiment_dir, 'output')

    parser = argparse.ArgumentParser(description='Generate Energy Savings chart (Figure 14)')
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
        args.output = os.path.join(default_output_dir, f'energy_saving_chart_{timestamp}.png')

    print(f"Scanning trace_log directory: {args.trace_log}")
    results = collect_results(args.trace_log)

    if not results:
        print("No results found!")
        return 1

    # Compute mix workloads
    results = compute_mix_workloads(results)

    # Calculate energy savings
    energy_savings = calculate_energy_savings(results)

    if not energy_savings:
        print("Could not calculate energy savings (DRAM baseline missing?)")
        return 1

    print_summary(energy_savings, results)
    generate_chart(energy_savings, args.output)

    return 0


if __name__ == '__main__':
    exit(main())

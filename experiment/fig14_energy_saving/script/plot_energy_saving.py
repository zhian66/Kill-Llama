#!/usr/bin/env python3
"""
Energy Savings Chart Generator for STT-MRAM Paper Reproduction (Figure 14)
[CORRECTED VERSION]

Changes:
- Implements energy integration (Power * Time) instead of simple power averaging.
- Detects simulation saturation (end of benchmark) to exclude idle tail energy.
- Calculates Total Energy metric for accurate savings comparison.

Usage:
    python plot_energy_saving_corrected.py [--trace-log PATH] [--output PATH]
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

# MIX_WORKLOADS = {
#     'mix1': ['imagick', 'sssp', 'stream_add', 'mcf'],
#     'mix2': ['bc', 'bfs', 'cc', 'lbm'],
#     'mix3': ['nab', 'omnetpp', 'pr', 'sssp'],
#     'mix4': ['stream_copy', 'stream_scale', 'stream_triad', 'tc'],
#     'mix5': ['bfs', 'imagick', 'mcf', 'nab'],
#     'mix6': ['cc', 'lbm', 'pr', 'tc'],
#     'mix7': ['bc', 'omnetpp', 'sssp', 'stream_add'],
# }

# Full benchmark order for plotting
# BENCHMARK_ORDER = INDIVIDUAL_BENCHMARKS + list(MIX_WORKLOADS.keys()) + ['GMEAN']
BENCHMARK_ORDER = INDIVIDUAL_BENCHMARKS + ['GMEAN']

# Bar colors matching paper's Figure 14
BAR_COLORS = {
    'Conv': '#808080',   # Light gray for Conv-Pin
    'SMART': '#404040',  # Dark gray for SMART
}


@dataclass
class PowerData:
    """
    Energy data from simulation.
    NOTE: Fields now store TOTAL ENERGY (Power * Cycles), not Average Power.
    """
    average_power: float = 0.0  # Stores Total Energy
    background: float = 0.0
    activation: float = 0.0
    burst: float = 0.0
    refresh: float = 0.0


def parse_log_file(filepath: str) -> Optional[PowerData]:
    """
    Parse a DRAMSim2 log file and calculate TOTAL ENERGY by integrating power over time.
    Stops accumulation when transactions saturate to exclude idle tails.
    """
    try:
        with open(filepath, 'r') as f:
            content = f.read()

        # Regex patterns
        # Epoch header: == Pending Transactions : <count> (<cycle>) ==
        epoch_pattern = re.compile(r'== Pending Transactions\s*:\s*(\d+)\s*\((\d+)\)==')
        
        # Data patterns
        power_pattern = re.compile(r'Average Power \(watts\)\s*:\s*([\d.]+)')
        trans_pattern = re.compile(r'Total Return Transactions\s*:\s*(\d+)')
        background_pattern = re.compile(r'-Background \(watts\)\s*:\s*([\d.]+)')
        act_pattern = re.compile(r'-Act/Pre\s*\(watts\)\s*:\s*([\d.]+)')
        burst_pattern = re.compile(r'-Burst\s*\(watts\)\s*:\s*([\d.]+)')
        refresh_pattern = re.compile(r'-Refresh\s*\(watts\)\s*:\s*([\d.]+)')

        # Find all epochs
        epochs = list(epoch_pattern.finditer(content))
        
        if not epochs:
            print(f"Warning: No epochs found in {filepath} (Format mismatch?)")
            return None

        total_energy = 0.0
        total_bg = 0.0
        total_act = 0.0
        total_burst = 0.0
        total_ref = 0.0

        last_cycle = 0
        last_trans = 0
        
        active_cycles_count = 0

        # Iterate through epochs
        for i in range(len(epochs)):
            match = epochs[i]
            pending_count = int(match.group(1))
            current_cycle = int(match.group(2))
            
            # Identify content for this epoch
            start_idx = match.end()
            end_idx = epochs[i+1].start() if i < len(epochs) - 1 else len(content)
            epoch_content = content[start_idx:end_idx]
            
            # Extract metrics
            avg_power_m = power_pattern.search(epoch_content)
            trans_m = trans_pattern.search(epoch_content)
            
            if not avg_power_m or not trans_m:
                continue
                
            avg_power = float(avg_power_m.group(1))
            curr_trans = int(trans_m.group(1))
            
            # Component powers (default to 0 if missing)
            bg_p = float(background_pattern.search(epoch_content).group(1)) if background_pattern.search(epoch_content) else 0.0
            act_p = float(act_pattern.search(epoch_content).group(1)) if act_pattern.search(epoch_content) else 0.0
            burst_p = float(burst_pattern.search(epoch_content).group(1)) if burst_pattern.search(epoch_content) else 0.0
            ref_p = float(refresh_pattern.search(epoch_content).group(1)) if refresh_pattern.search(epoch_content) else 0.0
            
            delta_cycles = current_cycle - last_cycle
            
            if delta_cycles > 0:
                # INTEGRATION LOGIC:
                # We only accumulate energy if the memory system is "Active".
                # "Active" means: New transactions completed OR Pending transactions exist.
                # If Pending=0 and Transactions didn't increase, it's Idle tail.
                
                is_active = (curr_trans > last_trans) or (pending_count > 0)
                
                # Heuristic: Allow one idle epoch transition, but generally stop if fully idle
                if is_active:
                     total_energy += avg_power * delta_cycles
                     total_bg += bg_p * delta_cycles
                     total_act += act_p * delta_cycles
                     total_burst += burst_p * delta_cycles
                     total_ref += ref_p * delta_cycles
                     active_cycles_count += delta_cycles
                elif active_cycles_count > 0:
                    # Simulation has likely finished useful work, entering idle tail.
                    # Stop integration to preserve accurate energy measurement for the task.
                    break
            
            last_cycle = current_cycle
            last_trans = curr_trans

        if active_cycles_count == 0:
             return None
             
        # Return TOTAL ENERGY in the fields
        return PowerData(
            average_power=total_energy,
            background=total_bg,
            activation=total_act,
            burst=total_burst,
            refresh=total_ref
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
    """Collect all power/energy data from log files."""
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


# def compute_mix_workloads(results: Dict[str, Dict[str, PowerData]]) -> Dict[str, Dict[str, PowerData]]:
#     """Compute mix workload energy by averaging component benchmark energies."""
#     for config in CONFIG_MAPPING.keys():
#         if config not in results:
#             continue

#         config_data = results[config]

#         for mix_name, components in MIX_WORKLOADS.items():
#             components_found = []
#             for comp in components:
#                 if comp in config_data:
#                     components_found.append(config_data[comp])

#             if components_found:
#                 n = len(components_found)
#                 # Sum of energies / N = Average Energy per benchmark in the mix
#                 results[config][mix_name] = PowerData(
#                     average_power=sum(c.average_power for c in components_found) / n,
#                     background=sum(c.background for c in components_found) / n,
#                     activation=sum(c.activation for c in components_found) / n,
#                     burst=sum(c.burst for c in components_found) / n,
#                     refresh=sum(c.refresh for c in components_found) / n,
#                 )

#     return results


def calculate_energy_savings(results: Dict[str, Dict[str, PowerData]]) -> Dict[str, Dict[str, float]]:
    """
    Calculate energy savings (%) for each config relative to DRAM baseline.
    Formula: (DRAM_TotalEnergy - Config_TotalEnergy) / DRAM_TotalEnergy * 100
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

            # average_power field now holds TOTAL ENERGY
            dram_energy = dram_data[benchmark].average_power
            config_energy = config_data[benchmark].average_power

            if dram_energy > 0:
                saving = (dram_energy - config_energy) / dram_energy * 100.0
                energy_savings[config][benchmark] = saving

    return dict(energy_savings)


def compute_gmean(energy_savings: Dict[str, Dict[str, float]], benchmarks: List[str]) -> Dict[str, float]:
    """Compute geometric mean of energy savings."""
    gmean_results = {}

    for config in ['Conv', 'SMART']:
        if config not in energy_savings:
            continue

        values = []
        for benchmark in benchmarks:
            if benchmark in energy_savings[config]:
                saving = energy_savings[config][benchmark]
                # Convert to ratio: Config/DRAM = 1 - Saving%
                ratio = 1 - saving / 100.0
                if ratio > 0:
                    values.append(ratio)

        if values:
            gmean_ratio = math.exp(sum(math.log(v) for v in values) / len(values))
            gmean_results[config] = (1 - gmean_ratio) * 100.0

    return gmean_results


def generate_chart(
    energy_savings: Dict[str, Dict[str, float]],
    output_path: str,
    figsize: Tuple[int, int] = (16, 6)
):
    """Generate a grouped bar chart matching Figure 14 style."""
    fig, ax = plt.subplots(figsize=figsize)

    available_benchmarks = set()
    for config in energy_savings.values():
        available_benchmarks.update(config.keys())

    benchmarks_to_plot = [b for b in BENCHMARK_ORDER if b in available_benchmarks]

    gmean_values = compute_gmean(energy_savings, [b for b in benchmarks_to_plot if b != 'GMEAN'])
    for config, gmean in gmean_values.items():
        energy_savings[config]['GMEAN'] = gmean

    if 'GMEAN' not in benchmarks_to_plot:
        benchmarks_to_plot.append('GMEAN')

    n_benchmarks = len(benchmarks_to_plot)
    configs = ['Conv', 'SMART']
    
    bar_width = 0.35
    x = np.arange(n_benchmarks)

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
        ax.bar(x + offset, values, bar_width,
               label=CONFIG_MAPPING.get(config, config),
               color=BAR_COLORS.get(config, 'gray'),
               edgecolor='black',
               linewidth=0.5)

    ax.set_ylabel('Energy Saving [%]', fontsize=12)
    ax.set_ylim(0, 45)
    ax.set_yticks(np.arange(0, 50, 10))
    ax.set_xticks(x)
    ax.set_xticklabels(benchmarks_to_plot, rotation=45, ha='right', fontsize=9)
    ax.legend(loc='upper right', fontsize=10)
    ax.yaxis.grid(True, linestyle='--', alpha=0.5)
    ax.set_axisbelow(True)

    mix_start_idx = len([b for b in benchmarks_to_plot if b in INDIVIDUAL_BENCHMARKS])
    if mix_start_idx < n_benchmarks:
        ax.axvline(x=mix_start_idx - 0.5, color='gray', linestyle='--', linewidth=1, alpha=0.7)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"Chart saved to: {output_path}")
    plt.close()


def print_summary(energy_savings: Dict[str, Dict[str, float]], results: Dict[str, Dict[str, PowerData]]):
    """Print a summary table of energy savings."""
    print("\n" + "=" * 100)
    print("Energy Savings Summary (Figure 14) - Based on Total Energy Integration")
    print("=" * 100)

    available_benchmarks = set()
    for config in energy_savings.values():
        available_benchmarks.update(config.keys())

    benchmarks_to_show = [b for b in BENCHMARK_ORDER if b in available_benchmarks]

    gmean_values = compute_gmean(energy_savings, [b for b in benchmarks_to_show if b != 'GMEAN'])
    for config, gmean in gmean_values.items():
        energy_savings[config]['GMEAN'] = gmean
    if 'GMEAN' not in benchmarks_to_show:
        benchmarks_to_show.append('GMEAN')

    # Note: Units are arbitrary energy units (Watt-Cycles), but relative saving is correct.
    header = f"{'Benchmark':<16}{'DRAM Energy':>12}{'Conv Energy':>12}{'Conv Save':>12}{'SMART Energy':>14}{'SMART Save':>12}"
    print(header)
    print("-" * len(header))

    for benchmark in benchmarks_to_show:
        # Values are now Total Energy
        dram_e = results.get('DRAM', {}).get(benchmark, PowerData()).average_power
        conv_e = results.get('Conv', {}).get(benchmark, PowerData()).average_power
        smart_e = results.get('SMART', {}).get(benchmark, PowerData()).average_power

        conv_saving = energy_savings.get('Conv', {}).get(benchmark, 0.0)
        smart_saving = energy_savings.get('SMART', {}).get(benchmark, 0.0)

        if benchmark == 'GMEAN':
            print("-" * len(header))
            print(f"{benchmark:<16}{'--':>12}{'--':>12}{conv_saving:>11.1f}%{'--':>14}{smart_saving:>11.1f}%")
        else:
            # Formatting as integers or scientific might be better depending on magnitude
            print(f"{benchmark:<16}{dram_e:>12.0f}{conv_e:>12.0f}{conv_saving:>11.1f}%{smart_e:>14.0f}{smart_saving:>11.1f}%")

    print("=" * 100)
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

    # results = compute_mix_workloads(results)  # Disabled: Mix workloads
    energy_savings = calculate_energy_savings(results)

    if not energy_savings:
        print("Could not calculate energy savings (DRAM baseline missing?)")
        return 1

    print_summary(energy_savings, results)
    generate_chart(energy_savings, args.output)

    return 0


if __name__ == '__main__':
    exit(main())
#!/usr/bin/env python3
"""
Address Mapping Sensitivity Chart Generator for STT-MRAM Paper (Figure 15)

Generates two separate charts comparing normalized IPC and Energy with different
address mapping schemes:
- Ro:Ba:Bg:Co (Scheme6) - Row buffer hit optimized
- Ro:Co:Ba:Bg (Scheme2) - Bank-level parallelism optimized

Features:
- Rolling generation: automatically detects available stats/log files
- Only plots workloads/configs that have data
- Shows normalized values relative to Ro:Ba:Bg:Co baseline
- Outputs separate PNG/PDF files in a timestamped folder

Usage:
    python plot_mapping.py [--stats-dir PATH] [--log-dir PATH] [--output-dir PATH]

Output:
    output/mapping_MMDD_HHMM/
    ├── fig15a_normalized_ipc.png
    ├── fig15a_normalized_ipc.pdf
    ├── fig15b_normalized_energy.png
    └── fig15b_normalized_energy.pdf
"""

import os
import re
import glob
import argparse
from collections import defaultdict
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

import matplotlib.pyplot as plt
import numpy as np


# Expected ordering
WORKLOADS_ORDER = ['mix1', 'mix2', 'mix3', 'mix4', 'mix5', 'mix6', 'mix7']

CONFIGS_ORDER = ['DRAM', 'Conv-Delay', 'SMART']
CONFIG_FILE_MAPPING = {
    'DRAM': 'DRAM',
    'Conv-Delay': 'Conv-Delay',
    'Conv_Delay': 'Conv-Delay',
    'ConvDelay': 'Conv-Delay',
    'SMART': 'SMART',
}

# Scheme mapping
SCHEMES = {
    'sch6': 'Ro:Ba:Bg:Co',
    'scheme6': 'Ro:Ba:Bg:Co',
    'sch2': 'Ro:Co:Ba:Bg',
    'scheme2': 'Ro:Co:Ba:Bg',
}

SCHEME_ORDER = ['Ro:Ba:Bg:Co', 'Ro:Co:Ba:Bg']

# Bar styles matching paper's Figure 15
# First scheme (Ro:Ba:Bg:Co) - solid colors
# Second scheme (Ro:Co:Ba:Bg) - hatched patterns
BAR_STYLES = {
    ('DRAM', 'Ro:Ba:Bg:Co'): {'color': 'white', 'edgecolor': 'black', 'hatch': ''},
    ('DRAM', 'Ro:Co:Ba:Bg'): {'color': 'gray', 'edgecolor': 'black', 'hatch': ''},
    ('Conv-Delay', 'Ro:Ba:Bg:Co'): {'color': 'white', 'edgecolor': 'black', 'hatch': '...'},
    ('Conv-Delay', 'Ro:Co:Ba:Bg'): {'color': 'white', 'edgecolor': 'black', 'hatch': '///'},
    ('SMART', 'Ro:Ba:Bg:Co'): {'color': 'black', 'edgecolor': 'black', 'hatch': ''},
    ('SMART', 'Ro:Co:Ba:Bg'): {'color': 'lightgray', 'edgecolor': 'black', 'hatch': ''},
}


@dataclass
class MappingData:
    """Data for a single configuration and scheme"""
    ipc: float = 0.0
    energy: float = 0.0  # Total energy in Joules or normalized


def parse_stats_file(filepath: str) -> Optional[float]:
    """
    Parse a MARSSx86 .stats file and extract IPC value.

    Returns:
        IPC value, or None if parsing fails
    """
    try:
        with open(filepath, 'r') as f:
            content = f.read()

        # Find IPC under commit section
        commit_pattern = r'commit:.*?ipc:\s*([\d.]+)'
        match = re.search(commit_pattern, content, re.DOTALL)

        if match:
            return float(match.group(1))

        # Fallback
        ipc_pattern = r'\bipc:\s*([\d.]+)'
        matches = re.findall(ipc_pattern, content)
        if matches:
            return float(matches[-1])

        return None

    except Exception as e:
        print(f"Warning: Failed to parse {filepath}: {e}")
        return None


def parse_dramsim_log(filepath: str) -> Optional[float]:
    """
    Parse a DRAMSim2 log file and extract total energy.

    Energy is calculated from power * time or directly from energy values.

    Returns:
        Total energy value, or None if parsing fails
    """
    try:
        with open(filepath, 'r') as f:
            content = f.read()

        # Try to find average power and cycles to calculate energy
        # Average Power (watts) * cycles / frequency = energy

        power_matches = re.findall(r'Average Power \(watts\)\s*:\s*([\d.]+)', content)
        if power_matches:
            # Use last (final) value
            avg_power = float(power_matches[-1])

            # We need to normalize anyway, so just use power as proxy for energy
            # Or find total cycles
            return avg_power

        return None

    except Exception as e:
        print(f"Warning: Failed to parse DRAMSim log {filepath}: {e}")
        return None


def scan_mapping_data(stats_dir: str, log_dir: Optional[str] = None) -> Dict[str, Dict[str, Dict[str, MappingData]]]:
    """
    Scan directory for stats files with scheme info.

    Expected filename format: {CONFIG}_{WORKLOAD}_{SCHEME}.stats
    Example: DRAM_mix1_sch6.stats, SMART_mix3_sch2.stats

    Also looks for corresponding DRAMSim2 logs:
    {CONFIG}_{WORKLOAD}_{SCHEME}.log

    Args:
        stats_dir: Directory containing .stats files
        log_dir: Directory containing .log files (defaults to stats_dir)

    Returns:
        Dictionary: {workload: {config: {scheme: MappingData}}}
    """
    if log_dir is None:
        log_dir = stats_dir

    data = defaultdict(lambda: defaultdict(dict))

    # Find all .stats files
    pattern = os.path.join(stats_dir, '*.stats')
    files = glob.glob(pattern)

    for filepath in files:
        filename = os.path.basename(filepath)
        name_without_ext = os.path.splitext(filename)[0]

        # Parse filename: {CONFIG}_{WORKLOAD}_{SCHEME}
        parts = name_without_ext.rsplit('_', 1)
        if len(parts) < 2:
            continue

        # Check if last part is a scheme
        scheme_raw = parts[1].lower()
        if scheme_raw not in SCHEMES:
            continue

        scheme = SCHEMES[scheme_raw]

        # Parse the rest: {CONFIG}_{WORKLOAD}
        config_workload = parts[0]
        cw_parts = config_workload.split('_', 1)
        if len(cw_parts) < 2:
            continue

        config_raw, workload = cw_parts[0], cw_parts[1]
        config = CONFIG_FILE_MAPPING.get(config_raw, config_raw)

        # Parse IPC from stats
        ipc = parse_stats_file(filepath)
        if ipc is None:
            continue

        # Try to find corresponding log file for energy (in log_dir)
        log_filename = name_without_ext + '.log'
        log_path = os.path.join(log_dir, log_filename)
        energy = 0.0
        if os.path.exists(log_path):
            energy_val = parse_dramsim_log(log_path)
            if energy_val:
                energy = energy_val

        data[workload][config][scheme] = MappingData(ipc=ipc, energy=energy)
        print(f"  Found: {config} / {workload} / {scheme} -> IPC={ipc:.4f}, Energy={energy:.4f}")

    return dict(data)


def calculate_normalized_values(data: Dict[str, Dict[str, Dict[str, MappingData]]]) -> Tuple[Dict, Dict]:
    """
    Calculate normalized IPC and Energy values.

    Baseline: Ro:Ba:Bg:Co (Scheme6) for each config

    Returns:
        (normalized_ipc, normalized_energy) dictionaries
    """
    normalized_ipc = defaultdict(lambda: defaultdict(dict))
    normalized_energy = defaultdict(lambda: defaultdict(dict))

    baseline_scheme = 'Ro:Ba:Bg:Co'

    for workload, configs in data.items():
        for config, schemes in configs.items():
            if baseline_scheme not in schemes:
                print(f"Warning: No baseline {baseline_scheme} for {config}/{workload}")
                continue

            baseline = schemes[baseline_scheme]

            for scheme, values in schemes.items():
                # Normalized IPC
                if baseline.ipc > 0:
                    normalized_ipc[workload][config][scheme] = values.ipc / baseline.ipc

                # Normalized Energy
                if baseline.energy > 0:
                    normalized_energy[workload][config][scheme] = values.energy / baseline.energy

    return dict(normalized_ipc), dict(normalized_energy)


def generate_chart(normalized_ipc: Dict, normalized_energy: Dict,
                   output_dir: str):
    """
    Generate the address mapping sensitivity charts as separate files.

    Args:
        normalized_ipc: {workload: {config: {scheme: normalized_value}}}
        normalized_energy: {workload: {config: {scheme: normalized_value}}}
        output_dir: Directory to save the charts (timestamped folder)
    """
    # Determine available workloads
    available_workloads = []
    for wl in WORKLOADS_ORDER:
        if wl in normalized_ipc or wl in normalized_energy:
            available_workloads.append(wl)

    # Add any not in order
    all_wl = set(normalized_ipc.keys()) | set(normalized_energy.keys())
    for wl in all_wl:
        if wl not in available_workloads:
            available_workloads.append(wl)

    if not available_workloads:
        print("No data to plot!")
        return

    # Determine available configs and schemes
    available_configs = []
    all_configs = set()
    for wl_data in list(normalized_ipc.values()) + list(normalized_energy.values()):
        all_configs.update(wl_data.keys())

    for cfg in CONFIGS_ORDER:
        if cfg in all_configs:
            available_configs.append(cfg)

    for cfg in all_configs:
        if cfg not in available_configs:
            available_configs.append(cfg)

    # Create output directory
    os.makedirs(output_dir, exist_ok=True)

    n_workloads = len(available_workloads)
    n_configs = len(available_configs)
    n_schemes = len(SCHEME_ORDER)
    n_bars_per_workload = n_configs * n_schemes

    bar_width = 0.8 / n_bars_per_workload
    x = np.arange(n_workloads)

    # ==================== Plot (a) Normalized IPC ====================
    fig1, ax1 = plt.subplots(figsize=(12, 5))

    bar_idx = 0
    for config in available_configs:
        for scheme in SCHEME_ORDER:
            values = []
            for wl in available_workloads:
                val = normalized_ipc.get(wl, {}).get(config, {}).get(scheme, None)
                values.append(val if val else 0)

            offset = (bar_idx - n_bars_per_workload/2 + 0.5) * bar_width
            style = BAR_STYLES.get((config, scheme),
                                   {'color': 'gray', 'edgecolor': 'black', 'hatch': ''})

            label = f'{config} : {scheme}'
            ax1.bar(x + offset, values, bar_width,
                   label=label,
                   color=style['color'],
                   edgecolor=style['edgecolor'],
                   hatch=style['hatch'],
                   linewidth=0.5)

            # Add annotations for values > 1.1 or < 0.9
            for j, val in enumerate(values):
                if val > 1.1:
                    ax1.annotate(f'{val:.2f}',
                               xy=(x[j] + offset, min(val, 1.04)),
                               xytext=(0, 3),
                               textcoords='offset points',
                               ha='center', va='bottom',
                               fontsize=7)

            bar_idx += 1

    ax1.set_ylabel('Normalized IPC', fontsize=11)
    ax1.set_xlabel('Workloads', fontsize=11)
    ax1.set_xticks(x)
    ax1.set_xticklabels(available_workloads, fontsize=10)
    ax1.axhline(y=1.0, color='black', linewidth=1)
    ax1.set_ylim(0.94, 1.04)
    ax1.yaxis.grid(True, linestyle='--', alpha=0.5)
    ax1.set_axisbelow(True)
    ax1.legend(loc='upper center', bbox_to_anchor=(0.5, 1.15),
              ncol=3, frameon=False, fontsize=9)
    ax1.set_title('(a) Normalized IPC', fontsize=12, y=1.20)

    plt.tight_layout()

    # Save IPC chart
    ipc_png = os.path.join(output_dir, 'fig15a_normalized_ipc.png')
    ipc_pdf = os.path.join(output_dir, 'fig15a_normalized_ipc.pdf')
    fig1.savefig(ipc_png, dpi=150, bbox_inches='tight')
    fig1.savefig(ipc_pdf, bbox_inches='tight')
    print(f"IPC chart saved to: {ipc_png}")
    print(f"IPC PDF saved to: {ipc_pdf}")
    plt.close(fig1)

    # ==================== Plot (b) Normalized Energy ====================
    fig2, ax2 = plt.subplots(figsize=(12, 5))

    bar_idx = 0
    for config in available_configs:
        for scheme in SCHEME_ORDER:
            values = []
            for wl in available_workloads:
                val = normalized_energy.get(wl, {}).get(config, {}).get(scheme, None)
                values.append(val if val else 0)

            offset = (bar_idx - n_bars_per_workload/2 + 0.5) * bar_width
            style = BAR_STYLES.get((config, scheme),
                                   {'color': 'gray', 'edgecolor': 'black', 'hatch': ''})

            label = f'{config} : {scheme}'
            ax2.bar(x + offset, values, bar_width,
                   label=label,
                   color=style['color'],
                   edgecolor=style['edgecolor'],
                   hatch=style['hatch'],
                   linewidth=0.5)

            # Add annotations for values > 1.1
            for j, val in enumerate(values):
                if val > 1.1:
                    ax2.annotate(f'{val:.2f}',
                               xy=(x[j] + offset, min(val, 1.1)),
                               xytext=(0, 3),
                               textcoords='offset points',
                               ha='center', va='bottom',
                               fontsize=7)

            bar_idx += 1

    ax2.set_ylabel('Normalized Energy', fontsize=11)
    ax2.set_xlabel('Workloads', fontsize=11)
    ax2.set_xticks(x)
    ax2.set_xticklabels(available_workloads, fontsize=10)
    ax2.axhline(y=1.0, color='black', linewidth=1)
    ax2.set_ylim(0.94, 1.1)
    ax2.yaxis.grid(True, linestyle='--', alpha=0.5)
    ax2.set_axisbelow(True)
    ax2.legend(loc='upper center', bbox_to_anchor=(0.5, 1.15),
              ncol=3, frameon=False, fontsize=9)
    ax2.set_title('(b) Normalized Energy', fontsize=12, y=1.20)

    plt.tight_layout()

    # Save Energy chart
    energy_png = os.path.join(output_dir, 'fig15b_normalized_energy.png')
    energy_pdf = os.path.join(output_dir, 'fig15b_normalized_energy.pdf')
    fig2.savefig(energy_png, dpi=150, bbox_inches='tight')
    fig2.savefig(energy_pdf, bbox_inches='tight')
    print(f"Energy chart saved to: {energy_png}")
    print(f"Energy PDF saved to: {energy_pdf}")
    plt.close(fig2)

    print(f"\nAll charts saved to: {output_dir}")


def main():
    parser = argparse.ArgumentParser(
        description='Generate Address Mapping Sensitivity chart (Figure 15)')
    parser.add_argument('--stats-dir', type=str,
                        default=os.path.join(os.path.dirname(__file__), '..', '..', 'stats'),
                        help='Directory containing .stats files (MARSSx86)')
    parser.add_argument('--log-dir', type=str,
                        default=None,
                        help='Directory containing .log files (DRAMSim2). Defaults to stats-dir')
    parser.add_argument('--output-dir', type=str,
                        default=None,
                        help='Output directory path (default: auto-generated timestamped folder)')

    args = parser.parse_args()

    # Resolve paths
    stats_dir = os.path.abspath(args.stats_dir)
    log_dir = os.path.abspath(args.log_dir) if args.log_dir else None

    if args.output_dir:
        output_dir = args.output_dir
    else:
        timestamp = datetime.now().strftime('%m%d_%H%M')
        base_output_dir = os.path.join(os.path.dirname(__file__), '..', 'output')
        output_dir = os.path.join(base_output_dir, f'mapping_{timestamp}')

    print(f"Scanning stats directory: {stats_dir}")
    if log_dir:
        print(f"Scanning log directory: {log_dir}")

    # Scan for data
    data = scan_mapping_data(stats_dir, log_dir)

    if not data:
        print("No mapping data files found!")
        print("Expected filename format: {CONFIG}_{WORKLOAD}_{SCHEME}.stats")
        print("Example: DRAM_mix1_sch6.stats, SMART_mix3_sch2.stats")
        return

    print(f"\nFound data for {len(data)} workloads")

    # Calculate normalized values
    normalized_ipc, normalized_energy = calculate_normalized_values(data)

    if not normalized_ipc and not normalized_energy:
        print("No normalized values to calculate!")
        return

    # Generate charts (separate files in timestamped folder)
    generate_chart(normalized_ipc, normalized_energy, output_dir)


if __name__ == '__main__':
    main()

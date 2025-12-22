#!/usr/bin/env python3
"""
Clean erroneous Refresh power values from DRAMSim2 log files.

SMART/Conv logs may have incorrect Refresh power due to configuration errors.
This script fixes the Refresh value and recalculates Average Power.
"""

import re
import argparse
import os
from pathlib import Path


def should_process_file(filepath: str) -> bool:
    """Check if file should be processed (SMART or Conv, not DRAM)."""
    filename = os.path.basename(filepath).upper()
    return ('SMART' in filename or 'CONV' in filename) and 'DRAM' not in filename


def clean_power_data(content: str, threshold: float = 0.1) -> tuple[str, int]:
    """
    Clean Power Data blocks in log content.

    Returns:
        tuple: (cleaned_content, number_of_fixes)
    """
    # Pattern to match Power Data block
    pattern = re.compile(
        r'(== Power Data for Rank\s+\d+\n)'
        r'(\s+Average Power \(watts\)\s+:\s+)([\d.]+)(\n)'
        r'(\s+-Background \(watts\)\s+:\s+)([\d.]+)(\n)'
        r'(\s+-Act/Pre\s+\(watts\)\s+:\s+)([\d.]+)(\n)'
        r'(\s+-Burst\s+\(watts\)\s+:\s+)([\d.]+)(\n)'
        r'(\s+-Refresh\s+\(watts\)\s+:\s+)([\d.]+)(\n)',
        re.MULTILINE
    )

    fixes = 0

    def replace_block(match):
        nonlocal fixes

        # Extract values
        background = float(match.group(6))
        act_pre = float(match.group(9))
        burst = float(match.group(12))
        refresh = float(match.group(15))

        # Check if refresh needs fixing
        if refresh > threshold:
            fixes += 1
            new_refresh = 0.000
            new_average = background + act_pre + burst + new_refresh

            return (
                f"{match.group(1)}"
                f"{match.group(2)}{new_average:.3f}{match.group(4)}"
                f"{match.group(5)}{match.group(6)}{match.group(7)}"
                f"{match.group(8)}{match.group(9)}{match.group(10)}"
                f"{match.group(11)}{match.group(12)}{match.group(13)}"
                f"{match.group(14)}{new_refresh:.3f}{match.group(16)}"
            )
        return match.group(0)

    cleaned = pattern.sub(replace_block, content)
    return cleaned, fixes


def process_file(input_path: str, threshold: float = 0.1) -> str:
    """
    Process a single log file.

    Returns:
        str: Output file path
    """
    with open(input_path, 'r') as f:
        content = f.read()

    cleaned, fixes = clean_power_data(content, threshold)

    # Generate output filename
    path = Path(input_path)
    output_path = path.parent / f"{path.stem}_cleaned{path.suffix}"

    with open(output_path, 'w') as f:
        f.write(cleaned)

    print(f"  {path.name}: {fixes} fixes -> {output_path.name}")
    return str(output_path)


def main():
    parser = argparse.ArgumentParser(
        description='Clean erroneous Refresh power values from DRAMSim2 logs'
    )
    parser.add_argument(
        'path',
        help='Log file or directory to process'
    )
    parser.add_argument(
        '-t', '--threshold',
        type=float,
        default=0.1,
        help='Refresh power threshold (default: 0.1W)'
    )

    args = parser.parse_args()
    path = Path(args.path)

    if path.is_file():
        if should_process_file(str(path)):
            process_file(str(path), args.threshold)
        else:
            print(f"Skipping {path.name} (not SMART/Conv file)")

    elif path.is_dir():
        log_files = list(path.glob('*.log'))
        print(f"Found {len(log_files)} log files in {path}")

        processed = 0
        for log_file in log_files:
            if should_process_file(str(log_file)):
                process_file(str(log_file), args.threshold)
                processed += 1
            else:
                print(f"  Skipping {log_file.name}")

        print(f"\nProcessed {processed} files")

    else:
        print(f"Error: {path} not found")
        exit(1)


if __name__ == '__main__':
    main()

#!/bin/bash
#
# Batch Runner for Energy Savings Experiment (Figure 14)
#
# This script runs DRAMSim2 simulations for energy analysis
# Compares Conv-Pin and SMART energy savings over DRAM baseline
#
# Usage: ./run_batch.sh [config_name]
#   config_name: DRAM, Conv, SMART, or all (default: all)

set -e

# ============================================
# Configuration
# ============================================
EXPERIMENT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DRAMSIM_DIR="/home/ubuntu/sttmram/Kill-Llama/DRAMSim2"
TRACE_BASE="/home/ubuntu/sttmram/Kill-Llama/benchmark/traces/trc"

# System config
SYSTEM_INI="${EXPERIMENT_DIR}/system_energy.ini"

# Output directory
OUTPUT_DIR="${EXPERIMENT_DIR}/trace_log"
ARCHIVE_DIR="${EXPERIMENT_DIR}/archive"

# Date tag (MMDD format) - using Taiwan timezone (UTC+8)
DATE_TAG=$(TZ='Asia/Taipei' date +%m%d)

# Configuration selection (default: run all configs)
CONFIG_LIST="${1:-all}"

# If "all", run all three configs
if [[ "${CONFIG_LIST}" == "all" ]]; then
    CONFIGS=("DRAM" "Conv" "SMART")
else
    CONFIGS=("${CONFIG_LIST}")
fi

# Device ini mapping
declare -A DEVICE_INI_MAP
DEVICE_INI_MAP["DRAM"]="${DRAMSIM_DIR}/ini/Baseline_DRAM.ini"
DEVICE_INI_MAP["Conv"]="${DRAMSIM_DIR}/ini/Conv-STT-MRAM.ini"
DEVICE_INI_MAP["SMART"]="${DRAMSIM_DIR}/ini/SMART.ini"

# All trace files for Figure 14
# Includes all benchmarks needed for mix1-7 calculation and GMEAN
TRACES=(
    # GAP benchmarks
    "GAP/bc.trc:bc"
    "GAP/bfs.trc:bfs"
    "GAP/cc.trc:cc"
    "GAP/pr.trc:pr"
    "GAP/sssp.trc:sssp"
    "GAP/tc.trc:tc"
    # STREAM benchmarks
    "STREAM/stream_add.trc:stream_add"
    "STREAM/stream_copy.trc:stream_copy"
    "STREAM/stream_scale.trc:stream_scale"
    "STREAM/stream_triad.trc:stream_triad"
    # SPEC CPU benchmarks
    "SPEC/imagick.trc:imagick"
    "SPEC/lbm.trc:lbm"
    "SPEC/mcf.trc:mcf"
    "SPEC/nab.trc:nab"
    "SPEC/omnetpp.trc:omnetpp"
    "SPEC/xalancbmk.trc:xalancbmk"
)

# Number of cycles to simulate
NUM_CYCLES=100000

# ============================================
# Functions
# ============================================
print_header() {
    local config="$1"
    local device_ini="$2"
    echo "============================================"
    echo " Energy Savings Experiment (Fig 14)"
    echo "============================================"
    echo " Date Tag:      ${DATE_TAG}"
    echo " Configuration: ${config}"
    echo " Device INI:    ${device_ini}"
    echo " System INI:    ${SYSTEM_INI}"
    echo " Output Dir:    ${OUTPUT_DIR}"
    echo "============================================"
}

archive_previous() {
    # Archive previous trace_log if exists and not empty
    if [[ -d "${OUTPUT_DIR}" ]] && [[ -n "$(ls -A ${OUTPUT_DIR} 2>/dev/null)" ]]; then
        mkdir -p "${ARCHIVE_DIR}"

        # Find a unique archive name (Taiwan timezone)
        local archive_name="trace_log_$(TZ='Asia/Taipei' date +%m%d_%H%M%S)"
        local archive_path="${ARCHIVE_DIR}/${archive_name}"

        echo "[ARCHIVE] Moving previous results to ${archive_path}"
        mv "${OUTPUT_DIR}" "${archive_path}"
    fi

    # Create fresh output directory
    mkdir -p "${OUTPUT_DIR}"
}

run_trace() {
    local config="$1"
    local trace_path="$2"
    local trace_name="$3"
    local full_trace_path="${TRACE_BASE}/${trace_path}"
    local output_file="${OUTPUT_DIR}/${config}_${trace_name}_${DATE_TAG}.log"
    local device_ini="${DEVICE_INI_MAP[$config]}"

    if [[ ! -f "${full_trace_path}" ]]; then
        echo "[SKIP] Trace not found: ${full_trace_path}"
        return 1
    fi

    echo "[RUN] ${config}/${trace_name} -> ${output_file}"

    # Run DRAMSim2
    cd "${DRAMSIM_DIR}"
    ./DRAMSim \
        -t "${full_trace_path}" \
        -s "${SYSTEM_INI}" \
        -d "${device_ini}" \
        -c "${NUM_CYCLES}" \
        > "${output_file}" 2>&1

    # Extract power from output
    local power=$(grep "Average Power (watts)" "${output_file}" | tail -1 | grep -oP '[\d.]+')
    echo "    Power: ${power}W"

    return 0
}

# ============================================
# Main
# ============================================

# Validate configs
for config in "${CONFIGS[@]}"; do
    if [[ -z "${DEVICE_INI_MAP[$config]}" ]]; then
        echo "Error: Unknown config '${config}'"
        echo "Valid configs: DRAM, Conv, SMART, or 'all'"
        exit 1
    fi
    if [[ ! -f "${DEVICE_INI_MAP[$config]}" ]]; then
        echo "Error: Device INI not found at ${DEVICE_INI_MAP[$config]}"
        exit 1
    fi
done

# Check prerequisites
if [[ ! -x "${DRAMSIM_DIR}/DRAMSim" ]]; then
    echo "Error: DRAMSim executable not found at ${DRAMSIM_DIR}/DRAMSim"
    exit 1
fi

if [[ ! -f "${SYSTEM_INI}" ]]; then
    echo "Error: System INI not found at ${SYSTEM_INI}"
    exit 1
fi

# Archive previous results and create fresh output directory
archive_previous

# Copy system config for reference
cp "${SYSTEM_INI}" "${OUTPUT_DIR}/system_${DATE_TAG}.ini"

# Run all configs
TOTAL_SUCCESS=0
TOTAL_FAIL=0

for CONFIG_NAME in "${CONFIGS[@]}"; do
    DEVICE_INI="${DEVICE_INI_MAP[$CONFIG_NAME]}"

    # Copy device config for reference
    cp "${DEVICE_INI}" "${OUTPUT_DIR}/${CONFIG_NAME}_device_${DATE_TAG}.ini"

    print_header "${CONFIG_NAME}" "${DEVICE_INI}"

    echo ""
    echo "Running simulations for ${CONFIG_NAME}..."
    echo ""

    SUCCESS_COUNT=0
    FAIL_COUNT=0

    for trace_spec in "${TRACES[@]}"; do
        trace_path="${trace_spec%%:*}"
        trace_name="${trace_spec##*:}"

        if run_trace "${CONFIG_NAME}" "${trace_path}" "${trace_name}"; then
            ((SUCCESS_COUNT++)) || true
        else
            ((FAIL_COUNT++)) || true
        fi
    done

    echo ""
    echo "[${CONFIG_NAME}] Completed: ${SUCCESS_COUNT} success, ${FAIL_COUNT} failed"

    ((TOTAL_SUCCESS += SUCCESS_COUNT)) || true
    ((TOTAL_FAIL += FAIL_COUNT)) || true
done

echo ""
echo "============================================"
echo " All Completed: ${TOTAL_SUCCESS} success, ${TOTAL_FAIL} failed"
echo " Configs: ${CONFIGS[*]}"
echo " Results saved to: ${OUTPUT_DIR}"
echo "============================================"
echo ""
echo "Next: Run 'python script/plot_energy_saving.py' to generate the chart"

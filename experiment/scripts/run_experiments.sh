#!/bin/bash
#
# MARSSx86 Experiment Runner
# ==========================
#
# This script runs all experiments for the SMART STT-MRAM paper reproduction.
# It iterates over workloads, memory configurations, and address mapping schemes.
#
# Usage:
#   ./run_experiments.sh                    # Run all experiments
#   ./run_experiments.sh stream_triad       # Run specific workload
#   ./run_experiments.sh stream_triad DRAM  # Run specific workload + config
#   ./run_experiments.sh --pilot            # Run pilot test only
#

set -e

# ============================================
# Configuration
# ============================================
PROJ_ROOT="/home/ubuntu/sttmram/Kill-Llama"
MARSS_DIR="${PROJ_ROOT}/marss.dramsim"
QEMU_BIN="${MARSS_DIR}/qemu/qemu-system-x86_64"
DISK_IMAGE="${MARSS_DIR}/ubuntu_12_04.qcow2"
DRAMSIM_DIR="${PROJ_ROOT}/DRAMSim2"
RESULTS_DIR="${PROJ_ROOT}/experiment/results"
CONFIGS_DIR="${PROJ_ROOT}/experiment/configs"

# Experiment parameters
INST_COUNT="${INST_COUNT:-300000000}"  # 300M instructions (adjustable via env var)

# Memory configurations
declare -A MEM_CONFIGS
MEM_CONFIGS["DRAM"]="${DRAMSIM_DIR}/ini/Baseline_DRAM.ini"
MEM_CONFIGS["Conv"]="${DRAMSIM_DIR}/ini/Conv-STT-MRAM.ini"
MEM_CONFIGS["SMART"]="${DRAMSIM_DIR}/ini/SMART.ini"

# Address mapping schemes
declare -A SCHEMES
SCHEMES["sch2"]="${DRAMSIM_DIR}/system.ini"
SCHEMES["sch6"]="${DRAMSIM_DIR}/system_sch6.ini"

# Workloads (checkpoint name -> machine type)
# Available machine types: quad_core, ooo_2_th, moesi_private_L2, private_L2, shared_l2
# Note: single_core is NOT available - using quad_core instead
# TODO: Generate single_core machine type from config/default.conf
declare -A WORKLOADS
WORKLOADS["stream_triad"]="quad_core"
WORKLOADS["stream_copy"]="quad_core"
WORKLOADS["stream_add"]="quad_core"
WORKLOADS["stream_scale"]="quad_core"
# GAP benchmarks
WORKLOADS["gap_bfs"]="quad_core"
WORKLOADS["gap_sssp"]="quad_core"
WORKLOADS["gap_bc"]="quad_core"
WORKLOADS["gap_cc"]="quad_core"
WORKLOADS["gap_pr"]="quad_core"
WORKLOADS["gap_tc"]="quad_core"
# PARSEC benchmarks
WORKLOADS["blackscholes"]="quad_core"
WORKLOADS["canneal"]="quad_core"
WORKLOADS["streamcluster"]="quad_core"
WORKLOADS["fluidanimate"]="quad_core"
WORKLOADS["swaptions"]="quad_core"
WORKLOADS["freqmine"]="quad_core"
# MIX (to be added)
# WORKLOADS["mix1"]="quad_core"

# Date tag for file naming
DATE_TAG=$(TZ='Asia/Taipei' date +%m%d_%H%M)

# ============================================
# Functions
# ============================================

print_header() {
    echo ""
    echo "============================================"
    echo " MARSSx86 Experiment Runner"
    echo " Date: $(date)"
    echo " Instructions: ${INST_COUNT}"
    echo "============================================"
    echo ""
}

print_config() {
    local workload="$1"
    local config="$2"
    local scheme="$3"
    local run_id="$4"

    echo "--------------------------------------------"
    echo " Workload:  ${workload}"
    echo " Config:    ${config}"
    echo " Scheme:    ${scheme}"
    echo " Run ID:    ${run_id}"
    echo "--------------------------------------------"
}

check_prerequisites() {
    local errors=0

    if [[ ! -x "${QEMU_BIN}" ]]; then
        echo "ERROR: QEMU binary not found: ${QEMU_BIN}"
        ((errors++))
    fi

    if [[ ! -f "${DISK_IMAGE}" ]]; then
        echo "ERROR: Disk image not found: ${DISK_IMAGE}"
        ((errors++))
    fi

    for config in "${!MEM_CONFIGS[@]}"; do
        if [[ ! -f "${MEM_CONFIGS[$config]}" ]]; then
            echo "ERROR: Device INI not found: ${MEM_CONFIGS[$config]}"
            ((errors++))
        fi
    done

    for scheme in "${!SCHEMES[@]}"; do
        if [[ ! -f "${SCHEMES[$scheme]}" ]]; then
            echo "ERROR: System INI not found: ${SCHEMES[$scheme]}"
            ((errors++))
        fi
    done

    if [[ ${errors} -gt 0 ]]; then
        echo ""
        echo "Found ${errors} error(s). Please fix them before running."
        exit 1
    fi
}

create_simconfig() {
    local run_id="$1"
    local device_ini="$2"
    local system_ini="$3"
    local machine="$4"
    local stats_file="$5"
    local log_dir="$6"

    local config_file="${CONFIGS_DIR}/${run_id}.simconfig"

    mkdir -p "${CONFIGS_DIR}"
    mkdir -p "${log_dir}"

    cat > "${config_file}" <<EOF
-run
-stopinsns ${INST_COUNT}
-stats ${stats_file}
-logfile ${RESULTS_DIR}/${run_id}.log
-dramsim-device-ini-file ${device_ini}
-dramsim-system-ini-file ${system_ini}
-dramsim-results-dir-name ${log_dir}
-machine ${machine}
-kill-after-run
-quiet
EOF

    echo "${config_file}"
}

run_experiment() {
    local workload="$1"
    local config="$2"
    local scheme="$3"

    local device_ini="${MEM_CONFIGS[$config]}"
    local system_ini="${SCHEMES[$scheme]}"
    local machine="${WORKLOADS[$workload]}"

    # Generate run ID: {CONFIG}_{WORKLOAD}_{SCHEME}_{INST}_{DATE}
    local inst_short=$((INST_COUNT / 1000000))M
    local run_id="${config}_${workload}_${scheme}_${inst_short}"

    local stats_file="${RESULTS_DIR}/${run_id}.stats"
    local log_dir="${RESULTS_DIR}/${run_id}_logs"
    local console_log="${RESULTS_DIR}/${run_id}.console.log"
    local checkpoint="chk_${workload}"

    print_config "${workload}" "${config}" "${scheme}" "${run_id}"

    # Check if checkpoint exists
    # Note: We can't easily check checkpoint existence without querying the disk image
    # For now, we'll just try to run and handle errors

    # Create simconfig
    local config_file
    config_file=$(create_simconfig "${run_id}" "${device_ini}" "${system_ini}" "${machine}" "${stats_file}" "${log_dir}")

    echo "[INFO] Config: ${config_file}"
    echo "[INFO] Stats:  ${stats_file}"
    echo "[INFO] Logs:   ${log_dir}"

    # Set environment
    export LD_LIBRARY_PATH="${DRAMSIM_DIR}:${LD_LIBRARY_PATH}"

    # Run QEMU - must run from MARSS_DIR for BIOS files
    echo "[INFO] Starting simulation..."
    local start_time=$(date +%s)

    pushd "${MARSS_DIR}" > /dev/null
    "${QEMU_BIN}" -m 8G \
        -drive file="${DISK_IMAGE}",format=qcow2 \
        -loadvm "${checkpoint}" \
        -simconfig "${config_file}" \
        -nographic \
        -snapshot \
        > "${console_log}" 2>&1
    popd > /dev/null

    local exit_code=$?
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))

    # Check results
    if [[ ${exit_code} -eq 0 ]] && [[ -f "${stats_file}" ]] && [[ -s "${stats_file}" ]]; then
        echo "[SUCCESS] Completed in ${duration}s"
        echo "[SUCCESS] Stats: $(wc -l < "${stats_file}") lines"
        return 0
    else
        echo "[FAILED] Exit code: ${exit_code}, Duration: ${duration}s"
        echo "[FAILED] Check: ${console_log}"
        tail -20 "${console_log}" 2>/dev/null || true
        return 1
    fi
}

run_pilot_test() {
    echo ""
    echo "############################################"
    echo " PILOT TEST"
    echo " Running: stream_triad + DRAM + sch6"
    echo "############################################"
    echo ""

    run_experiment "stream_triad" "DRAM" "sch6"
}

run_all_experiments() {
    local filter_workload="${1:-}"
    local filter_config="${2:-}"

    local total=0
    local success=0
    local failed=0

    # Calculate total
    for workload in "${!WORKLOADS[@]}"; do
        [[ -n "${filter_workload}" ]] && [[ "${workload}" != "${filter_workload}" ]] && continue
        for config in "${!MEM_CONFIGS[@]}"; do
            [[ -n "${filter_config}" ]] && [[ "${config}" != "${filter_config}" ]] && continue
            for scheme in "${!SCHEMES[@]}"; do
                ((total++))
            done
        done
    done

    echo ""
    echo "############################################"
    echo " EXPERIMENT BATCH"
    echo " Total experiments: ${total}"
    echo "############################################"
    echo ""

    local current=0

    for workload in "${!WORKLOADS[@]}"; do
        [[ -n "${filter_workload}" ]] && [[ "${workload}" != "${filter_workload}" ]] && continue

        for config in "${!MEM_CONFIGS[@]}"; do
            [[ -n "${filter_config}" ]] && [[ "${config}" != "${filter_config}" ]] && continue

            for scheme in "${!SCHEMES[@]}"; do
                ((current++))
                echo ""
                echo ">>> Progress: ${current}/${total}"
                echo ""

                if run_experiment "${workload}" "${config}" "${scheme}"; then
                    ((success++))
                else
                    ((failed++))
                fi
            done
        done
    done

    echo ""
    echo "############################################"
    echo " BATCH COMPLETE"
    echo " Total:   ${total}"
    echo " Success: ${success}"
    echo " Failed:  ${failed}"
    echo "############################################"
    echo ""
}

# ============================================
# Main
# ============================================

print_header
check_prerequisites

mkdir -p "${RESULTS_DIR}"
mkdir -p "${CONFIGS_DIR}"

case "${1:-}" in
    --pilot)
        run_pilot_test
        ;;
    --help|-h)
        echo "Usage: $0 [OPTIONS] [WORKLOAD] [CONFIG]"
        echo ""
        echo "Options:"
        echo "  --pilot     Run pilot test only (stream_triad + DRAM + sch6)"
        echo "  --help      Show this help message"
        echo ""
        echo "Examples:"
        echo "  $0                      # Run all experiments"
        echo "  $0 stream_triad         # Run all configs for stream_triad"
        echo "  $0 stream_triad DRAM    # Run DRAM config for stream_triad"
        echo "  $0 --pilot              # Run pilot test"
        echo ""
        echo "Environment variables:"
        echo "  INST_COUNT   Number of instructions (default: 300000000)"
        echo ""
        echo "Available workloads: ${!WORKLOADS[*]}"
        echo "Available configs: ${!MEM_CONFIGS[*]}"
        echo "Available schemes: ${!SCHEMES[*]}"
        ;;
    *)
        run_all_experiments "${1:-}" "${2:-}"
        ;;
esac

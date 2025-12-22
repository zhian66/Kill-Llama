/*
 * PARSEC Hooks Implementation for MARSSx86
 * Maps PARSEC ROI hooks to ptlcalls
 */

#include <stdio.h>
#include "hooks.h"
#include "../ptlcalls.h"

static const char* benchmark_names[] = {
    "blackscholes", "bodytrack", "canneal", "dedup", "facesim",
    "ferret", "fluidanimate", "freqmine", "raytrace", "streamcluster",
    "swaptions", "vips", "x264"
};

void __parsec_bench_begin(enum __parsec_benchmark __bench) {
    if (__bench <= __parsec_x264) {
        printf("[PARSEC] Benchmark %s starting\n", benchmark_names[__bench]);
    }
    fflush(stdout);
}

void __parsec_bench_end() {
    printf("[PARSEC] Benchmark finished\n");
    fflush(stdout);
}

void __parsec_roi_begin() {
    printf("[PARSEC] ROI Begin - Switching to Simulation Mode\n");
    fflush(stdout);
    ptlcall_switch_to_sim();
}

void __parsec_roi_end() {
    printf("[PARSEC] ROI End - Ending Simulation\n");
    fflush(stdout);
    ptlcall_kill();
}

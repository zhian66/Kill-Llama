/*
 * hooks.c - ROI (Region of Interest) Hooks for MARSSx86 Simulation
 *
 * These hooks are used to switch between emulation and simulation modes.
 * Include this file and link hooks.o with your benchmark.
 */

#include <stdio.h>
#include "ptlcalls.h"

void __parsec_roi_begin(void) {
    printf("HOOKS: Switching to Simulation Mode...\n");
    fflush(stdout);
    ptlcall_switch_to_sim();
}

void __parsec_roi_end(void) {
    printf("HOOKS: Killing Simulation...\n");
    fflush(stdout);
    ptlcall_kill();
}

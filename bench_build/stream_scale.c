/*
 * STREAM Benchmark - SCALE Only
 * Modified for MARSSx86 simulation with ptlcalls hooks
 *
 * SCALE: b[i] = scalar * c[i]
 */

#include <stdio.h>
#include <stdlib.h>
#include "ptlcalls.h"

#ifndef STREAM_ARRAY_SIZE
#define STREAM_ARRAY_SIZE 10000000
#endif

#ifndef STREAM_TYPE
#define STREAM_TYPE double
#endif

#ifndef NTIMES
#define NTIMES 10
#endif

static volatile STREAM_TYPE b[STREAM_ARRAY_SIZE];
static volatile STREAM_TYPE c[STREAM_ARRAY_SIZE];

int main(int argc, char *argv[])
{
    ssize_t j;
    int k;
    STREAM_TYPE scalar = 3.0;

    printf("STREAM SCALE Benchmark for MARSSx86\n");
    printf("Array size = %llu elements\n", (unsigned long long)STREAM_ARRAY_SIZE);
    printf("Memory per array = %.1f MiB\n",
           sizeof(STREAM_TYPE) * (double)STREAM_ARRAY_SIZE / 1024.0 / 1024.0);
    printf("Total memory = %.1f MiB\n",
           2.0 * sizeof(STREAM_TYPE) * (double)STREAM_ARRAY_SIZE / 1024.0 / 1024.0);
    printf("Number of iterations = %d\n", NTIMES);
    fflush(stdout);

    /* Initialize arrays */
    printf("Initializing arrays...\n");
    fflush(stdout);
    for (j = 0; j < STREAM_ARRAY_SIZE; j++) {
        b[j] = 0.0;
        c[j] = 1.0;
    }

    printf("Starting simulation (SCALE: b = scalar*c)...\n");
    fflush(stdout);

    /* Switch to simulation mode */
    ptlcall_switch_to_sim();

    /* SCALE kernel */
    for (k = 0; k < NTIMES; k++) {
        for (j = 0; j < STREAM_ARRAY_SIZE; j++) {
            b[j] = scalar * c[j];
        }
    }

    /* End simulation */
    ptlcall_kill();

    printf("SCALE completed.\n");
    return 0;
}

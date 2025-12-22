#!/bin/bash
#
# Compile PARSEC benchmarks for MARSSx86
#

set -e

BENCH_DIR="/home/ubuntu/sttmram/Kill-Llama/bench_build"
PARSEC_DIR="$BENCH_DIR/parsec/parsec-benchmark-master/pkgs"
HOOKS_DIR="$BENCH_DIR/parsec_hooks"
OUTPUT_DIR="$BENCH_DIR/parsec_bin"

mkdir -p $OUTPUT_DIR

# Common flags
CFLAGS="-O2 -static -D_GNU_SOURCE -DENABLE_PARSEC_HOOKS -DENABLE_THREADS -pthread"
CXXFLAGS="$CFLAGS"
INCLUDES="-I$HOOKS_DIR -I$BENCH_DIR"

# Compile hooks library with ptlcalls
echo "=== Compiling hooks library ==="
gcc -c $CFLAGS $INCLUDES $HOOKS_DIR/hooks.c -o $HOOKS_DIR/hooks.o
gcc -c $CFLAGS $INCLUDES $BENCH_DIR/hooks.c -o $BENCH_DIR/ptlcall_hooks.o

echo ""
echo "=== Compiling Blackscholes ==="
cd $PARSEC_DIR/apps/blackscholes/src
# Preprocess m4 file to get the actual source
if [ -f c.m4.pthreads ]; then
    m4 -D ENABLE_THREADS c.m4.pthreads > blackscholes_pthreads.c 2>/dev/null || cp blackscholes.c blackscholes_pthreads.c
fi
gcc $CFLAGS $INCLUDES -lm \
    blackscholes.c \
    $HOOKS_DIR/hooks.o $BENCH_DIR/ptlcall_hooks.o \
    -o $OUTPUT_DIR/blackscholes 2>&1 || echo "Blackscholes compilation failed"

echo ""
echo "=== Compiling Canneal ==="
cd $PARSEC_DIR/kernels/canneal/src
g++ $CXXFLAGS $INCLUDES \
    main.cpp annealer_thread.cpp netlist.cpp netlist_elem.cpp rng.cpp \
    $HOOKS_DIR/hooks.o $BENCH_DIR/ptlcall_hooks.o \
    -o $OUTPUT_DIR/canneal 2>&1 || echo "Canneal compilation failed"

echo ""
echo "=== Compiling Streamcluster ==="
cd $PARSEC_DIR/kernels/streamcluster/src
g++ $CXXFLAGS $INCLUDES -lm \
    streamcluster.cpp \
    $HOOKS_DIR/hooks.o $BENCH_DIR/ptlcall_hooks.o \
    -o $OUTPUT_DIR/streamcluster 2>&1 || echo "Streamcluster compilation failed"

echo ""
echo "=== Compiling Fluidanimate ==="
cd $PARSEC_DIR/apps/fluidanimate/src
g++ $CXXFLAGS $INCLUDES -lm \
    pthreads.cpp cellpool.cpp \
    $HOOKS_DIR/hooks.o $BENCH_DIR/ptlcall_hooks.o \
    -o $OUTPUT_DIR/fluidanimate 2>&1 || echo "Fluidanimate compilation failed"

echo ""
echo "=== Compiling Swaptions ==="
cd $PARSEC_DIR/apps/swaptions/src
g++ $CXXFLAGS $INCLUDES -lm \
    HJM_Securities.cpp HJM_SimPath_Forward_Blocking.cpp HJM.cpp \
    CumNormalInv.cpp MaxFunction.cpp RanUnif.cpp nr_routines.cpp icdf.cpp \
    $HOOKS_DIR/hooks.o $BENCH_DIR/ptlcall_hooks.o \
    -o $OUTPUT_DIR/swaptions 2>&1 || echo "Swaptions compilation failed"

echo ""
echo "=== Compiling Freqmine ==="
cd $PARSEC_DIR/apps/freqmine/src
g++ $CXXFLAGS $INCLUDES \
    fp_tree.cpp data.cpp fpmax.cpp fp_node.cpp buffer.cpp fsout.cpp \
    wtime.cpp fpgrowth.cpp \
    $HOOKS_DIR/hooks.o $BENCH_DIR/ptlcall_hooks.o \
    -o $OUTPUT_DIR/freqmine 2>&1 || echo "Freqmine compilation failed"

echo ""
echo "=== Results ==="
ls -la $OUTPUT_DIR/

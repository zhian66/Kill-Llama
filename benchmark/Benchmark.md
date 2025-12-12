# Benchmark Reference

## Benchmark Suites

| Suite | Source | Notes |
|-------|--------|-------|
| SPEC CPU 2017 | [spec.org](https://www.spec.org/cpu2017/) | License required |
| STREAM | [GitHub](https://github.com/jeffhammond/STREAM) | Memory bandwidth |
| GAP | [GitHub](https://github.com/sbeamer/gapbs) | Graph processing (Kronecker 2^20 vertices) |

## Multi-core Workload Mixes

| Workload | Applications |
|----------|--------------|
| mix1 | imagick, sssp, stream_add, mcf |
| mix2 | leela, deepsjeng, omnetpp, stream_copy |
| mix3 | sssp, bfs, stream_scale, lbm |
| mix4 | bfs, stream_add, mcf, lbm |
| mix5 | bfs, mcf, stream_triad, lbm |
| mix6 | sssp, stream_scale, stream_triad, stream_copy |
| mix7 | mcf, stream_triad, lbm, stream_copy |

> MPKI increases from mix1 to mix7. Each workload simulates 1 billion instructions in ROI.

## Directory Structure

```
traces/
├── test/    # Test traces for DRAMSim2 validation
└── raw/     # SPEC CPU 2017 compressed traces (.gz)
```

## Trace Format

DRAMSim2 supports two formats: **mase** and **k6** (recommended).

### k6 Format

```
<address> <command> <cycle>
```

Example:

```
0x10000 P_MEM_RD 10
0x10040 P_MEM_RD 20
0x10080 P_MEM_WR 30
```

Commands: `P_MEM_RD` (read), `P_MEM_WR` (write)

## Converting Traces

Use `traceParse.py` to convert compressed traces to `.trc` format:

```bash
cd DRAMSim2/traces
./traceParse.py <trace_name>.trc.gz
```

Output: `<trace_name>.trc` ready for DRAMSim2.

> Note: Trace filename must start with `k6` or `mase` prefix for parser detection.

## Trace Generation

Common tools for generating memory traces:

| Tool | Description |
|------|-------------|
| [Pin](https://www.intel.com/content/www/us/en/developer/articles/tool/pin-a-dynamic-binary-instrumentation-tool.html) | Intel binary instrumentation (widely used for SPEC) |
| [DynamoRIO](https://dynamorio.org/) | Open-source alternative |
| [gem5](https://www.gem5.org/) | Full-system simulator with trace output |

> TBD: Specific trace generation workflow to be documented.

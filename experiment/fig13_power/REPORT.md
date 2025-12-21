# Power Breakdown Analysis Report (Figure 12)

## Overview

This report analyzes the power consumption breakdown across three memory architectures:
- **DRAM**: Baseline DDR4 DRAM
- **Conv-Pin**: Conventional STT-MRAM (sensing at ACT time)
- **SMART**: STT-MRAM with Deferred Sensing (sensing at READ time)

---

## How to Read the Chart

### Stacked Bar Components (Left Y-axis: Power [W])

| Component | Pattern | Description |
|-----------|---------|-------------|
| **Background** | Dotted | Standby power when memory is idle or in power-down mode |
| **Activation** | Solid Black | Power consumed during ACTIVATE command (row opening) |
| **Read/Write** | Diagonal Stripe | Power consumed during READ/WRITE data burst |
| **Refresh** | Solid Gray | Power for periodic refresh (DRAM only) |

### Row Hit Rate Line (Right Y-axis: %)

The line with 'x' markers shows the **Row Buffer Hit Rate** - the percentage of memory accesses that find the requested row already open in the row buffer.

---

## Simulation Results

| Benchmark | Config | Background | Activation | Read/Write | Refresh | Total | Hit Rate |
|-----------|--------|------------|------------|------------|---------|-------|----------|
| nab | DRAM | 0.412W | 0.073W | 0.056W | 0.006W | 0.547W | 50.0% |
| nab | Conv-Pin | 0.365W | 0.066W | 0.081W | 0.000W | 0.512W | 50.0% |
| nab | SMART | 0.355W | 0.007W | 0.164W | 0.000W | 0.526W | 50.0% |
| mix1 | DRAM | 0.419W | 0.056W | 0.177W | 0.006W | 0.658W | 70.1% |
| mix1 | Conv-Pin | 0.365W | 0.055W | 0.186W | 0.000W | 0.606W | 66.8% |
| mix1 | SMART | 0.355W | 0.005W | 0.291W | 0.000W | 0.651W | 70.0% |
| pr | DRAM | 0.425W | 0.042W | 0.379W | 0.006W | 0.852W | 92.2% |
| pr | Conv-Pin | 0.365W | 0.050W | 0.358W | 0.000W | 0.773W | 85.6% |
| pr | SMART | 0.355W | 0.002W | 0.481W | 0.000W | 0.838W | 92.6% |
| lbm | DRAM | 0.436W | 0.014W | 0.318W | 0.006W | 0.774W | 96.8% |
| lbm | Conv-Pin | 0.365W | 0.027W | 0.265W | 0.000W | 0.657W | 88.9% |
| lbm | SMART | 0.355W | 0.000W | 0.348W | 0.000W | 0.703W | 96.9% |

---

## Key Observations

### 1. Activation Power: SMART is Extremely Low

| Config | ACT Power Range | Reason |
|--------|-----------------|--------|
| DRAM | 0.014 - 0.073W | Sensing happens at ACT time |
| Conv-Pin | 0.027 - 0.066W | Sensing happens at ACT time |
| **SMART** | **0.000 - 0.007W** | **No sensing at ACT (deferred to READ)** |

**Key Insight**: SMART's ACT power is nearly zero because the energy-intensive sensing operation is moved from ACTIVATE to READ command. This is the core innovation of the SMART architecture.

---

### 2. Read/Write Power: SMART is Highest

| Config | RD/WR Power Range | Reason |
|--------|-------------------|--------|
| DRAM | 0.056 - 0.379W | Data burst only |
| Conv-Pin | 0.081 - 0.358W | Data burst + higher write current |
| **SMART** | **0.164 - 0.481W** | **Data burst + sensing at READ** |

**Key Insight**: SMART's RD/WR power is highest because sensing energy is transferred here from ACT. This is expected behavior - the energy is not eliminated, just relocated.

**IDD4R Comparison** (Read Current):
- DRAM: 146 mA
- Conv-Pin: 141 mA
- SMART: 150 mA (higher due to sensing at READ)

---

### 3. Background Power: STT-MRAM is Lower

| Config | Background Power | IDD3N (Active Standby) |
|--------|------------------|------------------------|
| DRAM | 0.412 - 0.436W | 46 mA |
| Conv-Pin | 0.365W (fixed) | 38 mA |
| **SMART** | **0.355W (fixed)** | **37 mA** |

**Key Insight**: STT-MRAM has lower leakage current than DRAM capacitors, resulting in lower background power.

---

### 4. Refresh Power: STT-MRAM Eliminates It

| Config | Refresh Power | Reason |
|--------|---------------|--------|
| DRAM | ~0.006W | Capacitors need periodic refresh |
| Conv-Pin | 0.000W | Non-volatile, no refresh needed |
| SMART | 0.000W | Non-volatile, no refresh needed |

**Key Insight**: STT-MRAM is non-volatile, completely eliminating refresh overhead.

---

### 5. Row Hit Rate: Page Size Matters

| Config | Page Size | Hit Rate Trend |
|--------|-----------|----------------|
| DRAM | 1KB | High (50-97%) |
| Conv-Pin | 64B | **Lower** (50-89%) |
| SMART | 1KB | High (50-97%) |

**Key Insight**: Conv-Pin has a smaller page size (64B vs 1KB) due to limited sense amplifiers, resulting in lower hit rates. SMART maintains the same page size as DRAM.

---

## Energy Trade-offs Explained

### SMART's Deferred Sensing Strategy

```
Traditional (DRAM/Conv-Pin):
  ACT ──────────────────> READ ──────────────────> Data
       [Sensing here]           [Burst only]
       High ACT power           Low RD power

SMART:
  ACT ──────────────────> READ ──────────────────> Data
       [No sensing]             [Sensing + Burst]
       ~0 ACT power             High RD power
```

### Why This Matters

1. **Row Buffer Hits Save Energy**:
   - On a hit, only READ is issued (no ACT needed)
   - SMART: Low ACT energy saved per hit
   - But SMART pays sensing cost at every READ

2. **Row Buffer Misses**:
   - Both ACT and READ are issued
   - SMART: Still low ACT, but higher READ
   - Net effect depends on workload

3. **Overall Benefit**:
   - Higher hit rate (same page size as DRAM) → fewer ACTs
   - Lower tRRD/tFAW constraints → better parallelism
   - No refresh → continuous operation

---

## Workload Characteristics

| Benchmark | Type | Memory Intensity | Hit Rate |
|-----------|------|------------------|----------|
| **nab** | SPEC CPU | Low | ~50% |
| **mix1** | Mixed | Medium | ~67-70% |
| **pr** | Graph (PageRank) | High | ~86-93% |
| **lbm** | SPEC CPU (Fluid) | High | ~89-97% |

**Trend**: As memory intensity increases (nab → lbm), the RD/WR component dominates total power for all configurations.

---

## Comparison with Paper's Claims

| Paper Claim | Simulation Result | Match |
|-------------|-------------------|-------|
| SMART ACT power is extremely low | 0.000-0.007W vs 0.014-0.073W (DRAM) | ✅ |
| SMART RD/WR power is highest | 0.164-0.481W vs 0.056-0.379W (DRAM) | ✅ |
| STT-MRAM has no refresh | 0.000W for Conv-Pin and SMART | ✅ |
| Conv-Pin has lower hit rate | 50-89% vs 50-97% (DRAM/SMART) | ✅ |
| Background power lower in STT-MRAM | 0.355-0.365W vs 0.412-0.436W | ✅ |

---

## Summary

The simulation results **fully match the paper's expected behavior**:

1. **SMART successfully moves sensing energy from ACT to READ**
2. **STT-MRAM eliminates refresh power**
3. **SMART maintains DRAM-level hit rates** (unlike Conv-Pin)
4. **Background power is lower in STT-MRAM** due to lower leakage

The power breakdown visualization clearly shows these trade-offs, with SMART's nearly-zero black bars (ACT) compensated by larger striped sections (RD/WR).

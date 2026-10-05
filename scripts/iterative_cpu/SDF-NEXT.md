# SDF rejection and search improvements, September 24

The previous accelerator still spent most Astra physics time searching SDF
collisions. Conservative bounds now reject primitive/SDF pairs separated from
the interpolated nonpositive field, including its negative exterior extension.
The SIMD kernel also reuses finite-difference leaf lookups inside identical
table cells. Both changes preserve the original arithmetic for retained
queries, contact order, solver parameters, and controller behavior.

Measured against the previously deployed native kernel, on one pinned CPU:

| Captured physics state | Speedup |
|---|---:|
| Astra 1 / Astra 6 | 3.20–3.21× across three repeats |
| Astra 2 / Gemini 3.8 Flash sampling champion | 2.27–2.29× across three repeats |
| Astra 9 / Gemini 9 | 2.68× |
| Three Fable/GPT/Grok/Opus cases | 1.00×, within timing noise |

These are 1,000-substep captured-state comparisons, alternating old/new execution
order. Every integration state, acceleration, constraint force, sensor value,
and ordered contact field matched bit for bit. Diagnostic builds additionally
compared SIMD queries to scalar arithmetic and ran the stock collider on every
rejected pair. Independent checks covered **196,800 field points**, **12,480
randomized primitive/SDF poses**, and **8,310 rejected pairs** verified to return
no contacts in the stock collider.

With the actual controllers, the first three simulated seconds of the longest
pair (Astra 2 red, seed 7102) took **44.95 → 34.40 seconds**, a **1.31×** measured
end-to-end prefix improvement over the prior optimized version. All 900 hashed
events matched. These timings include parity hashing and setup and are one
sequential pair on a shared host, not a prediction of the full match's runtime.

One complete Fable 5.1 / Opus match was rerun: all **2,110 events**, including
the entire final record, matched the saved original reference. No additional
full-length reference run was needed.

Rejected experiments: 8-lane SIMD reached roughly 0.78–0.80× the existing
16-lane throughput, 4 lanes 0.58–0.60×, and moving the whole divergent search
inside SIMD 0.74–0.77×. Exact-cell query reuse alone gave roughly 5–8% in the
initial checks. The hot collision code already executes as compiled C/ISPC;
Cython handles observation/interval overhead. A Numba/JIT wrapper would retain
the expensive native work, so no additional runtime/compiler dependency was
introduced.

Implementation, enclosure reasoning, supported scales, and fallbacks are in
[COLLISION-BOUNDS.md](../../mjarena/envs/match_accel/COLLISION-BOUNDS.md).
Build with `--verify-simd --verify-rejection` for diagnostics; use a regular
build for production. Never overwrite a library loaded by an existing worker.

Raw timings, binary hashes, and validation summaries:
[sdf-next-20260924.json](evidence/sdf-next-20260924.json).

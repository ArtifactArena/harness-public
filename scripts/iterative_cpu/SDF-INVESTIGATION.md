# Follow-up SDF investigation, September 24

This records the first seven experiments. A subsequent implementation of
conservative field bounds and exact SIMD query reuse produced substantial gains;
see [SDF-NEXT.md](SDF-NEXT.md).

The remaining accelerated tail was mostly Astra. In a captured Astra 01/06
state, 200 physics substeps took 0.479 seconds. Sphere/SDF collision callbacks
accounted for 0.320 seconds and cylinder/SDF for 0.129 seconds: approximately
94% combined. This sample measures physics only, not total match runtime.

Seven implementation variants were tested against the deployed single-core
SIMD kernel. Each test alternated old/new execution order on one pinned CPU and
compared 500 consecutive substeps exactly: complete integration state,
accelerations, constraint forces, sensors and ordered contact fields. All
comparisons passed. No GPU, extra physics threads, reduced precision, altered
iterations or toleranced equality were used.

| Experimental change | Physics speedup over deployed kernel |
|---|---:|
| Straight-line fast path for known octree leaves | 1.009× |
| Binary-search correction of leaf-index guesses | 0.763× |
| Unroll interpolation loops | 1.029× |
| Scalar execution when one SIMD search point remains | 1.021× |
| Scalar execution when at most two points remain | 1.000× |
| Scalar execution when at most four points remain | 1.058× initially |
| Reuse sphere norm between value and gradient | 1.021× |

The four-point scalar-tail candidate repeated at **1.026×, 1.013× and 1.008×**.
The initial 6% result was not stable. The other small gains are insufficient
evidence of a reliable improvement across tournament bots and CPU contention.
The binary-search variant is a clear regression on this captured state.

**None of these SDF variants was deployed.** Production retains the previously
validated SIMD kernel. The separate nearest-32 observation optimization is
deployed and does provide the measured 1.37× end-to-end prefix improvement.
SDF physics remains a target for further work; these measurements do not prove
that the existing kernel is optimal.

Raw timings, binary identities and parity results are in
[`evidence/sdf-experiments.json`](evidence/sdf-experiments.json). Experimental
builders and captured inputs are retained outside production on the GPU cluster under
`<scratch>/artifactarena/match-parity-opt-20260924/further` and in
the corresponding local run archive. The test binaries and generated sources
are in the allocated-node cache
`<local>/artifactarena/match-parity-opt-20260924/further` on gpu-node-5.
This investigation used short captured-state checks rather than additional
full-length tournament matches.

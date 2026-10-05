# Conservative SDF rejection and query reuse

MuJoCo's ordinary broad phase admits expensive primitive/SDF pairs that cannot
produce contacts. A geometric mesh bound is insufficient to reject them:
MuJoCo's interpolated field can be negative outside the mesh/root bounding box.
The accelerator now encloses that **interpolated nonpositive field**, then
rejects only primitives separated from the enclosure. Surviving pairs execute
the existing collider in the original order with unchanged search parameters.

## Field enclosure

At context creation, build a six-double enclosure for each octree node, using
the original tree as a bounding-volume hierarchy. The extra memory is
`48 * model.noct` bytes plus one validity byte per mesh. Destroying the context
frees its enclosure; model geometry must remain fixed as before.

For a leaf, expand the coordinate interval by `2e-8`, covering the reference
`findOct` membership tolerance of `1e-8` and rounded endpoint arithmetic. Let
`eta[k]` be that expansion divided by the leaf width and
`S = product(1 + 2*eta[k])`. Trilinear weights sum to one, and their absolute sum
is bounded by S. Consequently the interpolated value is bounded below by:

```
min(coeff) - (S - 1) / 2 * (max(coeff) - min(coeff))
```

The implementation evaluates this bound in long double and subtracts
`1e-10 * (1 + max(abs(coeff))) * S`, an outward allowance substantially larger
than the double interpolation's rounding error at the supported scales.
Strictly positive leaves are empty. Other leaves retain an enlarged box.

Exterior queries add distance from the root box to the interpolated value of
the projected point. MuJoCo projects those points `1e-6` inside the root.
Therefore leaves touching its `1.1e-6` boundary strip extend outward by their
negative lower bound plus `2e-6`. This encloses possible negative exterior
values rather than assuming that the field vanishes at the mesh boundary.
Parent boxes enclose all their retained children. Stored endpoints are rounded
outward with `nextafter`.

Unsupported meshes fall back to the original collider: nonfinite data, leaf
endpoints outside ±1000, widths below `2e-6`, coefficients outside ±1e6, or
allocation failure. Models over two million octree nodes also skip this cache.
Plugins and the existing unsupported physics configurations retain their
existing fallback.

## Primitive rejection

Spheres, capsules, cylinders, and boxes have conservative enclosing spheres;
the latter three also use an enclosing box. The test uses the same pose mapping
as the reference SDF evaluation. It explicitly inverts the rounded matrix in
long double instead of treating its transpose as an exact inverse. A row-sum
bound on the inverse Gram matrix bounds the sphere's transformed radius.
Outward allowances cover primitive-distance and transform rounding; unsupported
sizes, positions, or transforms fall back. Tests are strict, preserving touching
and uncertain pairs. This changes neither contact order nor solver input for
retained pairs.

## SIMD query reuse

The exterior SDF gradient evaluates three nearby finite-difference points.
The AVX-512 kernel now reuses the base point's leaf only when each projected
query lies in the **same table cell, delimited by the exact split cuts**.
Otherwise it performs the original lookup. Interpolation uses the original
arithmetic and reduction order; derivatives are not replaced with approximations.

The current 16-lane SIMD batching remains in use. Experiments with 4 and 8 lanes,
and with the whole divergent search inside SIMD, were slower. Cython already
handles observation/interval overhead. Numba or a JIT wrapper around these
native collision calls would not remove their work, so no JIT dependency was
added.

## Verification

Build with both `--verify-simd` and `--verify-rejection` for diagnostics.
The first compares SIMD values/gradients to scalar arithmetic; the second runs
the stock collider for every rejected pair and fails if it returns a contact.
Use a regular build for timing; the diagnostic build deliberately repeats work.

`scripts/match_accel/check_rejection.py` additionally checks nonpositive field
points against the enclosure and randomized primitive/SDF pairs against stock
MuJoCo. It includes root faces, projection offsets, adjacent floating-point
values, and sampled leaf corners. Paired physics validation still compares
integration state, accelerations, forces, sensors, and ordered contacts after
every substep. Controller-level and complete-record parity are separate checks.

See `scripts/iterative_cpu/evidence/sdf-next-20260924.json` for measured results.

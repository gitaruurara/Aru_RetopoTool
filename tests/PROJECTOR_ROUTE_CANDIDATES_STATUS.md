# Route fitting candidates: not enabled by default

Two opt-in build flags were evaluated in separate Maya 2027 processes; the
interactive Maya and default v7 projector were left unchanged.

- PrecomputePath caches immutable polyline vectors and squared lengths inside
  the closest-segment fitter. Exact v7 parity passed, including transformed
  geometry, degenerate controls, worker thresholds, draft/refined modes. No
  meaningful speedup: 256 draft curves 13.45 -> 13.54 ms (untransformed).
- IdentityProjection skips identity matrix conversions in route projections.
  Maximum observed coordinate difference was 2.22e-16; transformed cases matched.
  256 draft curves 13.39 -> 13.23 ms; refined 32.08 -> 31.70 ms. This small
  isolated difference does not justify enabling the candidate or claiming a
  frame-rate improvement. It is not exact-bit parity.

Both flags default off. Candidate DLLs have distinct filenames; standard startup
continues to load v7. Tests reproduce the comparison. No 2024 candidate adoption,
no live editing measurement, and no evidence of reaching the 60 FPS objective.
Projection work dominates these small arithmetic savings; future changes should
measure query volume and whole-interaction cost rather than rely on this cache.

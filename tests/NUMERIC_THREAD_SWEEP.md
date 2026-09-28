# Numeric pipeline thread-count sweep — 2026-09-18

Current retopo.cpp + mesh_buffer.cpp, Maya 2027, /O2, NumericPipeline,
ReuseScratch, IncrementalStencil, InputCache; leaf size 8. Separate candidate
MLLs; default numeric MLL and running interactive Maya were not changed.
CPU: Intel Core Ultra 9 285K, 24 cores / 24 logical processors.

Existing native_relax_replay.py alternates recorded original/relaxed controls
12 times per process. Each reported median excludes the first two samples.
46,873 vertices / 46,528 faces. This measures native coordinate evaluation
only, excluding brush work, guide writes, picking and GPU redraw.

| Requested worker cap | Forward median ms | Reverse median ms |
| --- | ---: | ---: |
| 1 | 80.625 | 81.417 |
| 4 | 22.686 | 22.756 |
| 8 | 12.911 | 13.689 |
| 16 | 11.044 | 11.002 |
| 24 | 10.900 | 11.385 |
| 32 | 10.978 | 11.052 |

32 is clamped to hardware_concurrency (24 here), so it is another measurement
of the 24-worker configuration, not evidence for running 32 workers.
Execution order: 1,4,8,16,16,8,4,1,24,32,32,24. All twelve reports have identical
SHA-256 hashes for both final poses. Raw timings and hashes are retained in
numeric_thread_sweep.jsonl; individual replay reports and build logs remain
alongside it. This equality check covers these two recorded poses only.

Decision: retain the default cap of 16. Raising to 24 does not yield a clear
win; reducing to 8 or below significantly worsens this workload. No claim of
interactive improvement follows from this experiment. 60 FPS remains unmet.
Next priority: reduce computation/data/render work per edit, not increase
worker count. The full interactive bottleneck cannot be inferred from this
coordinate-only replay.

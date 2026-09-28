# Native normal-only projection

Added aru_maya_normals to avoid world hit conversion and polygon barycentric
binding calculation when a caller only needs the normal. Uses the same Maya
intersector, transformAsNormal, normalization and serial query order as
aru_maya_surface_hits. No reduced query count or approximation.

Both Maya 2024 and 2027 native_normals tests pass exact old v7 vs new output for
sphere/cube, negative/nonuniform scale and rotation, 0/1/324/1090/4096 queries,
owned buffers and nonfinite input rejection. Full smoke suites passed in both.
Older loaded DLLs without the export retain the previous surface-buffer path.

2027 near-surface sphere: 324 normals 0.125 -> 0.104 ms, 1090 normals
0.383 -> 0.311 ms, 4096 normals 1.360 -> 1.136 ms. Random far queries on a dense
sphere are dominated by closest-point traversal and show little improvement.
These are isolated normal-query timings; whole editing FPS has not been measured
for this change and 60 FPS remains unproven.

Default Python loader and build script now use aru_retopo_maya_projector_normals.dll;
both versions built. The open interactive session was not reloaded. The rejected
path-cache/identity experiments remain off in these builds.

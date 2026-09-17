# Compact native junction solver — adopted locally

Unlike the old Python analytic-inverse trial, this kernel constructs base samples and the regularized two-column inverse inside the joined native workers. Python transfers 12 controls + 6 direction values + initial lengths/chord, instead of 45 base coordinates and 94 inverse values per curve. The 0.1 diagonal prior bounds the small Gram solve for the caller's normalized directions.

2024/2027 sphere/cube, transformed/reflected/nonuniform, 1/15/16/500-curve tests: maximum eight-fit coordinate difference 3.89e-16. Isolated timing is not uniformly better (transformed-sphere 2024 43.17 -> 45.33 ms); do not generalize a universal speedup.

2027 continuous 200-EP eight-dab stroke: guide error 3.33e-15, final mesh error 0, metadata within 1e-9, Undo restored. Candidate is not bitwise identical to SVD and guide hashes differ.

500-patch GUI (same 1600x1000 viewport, brush 841/688, synchronous redraw):
gui_junction_compact: [(4, 39.03800000261981), (8, 37.165199988521636), (8, 37.96859999420121), (4, 39.371599996229634)]
gui_junction_compact_reverse: [(8, 37.309000006644055), (4, 38.02890000224579), (4, 39.64570000243839), (8, 36.93069999280851)]
Label 4=standard endpoints DLL; 8=compact junction candidate (both four workers). Mean trial medians: {4: 39.021050000883406, 8: 37.343374995543854}.

Historical candidate checks above preceded integration. No whole-scene simplification or rendering removal; no 60 FPS claim.

## Standard integration

Default DLL is now aru_retopo_maya_projector_compact.dll (2024/2027). New ABI aru_maya_junction_compact_v1 rejects oversized count before pointer traversal, finite/shape errors, and deleted owner. Directions outside normalized/zero range request SVD fallback; older DLL/missing accelerator also uses the existing SVD path.

Both release suites passed zero/parallel/opposite/random tangent configurations, scalar and worker-threshold counts, reflected nonuniform transforms, retained-output ownership, nonfinite buffers, size errors, zero count, unsupported direction fallback, deleted reference owner and oversized count. Maximum repeated-fit coordinate difference was 5.56e-16 in both versions. Actual old-DLL relaxation integration passed projection/topology/Undo/Shift handling. Both full smoke suites passed; logged drag exceptions are intentionally injected error-recovery cases.

GUI integrated source methods and actual compact DLL in diagnostic PID 38780: relax medians 37.554/38.749/38.436 ms, point 26.744 ms. Native mesh in that GUI remains certificates (same solver as certified); not a fresh entire-release GUI launch. Guide hashes differ from SVD as expected. A separate identical-input capture measured complete mesh error 6.66e-16, guide error 2.66e-15, exact float32 mesh positions, exact spline topology, Undo restored. Reports: gui_compact_integrated.json, gui_compact_delta.json.

Local default adopted; latest published GitHub remains f1ace39 until another push. Physical mouse latency and 60 FPS are not established.

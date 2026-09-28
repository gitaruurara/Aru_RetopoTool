# Fused native projected junction iterations

The four projected length iterations run in one native call, retaining the
Python-prepared SVD inverse, Bernstein coefficients, directions and bounds.
Each curve writes disjoint output; only the immutable MMeshIntersector is used
by workers, joined before return. No Maya scene access in worker threads.

Default projector/build name is aru_retopo_maya_projector_junction.dll, built
for 2024 and 2027. Older DLLs lacking the export retain Python iterations.
The unrelated analytic-inverse candidate remains disabled.

2027 isolated 500-curve sphere: 5.541 -> 3.775 ms; transformed sphere
28.248 -> 19.488 ms; transformed cube 4.877 -> 3.331 ms.
1/15/16/500 cases, negative/nonuniform scale, rotation and 8 repeated fits
passed with maximum handle deviation 1.12e-16 in both Maya versions.
2027 also checked malformed buffer sizes, nonfinite input, retained output
ownership and old-DLL fallback. Both Maya smoke suites passed on default DLL.

500-patch fixed 200-EP continuous stroke, warmups, native outMesh (no picking
or viewport): 2027 27.222 -> 26.309 ms; 2024 31.989 -> 28.329 ms.
Reports retain guide/mesh deviations and restored Undo state. 2024 loaded a
2027 recovery copy with unrelated USD/version warnings; use smoke and the
synthetic native tests for clean 2024 compatibility evidence.

This is not a GUI FPS measurement. 60 FPS remains unmet; standard display is
unchanged and the artist GUI was not reloaded during these standalone tests.


Superseded default binary: route/binding fusion now ships as bound.dll, which
also includes this junction export. See ROUTES_BOUND_STATUS.md.

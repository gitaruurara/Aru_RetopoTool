# Experimental GPU projection and mesh relaxation

This is a standalone DirectCompute prototype, not enabled by the Maya editor.
CUDA toolkit is not required. Hardware used: NVIDIA RTX 5060, Windows D3D11.

Build: `powershell -File cpp/build_gpu_projector.ps1`.
Run `python tests/gpu_projector_probe.py`, `python tests/gpu_relax_probe.py`,
and `python tests/gpu_relax_edges.py` sequentially. JSON/log files are evidence.

The DLL includes a 16-thread sleeping-team CPU comparator from retopo.cpp.
The relax benchmark interpolates recorded curve-edit control positions and
computes identical stencils before either timed solver call. Timing excludes
stencil evaluation, curve editing, Maya dependency graph work, and rendering.
GPU timing includes input upload and final readback. Topology is cached.

Latest warm median for 46,873 vertices, five iterations: GPU about 8.5 ms,
CPU about 10.1 ms. First GPU evaluation was about 18.7 ms. Without projection
result caching GPU took about 17 ms. These are not whole-interaction FPS.
Cache buffers hold source query/seed and answer separately for each iteration;
reuse requires exactly equal query coordinates, seed, and projection guard.
Topology replacement and vertex-count/iteration/guard changes invalidate caches.

Coordinate errors in the recorded replay are below 1e-15. Triangle seeds can
still differ at ties; do not claim bitwise equivalence. A separate 21-case test
covers sharp cube edges, disconnected components, degenerate triangles, settings
changes, and growing/shrinking buffers (maximum coordinate error below 2e-15).
This does not establish parity for arbitrary meshes or interactive stability.

Before production: integrate behind an explicit experimental backend switch,
validate device/resource failure fallback, ownership and evaluation threading,
reference mesh changes, Maya 2024/2027 interaction/Undo/save, and full 500-patch
point/relax/camera frame times. Avoid loading this DLL into the user scene until
lifecycle and fallback are wired. Current default editor backend is unchanged.

## Maya integration and interactive comparison (2026-09-18)

The optional native GPU candidate is now implemented in gpu_backend.h, enabled
by build_mesh_buffer.ps1 -GpuCompute. It requires explicit ARU_RETOPO_GPU_DLL
and ARU_RETOPO_GPU_SHADER environment paths; the default backend is unchanged.
Each serial node owns its device; reference changes recreate it, topology and
weights changes rebuild its buffers. Failed GPU calls preserve CPU input and
fall back to CPU. Both 2024/2027 native graph suites passed Undo/Redo, settings,
subdivision and scene reopen checks while confirming actual GPU calls. GPU/CPU
coordinate comparisons allow 1e-10; retained data checks remain exact.
An intentionally missing shader verified CPU fallback with zero coordinate error.

Live 500-patch brush benchmark with identical restored scene, direct GPU display
and GPU controls: CPU 45.98 ms vs GPU 49.90 ms median numeric brush call including
synchronous refresh. Both restored via Undo with exact ordinary/numeric final
net data. GPU stats: 21 successful evaluations, zero failures, one surface.
See gui_gpu_compute_cpu_baseline.json and gui_gpu_compute_candidate.json.
The candidate is NOT a demonstrated end-to-end speedup and is not promoted.
After the experiments, the live scene was reopened with the sleeping-team CPU
plugin from maya-before-gpu-20260918-034803.ma; GPU candidate unloaded.

Filtered base pass did not improve redraw materially (14.13 ms). Temporarily
hiding guides reduced redraw to 6.37 ms (not a proposed user-facing solution).
Guide callback profiling (gui_guide_timing.json) measured updateDG ~1.71 ms,
updateRenderItems ~0.46 ms, populateGeometry ~1.32 ms; the remaining guide cost
includes drawing/driver work, not just Python callbacks. Nested callback timings
must not be summed twice. The 60 FPS editing target remains unmet.

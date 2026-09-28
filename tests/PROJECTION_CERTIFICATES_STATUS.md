# Projection separation certificates: adopted

The solver is now integrated in cpp/retopo.cpp. cpp/build_interactive.ps1 builds
aru_retopo_mesh_buffer_certified.mll for Maya 2024/2027 with 16 workers, numeric
pipeline, scratch reuse, incremental stencil and input cache. Both binaries
are present. native_backend and viewport_session use this binary by default.
The old prototype generator intentionally stops after integration.

## Adoption evidence

- Production binaries: 640 warm + 64 cold C ABI comparisons per version,
  exact coordinates and seeds versus retained numeric_t16 baseline.
- Production node-state replay: all 24 hashes match baseline on each version,
  covering reference deformation, winding reversal/restoration, guide weights,
  adjacency order, solver settings, projection disable/re-enable and matrix.
- General Maya smoke suites pass on 2024/2027 (smoke_certified_*.log).
- GUI candidate/source used for integration: two isolated Maya 2027 processes,
  same input hash, camera, EP 645 and 1600x1000 viewport. Eight real brush calls
  per trial; first dab affects 443 EP; three trials. Final guide and entire
  double-coordinate mesh hashes match across both backends in every trial.
  Ordinary/numeric path parity and Undo also pass; point edit final hashes match.
  Baseline relax 57.978 / 59.786 / 58.205 ms; candidate 42.888 / 43.450 /
  43.927 ms. Point medians 29.499 / 27.109 ms. See gui_certificates_repeated_*.json.
  These are scripted handler + synchronous redraw timings, not mouse latency.
- Camera-only test: 48 refreshes, varied projected EP positions, unchanged
  46,873-vertex / 46,528-face output, restored camera; no error. This checks
  refresh stability and projections, not pixel-level absence of artifacts.

Earlier invalid GUI runs were rejected: fixed screen coordinates missed all
EPs after window resizing; the test now fails on empty brush results and accepts
an explicit screen anchor. Further mismatched camera/input/viewport trials were
not used for the adoption comparison. The final reports match all these inputs.
The saved fixture had guide xray OFF, invoking legacy Python addUIDrawables
(~95 ms redraw in one run). Both comparison fixtures explicitly enable xray;
this normal-display fallback remains an independent optimization opportunity.

One standalone 2027 cleanup entered a Windows exit-notification anomaly
(exit code 0 but unsignaled process handle). Its waiting batch was terminated;
it is not counted as clean completion. Subsequent instrumented baseline and
candidate processes both logged cleanup complete and exited 0. No crash in
editing was observed in these runs; the anomaly's root cause is not established.

60 FPS remains unmet. GPU GUI measurements above used the candidate binary
whose source was integrated; production binaries were independently rebuilt
and verified by numerical/node tests. No physical-input or 2024 GUI FPS claim.
Restart Maya for the new binary; never unload a live native node type in place.

## Historical prototype notes (superseded by adoption evidence above)

# Projection separation certificate candidate — 2026-09-18

Status: promising prototype, NOT the standard backend yet. Standard numeric
MLL and source retopo.cpp are unchanged; no interactive Maya was modified.

Generator: tests/create_projection_certificates.py creates a separate
cpp/retopo_certificates_candidate.cpp and build_certificates_candidate.ps1
from the current source/build. Build with NumericPipeline, ReuseScratch,
IncrementalStencil, InputCache, NativeThreads 16, MayaVersion 2027 and
BinaryName aru_retopo_mesh_buffer_certificates.mll. Keep this candidate
isolated until integrated viewport/stability coverage is completed.

For each cached projection, nearest search collects a conservative distance
bound to all other triangles. Pruned boxes contribute lower bounds; tested
losing triangles contribute distances. A guard-excluded triangle sets the
bound to zero, disabling certification. Moving the query reduces the stored
bound by displacement and a floating-point safety margin. Reuse is allowed
only when the previous winner is admissible under the new guard seed and its
new exact distance is strictly below that bound. Otherwise full search runs.
Exact-query/exact-seed cache path remains the existing path. The bound can
become overly conservative over repeated reuse, which triggers full search.
This design is not by itself a proof against all floating-point edge cases.

## Evidence

Maya 2027, Core Ultra 9 285K, 16 workers:
- Recorded 46,873-vertex / 46,528-face coordinate replay, ABBA: baseline
  10.175 / 10.804 ms; candidate 5.185 / 5.039 ms. Both pose SHA-256 outputs
  match for all four runs (projection_certificates_comparison.jsonl).
- Synthetic C ABI comparison: 480 calls of 512 points each, exact coordinate
  and output-seed equality. Curved grid, folded grid, disconnected close
  layers, degenerate triangles, 1e-5 scale, 1e6 translation. Repeated small
  and large motion; seed changes; changing guard, iteration count, strength
  and anchors. Report: projection_certificates_cases.json.
- Actual RelaxPreview, eight consecutive 200-EP dabs, evaluated native
  outMesh, no picking or viewport. Three baseline medians 27.542, 27.256,
  28.482 ms; candidate 20.518, 20.166, 22.302 ms. All three final guide JSON
  and mesh-coordinate hashes match exactly, Undo restored original guide
  data and cleared edit preview. Reports: projection_certificates_stroke_*.json.
- No prototype monkeypatch is applied to curve editing; projector remains
  the default tangents DLL. Only loaded mesh-buffer binary differs.

## Outstanding

No GUI frame-time claim. No Maya 2024 candidate build/test yet. Need separate
GUI sessions (node type cannot be registered by two MLLs simultaneously),
actual loaded-plugin ownership checks, drawing/camera and prolonged edits,
reference/topology rebuild and Undo/Redo coverage, and broader adversarial
certificate tests before adopting. 60 FPS remains unmet: even coordinate
plus edit alone currently exceeds 16.7 ms in this stroke workload.

## Follow-up validation (2026-09-18)

Built matching 16-worker candidate and baseline for Maya 2024. Extended tests
passed on both 2024 and 2027: 640 warm comparisons + 64 fresh-surface comparisons
per Maya version. Point count alternates 512/127 to invalidate cache size;
duplicate triangles, reversed winding, invalid seeds and option changes added.
Coordinates and output seeds remain exactly equal. Versioned cases reports
identify the Maya version.

Real stroke now asserts exactly one plugin owns aruRetopoMeshBuffer and checks
its filename; each report records the full actual plugin path. Maya 2024 completed
both processes successfully, all three guide/mesh hashes matching and Undo
restored. Candidate medians 23.058 / 20.772 / 22.121 ms; baseline 26.857 / 29.355 /
32.574 ms (no viewport, substantial run-to-run variability).

Maya 2027 candidate completed the edit/Undo assertions, producing medians
21.019 / 19.317 / 22.901 ms, but the surrounding run has not returned from
cleanup. Diagnostic mayapy PID 45572 appears in WMI with one thread while
GetProcessById/taskkill report no running instance; termination attempt did not
succeed. Do NOT count this as clean process completion or adopt the candidate.
Parent execution session 8639 was still pending at the last check. Next runs
have explicit scene-clear/uninitialize markers and a delayed Python stack dump.
No artist Maya was modified or terminated. GPU-inclusive testing remains pending.

from pathlib import Path
p=Path('tests/PROJECTION_CERTIFICATES_STATUS.md')
s=p.read_text(encoding='utf-8')
header='''# Projection separation certificates: adopted

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

'''
p.write_text(header+s,encoding='utf-8')
p=Path('README.md');s=p.read_text(encoding='utf-8').replace('新しいMayaでツールを起動します。2024/2027用','新しいMayaで、保存シーンを開く前にツールを起動します。2024/2027用');p.write_text(s,encoding='utf-8')

# Native projection consolidation — 2026-09-18

The interactive path requires the compact projector DLL for the running Maya version. The viewport session checks its file and required exports before scene changes. Missing files, incompatible exports and unavailable reference accelerators fail explicitly.

Removed old-DLL/Python alternatives for EP relaxation, normals, junction branch selection and junction length iterations. Route fitting and surface binding retrieval use one native operation; the position-only wrapper delegates to it.

Retained behavior-specific handling for hard surfaces, shared handles and endpoint/handle intersections. The compact solver still requests SVD for inputs outside its normalized-direction contract; this is numerical safety, not binary compatibility.

Validation:
- Maya 2024 and 2027: endpoint release cases, junction compact release cases, full Maya smoke suite passed.
- Endpoint reference comparison: 40 exact cases per version; transforms, deformation, ownership, invalid input and explicit dependency failure checks passed.
- Compact versus SVD: maximum coordinate difference 5.56e-16 or less.
- Existing diagnostic Maya 2027, 500-patch scene: scripted brush operation before/after refactor produced exactly equal guide JSON and mesh coordinates; Undo restored input. This checks the loaded helper changes, not a fresh GUI startup or physical mouse latency.
- No C++ algorithm or binary changed. No new performance claim or 60 FPS claim.

The historical experimental DLLs and benchmark scripts are not selected by the production path. This change consolidates projection and relaxation; it does not remove all compatibility code from unrelated subsystems.

## Visibility consolidation

Batch brush visibility now requires the native visibility DLL. File/ABI validation runs at session startup; invalid inputs, worker-thread calls and native execution failures are explicit errors rather than silent scalar fallbacks. The single-point visibility API remains for its actual callers.

Maya 2024 and 2027 visibility release comparisons (occlusion, perspective/orthographic views, deformation, transform, mirrored/nonuniform DAG instances) and full smoke suites passed. Missing/incompatible DLL rejection is covered. Existing diagnostic GUI brush comparison again produced exact guide JSON and mesh coordinates before/after, with Undo restoration. No new frame-time improvement is claimed.

## Screen projection and selection consolidation

The screen DLL now requires both point projection and fused curve-selection exports. Both signatures are set once when loading the library. Fused selection loads the standard DLL on first use even if point projection has not run yet. Missing/incompatible DLLs, invalid positions, non-main-thread calls and native execution failures are explicit errors. None is reserved for viewport-free batch execution. Session startup validates the screen DLL before changing scene state.

Maya 2024/2027 full smoke suites passed, including required-export rejection tests and batch selection parity. In diagnostic Maya 2027, 360 GUI selection comparisons across two perspective views and one orthographic view matched the NumPy reference exactly (including exclusions, tolerance changes and visibility). C++ selection medians were 2.28–2.46 ms versus 5.33–5.57 ms for the reference, but fused selection was already standard: these numbers are not a new refactor speedup. No 60 FPS claim.

## Integrated session validation

Added viewport_preflight to both Maya smoke runs: missing binary files and projector/visibility/screen loader failures preserve an active session and do not call stop, loadPlugin, native enable, GPU enable or disable. Both full smoke suites passed on 2024 and 2027.

Diagnostic GUI 2027 session stop/restart with current Python startup code successfully loaded all three required DLLs. The process retained its already-loaded certificates mesh build (equivalent solver source), so this is not fresh-process validation of the certified binary. Scripted brush and point-context editing, geometry change and Undo restoration passed with GPU guides and direct mesh buffers.

Single-run uninstrumented brush median: 37.157 ms; point drag median: 27.694 ms. Brush output matched the ordinary path exactly. These do not establish 60 FPS or an improvement over prior results. The point release attached to a spline (1589 -> 1590 splines), took 1055.622 ms, including patch transfer 105.118 ms and dirty/refresh 911.112 ms (nested timings, not additive). This identifies topology-change commit/redraw as a separate remaining latency source; normal drag and topology-changing release must not be conflated.

## Topology-changing release investigation

Release-only cProfile in the diagnostic GUI recorded one Plan construction and one compile_stencil call, dominating the Python profile. There was no evidence of duplicate plan evaluation; profile wall times include profiler overhead and are not interactive timing claims.

A candidate removed exact-zero sample coefficients before repeated dictionary accumulation. Twenty-one pure coefficient comparisons (3/4/5/6/8-gons across levels 1–4 and a large grid) were exact; standalone core tests and both Maya smoke suites passed. A 31,936-face grid reduced isolated compilation median from 140.833 to 131.041 ms. However, GUI ABBA release timings were baseline 1024.222/1035.249 ms versus candidate 1026.353/1025.635 ms. Final guide hashes and actual-scene compiled coefficients were exact, and Undo restored input. There is no compelling whole-operation gain; the candidate was reverted and is not part of production.

The next relevant scope is reuse of unaffected topology/stencils after a local spline attachment, or native plan construction. This investigation does not establish a rendering limit or 60 FPS.

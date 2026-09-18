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

## Reuse Coons coefficient templates within a build

Adopted local template reuse for four-sided patch interiors. The key includes canonical CV aliasing, every side segment and direction, and interior UV coordinates. Arithmetic is performed once per matching layout, then coefficients are remapped to each patch's CV IDs. The cache exists only during compilation; no scene, node or historical topology is retained. Non-quad subdivision remains unchanged.

Validation: 21 exact coefficient comparisons passed, including polygons at levels 1–4 and a 31,936-face grid. The grid compile median changed from 138.575 to 64.602 ms. Added independent reference-evaluation tests for reversed/multi-segment sides, shared handles and renumbered CVs under motion. All 13 core tests and full Maya 2024/2027 smoke suites passed.

Diagnostic GUI ABBA release timings: baseline 1025.966/1010.310 ms, template 1011.256/1009.141 ms. A follow-up pair measured 1009.432 versus 1026.409 ms, so no reliable whole-release gain is claimed. Final guide hashes, Undo and actual-scene compiled coefficients matched. The important scope finding is that this scene has only 25 four-sided patches among 500 regions (496 after attachment); most work remains in n-gon subdivision, outside Coons reuse. The change reduces duplicate work for quad layouts but does not establish 60 FPS, nor solve the ~1 second topology commit.

## Native sparse-composition prototype (not integrated)

Built a separate Maya-independent experimental DLL for composing sparse coefficient rows in the existing accumulation/insertion order. Production DLLs and core.py were unchanged. Twenty polygon/level comparisons were exact; the diagnostic scene's compiled coefficients, final guide hash and Undo also matched.

GUI ABBA topology-release timings: baseline 952.152/1011.068 ms, candidate 960.374/967.724 ms. This overlap does not establish a whole-operation win, so the candidate is not selected by production. Release profiling had identified one plan constructor and one stencil compilation, not duplicate evaluation.

A follow-up profile of the candidate compiler on the restored actual plan recorded 2.18 million Python calls, including 1.21 million list append calls and 567k abs calls. Its three native bridge invocations consumed 0.106 s of 0.542 s profiled compilation; Python final-row sorting/filtering/CSR packing remains substantial. These are profiler timings, not latency claims. Moving only row arithmetic to C++ leaves repeated Python/native row conversions and final packing; further native work needs to retain sparse rows across subdivision stages and produce final CSR directly, rather than add this bridge as another runtime path.

## Adopted native intermediate stencil state (ABI 5)

The production compiler now retains sparse subdivision rows in C++ across levels. Python supplies guide and Coons overrides; C++ sorts, filters and packs final CSR once. This replaces the Python subdivision accumulation path rather than adding a runtime fallback. The same core_v5 DLL supports Maya 2024 and 2027; native startup validates ABI 5 before session mutation. Handles use explicit finally cleanup, failed steps do not swap partial state, outputs own copied storage, and copy capacity is validated.

Candidate checks: 20 polygon/level cases and actual-scene coefficients were exactly equal. GUI ABBA topology-release baseline 1045.830/1018.686 ms versus candidate 773.502/818.571 ms, with matching final guide hashes and Undo restoration.

Production checks: all 13 core tests and both full Maya smoke suites passed. Additional randomized ordered multi-stage/override tests, output lifetime checks, malformed input/state preservation and copy-capacity checks passed in both mayapy 2024 and 2027. Current production ABI 5 loaded in the existing diagnostic GUI: scripted brush output matched the ordinary path, point editing changed geometry and Undo restored input. Integrated release 857.839 ms; brush 37.596 ms and point drag 26.670 ms. This improves topology-changing commits, not a demonstrated 60 FPS edit loop. The GUI still uses its existing certificates mesh build; this was not a fresh whole-bundle process launch.

## Final distribution verification and accepted milestone

The user accepted the current improvement as this milestone and explicitly requested a push after the next verification; 60 FPS remains unmet and is not claimed.

Verified a fresh git archive of 0e80ad8 using independent mayapy 2024/2027 processes and isolated Maya preference directories. All Aru_RetopoTool Python modules and native libraries were checked to resolve inside the archive. The certified mesh-buffer and fast-preview plugins loaded; core ABI 5, compact projector, visibility and screen libraries loaded from the distribution. Both full Maya smoke suites and all 15 core/compiler tests passed, with process exit codes 0 and no native shutdown stack trace using the normal scene-clear/plugin-unload/Maya-uninitialize sequence. The initial ad-hoc wrapper omitted that sequence and produced shutdown traces after passing tests; its cleanup was corrected before acceptance.

The archive test supplies NumPy for Python 3.10 separately (the installer's existing dependency behavior) and a sibling copy of the external CurveNet tool solely for the coexistence test. These are not untracked Retopo source dependencies. This is standalone distribution validation, supplemented by the earlier diagnostic GUI validation; it is not a fresh GUI latency benchmark.

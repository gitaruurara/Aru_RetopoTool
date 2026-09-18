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

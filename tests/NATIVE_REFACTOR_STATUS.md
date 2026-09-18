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

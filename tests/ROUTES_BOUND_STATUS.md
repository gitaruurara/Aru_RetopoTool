# Fused route fitting and handle bindings

Adopted in the normal relax path. Default projector/build is now
aru_retopo_maya_projector_bound.dll (Maya 2024 and 2027). The new optional
aru_maya_fit_routes_bound export performs handle fitting and binding queries
in the same joined worker batch. Workers read immutable intersector/polygon
buffers and write disjoint output. Scene-owner validation precedes launch.
Normals and world hit lists unused by the binding consumer are not converted
into Python containers. Old DLLs retain the separate fitting/binding path.
Hard-surface and shared-handle behavior retain their existing fallbacks.

Native verification in 2024/2027: 0/1/15/16/500 curves; sphere and cube;
negative/nonuniform scale and rotation; draft and release fitting. All fitted
coordinates and binding metadata match the old DLL exactly. Also checked
nonfinite inputs, degenerate endpoints, returned data ownership, old-DLL
fallback and exact preservation of the full legacy surface_hits output.
Both Maya smoke suites passed after integration; 2027 completion was retained
in smoke_routes_bound_2027.log. The suite includes transforms, Undo/Redo,
cancel, release, numeric-preview equivalence, and legacy coexistence.

500-patch / 200 fixed EP standalone eight-dab comparisons restore Undo and
have exactly equal guide JSON and mesh coordinates. Timing was mixed across
three pairs (see routes_bound_stroke_2027.json); no standalone speed claim.

GUI 2027 disposable PID 48640, scripted brush + synchronous normal GPU drawing:
prototype paired ABBA medians: old 44.711 / 44.486 ms, new 41.600 / 41.282 ms.
After production integration (no monkeypatch), ABBA medians: old 44.522 /
44.450 ms, new 42.903 / 41.714 ms. See gui_routes_bound_integrated.json;
each trial names the actual DLL and retains numeric stage samples. All runs
passed ordinary/numeric exact final data and Undo restoration. A separate
single current-default run measured 44.765 ms relax / 28.272 ms point, showing
cross-run variation; see gui_bound_current.json. Do not represent a paired
relative gain as a guaranteed absolute FPS. No physical mouse latency test.

The diagnostic Maya is left on the adopted bound DLL. Artist Maya was not
reloaded. Standard launch uses the new path without a mode toggle. No CUDA.
The 60 FPS goal is NOT achieved.


Default DLL subsequently advanced to tangents.dll, retaining this export.
See TANGENTS_STATUS.md for the latest integrated GUI measurements.

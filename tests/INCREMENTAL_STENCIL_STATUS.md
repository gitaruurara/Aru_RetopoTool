# Incremental stencil candidate

Build mesh_buffer with -SleepingTeam -InputCache -IncrementalStencil and the
separate aru_retopo_mesh_buffer_incremental.mll name (2024/2027 built).
Default plugin selection is unchanged. The live verification scene now uses the incremental candidate.

Cache the refined coordinates plus a reverse map from control vertices to output
stencil rows. Bitwise comparison of transformed controls finds changed controls;
only affected rows are reevaluated, preserving original term order. Edits affecting
more than half the rows use the original full parallel evaluator. Input validation
rebuilds, control count changes, and non-normal contexts invalidate the cache.
All returned Maya data remains separately owned, not a mutable cached buffer.

Both Maya versions passed native_graph regression, including subdivision/patch
changes, retained output ownership, Undo/Redo, settings and scene reopen.
2027 recorded replay: broad edit 10.205 ms, one control edit 4.069 ms vs adjacent
input-cache-only 4.530 ms. Pose hashes are identical for both comparison cases.
Measurements include native coordinate evaluation but no input handlers or redraw.

This improves a small part of editing. 60 FPS is not achieved. Direct UI integration
and specific non-normal evaluation context tests remain to be done before promotion.

## Live Maya 2027 validation

Backed up the scene to maya-before-incremental-20260918-041703.ma and opened a
separate candidate copy. Scripted MMB handler + synchronous redraw: baseline
31.710 ms, candidate 29.309 ms median, identical final guide hash and verified
Undo restoration/session cleanup (gui_incremental_point_{baseline,candidate}.json).
Numeric brush + redraw: 45.644 ms; ordinary/numeric final guide data identical,
Undo restored (gui_incremental_relax_candidate.json). Sixty camera orbit steps:
4.514 ms median, 11.923 ms max, zero curve resamples, camera and guide restored.

These results do not establish 60 FPS editing: first MMB step was 119.861 ms;
release with an actual topology attachment was 1227.586 ms. Capture confirmed
scene display returned after the test, but not close-up component/occlusion parity.
Live native node is incremental candidate; temporary preview shapes were cleaned
up and the default tool backend has not been promoted or pushed.

## Point preview initialization

PointPreview.read now obtains immutable parsed metadata from from_json_cached
and creates an owned editable copy through _evaluated_copy using raw base positions
(not evaluated CP offsets). This avoids repeated JSON decoding and endpoint/chain
classification at stroke start. Shared-cache mutation, legacy release parity,
nonzero CP offsets, Undo/Redo, save, cancel and error paths passed the full smoke
suite on Maya 2024 and 2027.

Live same-scene point benchmark: first drag 34.653 ms vs previous 119.861 ms;
median 28.205 ms; final guide hash unchanged; Undo/session cleanup passed.
Evidence: gui_point_cached_initialization.json, smoke_point_cached_2024/2027.log.
Topology-changing release remains about 1.24 s. Editing 60 FPS remains unmet.

# Occlusion investigation, 2026-09-18 (incomplete)

Production worktree only: gpu_preview.py changed, not committed/pushed.
Diagnostic Maya PID 38780 port 50018 alive and responsive. Cylinder fixture remains.
Do not overwrite tests/occlusion_before_test.ma: backup of original 500-patch scene.

Findings:
- Preserve depth in both Foreground passes (mask 0), avoiding reference occlusion loss.
- MCameraOverride projection Z alone is ignored/rebuilt by Maya. Near/far overrides
  have effect when mUseProjectionMatrix is also true. Verified callback matrices.
- fn.isOrtho is a METHOD, use isOrtho().
- Perspective near/far *1.005 produces front cyan surface + edges with hidden rear
  on radius-3 cylinder; guides *1.006. Orthographic planes +orthoWidth*.005/.006.
- Current implementation queries the destination panel camera on each pass, uses
  M3dView projectionMatrix. XY and actual scene vertices unchanged.
- gui_occlusion_current.py reloads gpu_preview safely via viewport_session.stop/start,
  enters real guide context, captures front/back/ortho/restored cameras.
- occlusion_current_front.png and ortho.png visually show correct surface + edges,
  HOWEVER FRONT EP/HANDLE MARKERS ARE MISSING except handles outside silhouette.
  Cannot claim guides finished. Likely stock fat-point depth handling differs.
- Increasing guide bias .005 -> .006 restored some silhouette points but no front EPs.
- gui_occlusion_priority.py control priority 10000 showed rear tangent lines but
  removed point markers. This monkeypatch has been RESTORED to original function.
  Do not adopt high priority. Source gpu_guides.py unchanged.
- No release-stall work in this turn. Prior profile still shows attachment causes
  topology Plan/compile rebuilding ~858ms; need ordinary nonattachment measurement
  separately in backed-up large scene, then fix costly topology updates.

Temporary scripts/captures are untracked. gui_bias_recreated.py experiments (including
preSceneRender JSON logging) are no longer installed; gpu_preview was reloaded.
Current loaded GPU preview matches working tree. No production completion claimed.

## Continuation 2026-09-18: points fixed, release still incomplete

Current changes: gpu_preview.py, editor/curvenet/gpu_guides.py,
NEW editor/curvenet/gpu_point_shader.py, core.py, tests/test_core.py.
No commits/push. Do not stage temporary tests or downloaded Autodesk fragment XML.

Point root causes:
- mayaPoint2Quad geometry shader adds size-dependent depth pushback (-dp where
  perspective dpScale=-depthPriorityThreshold). This hid points behind surfaces.
- Custom private geometry fragment derived at runtime from installed Maya XML
  removes only outS.Pc.z extra assignment; no Autodesk shader source distributed.
- gpu_point_shader builds its own graph (aruRetopoDepthPointShaderV2) because
  getFragmentXML for already-compiled stock graph can omit vertex connection/inputs.
- Crucial: item.getShader() parameter edits require item.setShader(shader) afterwards.
  Rebinding after point size/color updates FIXED disappearance on reopen. Applied
  same correction to curve line color/width updates as well.
- gui_occlusion_reopen.py saves cylinder fixture, new/open, reloads gpu_guides,
  then gui_occlusion_current. Images front/ortho show correct EPs and no rear rings.
  Current ortho image also clearly shows cyan front handle points. Restored camera.
- gpu_guides monkeypatches from trial/runtime helpers are gone (module reloaded).
- Point shader actual 2024 GPU validation still needed; smoke is not viewport test.
- Bias remains fixed screen-relative (.005 surface, .006 guides). Need zoom/scaled
  mesh tests to ensure far-distance bias does not expose rear thin surfaces.

Current diagnostic PID38780 port50018 is on restored large 500-patch scene now,
NOT cylinder. Cylinder scene preserved tests/occlusion_cylinder_test.ma; original
500-patch backup remains tests/occlusion_before_test.ma. No artist scene touched.

Release measurements:
- gui_release_directions.py tested right/up/left, ALL accidentally/intentionally
  attach to nearby spline in dense fixture. 758/840/838ms. Topology1589->1590splines.
- gui_release_required_steps.py compares attach and no_attach_diagnostic. The latter
  mocks only _find_spline_under_screen=None to isolate ordinary finalization; do NOT
  call this an actual free-space mouse test. Ordinary finalization ~58ms, topology
  unchanged. Attach still715.5ms, patch_transfer100.3ms, dirty refresh577.7ms.
- New core._required_subdivision_steps works backward before generating coefficient
  rows, skips overwritten guide/Coons rows. Topology and output numbering unchanged.
  Saves some time but NOT enough. Source production now has pruned intermediate rows.
- 20 cases against original full Plan at tests/plan_full_reference.py: triangle/quad/
  pentagon/octagon + mixed triangle/quad, levels1..4, random moved CVs. EXACT compiled
  CSR equal; faces, adjacency, guide assignments equal; final positions error0.
  Result tests/required_steps_parity.json. Reference snapshot is untracked.
- test_core normalization now checks nonempty intermediate rows AND every final
  compiled row sums1. All13 tests pass.
- Maya registered plugin uses compute.__func__.__globals__['Plan'], not reliably
  sys.modules entry. gui_release_required_steps installs reloaded core.Plan there.
  Current diagnostic uses NEW Plan via this globals assignment.
- New gui_release_profile.txt profile:1.204s instrumented; Plan.__init__.855s,
  _required_subdivision_steps .364s, compile_stencil .142s. Still topology graph +
  coefficient generation dominates. Prior profile2.197s, oldcompile1.01s/Plan.992s.
- Native per-level subdivision topology/weights is next useful optimization. Current
  Python builds faces/edge incidence/maps/UV/CSR. Can move exact numbered child faces,
  sorted edge IDs and Catmull-Clark CSR to C++ core; preserve quad UV and guides.
  No fallback architecture needed. Existing build_windows.ps1 -CoreOnly supports
  -OutputDirectory for candidate DLL build while current core is loaded. CoreABI5
  currently mandatory; extension/new ABI must be handled consistently if adopted.

Validation:
- tests/smoke_occlusion_required_2024.log: ALL MAYA SMOKE TESTS PASSED 2024, exit0.
- tests/smoke_occlusion_required_2027.log: ALL MAYA SMOKE TESTS PASSED 2027, exit0.
- RuntimeError injected preview/point errors are expected regression tests.
- git diff --check passed. Goal incomplete: release still715ms and broader viewport
  validations pending; do not mark complete or push as finished.

## Continuation: native topology ABI 6 (incomplete goal)

Production now uses bin/aru_retopo_core_v6.dll. New files that MUST be staged when
ready: cpp/subdivision.h, subdivision.py, bin/aru_retopo_core_v6.dll,
editor/curvenet/gpu_point_shader.py, tests/test_subdivision.py. Existing tracked
changes also include core.py, native.py, cpp/retopo.cpp, build_windows.ps1,
CMakeLists.txt, README.md, patch_transfer.py, gpu_preview.py, gpu_guides.py,
tests/test_core.py. Old core_v5.dll still tracked/on disk; not used by new startup.
Do not remove a loaded binary from disk. No commit/push yet.

C++ kernel:
- subdivision.h exports owned Step and Plan handles. Exact child vertex ordering:
  old vertices, lexicographically sorted edges, original-order face centers.
- Plan computes all levels, guide edge parameters, quad UV propagation, final
  adjacency. subdivision.plan copies owned CSR/geometry buffers and closes handle
  in finally. core.Plan uses this only; superseded Python topology/pruned-step
  implementations and temporary per-level Python bridge were removed.
- Full CC rows still built in C++; guide/Coons overrides composed as before.
- Initial empty topology bug fixed (null data pointer allowed for zero entries).
- 20 old/new cases: mixed triangle/quad, polygons3/4/5/8, levels1..4, moved CVs;
  topology, adjacency, guides identical; final position/CSR errors <1e-12 (shown
  cases exact0). tests/subdivision_plan_parity.py/.json. Reference snapshot is
  tests/plan_full_reference.py (untracked). Test script still selects candidate
  bin/subdivision_ready/core_v5.dll; production numerical tests use real v6.
- New tests/test_subdivision.py validates analytical boundary masks/numbering,
  retained output ownership, empty/malformed input. Passed systemPython and
  mayapy2024/2027. Existing13 core+2 compiler tests also pass with productionv6.
- tests/test_core now additionally checks all final CSR row sums1; intermediate
  row normalization assertion restored to original (no empty-row exemption).

Other optimization:
- patch_transfer indexes children by parent instead of scanning all1590splines
  once per selected patch. Precomputes loop keys. Same flood-fill/ownership rules.
- core.regions caches raw normal_at results once per EP for loop orientation;
  previously queried same EP repeatedly. Geometry/normals unchanged.

Maya diagnostics:
- PID38780 port50018 still alive, large500patch fixture, Undo restores after tests.
- Current Maya uses production native module reloaded to v6, subdivision reloaded
  with DEFAULT native.library (no candidate override), core.Plan installed through
  MPxNode.compute.__func__.__globals__['Plan']. patch_transfer reloaded.
- IMPORTANT: first one-shot native-plan timing193ms was INVALID: stale module did
  not export plan, node.status returned ERROR. Those results were rejected. Added
  gui_point_drag mesh_status/plan_status; new helpers assert no ERROR. Always check
  plan status and actual output mesh, not only guide changes/Undo.
- Valid timing after reload: native plan515ms; productionv6+transfer421ms;
  latest normal caching: attach413.162ms, patch_transfer60.152ms, refresh319.136ms.
  Nonattachment isolated diagnostic55.111ms (spline-hit mocked None, not physical
  free-space mouse test). Native plan reports496regions/46144quads/46552verts after
  attach,500regions/46528quads/46873verts after ordinary move. Restoredtrue.
- Results tests/release_production_v6.json via gui_release_production_v6.py.
- Profile tests/gui_release_profile.txt (before final normal cache): .475s sampled,
  Plan ctor.138s, subdivision.plan.053s, compile_stencil.139s, Composer.set.027s,
  Composer.packed.022s. This is now far below old~2.197s sampled, but release still
  ~0.41s. Do NOT mark stall fixed yet.
- Actual output mesh face-count/finiteness/hash comparison is still worth adding
  to GUI helper; mesh_status comes from legacy generator and can be stale. Plan
  status now checked, but direct-buffer node output should also be validated.

Tests after production integration:
- smoke_subdivision_v6_2024.log ALL MAYA SMOKE TESTS PASSED 2024, processexit0.
- smoke_subdivision_v6_2027.log ALL MAYA SMOKE TESTS PASSED 2027, processexit0.
- git diff --check passed.

Remaining opportunities/requirements:
1. Reduce remaining compile_stencil Python Coons dictionaries + CSR round trips,
   possibly perform exact guide/Coons composition while native Plan owns its steps.
   Native Plan currently frees steps after copying them; a direct native compiler
   could avoid returning300kcoeff entries toPython then sendingthemback. Preserve
   CV aliasing, side direction/multisegment interpolation and ordered arithmetic.
2. Viewport2024 realGPU validation pending. Current shader confirmed2027 only.
3. Existing depth bias is fixed fraction of camera depth (.005surface/.006guide).
   Must test far zoom/scaled/thin meshes. At huge camera distance bias may expose
   rear surfaces again. Cap world-space bias relative to reference mesh bounds,
   or adopt reference-specific depth approach; avoid claiming current cylinder
   test proves all zooms. Orthographic bias scales orthoWidth similarly.
4. Final fresh process/reopen/Undo/Redo and direct mesh geometry validation before
   completion. No push until real verification, no goal complete yet.

2026-09-18 continued validation:
- User requested old Maya shutdown: diagnostic PIDs 48640 and 38780 terminated;
  artist PID49428 preserved, diagnostic Maya2024 PID52504 / port50024 remains.
- Maya2024 fixture completed after direct command-port execution with outer
  exception capture. Socket newline/NUL alone is not proof of execution.
- bounded_depth_2024.json: 16 regions / 256 quads / 288 vertices Native.
  Viewed bounded_2024_near/far/ortho.png: front cyan surface, black topology,
  front EPs/handles visible, rear guides/faces occluded in these three views.
  Far camera is 8x distance with focal length 280 vs 35; orthoWidth12.
- Current depth bias bounded to 2% minimum positive transformed reference bbox
  dimension and camera-depth fraction .005. Guide depth priorities reduced to
  0/1 curves, 0 controls to avoid camera-distance-dependent rear-point bleed.
- cylinder_interaction_2024.json: 48 forced camera redraws, guide JSON unchanged;
  real context point drag on EP9, 8 steps with delta(1,1), release10.567ms,
  geometry data changed, Undo restored, no plan ERROR, same 40 splines/104 CVs.
  Input was scripted draggerContext queries, not physical mouse events.
- GUI capture also showed a Maya2027 error-report dialog left over beside the
  functioning Maya2024 viewport. No report sent. No Maya2024 crash observed.
- git diff --check passed. Goal NOT complete: large attachment release remains
  413ms in previous valid measurement; direct-buffer output validation and
  further topology rebuild optimization remain. No commit/push this turn.

2026-09-18 performance experiments and direct-buffer verification:
- Launched diagnostic Maya2027 PID42912 on port50018 after stopping diagnostic
  Maya2024 PID52504. Artist PID49428 remained untouched (loaded core_v4).
- Rebuilt core_v6 with batched patch instance API candidate; 19 unit tests and
  20 old/new coefficient comparisons passed. Same 500patch/46873vertex plan:
  6 alternating measured samples: Python remap median92.165ms, native instances
  median91.024ms. Negligible benefit: removed the added API and production call.
- Tested returning owned array.array instead of lists from Composer.packed.
  Alternating real drag/release on same 2027 process and input screen1546,1145:
  list median376.2075ms, arrays454.0284ms (exclude first pair). Removed this change.
- gui_point_drag.py now reads actual aruRetopoMeshBuffer outPositions, faceCounts,
  faceIndices before Undo. Checks finite coords, index range, counts, hashes.
  release_arrays_comparison.json proves EXACT coordinate and topology hashes
  before/after for all four pairs and Undo restored. Plan outputs not ERROR.
  Same input produces498regions/46320quads/46700vertices when attached, differing
  from prior 1600px viewport result (496regions); do not compare timing directly.
- All experiments rolled back; production core.py/stencil_compiler.py behavior
  remains pre-experiment. core_v6 rebuilt without added unused instances API.
  Diagnostic42912 stopped, production DLL restored from bin/arrays_candidate;
  artist49428 remains. No live diagnostic Maya now; launch fresh for next GUI.
- 18 tests pass on restored production DLL. No goal completion or push.
- Remaining: reduce global topology regeneration on local attachment changes.
  Two microoptimizations measured and rejected. Do not reintroduce either based
  on intuition. Display verification from prior turn remains valid; same source.

2026-09-18 native plan composition AFTER published checkpoint876ebe6:
- Published checkpoint main876ebe61b8f14253364dbdaad3ffc0b55a4b93ac stays on remote.
- Added cpp/subdivision_compile.h. Native Plan retains original faces/guide edges
  and step CSR; compile computes guide overrides, prunes unused Catmull-Clark
  dependencies, evaluates Coons rows, and packs the final stencil in C++.
- Python Steps owns plan handle, lazily copies steps only for evaluation/tests;
  production compile uses retained native arrays. No runtime Python compiler
  fallback. API7/core_v7 is separate from published v6; oldDLLlefton disk.
- tests/check_native_plan_compile.py: 20 cases coefficient equality (maxerror0),
  13 core tests pass. Same saved~46k-face input standalone median plan+compile
  before186.519ms after139.327ms; compile84.0235->41.2548ms.
- Fresh diagnostic2027 PID44048 / port50018 (artist49428 unchanged). Native
  candidate DLL loaded explicitly into that fresh process. Four alternating
  real context attach/Undo pairs: release_native_plan_comparison.json.
  Excluding firstpair: beforemedian436.3827ms / after330.7157ms. Exact outPositions
  and faceIndices hashes all4pairs. Undo restored every time; plans not ERROR.
- Integrated production source, v7build; release_production_v7.json confirms
  production native version7, attach336.310ms / no-attach-diagnostic59.316ms,
  matching prior baseline hashes:46700vertices/46320faces/498regions on attach.
  no-attach case suppresses curve hit testing, not physical free-space input.
- Added ownership/closed handle/rejected compilation/empty plan regressions;
  19 tests passed productionv7. 2024/2027 maya_smoke both exit0 and ALL MAYA SMOKE
  TESTS PASSED. Logged exceptions are injected preview-drag/point-preview tests.
- Both core_v6 published and core_v7 integrated remain on disk. No new push yet.
- Remaining performance work: ~0.33s local attachment topology rebuild still
  visible; native Plan construction and patch transfer are next largest costs.
  Keep goal active until actual requested interaction outcome is verified.

2026-09-18 post-v7 profile and scratch masks:
- Profile on diagnostic44048: native Plan209ms inclcompile; subdivisioncreate53ms,
  compile38ms, to_dict70ms. gc.callbacks confirmed generation2 collections of
  60-70ms, often collecting0 objects. This is real global GC work; do not globally
  disable/freeze GC or shift this delay elsewhere and claim it is removed.
- Tested lazy_objects for patch transfer clones: final geometry identical but
  release times not reliably better. Reverted.
- Tested lazy Python faces/patch views and directflatMeshpayload: final geometry
  identical, asserted views not materialized; release improvement not sustained.
  Reverted ALL core.py / bothplanplugins / patch_transfer.py experiments.
- Adopted ONLY C++ Mask scratch row reuse in subdivision.h. Replaces std::map
  percoefficient allocations with one reusable small contiguous row, linear
  accumulation preserving operation order, sorted indices on emit. ABI7 unchanged.
- flat_masks_comparison.json: 6 warmalternating inputruns, exact faces/guides/UV/
  all intermediate CSR and final coefficient equality. Plan106.856->91.042ms;
  totalplan+compile143.894->126.865ms. 19 tests candidate pass.
- 6-pair GUI first comparison was GC-phase biased; followed with12pairs where
  before/after ordering reverses eachpair. release_flat_masks_balanced.json:
  exact output hashes and Undo restore all12pairs; noerrors.
  IncludingGC median387.524->377.398ms, mean363.426->362.272ms (essentiallysame).
  Subtracting measured in-releaseGC median318.665->306.644ms; this is computation
  diagnostic only, NOT achieved userinteraction latency. Strongerclaimunsupported.
- Diagnostic44048 stopped after verification, artist49428 preserved. No live
  diagnosticMaya now. CandidateDLL copied toproductionbin/aru_retopo_core_v7.dll.
  19 productiontests pass; priorv7 2024/2027 fullsmoke already passed. This change
  preserves ABI, output data, ownership, and algorithms except allocationstrategy.
- Remaining globalGC + fullnativePlan topology rebuild. Goal staysactive.
  Publishedmain remains876ebe6; localv7commit3488160 plusnew scratchmaskcommit.

2026-09-18 production v8 final verification:
- Native oriented halfedge region detection replaces Python implementation; ABI8.
- 161 exact loop parity cases. 22 production unit tests passed.
- Eight alternating GUI pairs: release median372.960->295.798ms,
  mean354.324->316.202ms; exact output hashes and Undo restored all pairs.
- Production v8 real context handlers with scripted input, no disabled snapping:
  free move release60.386ms, attachment release299.303ms. Both changed data and
  Undo restored; attachment geometry/connectivity hashes equal baseline.
- Full Maya2024 and2027 smoke runs exit0: ALL MAYA SMOKE TESTS PASSED.
- v8 cylinder near perspective, 8x far perspective and orthographic images viewed:
  front surfaces/edges/EPs visible, rear surfaces/guides occluded.
- Diagnostic PID51456 remains on cylinder fixture, artist49428 untouched.
- Remote remains876ebe6 for user testing. v8 changes are local only.
- Remaining limitation: topology-changing attachments rebuild the full plan and
  take roughly0.3s at500patches. Ordinary move no longer reproduces1s release stall
  in scripted handler validation. Physical mouse experience awaits user feedback.

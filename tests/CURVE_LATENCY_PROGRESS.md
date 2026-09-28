# Current-scene curve latency: work in progress

The requested ~16 ms from curve release through visible confirmation is NOT achieved yet. Keep the goal active.

## Verified checkpoint

Scene: Toriel_retopotest.mb, live Maya 2027. A non-destructive export is stored locally in current_curve_latency_scene.mb (ignored by git). The user scene was not saved or replaced.

- Removed repeated complete topology analysis per saved local field. One SceneTransfer now feeds selected-patch and local-edit transfer. Native normal queries are batched, unchanged attributes are not rewritten, and reference projection is built only when resampling is necessary.
- Conservative Bezier control-hull bounds skip distant curves. Segment intersection normals and calculations are batched. Mirrored nearest-curve/endpoint searches reject distant candidates before sampling or matrix lookup.
- Symmetry seam constraints reuse object matrices and endpoint tests within an operation.
- Local parameter coordinates reuse immutable subdivision templates.
- Native plan provider retains its reference projection accelerator until referenceMesh is dirtied. Newly discovered region layouts and relevant spline controls must match before compiled plan buffers can be reused.
- Foreground depth limits retain their numeric behavior while caching node discovery with add/remove callbacks. meshName and connections remain live API reads every frame.

## Measurements

current_curve_commit.py runs release and actual native mesh evaluation on a copy of the current scene, with Undo restoration. It supplies a fixed valid endpoint placement instead of GUI cursor picking. This is NOT complete interactive timing.

Latest unprofiled warm samples: release 29.53 / 30.67 ms; native evaluation 31.57 / 32.63 ms (about 61-63 ms total). First iteration: 66.79 + 37.13 ms. Exact output is current_curve_commit.json.

Current live viewport after foreground optimization: dirty guide redraw 23.54-36.60 ms (current_curve_viewport_after.json). This is redraw alone; it must not be reported as full commit latency.

## Validation

Maya 2024 and 2027 curve_latency_regression.py exited 0. Checks cover 190 synthetic curve-pair comparisons, 50 nearest-curve comparisons, original UV coordinates for 3/4/5/7-gons and levels 1-4, region ancestry, plan reuse and split/Undo invalidation, reference mesh invalidation, symmetry constraints, foreground node discovery invalidation, and filled/unfilled patch preservation.

Current-scene 96-pair crossing comparison matched old output (curve_latency_numeric_parity.json). Batched normal output exactly matched old normal queries for current endpoints. Existing curve_edit_features.py and 21 core/region/local-edit tests passed on both Maya versions during optimization. Latest added regressions also check native plan behavior. A third-party startup SciPy traceback appears in some Maya 2027 logs but the test process exits 0; use PASS lines and return code, not absence of startup warnings.

## Runtime and next work

Tested Python changes are hot-installed in the current live editor without unloading plugins. RetopoPlan1 status is valid. Native provider methods were updated on its existing class, preserving registered Maya attributes.

__main__._aru_latency is a temporary timing monitor around real release/commit/draw operations. No user release has been captured yet. Inspect its rows, and restore its original list of (object, name, function) entries when removing it. __main__._aru_latency_test_processes retains the final standalone process objects (both exited 0).

Remaining: reduce topology transfer and native plan rebuild further, measure representative actual GUI creation/splits including rendering and cold spikes, validate generated geometry against pre-optimization results. Do not declare completion from the current ~60 ms offline measurement or redraw-only timing.


## Continuation checkpoint: native correspondence and shared paint parsing

- Added optional Python/Maya-independent `transfer_native.py`, `cpp/transfer.cpp`, `bin/aru_retopo_transfer_v1.dll` (23,552 bytes), CMake target and `cpp/build_transfer.ps1`. Native endpoint correspondence preserves ordered first matches, reversals, duplicate endpoints and strict squared-distance tolerance. A tested Python fallback remains available. Dimension checks protect native input buffers.
- Correspondence timing on the current network: Python 2.84-3.11 ms vs native 0.69-0.84 ms, exact matching output including reversed duplicate splines.
- `local_fields.decoded` shares an LRU of four read-only paint JSON payloads between local-edit transfer and native plan evaluation. Callers never mutate cached fields.
- Both changes were hot-installed in live Maya, including the existing plan provider's compute method. Scene data has not been saved or replaced.
- Final standalone jobs `__main__._aru_latency_native_jobs`: Maya 2024 regression PID 44124, Maya 2027 regression PID 33468, Maya 2027 benchmark PID 48100; all returned 0. Regression includes native correspondence/tolerance/invalid-dimension checks as well as the prior invariants.
- Latest current_curve_commit.json: warm release 24.34-25.15 ms, evaluation 26.93-27.40 ms (about 51-52 ms total). First iteration 57.18 + 33.93 ms. Still NOT the requested ~16 ms, and still no actual user GUI release captured.
- Native timing stages: approximately 20.5-21 ms input/plan evaluation, 0.01 ms topology validation, 5.6-5.7 ms projection/relaxation, 0.5 ms mesh creation/output.
- Detailed isolated instrumentation is in current_curve_stages.py/json. Its warm provider.compute is ~20 ms: selected_regions 3.4 ms, Plan 7.3 ms (native subdivision 4.7 ms included), stencil compilation 1.4 ms, field weights 2.9 ms. Release includes prepare_all ~10.3 ms (SceneTransfer ~4.1, Transfer ~4.2), commit ~15.3 ms, source+mirror fitting/intersections ~6 ms. These are inclusive/nested times, not additive independent stages.
- Build job `__main__._aru_transfer_build` and detailed benchmark `__main__._aru_latency_stages` also returned 0. No unfinished subprocess remains from this continuation.
- Actual live redraw remains ~24-36 ms independently of commit. GPU preview has three scene passes; investigate only with visual equivalence checks, preserving the earlier foreground visibility fix. More substantial plan/commit work is still required; do not reduce the goal to callback time or defer actual confirmation and call it complete.


## 2026-09-18: actual GUI stall identified and reduced

- Actual releases recorded 1,139?1,382 ms. Correctly instrumenting the copied
  globals of the hot-installed accessor.write showed 1,091?1,305 ms inside
  synchronous `_dirty_shape_view`, not field transfer (0.3?14 ms).
- cProfile of actual commit refresh caught PatchTool.rebuild constructing 204
  separate Plans, each repeating full region discovery and canonical alias scans.
  This was the dominant one-second path; legacy generator compute was not it.
- patch_context.py now discovers regions once, rotates each loop identically,
  passes precomputed region_loops, retains Surface until reference vertices or
  triangles change, and caches each candidate by directed side grouping, spline
  controls, and their positions. Unchanged candidate mesh objects are reused;
  removed candidates are discarded. Normal queries use endpoints only.
- symmetry_ops.py now uses a spatial endpoint index and endpoint-pair spline
  index, retaining strict tolerance, lowest-index duplicate resolution, sequential
  creation, and manual-handle propagation. Axis/space are resolved once.
- Current-scene 206-patch comparison: old rebuild 1,077.40 ms; new first build
  346.41 ms, cached rebuild 60.88 ms before indexed symmetry; 35?37 ms after it.
  All preview triangle coordinates matched exactly (max delta 0), paired maps equal.
  Runtime monitor also saw 18.16 ms with no candidate rebuild, but this is NOT
  complete confirmation latency. Observed real releases after preview fix still
  189?325 ms. Goal ~16 ms remains NOT achieved.
- Saved-scene benchmark now includes hover rebuild separately:
  current_curve_preview_commit.json warm release 25.56?28.62 ms + output evaluation
  26.43?27.10 ms + hover rebuild 37.80?39.30 ms. It still lacks actual viewport and
  cursor, and uses the older exported scene; do not claim these as real GUI times.
- local_edit_transfer.py loop reuse and closest_many were checked on triangle,
  quad and pentagon atlases against scalar Maya face choices. Previously saved
  current painted split parity: 106.6 -> 81.24 ms, max field difference 2.78e-16.
- Maya 2024 and 2027: curve_latency_regression and curve_edit_features passed
  (including 21 core/regions/local edits tests). New patch_preview_latency test
  checks geometry parity, changed-only reuse, reference edits, Undo/Redo, symmetry
  axes/spaces/create and locked manual handles. Final repeat after restricting
  normal queries to endpoints stored in curve_latency_preview_final_*.log.
- Source updates are hot-installed in the live Maya instance. No user scene save.
  No native plugins unloaded. Heavy cProfile wrappers removed; lightweight
  _aru_latency timings remain. _aru_preview_monitor_original is an OLD method;
  DO NOT restore it. _aru_write_profile_original is restored already.
- Read-only/same-value live diagnostics: dgdirty/refresh, same netData re-set,
  then identical-data accessor.write(refresh=False) only after verifying zero CPs,
  no active drag and byte-identical JSON. Undo recording temporarily disabled
  without flushing and restored. Same-value write profiled ~7 ms; real writes
  still need timing of native command/Undo/reentrant timer costs.
- Potential next work: actual-release profile after these changes, avoiding
  repeated full hover builds when many curve IDs shift; investigate write's
  unaccounted ~40 ms and synchronous draw, and main-thread timer reentrancy.
  Profiling CP reads alone: API asMDataHandle ~2.17 ms vs cmds.getAttr ~6.54 ms;
  child asDouble ~6.27 ms. No CP implementation changed (handle ownership needs
  checking before using asMDataHandle in a repeated production path).

## Crash investigation and handle lifetime fix (23:30 onward)

- User reported Maya crashed; user explicitly does NOT need unsaved-data recovery.
- Windows System event 2004 at 23:30:09: main maya.exe PID 52536 committed
  163,591,880,704 bytes (~152.36 GiB). Independent Maya2027 test failed importing
  OpenMayaRender due to paging-file exhaustion; Maya2024 test also failed under
  system-wide exhaustion. Parallel test load was initially suspected, but the
  dominant allocation was the main Maya process. Keep tests sequential now.
- Confirmed an actual leak in production MPlug.asMDataHandle() references:
  patch_context rebuild/hover and local_edit_runtime Snapshot used handles without
  the required MPlug.destructHandle(). Added maya_data.plug_handle contextmanager
  and changed all three production sites to release in finally.
- Official ownership contract: https://help.autodesk.com/cloudhelp/2027/ENU/MAYA-API-REF/cpp_ref/class_m_plug.html
- Bounded standalone saved-scene reproduction: 16 unbalanced reference reads grew
  private commit by 54,632,448 bytes (~52.1 MiB), while 500 balanced reads grew 0.
  Simple polyPlane output did NOT reproduce leakage: testing the actual connected
  referenceMesh input matters. tests/data_handle_memory_scene.json/log record it.
  Thus leak is established and contributed to huge memory growth; cannot prove
  it is the only contributor or that all memory instability is resolved yet.
- Fresh Maya PID 52612, user reopened Toriel_retopotest.mb. No recovery performed.
  Hot-installed new PatchTool.rebuild, PatchTool.hover, Snapshot.__init__ methods
  with plug_handle. Verified active instance class and function globals match.
  Old instrumentation in __main__ was lost on crash; do not assume it exists.
  Main private memory was ~15.5 GB before hotfix, ~17.0 GB after tests while user
  was working. Existing leaked allocations cannot be reclaimed by the fix.
- Shell tools work with require_escalated! Ordinary sandbox exec/apply_patch fail
  helper_unknown_error. Use escalated read/write shell when needed, auto-review
  accepted diagnostic and scoped workspace edit commands. rg now available there.
  Repo root is Aru_RetopoTool itself, not D:/Dropbox/App.
- Tests after handle fix: sequential Maya2027 and Maya2024, both
  curve_latency_regression + curve_edit_features passed exit0. New runner
  tests/run_maya_test.py initializes Maya BEFORE importing test module: direct
  feature script had startup userSetup interference clearing __main__.e.
  Logs: tests/handle_fix_<test>_<year>.log. 21 unittest checks also pass.
- Control-point compaction batched capture fix WAS saved and installed before
  crash: prune_orphan_cvs_and_write batches contiguous existing CP indices instead
  of ~1100 getAttr calls. Regression covers nonzero offset remapping + Undo/Redo.
- Later real releases BEFORE crash also included 1,176–1,227 ms cases when orphan
  compaction triggered. Breakdown: prepare_all 377–491 ms; viewport403–470 ms;
  individual CP capture ~250ms. Normal moves often ~85–202ms. Goal remains active
  and NOT achieved. Do not summarize all operations as <=300ms.
- Proposed local_edit_transfer same-parameterization shortcut WAS NOT APPLIED:
  the tool connection failed before executing its edit. No source change from it.
  Investigate next: CV/spline renumbering causes unchanged painted patches to
  resample unnecessarily and invalidates preview candidates by global IDs.
- tests/CURVE_LATENCY_PROGRESS.md prior paragraphs stating final status are
  superseded by this crash section. No scene save, no plugin unload, no goal
  completion. Current source stability fix needs continued memory observation.

## Renumbering optimization (23:54)

- Previous goal turn was progress: confirmed/fixed handle leak. This turn also
  progresses the original goal; actual full-confirmation ~16ms still unproven.
- local_edit_transfer.parameter_boundary compares EXACT directed Bezier controls
  and side grouping in Plan's canonical parameter origin. prepare preserves paint
  samples and reduction UV edges when only patch IDs change and this signature
  matches. Changed shape/origin still resamples; no tolerance shortcut.
- PatchTool.rebuild cache now keys by directed control positions plus relative
  endpoint order, retaining Plan triangle/vertex order while allowing global CV
  and spline IDs to change. Reused meshes get their new patch key. Reference
  changes still clear cache. Existing first-match symmetry behavior retained.
- tests/renumber_local_edits.py: exact paint/reduction preservation, changed shape
  and rotated UV origin fallback, Undo/Redo. Added to curve_latency_regression.
  tests/patch_preview_latency.py now checks actual Maya candidate mesh reuse for
  CV renumbering and spline-index shifts, against original geometry results.
- Sequential Maya2027 and2024 curve_latency_regression + curve_edit_features all
  pass (tests/renumber_<test>_<year>.log). git diff --check passed.
- Both source changes installed live after mouse operation ended. Heavy profiler
  not used. __main__._aru_release_samples is a new last-100 lightweight release
  monitor, installed on type(__main__.__retopoGuideCtx__).release. It only records
  elapsed ms currently, including no-op releases; do NOT treat low no-op times
  as successful confirmation. Previous _aru_latency no longer exists since crash.
- tests/current_renumber_latency.py uses exported older scene and deliberately
  seeds 20 nonuniform fields on existing regions. New exact retention ran 9.67ms
  and8.75ms; all20 fields preserved exactly. Baseline resampling failed at168.81ms
  with Degenerate patch atlas, so this is NOT a full old/new speed comparison.
  No user scene writes are used by this benchmark.
- Initial shell-launched scene benchmarks were INVALID: missing Maya plugin and
  script paths caused zero regions in evaluated guideData; all old fields dropped.
  DO NOT use earlier 363->94ms/all0-field figures. Correct subprocess inheritance
  from live Maya restored190+regions. Some first20 projected atlas faces remain
  degenerate; exact renumbering does not need these unnecessary projections.
- Launch full-scene benchmarks from live Maya with os.environ.copy(), prepend
  Maya2027/Python/Lib/site-packages and root.parent to PYTHONPATH. Retain Popen and
  confirm termination before next process. __main__._aru_renumber_job exited0.
  Fixture tests in blank scenes work through shell with proper MAYA_LOCATION.
- Main Maya PID52612 remained ~17.09GB private commit at start of this turn, compared
  to~17.05GB at prior turn end. No renewed massive growth observed. Existing leaked
  allocations pre-hotfix remain. No native plugin reloads or user scene saves.
- Next: read new actual-release samples, instrument whole commits with light
  substage timers if needed; optimize remaining native plan/Undo/view refresh
  costs. Goal requires actual current-scene full confirmation, not merely the
  9ms data-transfer substage or saved-scene/offscreen benchmarks.

### Latest real GUI timings after renumbering hot install

- Real releases recorded ~287–542ms; no-op releases ~0.03ms MUST be excluded.
- Lightweight per-stage monitor installed live:
  __main__._aru_commit_stages (last300 tuples label/ms),
  __main__._aru_commit_stage_originals (restore only if current wrapper still
  wraps that original). Wrappers: patch_transfer.prepare_all, edit._reset_control_points,
  edit._dirty_shape_view, edit.prune_orphan_cvs_and_write,
  edit.RetopoGuideAccessor.write, PatchTool.rebuild.
  Accessor.write uses edit.__dict__ directly now (not old copied globals).
- Recent move commits: transfer0.275–0.282ms, reset_control_points12.8–14.4ms,
  hover_rebuild58–59ms nested in refresh, refresh213–214ms,
  write273–276ms, full release~288–292ms. Ordinary drag refresh itself~60–64ms.
  Cached hover rebuild9–10ms appears repeatedly on cursor moves.
- Likely next diagnostic: PatchTool.tick's QTimer can fire inside cmds.refresh,
  rebuilding hover and calling cmds.refresh(force=True) again. Consider a scoped
  redraw-depth guard to keep auxiliary timer work from recursively refreshing
  during committed-frame rendering, preserving forced click/hover correctness.
  This is a hypothesis from timings/source, NOT yet implemented or proven.
- Main private commit17565745152 bytes (~16.36GiB) at latest shell check; source
  update and independent tests did not reproduce the152GiB crash runaway.

## 2026-09-19: synchronous redraw guard and fast CP snapshots

- Previous goal turn classified as progress. Current turn implemented and verified
  two further latency changes; full current-scene confirmation16ms still unproven.
- curve_net_edit._VIEW_REFRESH_DEPTH + view_refresh_active scope synchronous
  _dirty_shape_view refresh with try/finally. PatchTool.tick skips auxiliary timer
  work during that scope, preserving force=True explicit click evaluation.
- tests/refresh_reentry.py tests suppressed nested timer, forced click path,
  nested render failures and return to normal updates. Added to latency suite.
- Live install mutates original unwrapped function __code__ IN PLACE for
  _dirty_shape_view and PatchTool.tick, keeping imported aliases and the QTimer's
  already-captured bound slot working. edit._VIEW_REFRESH_DEPTH initialized0;
  edit.view_refresh_active installed with edit.__dict__ globals and lightweight
  counter __main__._aru_refresh_guard_skips. Do not replace the class method alone
  and assume an existing Qt signal slot changes; it retains the old function.
- Actual no-edit frame test observed4 guarded nested timer calls across5 refreshes.
  No real user release has occurred since guard install yet; release sample array
  cleared at installation and remains empty. Do not claim real commit improvement.
- maya_data.double3_array_values reads one owned MPlug data handle and iterates
  MArrayDataHandle.outputValue. inputValue is explicitly INVALID for plug handles.
  Array wrapper is discarded and plug.destructHandle always runs in finally.
- Important discovered correctness condition: plug-level array snapshots do NOT
  evaluate dirty CHILD connections, even with evaluateNumElements. Helper scans
  MFnDependencyNode.getConnections and reads only connected array elements through
  element.child(axis).asDouble. Ordinary unconnected CP arrays retain fast path.
- _reset_control_points and prune_orphan_cvs_and_write now use this helper for
  read capture. Existing command-based writes, locked-channel fallback, Undo and
  sparse logical indices remain unchanged. Both original function __code__ values
  were hot-updated in place to preserve wrappers/aliases. maya_data module reloaded.
- Live current guide has1556 CPs. Old cmds snapshot~8.96ms; new helper initially
  0.60ms, final connected-aware helper over20 samples median0.287ms,max0.586ms.
  Every tuple matched cmds values. This is READ ONLY substage timing, not commit.
- tests/control_point_snapshot.py covers empty/sparse arrays, dirty child driver,
  locked reset, Undo/Redo; included in curve_latency_regression. Sequential
  Maya2027 and2024 latency suite + curve_edit_features all exit0 after final CP fix.
  Logs tests/snapshot_<test>_<year>.log. Standalone process session47847 finished.
- Unchanged-geometry live redraws still cost61–64ms. Temporarily measured rendering
  operations and restored all operations afterwards: base-only30.6–45.1ms,
  base+mesh foreground59.9–62.5ms, all3passes62.9–64.6ms. Full override restored.
  Temporarily tested Maya default renderer on modelPanel4 then restored exact
  override, with Undo recording preserved: samples40.9,28.8,250.2ms (outlier);
  retopo override median61.9ms. No scene geometry/selection/file changes.
- Therefore rendering itself currently exceeds16ms even without an edit. Next
  useful work: profile/reduce base rendering and mesh foreground pass overhead
  while preserving reference occlusion and original foreground requirements;
  inspect actual new releases when user edits again. Could compare plain refresh
  without explicit geometry dirty vs _dirty_shape_view, to isolate buffer uploads.
  Do not disable foreground or sacrifice actual visible result to claim16ms.

## 2026-09-19: ordinary guide drawing fallback

- Live guide xray=False, even though viewport_session active, GPU_CONTROLS=True,
  _gpu_world_guides=True. CPU fallback is therefore intentional; did NOT enable
  xray or alter user's depth/display setting to improve timing.
- curve_net_draw._cached_bezier_strips retains exact double precision MPointArray
  strips, invalidates on topology/count/sample-count or affected control position
  changes (including in-place position edits). Unchanged strips keep identity.
- Ordinary world-space control drawing now uses existing contiguous style batches
  through draw_controls(wrapped=False). Preserves EP-before-handle order, selected,
  mirrored and fixed manual-handle colors/sizes, hidden-handle selection behavior.
  Screen-space _ForegroundDraw legacy branch remains unchanged.
- Live installed helper and addUIDrawables function __code__ in place; gpu_guides
  reloaded and GPU_CONTROLS restored True. Existing registered override retained.
- Current scene unchanged-geometry dirty redraw seven samples:
  59.05(first),44.13,31.25,45.50,31.58,43.98,31.32 ms; warm median37.78 ms vs
  previous60.6-64.7 ms. This is redraw only, NOT full edited confirmation.
- cProfile addUIDrawables25ms ->8ms; _bezier_strips11ms eliminated on unchanged
  controls, cached helper~1ms. 613lineStrip calls remain~3ms, controls3ms through
  106points batches and tangent lineList. Native render overhead still remains.
- tests/ordinary_guide_draw.py added to latency regression: exact curve coordinates,
  changed-only strip replacement, topology change, invalid index, empty geometry,
  ordinary marker order/colors/sizes and hidden handles versus legacy branch.
- Actual live release samples remain empty since redraw-guard install; full16ms
  target unverified. Goal remains ACTIVE. No scene file saved or geometry edited.
- Sequential Maya2027 and2024 ordinary_guide_draw, gpu_control_batches and curve_latency_regression all exit0; session37605 completed. Scoped git diff --check passed.

## 2026-09-19: ordinary GPU curves and bounded patch-key cache

- Previous goal turn classified as progress. Goal remains ACTIVE, full edited
  confirmation16ms is not achieved or verified.
- gpu_guides.configure(enabled, foreground=True) now separates buffer use from
  Xray decoration. curve_net_draw.updateRenderItems enables world GPU curves
  whenever _gpu_world_guides is active; foreground=self._xray. Ordinary mode
  disables outline render item and GPU controls; controls retain contiguous UI
  batches/order from preceding fix. GPU session off retains CPU fallback.
- Tested temporary live candidate first and restored original functions before
  implementation. Current scene xray remains False. Before/candidate viewport
  images tests/ordinary_gpu_before.png and ordinary_gpu_candidate.png,2641x1597:
  mean absolute RGBA difference0.00606;923/4217677 pixels differ,124 have channel
  diff>80 (subpixel raster differences; not a claim of exact visual identity).
- Live source installed by replacing updateRenderItems.__code__ in place, reload
  gpu_guides then restore GPU_CONTROLS=True; no plugin unloading/re-registration.
  Seven unchanged-geometry redraws40.44(first),24.43,37.32,25.00,36.33,23.87,36.97ms;
  warm median30.66ms vs preceding37.78ms. These are ONLY redraw timings.
- ordinary_guide_draw now tests render-item switching foreground/ordinary/off,
  invalid owner, ordered controls. gpu_guide_buffers standalone test initially
  failed missing retopoGuideNode registration; added guides.load to test setup.
  Then sequential2027/2024 gpu_guide_buffers,curve_edit_features and latency
  regression all exit0(session93575 finished). No test process remains active.
- Existing saved-scene current_curve_preview_commit benchmark ran with inherited
  live Maya environment.190patches,3144vertices, older saved net than live613
  splines. Baseline warm release23.91/26.58ms; evaluation27.74/30.71ms;
  preview32.28/31.97ms,0candidates rebuilt. Not current live GUI confirmation.
- core.patch_key now delegates immutable walk tuple to bounded4096-entry LRU.
  Exact directed canonical JSON unchanged across rotation/grouping; ignores
  positions by design. tests/patch_key_cache covers random/repeated directed
  edges, list/tuple inputs, mutation, rotations, empty error and eviction cap.
  Included in latency regression;2027/2024 both exit0(session17225 finished).
  Core helper and patch_key installed live using AST, no full core reload.
- After cache, saved-scene warm release21.15/22.42ms, evaluation26.51/26.91ms,
  preview29.38/31.29ms. Run-to-run variation applies. cProfile JSON dumps947->3
  calls; patch_key no longer a leading cost. Before reports retained as
  tests/current_curve_preview_before_key_cache.json and _profile.txt.
  Latest __main__._aru_current_commit_job PID50916 confirmed exit0, previous50424
  alsoexit0. Latest profile/report under current_curve_preview_commit*.
- Next: full confirmation still requires release+evaluation+visible redraw; do
  not add the live redraw number to unrelated saved fixture as measured total.
  Saved profile remaining costs regions_native.regions3calls~14ms, patch transfer
 13ms, core.Plan8ms, fields.weights8ms, symmetry endpoint neighbor search7ms,
  subdivision4ms. Main live _aru_release_samples still empty. UI/scene unchanged.
- Scoped git diff --check passed. Unsaved recovery remains explicitly unnecessary.

## 2026-09-19: sparse paint coordinates and exact region result reuse

- Previous turn classified as progress; full16ms goal remains ACTIVE/unachieved.
- core.Plan.edit_coordinates(keys=None) now supports selective patch requests,
  retaining partial coordinates until full coordinates are needed. Full output
  remains in region_keys order. local_fields.coordinates accepts keys and skips
  untouched patches while preserving subdivision face offsets/count validation.
  local_fields.weights requests only fields' keys. ReducedPlan supports optional
  key filtering over its already constructed redistributed coordinates.
- regions_native.spline_aliases computes curve extent/tolerance only when another
  spline shares endpoint IDs; comparisons/tolerance unchanged for duplicates.
- tests/sparse_field_coordinates.py compares exact weights with old full-coordinate
  path: shared seams, partial/stale/empty paint, partial->full cache, n-gons at
  levels1-3, reduced plans, duplicate/reversed curved edges. Included in latency
  suite.2027/2024 latency +curve_edit_features all exit0(session6920 finished).
- Live installed function __code__/__defaults__ in place for core.Plan and
  ReducedPlan.edit_coordinates, local_fields.coordinates/weights, spline_aliases;
  retained imported aliases/classes. No plugin reload or user geometry changes.
- Instrumented saved-scene region call inputs in tests/current_region_reuse_probe.py
  (probe is diagnostic, NOT a timing benchmark). PID22208 confirmed exit0.
  Position/connectivity identical across transfer, plan and hover; transfer normal
  vectors DIFFER by up to0.5997459754 from plan normals. Plan and hover normals
  exactly equal. Therefore NEVER reuse regions based only on geometry/topology.
- regions_native._REGION_CACHE OrderedDict max4 entries caches immutable results
  keyed by exact packed positions, deduplicated controls, endpoint normals and
  source spline IDs. Normal callbacks and input validation still run on hits;
  native region allocation/walk/copy skipped. Return fresh outer/loop lists,
  immutable side tuples shared; callers cannot mutate cached grouping. Handles
  still destruct on every cache miss in finally. Exceptions are not cached.
- tests/region_input_cache.py covers hit, position/normal/connectivity invalidation,
  returned-list mutation, bounded eviction and malformed normals. Initial isolated
  test proxy lacked real ctypes restype initialization, causing pointer truncation
  in test only; fixed by priming real function signatures before proxying constructor.
  Main Maya unaffected. Final2027/2024 latency suite both exit0(session81323 done).
- Live initialized regions_native._REGION_CACHE=OrderedDict, replaced regions
  __code__ in place; core.regions is same object. Do not reload node plugins.
- New saved-scene benchmark tests/current_curve_preview_commit.py explicitly clears
  region cache before EACH edit, preventing repeated Undo/replay from overstating
  new-edit performance. Current job __main__._aru_current_commit_job PID53052 exit0.
  Warm release20.96/19.92ms, evaluation25.11/27.62ms, hover31.62/28.36ms. Cold first
  release56.29ms. This older saved scene has190patches/3144vertices/414->416splines,
  NOT live613-spline scene; no GUI draw included. Not evidence of full16ms.
- Earlier intermediate jobs49004 and52424 both exit0. Before sparse and before
  region cache reports retained under current_curve_preview_before_sparse* and
  current_curve_preview_before_region_cache*. Replay-cache report separate under
  current_curve_preview_replay_cache*. Probe profile uses current_region_probe_commit*.
- Profile field weights~8->4ms, regions3calls~14->11ms before region cache (cProfile
  only; total timings variable). Latest real release samples in main still empty.
  Next needs full edit evaluation and visible redraw; current redraw~24-37ms alone
  still exceeds16ms. Saved evaluation~25ms and auxiliary hover~30ms remain targets.
- Scoped git diff --check passed; no subprocess remains running at handoff.

## 2026-09-19: reference snapshot, symmetry lookup and real release samples

- Previous turn progress. Goal ACTIVE; actual user releases now provide stronger
  evidence and remain~160-260ms, NOT16ms. Do not rely on earlier empty sample state.
- symmetry_ops.mirrored_splines resolves object matrices once per invocation,
  mirrors endpoints/created handles with same Maya API1 point operations; explicit
  3D neighbor keys replace nested generators. Strict distance keeps Python sum
  of the same squared terms (important rounding), lowest-index tie unchanged.
  Backup tests/symmetry_ops_before_neighbor_fastpath.py.txt. Expanded existing
  patch_preview_latency with translation,rotation,nonuniformscale before all
  axes/spaces/create modes. Both2027/2024 pass including manual handles.
- maya_data.ReferenceMeshSnapshot owns immutable point/triangle tuples and one
  addNodeDirtyPlugCallback on generator referenceMesh INPUT. API docstring verified
  callback only reports input plugs. Cache revision invalidates only referenceMesh;
  balanced plug_handle copy on changes; never retains MDataHandle or MFnMesh refs.
  close removes callback and clears snapshot. PatchTool.__init__ owns it, stop
  closes it, rebuild uses it; unmanaged SimpleNamespace callers retain direct read.
- tests/reference_mesh_snapshot.py checks repeated reference vertex edits,
  transform, topology, reconnect, Undo/Redo, repeated stable reads and cleanup.
  patch_preview_latency now installs/closes snapshot in test to exercise cached
  surface invalidation against legacy geometry. Added to latency regression.
  Sequential2027/2024 latency+features all pass(session23575 done); transformed
  symmetry repeat2027/2024 pass(session94849 done). Scoped diff --check passed.
- Live class installed via AST in maya_data (no module reload). pc.ReferenceMeshSnapshot
  updated. Existing pc.PatchTool instance given snapshot; methods updated IN PLACE.
  Important __init__ uses super() and has __class__ closure: standalone method AST
  installation initially failed (no mutation of that method). Successful install
  compiled methods inside temporary plain class, checked co_freevars equality and
  assigned __code__ to original functions, retaining ORIGINAL __class__ closure.
  rebuild wrapper original accessed with inspect.unwrap, same for stop/init.
- Current live forced hover rebuild before reference cache29.44/30.44ms after warmup
  (first243ms outlier); after first28ms then18.35-21.68ms. Idle cached rebuild
  ~0.068-0.088ms vs previous~10ms. These are isolated hover timings, not commits.
  Saved detailed profile tests/current_hover_reference_cache_profile.txt.
- Actual user editing resumed while tools running. Before lazy edit read install,
  releases include161.65,162.45,196.58,165.04,164.11,198.37,261.06,178.68,176.81,
 184.01,186.58ms; one46ms operation and noops excluded from broad claims.
  Stage example write167.55ms, refresh113.24ms, transfer0.31ms, CP reset1.20ms.
  Main scene network changed with user edits; do not use old613 count as current.
- Captured ONE real release with cProfile then automatically restored existing
  release wrapper. __main__._aru_profiled_release stores timestamp/path and
  ms_with_profiling434.05ms (NOT normal latency). Text profile:
  tests/live_release_after_reference_cache_profile.txt.22classify_endpoints calls
 41ms,22_rebuild_curves19ms, patch transfer18ms, 2addUIDrawables11ms, etc.
  __main__._aru_capture_one wrapper no longer active (confirmed).
- Editing read path now RetopoGuideAccessor.read -> from_json(raw,lazy_objects=True),
  OWNED mutable data, not shared parse cache. from_json gained optional lazy_objects
  defaultFalse. Existing lazy classification skips repeated unchanged topology and
  builds EP/Handle wrappers on demand. No default behavior change to other callers.
- tests/edit_lazy_classification verifies eager parity, mutable ownership, wrappers,
  repeated classification skips, split with EXPLICIT classify (required existing
  contract), standalone EP. Initial test omitted classify after split and compared
  stale eager indices; fixed test contract, not production split behavior.
  Added to latency regression.2027/2024 latency+features all pass(session54628 done).
- Live from_json.__func__.__code__/__kwdefaults__ and accessor.read.__code__ installed
  in place after tests. __main__._aru_lazy_install_time and _aru_lazy_release_start=55
  record boundary for subsequent real samples. At install pc._active was None (user
  switched tool); real context still available. Therefore no assumption active hover
  exists now. Existing stopped instance should have closed snapshot via new stop.
- Next: inspect fresh real releases after lazy read; optionally one scoped profile.
  Actual release shows2addUIDrawables / high synchronous refresh; inspect exact call
  stacks before consolidating redraw. Need full current-scene edit+visible frame
  ~16ms, not microbenchmarks. No test processes running at handoff.

## 2026-09-19: native profiler identified expensive Attribute Editor JSON field

- Previous turn progress. Current live releases after lazy read were still~195-204ms;
  no16ms completion. Goal ACTIVE. Current scene is being edited by user; no fixed
  count assumption. Never restore an old fixture/net into the live scene.
- Scoped one-release command tracer proved ONE cmds.refresh call for regular curve
  commit, not duplicate refresh. Example309.13ms release: getAttr outNetData11.30ms,
  setAttr netData58.43ms, refresh189.84ms. tests/live_release_command_trace.json.
  All temporary cmds.setAttr/getAttr/refresh replacements automatically restored.
- setAttr-only cProfile showed almost no Python time despite58.41ms elapsed.
  tests/live_setattr_profile.txt. Additional one-release node-method wrappers:
  childChanged0.004ms, setDependentsDirty0.079ms, _getFinalPositions17.60ms.
  tests/live_release_node_trace.json. All class wrappers automatically restored.
- tests/string_write_probe.py in separate inherited-env Maya2027 saved scene:
  initially same-value writes~0.1ms (not useful change test). Revised to change a
  CV position and fully evaluate native output between writes, EM parallel:
  cmds.setAttr~0.31-0.36ms vs MDGModifier~0.14-0.24ms. Does NOT explain live58ms.
  Rejected unnecessary custom undo-command rewrite. Processes43056/43504 exit0.
- Live Maya command echo=False, script history writing=False. cmds.refresh has NO
  query flag; suspension query failed harmlessly, no suspend state was changed.
  MRenderer.setGeometryDrawDirty doc verified topologyChanged defaultsTrue; did not
  change it without correctness/performance evidence.
- Maya native profiler originally samplingFalse,eventCount0,buffer20MB. Captured one
  actual release218.95ms,2726events; returned samplingFalse and restored release hook.
  tests/live_release_maya_profile.json is NATIVE TAB-DELIMITED profiler format,
  despite unfortunate .json suffix. Event Duration is microsecond scale, confirmed
  event-span218920 matches218.95ms wall time. Nested durations must NOT be summed.
  Native summary tests/live_release_maya_summary.json:
    sendAttributeChangedMsg(aruRetopoGuideShape1)56.785ms
    QtPaint69.706ms (QtUpdateRequest70.007ms parent)
    VP2OverrideRender65.884ms; NativeCompute17.313ms; guideCompute10.964ms;
    render-list build21.668ms. Foreground extra passes only~1-2ms each.
- capture_maya_ui showed Attribute Editor displaying Net Data as a QLineEdit with
  huge JSON (live netData272697chars). This explained GUI-only notification/paint
  stall that batch reproduction lacked. Qt capture viewport area black is normal
  GL Qt-grab limitation; don't infer lost scene rendering from Qt screenshot.
- Production curve_net_node.initialize now sets aNetData tAttr.setHidden(True).
  Attribute remains storable/readable/writable, same name/type/data/Undo behavior;
  only automatic Attribute Editor text field removed. No tool settings hidden.
- Live applied om1.MFnAttribute(RetopoGuideNode.aNetData).setHidden(True) and
  cmds.refreshEditorTemplates(); NO plugin reload/unload. attributeQuery hidden=True.
  QApplication widget scan found NO QLineEdit with text length>10000 afterwards.
  tests/hidden_net_data.py verifies hidden netData, visible meshName/curveColor,
  edit/evaluation, Undo/Redo. Added to latency suite.2027/2024 latency+features all
  exit0(session64009 completed); scoped git diff --check passed.
- Release samples are capped100: len-based install indices stop working at100.
  Archived pre-hide data in __main__._aru_pre_hidden_release_archive, then cleared
  existing __main__._aru_release_samples IN PLACE for fresh post-hide samples.
  Many real post-hide releases~84.5-92.4ms. Slower operations188.5/376.5/180.2ms
  also exist. Do not claim all edits are90ms or16ms. Current _aru_release_samples
  contains only post-hide samples, including one native-profiled145.4ms sample.
- Captured another actual release145.40ms,2781events after hide; saved separately as
  tests/live_release_hidden_data.mayaProfile. Before profiler data preserved on disk;
  reset only our own records after checking eventCount and samplingFalse.
  __main__._aru_hidden_native_profile stores report. Release hook auto-restored;
  profiler samplingFalse after capture. Native before/after analysis artifact:
  tests/live_hidden_data_native_comparison.json.
  After: no attribute notification >0.1ms; longest QtPaint0.224ms (others<.034ms).
  Confirms UI bottleneck removed. Native render81.4ms on this different edit,
  planCompute29.38ms; render-list build22.57ms, plugin per-frame update47.44ms.
- Next focus: actual mesh/guide evaluation and render-list construction. Regular
  curve release refresh is ONE call; don't remove required frame based on earlier
  two addUIDrawables counts. Keep16ms full current-scene edit+visible result goal.
  No active test processes or profiling wrappers remain. Retain lightweight release
  timing and stage wrappers. No scene data saved or overwritten.

## 2026-09-19: final-position bounding calculation uses owned CP snapshot

- Replaced _computeFinalPositions API1 per-element/child plug reads with existing
  maya_data.double3_array_values API2 owned snapshot. Resolve full DAG path (safe
  with duplicate short names). Keep exact 1e-9 cutoff, out-of-range filtering and
  all surface-bind/deformer/sculpt/handle propagation logic unchanged.
- tests/final_position_snapshot.py compares result against legacy plug reader,
  including live connected EP changes, manual handle, sparse/out-of-range CP and
  Undo/Redo. API1 MFnDependencyNode.userNode gives MPxNode wrapper (not Python
  subclass), so test uses a shim with real node MObject + decoded netData and runs
  the actual unbound production method. Initial test harness AttributeError fixed.
- Maya2027 and2024 final_position_snapshot, curve_latency_regression and
  curve_edit_features all pass sequentially (session77559 finished exit0).
  Logs tests/final_snapshot_<test>_<year>.log. Added new test to latency suite after
  both independently passed. Scoped git diff --check passed.
- Live checked mouse up, compiled only changed method AST, compared OLD and NEW
  against current2349CVscene without writes. Exact position equality. Legacy
  15.89-17.45ms versus snapshot1.58-2.61ms (seven samples each). Only this stage.
  Installed __code__ in place, imported nd.double3_array_values, no plugin reload.
  __main__._aru_final_position_snapshot_report retains timings/equality/count.
- Archived samples to __main__._aru_pre_final_snapshot_samples and cleared existing
  _aru_release_samples in place after install. Fresh actual releases69.95,69.27,
  68.65,76.38ms (exclude .03ms noops). Previous recent ordinary releases86-94ms.
  Current regular refresh samples51-55ms. Full16ms target NOT reached; goalACTIVE.
- No active test process or temporary profiling wrapper. User scene never saved or
  replaced. Read native evaluation path next: _computeOutNetData/_readControlPointDeltas,
  and plan evaluation. outPositions includes editPreviewPositions whereas direct
  _computeFinalPositions does not; don't blindly alias those semantic paths.
- Earlier native render-list build~22ms included _getFinalPositions~17ms, likely
  improved by this fix, but new native profile required to prove exact attribution.

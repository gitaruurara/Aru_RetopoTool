# Performance investigation — 2026-09-17

Goal remains active: sustain 60fps while editing larger curve networks and retopo meshes, not only idle redraw.
Current live scene: aruRetopoGenerator1, 22 regions, 1456 quads, 1485 vertices; Maya 2027.
Measurements used perf_counter around cmds.refresh(force=True), with cProfile for bottlenecks.
Camera and control-point probes restored original values in finally blocks. They did not change subdivision settings.

Baseline static refresh: 12 samples 58.9–62.8 ms. Overlay prepareForDraw used 0.660s total / 12 frames, 59472 closestIntersection calls.
Implemented standalone display.cpp batched BVH visibility and per-camera DrawData cache; added bin/aru_retopo_display.dll, build script/CMake support.
After warmup static refresh typically 6–8 ms; occasional spikes up to 22.8 ms. Cache used to be discarded every frame by oldData handling.
24 camera-orbit refresh probes: median 8.654 ms, range 5.088–27.571 ms. Not a sustained 60fps pass.
8 control-point deformation probes: 62.45–67.28 ms. Remaining major costs per frame: native.Surface.relax ~21ms, core.Plan.evaluate ~14ms, rebuilding wire BVH ~6ms, guide drawing ~5ms.
Native visibility parity test: outer/inner cubes, perspective + orthographic; exact match with old Maya ray implementation. All Maya smoke tests passed 2024 and 2027.

Next work:
- Surface::project currently starts nearest-point search at infinite distance even with a valid previous triangle seed. Use the seed triangle as an initial upper bound, preserving guard semantics.
- core.Plan.evaluate is a linear map from guide CVs (fixed per-side parametrization). Compile subdivision/guide/Coons coefficients once per topology; evaluate in one cached native stencil call.
- Avoid rebuilding wire BVH on every deformation; refit tree/topology caching, packed buffers.
- patch_context timer rereads reference geometry and creates all patch candidates after guide changes. Profile real hover/drag event-loop work and optimize invalidation and picking.
- Test dense scenes and real editing/frame-time percentiles before marking goal complete.

Existing uncommitted changes from preceding tasks (patch_transfer.py and foreground guide drawing) must be preserved.


## Continuation: exact compiled stencils and parallel projection

Previous goal turn: progress (measured bottleneck, native visibility implementation and parity tests).
- core.Plan.compile_stencil now composes subdivision + guide constraints + Coons coefficients once; CompiledStencil retains ctypes buffers. Hot topology plans use one native stencil per evaluation. Pure Python reference evaluation remains for parity checks.
- Seeded closest-triangle candidate initializes the BVH bound. Alone this did not substantially reduce projection time.
- Core ABI 3 (bin/aru_retopo_core_v3.dll): OpenMP 4 workers for >=512 vertices; pinned guide vertices reuse their already projected targets during relax. CMake + Windows build updated. v2 DLL is a superseded profiling artifact, ignored; live process may still have it loaded, do not delete a loaded DLL.
- Native loader no longer calls maya.cmds.about from DG evaluation; command-thread errors during first hot-load were diagnosed and excluded from timings.
- Correct-output deformation after compiled stencil: ~44–48 ms (old ~64 ms), output valid 1456 quads.
- After parallel relax: 16 mutation+refresh probes 30.086–38.727 ms. Final restore status reported a 133.6ms DG spike, so latency/outliers still need investigation. Do NOT claim 60fps.
- patch_context now filters unrelated Qt events early, tracks generator dirty revisions, and skips unchanged hover work. Current live PatchTool updated and timer active. Geometry invalidation/real event-loop timing needs dedicated broader tests.
- New compiled stencil parity tests: triangle/quad/pentagon/octagon, levels1–3, three random CV motions, max error <1e-10; 11 core unit tests passed.
- Full Maya smoke suites passed 2024 and 2027 after ABI3 and hover changes.

Next: profile current correct-output deformation again; reduce wire BVH rebuild cost (topology refit), guide draw call count/screen projection work; investigate OpenMP scheduling spikes and actual interactive context route fitting. Test denser networks and sustained event-loop work. Goal remains active. No push yet.

## Continuation: requested 500 patches / ~50k polygons

User confirmed target500patches/50k polygons. Deterministic honeycomb fixture in tests/dense_performance.py has500regions,46528quads,46873vertices,1589guides on sphere. Local one-CV motion only; not yet broad multi-guide drag or denseviewport benchmark.
- Baseline warmed evaluate~11ms + relax~204ms (dense_baseline.json).
- ABI4 caches each iteration's projection only for EXACT query xyz + incoming seed + guard; dimensions/iteration/guard reset cache. Deformation/strength/guideweight/seeds parity against freshSurface tested >512vertices including OpenMP, output<1e-12 and identical seeds.
- PackedPoints retains native stencil results through relax; adjacency/guideweight ctypes arrays cached per immutablePlan. Detached buffer owns output, retained results cannot be overwritten by subsequent evaluations.
- Current dense warmed evaluate3.2–3.5ms + relax15.5–16ms (~19ms total), first warm transition47ms then19ms. Topology389ms + first compiled evaluation414ms + initial relax220ms remain. Rendering/DG meshcreation excluded: NOT60fps pass. See dense_cached.json.
- Standalone runner now uninitializes Maya before os._exit; parity+benchmark exits clean0.
- display_v2 refits BVH for unchanged triangulation; deformed refit equals freshBVH in perspective and ortho. Foreground guide lines batch projected numpy coordinates + lineList.
- Critical interactive finding: camera.isOrtho is a METHOD. Passing method object caused int(ortho) exception, silently missing ALL retopoedges. Fixed to camera.isOrtho(). Earlier live measurements with absent edges are INVALID for completed rendering. Live draw module hotpatched and caches reset; capture confirms surface, edges, outlined guides,EPs present.
- Correct-output 22patch live CP-mutation+refresh16samples26–33.6ms, median29.336ms after warmup; generator status7.4ms. Still not60fps. User geometry restored finally.
- Maya2024+2027 smoke suites passed ABI4+PackedPoints;11 coretests passed. Added refit test passed live after suites. Need add direct draw.prepareForDraw test to catch API-call errors automatically; viewport callbacks aren't exercised in standalone smoke currently.
- README, CMake,build_windows name core_v4/display_v2. Superseded v3/displayv1 ignored but left on disk (loaded olderDLLs). Latest versions loaded live.

Next: direct draw integration regression, profile correct-output draw + actual edit context; dense viewport and multi-guide gestures. Most remaining dense compute time is Python unpack/seed packing, plus fullvertex loops. Consider native point buffers to Maya bulk mesh upload and topology caching. Do not count missing edges or reduced quality as performance success. Goal active, no push.

## Continuation: correct draw profile and GPU direction

Previous turn classified progress (ABI4, dense fixture, exact parity and camera.isOrtho fix). Current turn also progress.
- display ABI filename v3: merge consecutive visible subsegments per edge after unchanged 4-sample occlusion test. Legacy aru_wire_visible preserved for exact reference tests; compact export used by Draw. MPointArray now accepts tuple list directly, eliminates Python MPoint-per-endpoint allocations. Test checks original exact equality, compact total length + coverage of every original endpoint, refit equality.
- Correct live22patch frame median23.04ms after compactwire, but one156ms spike among16; still NOT60fps. Earlier29.34ms before compact. Live displayv3 loaded, edges included.
- tests/display.prepare_probe invokes actual Draw.prepareForDraw with mesh+camera in disposable process, catches camera API errors now. It runs in smoke suite. Maya2024 passed this integration +compact; Maya2027 passed after additional mesh topology reuse below.
- Dense fixture now measures Maya transfer and real draw callback (no GPUrender): meshcreation32.35ms, COLD prepareForDraw671–935ms, calculation~18.7ms. tests/dense_draw.json. Cold includes edge graph/BVH/normal collection/outputarrays; NOT per-drag warm timing. Need profile warm refit + orbit + idle separately at500patches, and actual GPU frame time.
- User asked whether GPU is used. Answered: CPUC++ projection/relax4threads, GPU currently only Maya viewport; generation isn'tGPU. Next direction GPU depth/vertexbuffer rendering, preserving foreground and hidden-back-edge behavior.
- Autodesk official MRenderItem docs support cached vertex/index buffers via SubSceneOverride; depthPriority only biases depth, not unrestricted foreground drawing. Cannot simply replace xray and claim buried geometry fixed. Need prototype separate surface+wire pass/depth handling; investigate local Maya2024/2027 devkit/includes/libs, all present2027.
- Mesh topology transfer optimization measured isolated50kquad mesh: MFnMesh.create~7ms vs copyTemplate+setPoints~2ms (prepacked MPointArray). Plugin now private template perPlan, copy into freshDG output then setPoints, never mutates prior output. MPointArray(generated) avoids individual MPoint allocation (~20ms vs34ms for50kpoints). Maya2027 suite passed. This plugin change NOT hotloaded into live scene yet;2024 needs rerun after pluginchange.
- Latest code core_v4/display_v3; CMake/PS1/README aligned. Olderdisplayv2 ignored left on disk. No push. Goal active, not blocked.

## Continuation: dense warm profiling and GPU foreground prototype

Previous turn classified progress (compact wire, integration callback regression, mesh template). This turn progress, no blocker.
- tests/display.prepare_probe(detailed=True) now tests cold, idle, orbit and deformation with cProfile. Restores camera transformation + meshpoints. Fixed MFnTransform world-space path binding in runner.
- 500patch CPU draw: idle22ms (full tuple reconstruction), orbit333–335ms, deformation393–396ms; native visibility245ms inclunpack, update27ms. tests/dense_draw_profile.json. These are callback times without finalGPU rendering. Clear evidence CPU ray/point transfer must leave interactive draw path.
- New opt-in gpu_preview.py experiment: MRenderOverride base fullscene pass, foreground MSceneRender filtered to retopo outputs/guides/overlay, depth-only clear, shaded|wireframe standard Maya GPU rendering, HUD/present. Native meshes' alwaysDrawOnTop temporarily false, CPUoverlay enabledfalse. Restores attributes + viewport override on disable.
- Tested in user's current22patch scene Maya2027. InitialGPU frame had blackbackground and rearwire through opening. Fixed baseclear.setOverridesColors(False), foregroundculling kCullBackFaces and mesh.backfaceCulling=3. Approvedcapture now shows background restored, foregroundfaces/edges and guides/EPs, no rearwire visible through opening. Wire remains brightyellow/white instead of dark desired; RGB override attempt ineffective in combined render mode. Need solve color + selection/interaction behavior, panelisolation/multipleoutput/freshscene lifecycle before production integration.
- GPU initial20 CP+refresh samples warm17–23ms median19.834ms, no denseGPU test yet. This is not60fps. Exact display parity not fully established; e.g concave/overlapping patches, shape selection and patchhover still need tests.
- Auto-review rejected capture once due sensitive-scene-image export authorization. User explicitly approved currentviewport capture in async reply. Subsequent toolcaptures permitted and visualchecks done. Do NOT ask again for same scope. No outstanding approval blocker.
- Prototype module hotreload lost registeredPythonobject after findRenderOverride basewrapper; deregister basewrapper failed. Registered second runtimeNAME aruRetopoGPUPreview2 instead. Current prototype variable _override ownsPreview2. Both old registrations may persist untilMaya exit, neither active now. Avoid reloading without retaining Pythonreference. File now preserves _override/_saved dicts withglobals().get acrossreload. FiledefaultNAME remains aruRetopoGPUPreview (newMaya process fine). For live useexistingPreview2 instance.
- Finally gpu_preview.disable() restored panel4 override empty and allattributevalues; pending_attributes0. User scene ordinaryCPUdisplay restored. No defaultGPU mode or automaticstartup added yet.

Next: denseGPU benchmark in temporary restored scene, improveguide drawing/meshtransfer, solve wirecolor and inputselection+hover; integrate optionalGPUpreview only after validating fullbehavior.500patch sustained60fps remains goal; notcomplete. Nativecorev4/displayv3, no push.


## Crash recovery and lifecycle correction

Previous turn: progress (live_dense harness, crash identified, recovery copied), not successful benchmark. Live benchmark call356 timedout300s. Calls360/364 terminated after authoritative Maya crash dialog; no live jobs remain. No denseFPS results were produced.
- User prompted checking dialogs; ComputerUse UIA revealed Maya stopped/crash recovery dialog. Process Responding=True and risingCPU were misleading. Always check independent UI on long Maya hangs.
- Recovery saved C:/Users/aruur/AppData/Local/Temp/無題[回復-aruur.2026-09-17-14.39].ma and copied D:/Dropbox/App/.codex/recovery/retopo-20260917/maya-recovered.ma SHA256 E7CAD29DF5C79DDDE5612ECEFE10EC62340FC798C9D53388833DC618EA1D6812. Contains both user nodes and aruRetopoPerfTest namespace; test cleanup never finished. Keep originalcopy immutable, remove only benchmarknamespace after safe reopen. Camera/selection/modified restoration not proven.
- Minidump MayaCrashLog260917.1439.dmp parsed in node_repl. Exception C0000005 address7fffabd2d5ac = OpenMayaRender.dll RVA6d5ac. PE export startOperationIterator@MRenderOverride starts6d590, supportedDrawAPIs starts6d5c0. Crash lies inside native base startOperationIterator. Strong evidence for orphan override lifetime/hotreload path, not proof dense computation caused crash.
- gpu_preview.py now uses stored registered name (not current reloaded class NAME), deregisters originalPythoninstance on disable, only clears references AFTER deregistration succeeds. Never substitute findRenderOverride basewrapper. Existing globals persist acrossreload.
- tests/test_gpu_lifecycle.py uses weak registry to simulate non-owning native registration:20 enable/reload/NAMEchange/enable/disable cycles assert originalowner survives reload, viewportname stays registeredname, registry empty and owner collected afterdisable. Pass. This test is Pythonownership contract, NOT actualGPU/Maya validation.
- Actual mayapy lifecycle test attempted twice via node child_process (normal exec helper broken); both timed out30s in maya.standalone.initialize and owned testchildren terminated by timeout. second emitted starting isolatedMaya only, noinitialized marker. No native lifecycle validation yet.
- exec_command AND apply_patch are failing immediately with sandbox helper_unknown_error setup refresh had errors (infrastructurefailure, not policy denial). Node_repl fs + child_process are working for non-UI file/test operations.
- User was asked async to press Maya crash dialog Reopen because ComputerUse click failed coordinate input geometry unavailable; Tab had no effect. No reply yet. Do not falselyclaim restart completed. Screenshot returned unrelated passkeypermission screen while UIA was Maya; never act on this securitydialog. Current Maya remainscrashed until userreopens.
- node_repl retains fs,cp,root,crash buffer,PE parsedvariables; Sky apps/windows available but refresh beforeanyinput. Skills computeruse guidance+api+confirmations alreadyread. No GPU autostart. Goal active, no push. Need realMaya2024/2027 validation + clean500patch rerun and actual60fps beforecompletion.

## Recovery resumed 2026-09-17 15:12
- User explicitly authorized killing crashed Maya and starting new Maya; old PID35816 stopped, new Maya2027 PID22124 started via requested launcher. MCP command permission allowed with user authorization.
- Normal exec/apply_patch sandbox helper fails; escalated exec works. Actual isolated Maya2027 register/deregister 20-cycle lifecycle test passed. New struct.iter_unpack native buffer conversion and 15 unit tests passed in preceding continuation. Maya2024 full smoke now passed after mesh template and unpack changes (exit0).
- Read-only MCP proved new scene empty, unmodified, only four cameras. Opened immutable recovery copy WITHOUT force, executeScriptNodes=False. Initial force-open plus namespace deletion rejected by auto-review; neither executed.
- Recovered scene includes both original and benchmark nodes. Individual MCP hide command succeeded: only three benchmark root transforms hidden, original aruRetopoGuideShape1 fit in persp, selection cleared. No deletion or save; backup remains unchanged.
- Recovery UI has unsupported-nodes/read-error dialog and nested Python security prompts. Do NOT claim full recovery validated. Camera and original mesh display require further check after modals close.
- ComputerUse individually allowed observed MCP exec (hide code), standard contextlib/io imports and frame-inspection compile calls. Broad file-wide builtin trust checkbox rejected, unchanged. Later __main__ import allow also rejected because recovery-derived code identity unknown. No workaround. Asked async explicit permission for THIS recovery file Python loading, pending user reply. Current modal __main__ plus unsupported-node dialog remain. No further Maya MCP jobs pending; cell421 returned success.
- Sky window id265156; refresh state before action. Two old Autodesk error reporting windows also exist; do not transmit reports. Current Maya not shown crashed.
- Dense 500patch/50k real GPU FPS still unmeasured; goal active, no push, GPU prototype not production default.

## Dense GPU measurement and guide transfer 2026-09-17 15:58
- Previous turn progress: recovery hide succeeded, Maya2024 smoke. This turn progress: recovery permission resolved by explicit user `すべて読み込み許可して良いです`; all current modals closed. Repeated __main__ prompts individually allowed. No file-wide trust setting changed. Unknown node list empty; original generator22patch/1456faces and dense500/46528 outputs evaluated.
- New Maya GPU Preview registered/rendered/released successfully without crash. Current gp._override=None, modelPanel4 rendererOverrideName empty. gp._perf_state camera/selection/root visibility restored; benchmark3roots hidden, original1456faces retained. Recovery file not saved or altered.
- GPU dense visible image verified: turquoise surface, yellow wire, all guide markers, sphere background. Static refresh~3.6-6ms but camera-stale guide draw makes orbit INVALID until fixed. Mesh transform viewFit includes overlay locator default[-1,1] boundingbox at worldorigin, framing1000offset mesh incorrectly. Use exact meshSHAPE bounds or explicitcamera, not parent viewFit. Setcamera1000,9,4 rotate-65,0,0 and setGeometryDrawDirty on guides fixed visual framing for measurements.
- First valid dense deformation16samples227-237ms, periodic325-336ms. tests/dense_gpu_live.json. Profile tests/dense_gpu_profile.txt shows addUIDrawables192ms, wrapperflush128ms, Bezier26ms. GPU alone is NOT sufficient.
- curve_net_draw._ForegroundDraw now MPointArray from tuplelist in one call instead of MPoint-per-point:~187-193ms. Tested einsum instead of matmul no improvement; reverted.
- _bezier_strips(raw=True) returns numpyarrays when screen-space ForegroundDraw active. Flush consumes raw strips directly, removing MPointArray->MPoint->tuples roundtrip. Native worldspace/fallback retains old path. Deform afterchange typical154.7-160.5ms with260-275ms spikes. Updated live methods only via extracted AST (no plugin or GPUoverride reload). Latest source methods active in live.
- New foreground_projection.py regression compares rawbatch vs scalar MayaMPoint reference at identical24subdivisions, viewportoffset, projectionmatrix, clipping, outline+color strokes within1e-9. Full smoke suites passed2024+2027 afterchange.
- Latest profile: addUIDrawables~106ms inclflush67ms; intermittent _getSurfaceBindData105ms on trivial inputValue suggests GC/scheduling attribution, not enough evidence for bind algorithm change. Need profile allocations/GC, points batches, native buffer upload; do not optimize bogus attributed timer blindly.
- IMPORTANT unresolved correctness: screen-space guides cached by GeometryOverride don't automatically follow camera. Explicit setGeometryDrawDirty fixed capture, but realorbit must fix (likely worldspace GPU guide render items or proper camera-driven dirty) beforeclaiming60fps. DenseFPS activecontext drag/routefit notmeasured; CP mutation-only test is lowerbound. Wire color still yellow; must restore darkedge parity.
- Standalone dense_unpack.json: compiled evaluation2.6ms +relax12-14.8ms warmed; CPU draworbit~320ms/deform~380ms. GPUperformance effort remainsnecessary.
- One MCP action rejected because approval-review usage exhausted; fresh get_usage_limits subsequently ordinaryUsageAllowed true /0%used then same action passed. No current approval blocker/jobs. Goal active, NOT60fps, no push.

## GPU guide buffers and evaluated positions 2026-09-17 16:11
- Previous turn progress (raw guide transfer / tests). This turn progress, actual new renderer path and camera-follow evidence; NOT60fps.
- gpu_preview now base + retopo surface/wire depthclear + guide-only depthclear + HUD/present. _set_world_guides updates module flag and marks all guides dirty at mode transitions. _WorldForegroundDraw emits worldspace outlined lines and batches contiguous equal-color/size points via manager.points. Camera translation capture1000,9,4 ->1000,10,5 confirms guides follow mesh without manually dirtying guide (screen-space prior version stayed stale).
- Experimental gpu_guides.py configures two stock k3dThickLineShader renderitems outline/color, shared curve indexbuffer, float32 vertexbuffer concatenatedCP+Bezier samples uploaded via ctypes.memmove. Keeps exact24segments percurve. addUIDrawables omits curves ONLYwhen GPUcurveactive; handles/EPs/previews remain. Stockshader lineWidth float2 usage checked official Autodesk apiMeshGeometryOverride example. Curve selectionMask kSelectNurbsCurves needs real-context selection validation, not production claim.
- Important limitation: _gpu_world_guides is global to loaded drawmodule; simultaneous normal panels with GPU panel not validated. Opt-in experiment only, not UI/default mode. Normal mode still screen-space guidecamera issue; world fix presentlyGPUonly. Guide pass and surface separate verifiedsmall+dense screenshots; rear guide visibility as originalforeground intent, rear meshwire hidden. Meshwire remainsyellow notdark.
- Performance after GPUcurves initially~170-180ms vs rawUI155ms (GPUbuffer/rebuild cost offsets Python savings). Batchedmarkers addUIDrawables~32ms vs prior100ms, curvebufferpopulate5ms. UIupdateDG was35ms with12816MPlug.asDoublecalls.
- draw.updateDG now reads canonical evaluated outNetData and caches parsed RetopoGuideData, removing duplicated surface/deformer/sculpt/CP calculations; preservesmetadatafromnetData. Latest typicaldeform144-155ms, spikes~285ms. Need fullbind/deformer draw-position parity tests beyondrestCP; smoke existing sculpt tests do not exercise draw for allbindstates.
- tests/gpu_guide_buffers.py validates GPU indices produce same curve segments tofloat32tol and CPselectionprefix, direct actualGeometryOverride.updateDG matchesoutNetData after3CPedits. FullMaya2024+2027 smoke passed. MockGPUlifecycle20cycles passed. Actualinteractive registration/disable succeeded.
- Renderer device: RTX5060 8GB, OpenGL4.6 driver591.86. Notsoftwarefallback.
- Strong GC evidence now tests/dense_gpu_gc.json: local watcher added thenremoved in finally; gen2collections135/143/180ms matchspikes. Typical DG63-75ms +refresh82-89ms. NoGCpolicychanged. Reduceallocation/retainedobjectcounts; do not globallydisableGC as finalsolution. Output file containsallGCdurations, summarize rather than dumping.
- New measurement files dense_gpu_world.json, dense_gpu_buffers.json (prelatestDGsharing), dense_gpu_gc.json. No successful60FPS/livecontextgesture test yet.
- Finally restored currentturnsavedcamera/selection/rootvisibility; test3roots hidden; original1456faces present. SmallGPUcapture showsfacewire+outlinedguide+markers. gp.disable restorednormalrenderer, d._gpu_world_guidesFalse, gpownerreleasedTrue. NoactiveMCPjobs/permissions. No save/push. Keepimmutable recoverycopy.

## GPU control batching and compact plan validation 2026-09-17
- Previous goal turn made progress: enabled GPU preview in the user's currently focused modelPanel4, verified rendererOverrideName=aruRetopoGPUPreview and _gpu_world_guides=True. User is actively trying it; do not change camera/scene while they work.
- Normal screen-space guide camera invalidation is still unresolved. GPU mode remains enabled for user testing. No live module reload this turn; live GPU is the version preceding draw_controls/seed/compact-plan changes.
- Validated prior compact Plan arrays and retained native projection seeds with full Maya2024/2027 smoke suites. Native seed comparison with compact Plan, 500 patches/46873 vertices: list median13.707ms versus native8.051ms, exact output points and seed IDs agree. Relax-only timing, not frame time. tests/native_seed_compact_comparison.json.
- New gpu_guides.draw_controls submits raw-coordinate tangent line arrays and contiguous marker-style runs. Avoids per-point MPoint/MColor/manager calls while retaining EP-before-handle order, overlap ordering, selection/mirror/manual handle colors and sizes, hidden handles except selected. Ordinary path retained unchanged. addUIDrawables dispatches here only for _WorldForegroundDraw.
- New tests/gpu_control_batches.py extracts the retained ordinary control branch as an independent execution oracle, runs it through the world wrapper, compares flattened emitted primitives/styles/order against batches. Full dense1589-guide fixture, handles shown/hidden, selected/mirrored/manual states. Recording disabled for timing; real MPointArray conversions and wrapper execute but draw manager is a recorder, NOT GPU raster timing.
- Separate Maya2027 preparation comparison:18.397ms ->5.084ms; tests/gpu_control_batch_comparison.json. Full smoke after change passed2024 and2027 (logs smoke_gpu_controls_2024.log /2027.log). Concurrent smoke timings not used for primary performance claim.
- No scene changes, screenshot, restart, save or push this turn. GPU preview stays enabled. Goal remains active: latest actual dense edit+refresh baseline144-155ms, 60fps not achieved or newly measured. Real-context drag and latest drawing raster verification still required, plus ordinary-mode camera invalidation/multi-panel correctness.

## Fresh Maya after user-reported edit crash 2026-09-17
- Previous turn progress: GPU control batching + exact primitive/style parity, smoke2024/2027. This turn progress: actual DG benchmark, fresh GUI render/edit/lifecycle evidence, eliminated unnecessary evaluated-network classification from draw.updateDG.
- User reported crash while editing curves/points (not scene switch). Prior Maya process absent; latest dump %TEMP%/MayaCrashLog260917.1621.dmp. Local minidump exception0xc0000005, execute violation(operation8), address0x7fffc7def1f0, module python313.dll+0x62f1f0, thread41236. This is NOT a root-cause identification or fixed-crash claim. No crash reports uploaded.
- Launched fresh Maya2027 using authorized DCC/bat/luncher/maya.bat --2027. PID2960, initially unnamed/unmodified verified via MCP. First execute request delayed several minutes; process responsive, TCP50007 established. Sky repeatedly failed 'foreground window did not report a process id', even activation; user reported Maya displaying normally. Original pending MCP cell545 subsequently succeeded, no restart/bypass. No pending calls now.
- Created fresh synthetic scene (not recovered user's scene): gpuTestGuideShape, gpuTestReference, aruRetopoMesh1, aruRetopoGenerator1. Initially20patch1600quads; GPUenabled modelPanel4. Screenshot confirms turquoise shaded surface, yellowish edges, outlined guide/EPmarkers. Latest point batching code loaded at fresh startup, no hotreload. 60CPupdates plus cameraY changes and periodic gc.collect completed, median31.24ms/max44.48ms. This is scriptedCP editing, not full context mouse gestures.
- Changed same owned fixture to500patch46528quads, relaxIterations5. 24edits after4warmups median211.389ms/max376.396ms. tests/dense_gpu_fresh.json. Profile tests/dense_gpu_fresh_profile.txt: addUIDrawables28ms, updateDG15ms, full evaluated RetopoGuideData parsing32ms per miss/classification16ms, _out_json includes GC spike. Prior144-155ms baseline was older live/hotpatched/recovered configuration; do not claim an apples-to-apples regression cause from these numbers.
- 5 actual GPU disable/gc/enable cycles plus CPedit+refresh completed without crash on500fixture. Renderer stays aruRetopoGPUPreview on modelPanel4; fixture stays500patches. No save, no restored user file, immutable previous recovery remains untouched. Actual context gestures and crash reproduction still required.
- New tests/dense_dg_performance.py creates true guide->generator DG in disposable mayapy. 500patch46528quads46873vertices, median50.974ms CPedit+outMesh evaluation without raster (tests/dense_dg_before.json). Transfer alternatives tested at46873 vertices: tuple unpack+MPointArray20.17ms, numpy.tolist21.52ms, numpy direct35.03ms; no alternative adopted, no performance claim from rejected options.
- New on-disk-only draw.updateDG reads evaluated JSON positions directly, preserving cached rest metadata; avoids building/classifying full RetopoGuideData just for coordinates. Full smoke2024/2027 passed (smoke_draw_positions_VERSION.log), including actual override positions==outNetData and exactGPUcontrol parity. This last edit is NOT loaded in current GUI to avoid live registered callback changes during crash isolation.
- Goal remains active, NOT60fps. No new owner/lifetime fix proven. Next: fresh-load last draw change and real context edit crash reproduction; remove serialization/transfer bottlenecks, ordinary-mode camera invalidation, multi-panel/mode fidelity.

## Typed guide coordinates 2026-09-17
- Previous turn progress: fresh Maya creation/render/edit/cycle checks and direct-position parsing change. This turn progress: removed JSON serialization from new guide->mesh / draw coordinate evaluation path, tests and dense DG measurement.
- retopoGuideNode.outPositions is a nonstorable/nonwritable double-array output (xyz triples), computed by the same _computeOutNetData algorithm with positions_only=True; JSON output remains unchanged and independently dirty. API1 MScriptUtil owns temporary double storage while MDoubleArray/MFnDoubleArrayData copy it. All existing inputs affecting outNetData also affect outPositions, including inherited CP explicit dirty propagation and restore-attribute mapping.
- Generator optional guideRestData(string)+guidePositions(double array) use typed coordinates and cache rest JSON; legacy guideData remains connected to outNetData for all existing editor/context consumers. New maya_api.create connects optional typed inputs only when both loaded node schemas support them. Existing saved nodes with no new connections fall back to their original JSON behavior. No automatic mutation/migration of existing scenes.
- Draw updateDG uses outPositions where available, JSON fallback on older loaded guide schemas. No endpoint classification of evaluated positions; metadata still comes from cached rest netData.
- New tests/typed_positions.py compares exact typed triples against old JSON after CP edits, deformer input, sculptFalloff/sculptPose/poseFalloff dirty changes, surface binding and driver vertex mutation, empty netData then restoration. Also compares complete modern and disconnected-typed legacy generator mesh coordinates exactly across5edits. These exercise relevant data paths, not full mouse gestures. Added to smoke; full2024/2027 suites passed (smoke_typed_positions_VERSION.log), including save/reopen and GPU controls parity.
- Actual500patch46528quad/46873vertex DG-only benchmark median45.746ms versus previous50.974ms in separate process; tests/dense_dg_typed.json and dense_dg_before.json. Process scheduling/GC variation applies; this is not a controlled same-process A/B FPS claim. Profile confirms JSON serialization absent on warm typed DG path. Full viewport remains unmeasured for this change.
- Current GUI PID2960 remains previous-schema500patch test scene, GPUenabled modelPanel4, unchanged this turn. No live registered-plugin reload, restart, scene save or push. Latest GUI211ms/edit baseline predates typed output and direct-position parse. Crash during actual user edit still unproven cause; tests so far only scriptedCP and renderer cycles, not gesture. Goal active,60fps not achieved.

## Reference dirty cache and empty-mesh guard 2026-09-17
- Previous turn progress: typed coordinates and full tests. This turn progress: reference extraction invalidation cache,3EM-mode parity/Undo/connection tests, concrete empty-data native crash fix.
- RetopoNode._reference_dirty startsTrue; setDependentsDirty(referenceMesh) and preEvaluation.dirtyPlugExists(referenceMesh) invalidate. Unchanged reference avoids getPoints/getTriangles/finite scan; non-normal data.context always rereads and leaves normal cache dirty. Exceptions also invalidate. Geometry-key comparison/nativeSurface rebuilding remain unchanged when reference is reread.
- tests/reference_dirty.py compares output with a second generator forced to reread reference every comparison. DG/off, serial, parallel; animated reference transforms, CP edits, referencevertex moves/Undo, disconnect retained value, explicit emptydata, reconnect. Existing smoke2024/2027 passes after final fix. Non-normal evaluation behavior implemented conservatively but not directly exercised by this test.
- First test incorrectly expected disconnected input to become empty; Maya retains its last value. Corrected oracle to compare retained geometry, then separately sets empty MFnMeshData.
- Empty MFnMeshData initially crashed DISPOSABLE mayapy2027, exit-1073741819, dumpMayaCrashLog260917.1650.dmp. Log native stack Poly.dll!TdataMesh::forceIntoWorldSpace -> MDataHandle::asMeshTransformed. Fixed by checking asMesh().isNull/hasFn(kMesh) before transformed access. Explicit empty input now errors safely and reconnect recovers. Full2024/2027 smoke including this case passed. Do not conflate with earlier UI Python execute-violation dump1621.
- Dense DG-only measurement500patch46528quads median41.841ms, tests/dense_dg_reference_cache.json, compared to previous45.746ms typed-only in separate process (not controlled A/B; GC/scheduling may differ). No fresh fullviewport timing.
- User first reported current Maya crashed on tumble, then corrected 'クラッシュしてないかも'. Verified GUI PID2960 remained responsive; MCP returned GPUrenderer and selectSuperContext; capture succeeded and shows changed camera with all500patchguides. Current GUI did NOT crash in this reported episode. Apologized for assuming crash. Kept GPUenabled and camera/scene unchanged. Sky not used thisturn. Previous confirmed edit crash remains unresolved.
- Current GUI remains oldschema500patch synthetic scene, none of typed/refcache changes live. No reload/restart/save/push. No outstanding jobs. Goal active;60fps notachieved, latest fullGUIedit211ms frompriorbuild; ordinary-mode camera cache bug and true context mouse-gesture stability still pending.

## Native mesh transfer prototype 2026-09-17
- Previous turn progress: reference cache / empty-input native crash guard. This turn progress: independent C++ Maya mesh-transfer node compiled and measured, not production integration.
- New cpp/mesh_buffer.cpp registers experimental aruRetopoMeshBuffer localID0x00131AD5. Inputs xyz doubleArray, faceCounts/faceIndices intArrays; output mesh data. Serial compute validates dimensions/indices/finite coordinates, maintains a private topology template, copies into fresh output before updating points. Invalid inputs return empty mesh data. Topology changes compare complete counts/indices even if vertex count unchanged.
- cpp/build_mesh_buffer.ps1 uses installed VS/SDK and versioned Maya include/libs; built bin/2024 and bin/2027/aru_retopo_mesh_buffer.mll. No autoload/API create integration, no edit to original Aru_CurveNet.
- tests/mesh_buffer.py uses46873vertices46528quads. Compares all output vertices exactly against existing Python unpack+MPointArray+templatecopy+setPoints; retains previous MObjects and confirms later updates leave them intact. Reversing firstface indices verifies same-count topology rebuild. Invalid xyz count and NaN then valid restoration verified. Maya quantizes initial mesh coordinates; source comparison tolerance1e-6 but C++ vsPython output comparison remains exact.
- Empty MFnMeshData.hasFn(kMesh) reports true even though MFnMesh access can raise object-not-found. Test now checks kMeshData and no readable/nonempty mesh. Do not mistake this API behavior for retained stale mesh or weaken normal-path exact parity.
- Final2027 transfer medians23.059ms Python vs12.986ms native (tests/mesh_buffer_2027.json). Earlier2024 measurement15.229 vs11.687ms; final rerun report in mesh_buffer_2024.json. Times INCLUDE creation of typed coordinate data + MPlug input/output calls for C++ path; not native compute alone. Validation scans outsidetimers. Stage-only results, no60fps/frame claim. Binaries loaded only in disposable mayapy processes; current GUI untouched.
- No production C++meshbuffer integration yet; existing RetopoNode still emits mesh itself. Need integrate coherently with generator/overlay/bake/scene persistence, not wire a test node into artist scene without provenance. Alternative next step is move full stencil/relax/mesh chain into native DG to avoid intermediate Python conversion.
- CurrentGUI PID2960 previous-schema500fixture remainsGPUenabled; typed/refcache changes stillnotloaded. No UI actions, saves, restarts,push or outstandingjobs. Goal active, no60fps, prior editcrash rootcause/normal camera bug/multi-panel and actual contextgesture timing remain pending.

## Native guide stencil to mesh 2026-09-17
- Previous turn progress: C++ raw mesh-transfer prototype. This turn progress: same native node evaluates compiled guide stencils before mesh creation, removing generated-vertex transfer from this experimental path.
- Added optional stencilOffsets/stencilIndices intArrays and stencilWeights doubleArray to aruRetopoMeshBuffer; with no stencil existing raw-coordinate behavior remains. CSR bounds/monotonicity/weight finiteness validated before indexing; all input coordinates validated even if not referenced. Arithmetic order follows existing aru_stencil. Same private-template/fresh-output behavior preserved.
- Rebuilt bin/2024 and bin/2027 native plugin. Compiler clean after local variable shadow fix. Plugin is still opt-in/disposable-test-only; no production/GUI graph connections changed.
- New tests/native_stencil_mesh.py validates square Coons, pentagon subdivision, dense500patch fixture. Exact all-vertex native-vs-currentPython mesh comparison across16controlled CPchanges, retained prior output immutability, malformedCSR rejection +recovery. Both versions passed. Initial fixture normal unit() was invalid for horizontal singlepatch; corrected planar normals for small fixtures, spherical normal for dense; no production algorithm alteration for this test fix.
- Final dense4268controls ->46873vertices /500patch: Maya2027 oldPython compiledstencil+unpack+MPointArray+copy/setPoints24.920ms versus typedcontrols->native stencil+mesh10.779ms. Maya2024 16.542ms versus12.192ms. tests/native_stencil_mesh_VERSION.json. Includes control packing/attribute transfer in native timing, validation outside timers, warm same-process alternating order. Small patches native slightly slower (~0.05-0.07ms). These stage timings exclude projection/relax and GPUdraw, not full-frame FPS.
- Next coherent integration should put existing surface projection/relax C ABI in native node as well, then integrate graph provenance/metadata/overlay/bake/save behavior. CurrentPython generator still emits its own mesh. No claim that user GUI uses prototype.
- GUI unchanged from prior knownPID2960 oldschema500fixtureGPUenabled. No restart,hotreload,save,push or pendingjobs this turn. Goal remainsactive,60fps not achieved. Currentactualcontext mouse gestures and earlierconfirmededitcrash rootcause remain unverified; normalmode camera bug/multipanel unresolved.

## Native projection/relax pipeline 2026-09-17
- Previous turn progress: native stencil->mesh. This turn progress: native reference projection and relaxation integrated into same experimental node, guide matrix input, raw-buffer optimization, fixed actual shared-input mutation, extensive parity tests.
- cpp/mesh_buffer.cpp optionally enables projectToReference (defaultFalse), reads referenceMesh with empty-mesh guard, validates adjacencyOffsets/adjacencyIndices/guideWeights and solver inputs, owns native Surface/seeds, rebuilds Surface when reference vertices/triangles differ. Existing aru_surface_create/aru_relax statically linked from retopo.cpp (OpenMP4); destructor frees Surface. guideMatrix applies before stencil. Iterations0..30, strength0..1, guard, pervertex guideWeights0..1 supported.
- Avoided per-element Maya array calls in stencil by copying CSR/controls to contiguous vectors and calling existing aru_stencil. Mesh coordinate array conversion also uses bulk get/copy. Initial full pipeline native17.24ms reduced to~14.96ms with identical results.
- Important real bug found by settings-only updates: MDoubleArray xyz=pfn.array() shared input storage, so assigning refined/projected arrays could alter positions input after compute. Fixed with xyz.copy(pfn.array()). Tests now assert entire input coordinate array remains unchanged after every evaluation. Earlier node prototype binaries replaced; never loaded in user GUI. This is unrelated to prior UI crash.
- tests/native_stencil_mesh.py --project compares full500patch4268controls46873vertices /5relaxiterations against currentPython plan+Surface+mesh output. Exact allvertex comparisons, retained prior outputs, input preservation, malformedCSR recovery. Additional reference translateY and guide scale/translation, iterations0/5/3, strength.35/.7/0, weight1/.25, guardTrue/False changes pass bothversions.
- Test precision issue: manual DAG getPoints(kWorld) preserves double transform while existing MDataHandle.asMeshTransformed uses mesh precision; changed test oracle to obtain transformed reference points from actual RetopoNode.surface_key (emptyselected graph, no mesh generation). Did not relax exact native-vs-existing output equality. Guard seed history carried consistently acrossreference/settingschanges.
- Final full computation+mesh stage medians:2027 Python28.927ms vsnative14.960ms;2024 Python19.416ms vsnative13.591ms. tests/native_surface_mesh_VERSION.json. Timing includes native inputattribute transfer and outputevaluation, excludes graphguidegeneration/contextinteraction/GPUdraw. Under16.7ms median for this stage is NOT proof of60fps.
- Rebuilt2024/2027 .mll. Raw transfer and nonprojection stencil regression tests rerun onbothversions; resultsfilesupdated. No production graph/API create integration yet. Need coherent topology/metadata provenance/overlay/bake/scene lifecycle integration beforeusinginartistUI.
- Current GUI unchanged oldschema500fixtureGPUenabled; no reload,save,restart,push. Prior actualcontext editcrash rootcause and ordinarycamera/multipanel remainunresolved. Goalactive60fpsnotachieved.


### 2026-09-17 opt-in native graph integration

Added `native_backend.enable/disable` and cached `aruRetopoPlan` typed topology provider. Guide coordinates feed the C++ mesh node directly. Frontend settings and selection remain on the existing generator; mesh/overlay/bake/status consumers resolve the selected backend. This is opt-in and has NOT been installed in the current GUI session. Fresh-process saved-scene plugin discovery and full interactive timing remain unverified.

`tests/native_graph.py` passed in Maya 2024 and 2027: empty confirmed-patch set, enable Undo/Redo, CP edits, guide weights, relaxation settings, subdivisions, patch removal/restoration, generator selection, foreground setting, independent bake and disable Undo. Every generated vertex matches the existing generator exactly in this fixture. Legacy full smoke passed on both versions (`smoke_native_graph_2024.log`, `smoke_native_graph_2027.log`). GPU lifecycle unit test passed.

Integration exposed an unsupported API 2.0 `om.kUnknownParameter` return in the generator; changed it to `None`, consistent with Autodesk MPxNode.compute documentation (https://help.autodesk.com/cloudhelp/2020/ENU/Maya-SDK-MERGED/py_ref/class_open_maya_1_1_m_px_node.html). The first disposable test also hit the previously observed Python 3.13 callback destruction stack during interpreter shutdown. The harness now clears its scene and unloads plugins before standalone shutdown, like the existing smoke harness; this does not establish a fix for GUI edit crashes.

Read-only MCP check: the existing GUI PID 2960 responded normally in `retopoGuideDraggerCtx1`. The most recent suspected tumble crash was not an actual process exit. No GUI hot reload was performed. 60 fps is still unverified.


### 2026-09-17 native graph DG profile and stencil cache

The 500-patch fixture has 46,528 faces / 46,873 vertices / 4,268 controls. `dense_dg_performance.py --native` now evaluates the actual guide-to-native-output graph. Maya 2027 median was 16.17 ms before this change (`dense_dg_native_2027.json`), 14.37 ms with validated CSR caching, and 13.80 ms with independent stencil rows parallelized across four CPU threads (`dense_dg_native_parallel_2027.json`). These are sequential runs, subject to system variation; they EXCLUDE viewport drawing and context interaction and do not prove 60 fps. One sample still exceeded 16.67 ms substantially.

Added hidden `computeMilliseconds` output to native node: input/stencil, topology validation, reference projection/relaxation, mesh construction/output (milliseconds). CSR buffers are copied/validated only on dirty topology, changed control count, or non-normal evaluation context. DG `setDependentsDirty` and EM `preEvaluation` invalidate the cache. Invalid CSR keeps the cache dirty. Non-normal contexts do not leave a reusable normal-context cache. Row sums preserve their original arithmetic order when parallelized.

Validation passed on Maya 2024 and 2027: native graph in off/serial/parallel evaluation modes, same-size coefficient replacement, malformed CSR recovery, exact vertex parity against legacy native library on quad/pentagon/dense fixtures, reference/guide transforms, solver settings, preserved prior output objects. Logs: `native_graph_VERSION.log`, `native_stencil_cache_VERSION.log`, `native_surface_cache_VERSION.log`. Timing numbers in the last parity tests were collected concurrently across versions and should not be used for performance comparisons. Both version-specific mesh-buffer binaries rebuilt. No GUI hotreload or default-backend switch.


### 2026-09-17 native bulk topology/adjacency reads

Replaced repeated SDK `MIntArray::operator[]` / `MDoubleArray::operator[]` access during topology and solver input validation with one bulk copy and contiguous C++ vector validation. Input validation remains per evaluation; cached mesh topology is still compared by complete contents, including same-length connectivity changes. A trial bulk MPointArray constructor provided no improvement and was reverted.

Maya 2027 guide-to-mesh DG median: 11.15 ms (`dense_dg_native_vectors_2027.json`), versus the preceding 13.80 ms run. These are separate sequential trials, not a controlled frame-rate claim. Stage medians are approximately 3.09 ms input/stencil, 0.15 ms topology, 3.58 ms projection/relaxation, 3.20 ms mesh output. A periodic slow sample remains. No viewport/context costs included; GUI still uses older code.

Both 2024 and 2027 binaries rebuilt. Tests passed on both: `native_graph_vectors_VERSION.log` (off/serial/parallel DG settings, editing/Undo/bake); `mesh_buffer_vectors_VERSION.log` (exact geometry, preserved old output, same-count connectivity mutation, invalid positions); `native_surface_vectors_VERSION.log` (dense exact legacy parity, transforms and settings, malformed adjacency and NaN guide weights rejection/recovery, invalid stencil recovery). Concurrent test timings are correctness evidence only.


### 2026-09-17 fresh GUI with official launcher and MCP

Retired the experimental launcher that skipped userSetup. User corrected that this bypasses their MCP startup. Started `D:/Dropbox/App/DCC/bat/luncher/maya.bat --2027`, PID 28980, and verified MCP access plus an empty scene. Earlier GUI PIDs were already absent; no processes were killed in this run.

The benchmark appeared stuck because replacing `gui_native_report.tmp` over the JSON report failed with WinError 5; error reporting attempted the same failing replacement. Changed the diagnostic report to direct writing and added setup checkpoints and BaseException reporting. This was a harness failure, not proof of a Maya crash or a patch-detection stall. Native backend and GPU renderer were enabled via MCP on the existing synthetic fixture, without replacing registered callbacks.

Authoritative current GUI result `gui_native_report.json`: 500 patches, 46,528 quads / 46,873 vertices; forced-refresh median idle 4.5875 ms, camera rotation 4.25255 ms, CP update 42.1322 ms (max 156.3267 ms). Camera test rotates the camera transform, not a physical mouse tumble. Full context drag/hover is not covered. This does NOT meet 60 fps during editing. Previous GUI 211 ms result was an older fixture/session, not a controlled A/B comparison.

Profile `gui_native_profile.txt`: five updates spend about 52 ms in addUIDrawables/draw_controls, 24 ms in populateGeometry, and 11 ms in updateDG; these Python timings do not account for all native rendering time. Next focus: marker and guide draw-data assembly. New GUI PID 28980 remains available with native mesh and GPU preview enabled; no hotreload of registered guide callbacks performed.


### 2026-09-17 GPU draw preparation caches

`gpu_guides.py` caches validated spline sampling indices and contiguous marker-style runs, invalidating on connectivity, point count, selection, EP types, mirror/manual handles, sizes, colors or handle visibility. Point coordinates are refreshed every draw. Sampling uses NumPy batched matrix multiplication in double precision before conversion to float GPU vertices. Maya 2024/2027 full smoke passed (`smoke_gpu_cached_VERSION.log`), including legacy marker order/colors/sizes and curve sample parity after coordinate/connectivity changes.

Only the helper module `gpu_guides` (no registered Maya classes or global shader instances) was reloaded in the verified synthetic GUI PID 28980. `gui_native_draw_cache.json`: idle 4.36 ms, camera rotation 4.35 ms, edit 42.38 ms. This did NOT improve measured full-frame median versus 42.13 ms baseline (`gui_native_before_draw_cache.json`). The Python profile fell from 97 ms to 55 ms over five updates; draw_controls from 52 ms to 25 ms and populateGeometry from 24 ms to 7 ms. Do not equate this partial improvement to a frame-rate gain. Remaining marker assembly still ~5 ms/update; investigate GPU point render items. Runtime stock `k3dFatPointShader` exposes solidColor, pointSize, and depthPriority parameters.


### 2026-09-17 GPU point experiment and refresh bottleneck

Added opt-in `gpu_guides.GPU_CONTROLS` (False by default): point/tangent render items reuse the shared control vertex prefix. Contiguous runs produced too many render items; grouping matching styles reduces items, and selected green markers receive final depth priority. This has NOT passed interaction/overlap parity and is NOT enabled by default. Existing CV selection item stays responsible for component hits.

Initial 49/87 ms comparisons were confounded by guide xray switching off; profiles proved the 87 ms case used ordinary UIDrawables. Controlled comparison explicitly set xray True and restored its prior False value: UI markers 39.08 ms, GPU markers 40.53 ms. No frame-time gain established. GPU points were disabled again. Native mesh generation and GPU curve/surface preview remain enabled.

`gui_native_frame_stages.json` separates point edit (~0.73 ms), native DG evaluation (~10.49 ms), and subsequent refresh (~30.38 ms), with an occasional 159 ms refresh. `gui_native_visibility_diagnostic.json` temporarily toggled visibility and restored all values: both 42.12 ms, mesh only 39.00 ms, guides only 16.90 ms, neither 4.29 ms. These are diagnostic conditions only; hiding content is not a solution. Next focus is Maya mesh-output/VP2 geometry rebuilding after deformation, rather than further marker micro-optimization. Full context gestures and 60 fps still unverified.


### 2026-09-17 mesh update diagnostics

SDK research confirms `MPxNode::isTrackingTopology` and three-argument `attributeAffects` can distinguish changes that preserve topology. No production topology hints were changed yet: raw coordinate count and invalid-input empty output currently can change output topology, so marking all position changes topology-preserving would require a stronger data contract. Autodesk reference: https://help.autodesk.com/cloudhelp/2024/ENU/MAYA-API-REF/cpp_ref/class_m_px_node.html .

A temporary independent baked copy (46,528 faces) was deformed directly using MFnMesh.setPoints, with original guide/output hidden temporarily. `gui_direct_mesh_diagnostic.json`: setPoints median 23.46 ms, refresh 19.59 ms, total 43.43 ms. Copy deleted, original visibility/foreground object set/selection restored. This does not isolate the same conversion path as native DG, but fails to support blaming only generator topology notifications.

A temporary reference-only base render pass also failed to demonstrate a gain (`gui_native_single_mesh_pass.json`, ~107 ms). No matched adjacent control was collected, and Python timings also rose substantially; do not attribute the whole slowdown causally to pass filtering. Original render operation and xray setting restored; prototype operation retained until restoration completed. Current production render passes unchanged.

The GUI harness now records display/backend conditions at start/end and rejects runs whose xray, GPU guide/point switches, renderer or output source change. Actual mouse context behavior, multi-panel display, and 60 fps remain unverified.


### 2026-09-17 native v2 direct coordinate output

`aru_retopo_mesh_buffer_v2.mll` adds typed `outPositions`. Requests for coordinates/status evaluate and validate the stencil/projection result without creating a Maya mesh. A later outMesh request reuses the clean datablock coordinate output rather than solving again; requesting outMesh first still generates and cleans both outputs. All upstream attributes dirty both outputs. Invalid inputs publish empty coordinates/error status; empty patch selections stay empty. Existing output objects are not modified by subsequent evaluations.

Versioned binary avoids overwriting/loading over the current GUI's v1. New `native_backend.enable` calls in fresh processes load v2. Current GUI PID 28980 was NOT migrated. Build and test paths now reference v2. Direct GPU mesh display is NOT connected yet.

500-patch coordinate-only DG median 8.513 ms (`dense_dg_coordinates_2027.json`), excluding GPU upload and viewport/context costs. This is not a frame-rate result. Maya 2024 and 2027 passed `native_graph_positions_VERSION.log`: coordinate-first then mesh, old coordinate object immutability, existing exact native-vs-legacy mesh parity, CP/topology/settings, off/serial/parallel, Undo and bake. New coordinates-to-display comparison uses bit-equal float32 conversions because Maya initially quantizes mesh coordinates while solver output is double precision; existing exact mesh parity was not relaxed. Dense surface parity, transforms and invalid-input recovery passed `native_surface_positions_VERSION.log` on both versions.


### 2026-09-17 direct GPU buffer preview prototype

Added experimental `cpp/buffer_preview.cpp` (aruRetopoBufferPreview, local ID 0x00131AD7) and separate build script. Typed position/triangle/edge inputs feed a native MPxGeometryOverride without MFnMesh output. DG reads are confined to updateDG; nonfinite positions and invalid index ranges/stride disable both render items. This is NOT connected to the editing graph or enabled by default.

Loaded the distinct plugin into existing Maya 2027 PID 28980, leaving registered v1 solver untouched. Copied actual mesh object-space positions, MFnMesh.getTriangles and mesh edge endpoints once: 46,873 vertices / 93,056 triangles / 93,400 edges. Temporary foreground object replacement and original mesh/guide visibility changes were restored; diagnostic node deleted after measurement. Screenshot showed cyan surface/dark edges, but dense raster appearance and rear occlusion still need controlled visual validation.

`gui_buffer_preview_diagnostic.json`: 25 post-warmup updates, median assignment 0.392 ms, refresh 7.354 ms, combined 7.748 ms. Coordinates varied at one vertex. Guides hidden, no solver evaluation or context gestures: this is only a buffer-upload/display diagnostic, NOT full editing FPS or a matched comparison with previous runs. Initial diagnostic used a temporary API array wrapper and failed with index-out-of-range; corrected harness explicitly copies cmds.getAttr data before measurement. Next: fresh official-launcher GUI with v2 coordinate output, live topology wiring and full-guide/context benchmark.


### 2026-09-17 live buffer topology wiring prepared

Preview v2 adds faceCounts/faceIndices inputs. On connectivity or vertex-count change, it builds a temporary Maya mesh for triangulation and unique polygon edges; coordinate-only edits reuse those index buffers. Topology inputs are validated before use. Invalid rebuild leaves cache invalidated for recovery. Both Maya 2024/2027 builds passed; live topology mutation visual correctness remains unverified. `tests/gui_buffer_live.py` connects native v2 outPositions and topology inputs, measures full guide dirty/solver/refresh with xray True, and restores visibility, CP and foreground object set in finally. Not yet executed.

Official launcher default background launch failed because its shared log was held by existing Maya. Retried official maya.bat --2027 --foreground with unique redirected logs; new PID 16732 is responding with an empty Maya UI. Existing PID 28980 preserved. MCP still reaches 28980 (port 50007); new PID has not opened the MCP port, likely same-port conflict but not yet diagnosed in UI. Do not launch further instances or assume a crash. Next action: inspect new instance startup/connection and run live harness there.


### 2026-09-17 fresh GUI live direct-buffer measurement

User explicitly permitted closing old Maya. Auto-review initially rejected unsaved force quit; saved old PID 28980 to immutable recovery `D:/Dropbox/App/.codex/recovery/retopo-20260917/maya-before-gpu-v2-28980.ma` (654215 bytes, modified=False), then normal quit succeeded (MCP socket disconnect expected). New PID 16732 remains alive. Its empty UI had no blocking dialog. Entered aru_mcp_startup.start() through Maya MEL command line; MCP now verified PID 16732. No security preferences changed.

New fresh native-v2 fixture: 500 patches / 46,528 quads / 46,873 vertices. `gui_native_report.json` ordinary native mesh median edit 43.739 ms (max 137.121), xray True, world guides True, GPU point option False. Direct-coordinate preview via `tests/gui_buffer_live.py`: median edit 26.851 ms (max 122.982), idle 4.151 ms. Second profiled run written to `gui_buffer_live_profile.txt`; profile shows ~4.8 ms marker drawing per update. No claim that profiler wall total captures full frame.

With experimental GPU_CONTROLS=True, direct buffer median edit 21.499 ms (max 127.933), idle 4.221 ms (`gui_buffer_live_gpu_controls.json`). Restored GPU_CONTROLS=False, CP, visibility and foreground selection; diagnostic nodes deleted. This is still above 16.667 ms and still has slow outliers. Mouse-context editing, marker overlap/selection parity, back-surface occlusion, topology changes and camera tumbles still need verification. Synthetic single-CP change is not actual mouse drag. Harness now records PID/GPU marker mode and uses separate mode-specific filenames to prevent overwriting comparisons.


### 2026-09-17 actual relaxation path audit

User asked whether 21 ms covers point manipulation and relaxation. It does NOT: prior timings are synthetic CP setAttr+render only. `gui_relax_initial.json` executes actual brush_weights and relax(draft=True) at visible EP 645, screen (1546,1145). Dense fixture brush contains 200 EPs: brush 66.272 ms, relaxation 1529.533 ms, excludes redraw/Undo. Scene changes restored by Undo. Actual physical stroke still untested. This substantially contradicts any broad 21 ms editing claim.

Moved radius rejection before expensive visibility ray tests in brush_weights; exact weights equal legacy for all affected 200 EPs. New brush median 26.491 ms (1090 original ray candidates), with one 141 ms outlier: `gui_relax_brush_cull.json`. In junction fitting switched unused face/bary queries to existing position-only projection. Full relaxation evaluated outNetData JSON exactly equal to pre-change result for same weights/scene; measured 1282.536 ms (`gui_relax_position_only.json`). Separate sequential samples, not stable full-frame rate. Maya 2027 smoke passed (`smoke_relax_cull_2027.log`). `gui_relax_profile.txt` identifies repeated projection/bary calculations and per-curve fitting as major work; next focus should batch/vectorize or native-implement this real operation, preserving surface and tangent behavior.

Direct-buffer stage probe measured assign 0.689 ms, solver 8.100 ms, refresh 13.193 ms. A reference-only base pass gave 21.287 ms overall, no material gain; base operation restored. `tests/gui_buffer_live.py` now accepts split_stages for explicit stage measurement. GPU point option remains disabled by default after diagnostics. Goal is still far from proven for real relaxation.


### 2026-09-17 surface-fit invariant reuse

In `_fit_spline_handles_to_mesh`, seed projection and returned-error sampling now use existing `_closest_point_pos_only`; unused face/bary work removed. In `_smooth_junctions`, fixed Bernstein coefficients, sample bases and 47x2 least-squares matrix are assembled once per spline rather than rebuilding rows in each of four iterations. Same least-squares solver, sample count, iteration count and length clamps remain.

Fresh reference full relaxation call measured 1297.184 ms for same 200 EP weights. Optimized computation measured 464.085 ms, excluding scene write (accessor.write intercepted into in-memory data and restored in finally). Output positions exactly matched the captured pre-change output (max error 0.0): `gui_relax_vectorized.json`. The comparison is calculation-only versus earlier full function timing; do not report as actual mouse-stroke FPS. Maya 2024/2027 full smoke passed `smoke_relax_fit_VERSION.log`.

Initial GUI parity attempt omitted helper import inside the extracted fit function; corrected with local import. Its cleanup also reported Undo temporarily unavailable; current context subsequently verified selectSuperContext. Final diagnostic avoids scene writes and Undo entirely. Registered context/draw classes were not reloaded: only the fit function compiled from current source plus the unregistered relax helper module. Remaining work: bulk/native projection and curve fits, real brush/drag measurements and complete display pipeline; 60 fps not achieved.


### 2026-09-17 bulk Maya intersector projection

Added Maya-version-specific C ABI `cpp/maya_projector.cpp` / `build_maya_projector.ps1`, binaries bin/2024 and bin/2027/aru_retopo_maya_projector.dll. Uses the same object-space MMeshIntersector and world/inverse transform behavior as existing curve_net_edit, returning float hit positions transformed back in double precision. No registered node hotreload. Python owner uses existing mesh accelerator dirty callbacks and object identity, pruning invalid owners; global invalidation closes native handles. Native function checks owner lifetime and finite input. Called only by interactive main-thread functions. Missing DLL keeps existing position-only fallback.

Bulk queries replace per-point calls in geodesic relaxation, seed/error sampling, and junction fitting. Keeps sample/iteration counts and numerical algorithm. GUI: 10,000 random query positions exact equality (0.0 max error); bulk 88.39 ms vs scalar142.04 ms for that far-field query distribution. Full 200EP relaxation calculation (write intercepted/restored) 309.901 ms with 0.0 position difference vs original captured output: `gui_relax_bulk_projection.json`. Excludes writing, brush weights and viewport; not 60fps.

`tests/maya_projector.py` tests exact query parity for identity and translated/rotated/negative nonuniform scale, vertex edits, deletion and same-name recreation, asserts native cache used. Passed both 2024/2027 (`maya_projector_VERSION.log`). First direct 2024 invocation lacked configured NumPy path; reran through project maya_env via `run_maya_projector.bat`, passed. Maya 2027 full smoke passed `smoke_bulk_projection_2027.log`, including surface/tangent behavior and MMB release/manual/Undo. Next bottleneck is per-curve fitting itself and Python brush/commit overhead; actual gestures remain unverified.


### 2026-09-17 native Bezier-to-path fitter

Added pure numeric `cpp/path_fit.cpp`, `build_path_fit.ps1`, bin/aru_retopo_path_fit.dll and `editor/curvenet/path_fit.py`. Moves polyline projection, iterative two-handle normal-equation solve, fixed-handle branches, length clamps, convergence and final tangential candidate comparison into C++. Existing Maya geodesic construction, normals, surface metadata and mesh-error evaluation remain with the caller. Windows native path enabled when DLL present; original Python path remains available when disabled/missing/on other platforms.

GUI 200EP relaxation calculation (write intercepted and restored) 173.548 ms, maximum position difference from original reference 6.217e-15 (`gui_relax_native_path.json`). Prior bulk-projection calculation309.901 ms was a separate run. No actual mouse/brush/write/viewport cost included, no 60fps claim.

`tests/native_path_fit.py` compares native vs original full fitter for 12 randomized sphere curves x free/fixed1/fixed2 =36 cases, requires native DLL exercised, checks positions and returned mesh error <1e-9. Both Maya2024/2027 passed, worst position difference2.165e-15 (`native_path_fit_VERSION.log`). Maya2027 full smoke passed `smoke_native_path_2027.log`. Still need batch junction fitting/geodesic processing, total brush path profiling, saved-scene integration and full interactive60fps evidence.


### 2026-09-17 batched junction length fitting

Current instrumented 200EP computation170.842 ms: inclusive fit323calls75.379 ms, junction smoothing58.778 ms, world-data preparation11.790 ms, geodesic323calls17.150 ms (nested), bulk projector2055calls40.474 ms (nested). `gui_relax_stage_profile.json`; inclusive timings must not be summed.

`curve_net_relax._fit_junction_lengths` now gathers independent curves, computes batched pseudoinverses once, then projects all15sample points per curve in one query per iteration. Four iterations and length bounds unchanged. Shared handles or handle/endpoint overlap fall back to `_fit_junction_lengths_scalar` to preserve sequential dependencies. GUI calculation126.511 ms, max position difference6.217e-15 vs original reference (`gui_relax_batch_junctions.json`), excludes write/brush/render.

`tests/junction_batch.py` compares batched vs sequential junction fitting on dense500patch network at three weight densities, with/without manual handles (6cases each version). Passed Maya2024/2027; worst position difference4.441e-16 (`junction_batch_VERSION.log`). Goal still unmet; next work includes repeated fitting setup, JSON/world-data preparation and eventual fullcontext/viewport integration.


### 2026-09-17 numeric guide read and EP incidence

Relax _world_data reads evaluated outPositions plus cached netData metadata, avoiding output JSON generation/parse. Creates owned mutable positions and deep-copied surface_binding; retains legacy output JSON fallback for older schemas, preserves pose-driven rejection, validates coordinate count and skips identity world transform. Reclassification remains to construct correct EP/Handle wrappers. GUI warm read median4.134 ms, complete calculation122.464 ms before incidence change (`gui_relax_numeric_read.json`).

Built incident handle lists once per relaxation instead of scanning every spline for each affected EP. Self-loop first-side behavior preserved. Seven GUI computation samples (first excluded): median112.951 ms, one229.304 ms outlier, max position difference6.217e-15 vs original200EP reference (`gui_relax_incidence.json`). Initial single sample246.617 ms was not representative; do not claim stable113ms. Writing, brush and viewport excluded.

`tests/relax_numeric_read.py` compares complete serialized data to legacy outNetData under CP edits and translated/rotated guide transforms; mutates nested binding in returned data and verifies shared parse cache remains intact. Both Maya2024/2027 passed (`relax_numeric_read_VERSION.log`). Still far from60fps; full real operation timing and additional native batching required.


### 2026-09-17 actual write path and sparse tweak reset

Found _reset_control_points issued3*n setAttr calls, including already-zero CPs. New code inspects existing logical indices for sparse arrays, otherwise reads contiguous values, then resets only nonzero contiguous ranges with flattened double3 data. Locked/connected failures fall back to previous per-component early-exit behavior. Caller still owns Undo chunk. Initial tuple-array syntax failed and fell back; corrected to flat values. Full zero-array assignment cost86.274 ms, sparse-aware final4268CP/3changed reset0.641 ms2027 /1.066 ms2024 in tests. Avoids creating thousands of absent zero tweaks.

patch_transfer.prepare checks cached base spline connectivity before requesting evaluated JSON; position-only edits skip transfer work. Splits still use evaluated geometry and original transfer path.

`cp_bulk_reset_VERSION.log` passes sparse reset, Undo/Redo, locked-X behavior; final2024 test also includes dense all-CP reset. Full2027 smoke passed `smoke_sparse_cp_2027.log`. GUI loaded only changed reset function and unregistered patch-transfer helper. Actual200EP relax + write + synchronous current-view redraw took229.586 ms (`gui_relax_full_write.json`), ordinary native mesh + GPU preview, excluding brush_weights. This is a different scope from113ms calculation-only. Immediate MCP Undo was rejected as temporarily unavailable. Scheduled Undo with evalDeferred after the command completed; tests/gui_relax_restore.json confirms restored=true against evaluated guide JSON. No persistent benchmark edit. Full60fps remains unmet; direct buffer integration and further computation/commit reductions still required.


### 2026-09-17 native batched geodesic routes

Maya projector v2 DLL adds aru_maya_fit_routes: seed projection, object-space MMeshIntersector normals, arc-length resampling, geodesic iterations and native Bezier fitting run together across independent curves in one C ABI call. Build includes shared path_fit.cpp implementation. Both versioned2024/2027 binaries built without replacing loadedv1. maya_projector.clear() called before GUI helper reload, avoiding old-handle/new-ABI mixing.

Relax uses batch route fit only for independent automatic handles in smooth-surface mode. Shared handle/endpoint indices and hard-surface mode keep original per-curve route. Zero-length curves preserve skip/metadata behavior. Existing surface-binding metadata still refreshed from original API per handle.

GUI53curves native3.986 ms vs scalar14.238 ms, max error0.0. Five200EP relaxation calculation samples: median56.810 ms (excluding first), one186.173ms outlier; max position difference6.217e-15 vs originalcaptured output (`gui_relax_native_routes.json`). Excludes write/brush/display.

`tests/native_routes.py` compares batched route fitting to prior complete fitter on48cases covering draft/refined and translated/rotated/negative nonuniform-scale reference. Both2024/2027 passed with max error0.0 (`native_routes_VERSION.log`). Actual context and complete60fps still unmet. Next focus is EP/junction geometry queries and metadata, then full pipeline integration and stability.


### 2026-09-17 batched surface metadata and junction setup

Projector v4 provides bulk closest positions, normals, face IDs and legacy fan barycentric bindings. Relax uses it for EP projection, projected EP normals, fitted-handle bindings and junction normals. Degenerate faces preserve the legacy fallback; empty requests return an empty list. Full projector transform/deform/delete-recreate and metadata parity tests passed on 2024/2027 (maya_surface_hits_VERSION.log). Full smoke passed both versions (smoke_surface_hits_VERSION.log).

Removed the duplicate _dirty_shape_view call after relax in _relax_drag: RetopoGuideAccessor.write already performs synchronous current-view refresh. No timer or frame skipping was introduced. No claim of measured actual gesture savings yet; the current live context class has not been hot-reloaded.

Profiling the 200 EP calculation found 2,908 tiny numpy.linalg.norm calls and 2,354 array constructions. Junction-length setup now gathers controls into one array and computes chord/handle lengths and default directions in batches, retaining the shared-handle sequential fallback and all four solver iterations. Six junction parity cases passed on each Maya version, maximum error 4.441e-16 (junction_vector_setup_VERSION.log).

GUI PID16732 helper projector cache was cleared before loading v4; unregistered relax helper reloaded. No scene write during this calculation benchmark. Seven samples: 36.155, 33.787, 34.455, 178.785, 36.548, 34.327, 34.537 ms; median excluding first 34.496 ms. Maximum position error vs original 200 EP reference 6.217e-15 (gui_relax_vector_setup.json). Previous metadata-only median 37.333 ms. These are calculation-only timings, excluding brush, write and rendering, and retain a substantial slow outlier. Actual stable 60fps remains unproven and unmet.


### 2026-09-17 shared brush-event snapshot

Added brush_relax as the context entry point. It reads evaluated world data once, computes read-only screen/occlusion weights, then passes that owned snapshot to relaxation. Nothing persists across mouse events, camera changes or undo; standalone brush_weights and relax retain their independent-read behavior. _relax_drag now uses this path; the live registered context class was not hot-reloaded.

Surface-relax integration compares full serialized outputs of separate/shared reads with a transformed guide and CP tweak, verifies one read, unchanged source/cache ownership and no write for an empty brush. Full Maya2024/2027 smoke passed (smoke_shared_brush_VERSION.log), including Shift click/drag routing, projection and Undo.

Live Maya PID16732 helper-only benchmark at screen1546,1145 affects200EP in both paths. Seven interleaved samples, median excluding warmup: separate53.742 ms, shared49.107 ms. Complete output data equal. Includes real screen-space brush/occlusion weights and relaxation computation, EXCLUDES scene write and rendering. Both paths had slow outliers (164.303/178.333 ms). Data in gui_relax_shared_brush.json. Stable60fps remains unmet. Next candidate is repeated active3dView and MScriptUtil construction per EP in _world_to_screen, and remaining geometry/data-copy work.


### 2026-09-17 brush screen projection allocation

_world_to_screen_many obtains the active M3dView and allocates MScriptUtil output pointer owners once per call, then uses the same Maya worldToView short-pixel conversion for each EP. It does not cache view state across events. Brush uses this batch; scalar helper remains unchanged for other callers and unavailable-view fallback. Surface-relax mock screen inputs updated for batch signature.

Live16732,1090EP: exact pixel equality vs scalar at current camera. Seven interleaved timing samples, warmup excluded: scalar median2.514 ms, batch0.857 ms (gui_screen_batch.json). This measures only projection, not brush visibility, relaxation, write or rendering. Camera tumble visual stability and whole-gesture60fps are still unverified. Full smoke passed Maya2024/2027 (smoke_screen_batch_VERSION.log).


### 2026-09-17 slow-frame GC diagnosis

Attached a temporary gc callback during18 actual brush+calculation calls, with write/render replaced by no-op; restored write and removed callback in finally. GUI event trace saved in gui_relax_gc_profile.json. A174.002 ms sample spent126.376 ms inside generation2 collection; a160.030 ms sample spent112.369 ms there. This proves at least these large computation outliers are Python full-collection pauses, not native projection or GPU time. GC remains enabled and thresholds unchanged.

Source inspection: RetopoGuideData owns EP/Handle lists and maps, whose objects hold strong _cn back-references. Each _world_data/from_dict rebuild therefore creates cycles; classify_endpoints also recreates wrappers. Next work should reduce this temporary ownership/allocation while preserving external EP/Handle lifetime semantics. Do not globally disable GC or declare the pauses fixed. No60fps completion claim.


### 2026-09-17 lazy numeric snapshot wrappers

RetopoGuideData.from_dict accepts opt-in lazy_objects; default behavior remains eager. Relax world snapshots opt in. Classification still computes endpoint/curve topology, but defers EP/Handle object creation until a wrapper accessor is called. Accessors and Handle opposite lookup ensure materialization. Reclassification invalidates wrappers for lazy snapshots; external wrappers retain the original strong owner semantics. No global GC disable or threshold change.

Both Maya2024/2027 numeric-read tests pass full serialized parity under CP/world transforms and nested cache ownership, and additionally prove via weakref that an unused numeric snapshot is destroyed immediately without gc.collect. Accessing EP/handles materializes correctly, and an external EP retains its data owner. Full smoke passed both versions (relax_lazy_VERSION.log, smoke_lazy_VERSION.log).

Live data-model module was not hot-reloaded because registered code and existing data hold the old class. GUI slow-frame improvement is NOT yet measured; requires safe integration/restart. This removes a proven source of temporary cycles in relaxation, but does not prove all GC pauses are resolved.60fps remains unmet.


### 2026-09-17 isolated live lazy-data measurement

Loaded current disk data/relax sources under isolated module names and injected the isolated data class only into the trial relax module. Existing registered modules/classes and scene were not replaced. Writes were intercepted and restored in finally. Full serialized output matched the previous live implementation.

18 interleaved calls with captured serialized output: current median45.992 ms, lazy46.008 ms; full GC counts3/2, maxima179.028/183.465 ms (gui_relax_lazy.json). To remove retained output as a measurement confound, repeated30 sequential calls per variant with no-op writes and no output retention: current median47.066 ms, lazy47.143 ms; full GC counts4/3, maxima248.971/146.057 ms (gui_relax_lazy_no_capture.json). These measurements do NOT demonstrate a median speedup or eliminated GC pauses. Different maxima alone are insufficient to claim stable tail improvement.

Lazy wrappers preserve correctness and remove snapshot cycles in standalone lifetime tests, but more allocation/ownership sources remain. Native bridge creates NumPy/ctypes temporaries and route/surface result lists; inspect those with allocation evidence before further changes. No GC settings altered. Full real editing/render60fps remains unmet.


### 2026-09-17 direct NumPy projection results

Added points_array returning owned contiguous float64 output from native projection; list-returning API remains compatible. Both batched and sequential junction length solvers consume the array without tolist/np.array round trips. Fallback projects scalar points into an independent array. Maya2024/2027 projector tests verify exact coordinate parity, empty Nx3 shape, and modifying an output does not affect subsequent calls (projector_array_VERSION.log). Full smoke passed both (smoke_array_transfer_VERSION.log).

Live helper changes only: clear projector before reload, then AST-update two unregistered junction functions; do not reload data model/context classes. Twelve calls per variant, warmup excluded: brush/calculation with final serialized output capture median48.518 ms list path vs45.039 ms array path. Full output equal. gui_relax_array_transfer.json retains all samples. Scene writes/rendering excluded; GC remains enabled. Still above16.7ms before write/display, so60fps is not achieved.


### 2026-09-17 brush visibility intersection grid

make_visibility_test now creates Maya autoUniformGridParams once per closure and passes it to closestIntersection; Maya owns the grid. Optional use_acceleration=False retains an unaccelerated comparison path, and unavailable accelerator setup falls back to None. Normals, lift, ray endpoints and tolerances unchanged.

New visibility_accel test compares600 points across perspective/orthographic views on combined occluding spheres, then vertex deformation and mesh rotation. Both2024/2027 passed with exact booleans (visibility_accel_VERSION.log). Live only the unregistered visibility factory was AST-updated; scene unchanged. Real brush weights benchmark stored in gui_visibility_accel.json. Whole editing60fps remains unmet.


### 2026-09-17 current full brush/write/redraw measurement

Live16732 actual brush_relax at1546,1145 affected200EP with ordinary native mesh and GPU preview: total153.142 ms, accessor.write including redraw116.276 ms, synchronous redraw104.687 ms. One sample only; not a stable percentile or actual mouse gesture frame series. Test wrapped existing write/refresh timers in try/finally and restored wrappers. Undo deferred until MCP command exit; evaluated guide JSON equality confirmed restored=true (gui_relax_full_current.json).

A second actual brush operation profiled Python callbacks inside redraw. Profile accounts for15 ms, including GPU control UI draw~5ms, plan compute~4ms with JSON parsing, guide updateDG~3ms. This does NOT account for all native rendering/evaluation/waiting and must not be subtracted from the previous separate sample as a measured breakdown. Deferred undo confirmed restored=true (gui_refresh_profile.json). Registered classes unchanged; live helper mix documented in preceding entries. Current scene preserved. Next substantial bottleneck work must include native mesh construction/rendering and integrating direct GPU buffers, not only brush calculation.60fps remains unmet.


### 2026-09-17 actual relaxation with direct GPU buffer preview

Added tests/gui_buffer_relax.py, scheduled through evalDeferred so each real brush edit is immediately undoable. Creates a temporary v2 preview, connects native outPositions/face topology, compares ordinary mesh vs direct buffer foreground, then restores foreground object list, mesh visibility, evaluated guide data and deletes the temporary node. Five identical200EP steps per mode, each undone and equality-checked before the next. Final restored=true.

Full brush+relax+write+synchronous refresh medians excluding first: ordinary mesh141.071 ms, direct buffer125.440 ms. Raw samples in gui_buffer_relax.json, including250.908 ms ordinary outlier and229.844 ms first buffer sample. This is a controlled sequence of independent undo-restored edits, not actual continuous mouse dragging. UI point controls remained in their existing mode; no quality reduction. Direct buffer alone does not provide60fps and is not yet production-enabled.

Read plan compute afterward: stencil/topology cache already keys on spline connectivity/subdivisions/rebuildSerial/selected patches, not positions, but compute still parses changed guide JSON and sets all output payloads. Further profiling should separate reference/intersector invalidation, coordinate solve and output dirtiness when netData changes, rather than assume direct display fixes all refresh time. Scene preserved;60fps unmet.


### 2026-09-17 native solve versus display stages

Extended gui_buffer_relax diagnostic to explicitly evaluate native outPositions before refresh and read computeMilliseconds. Captures each phase and restores original refresh callback in finally; gui_buffer_relax_stages.json restored=true. Non-outlier coordinate evaluation54-58ms; native reference projection/relaxation consistently43.7-44.8ms. Input/stencil stage typically9-12ms (one116ms outlier). Subsequent direct-buffer redraw~20ms except GC-like outliers; ordinary mesh redraw~35-46ms. Whole medians are affected by outliers (buffer181.709ms vs ordinary148.425ms), so do not present this run as a stable buffer speedup.

Native source audit: reference surface recreated only when point/triangle vectors differ; coordinate-only guide changes do not deliberately rebuild it. aru_relax already uses four OpenMP threads, and build_mesh_buffer.ps1 enables /openmp. Prior ~8ms CP-change solve measurements therefore do not represent200EP relaxation where many more projected samples change and exact projection caches miss. Next native work should measure cache hit rates/thread scaling or improve projection search for this actual workload; no lower iteration count or narrowed scope is acceptable as proof of60fps. Goal remains unmet.


### 2026-09-17 BVH bound reuse candidate

retopo.cpp search previously computed child box distances for traversal order, then recomputed each distance on entry. Pass the already computed lower bound into recursive calls; preserve strict pruning/comparison rules and near-first traversal including tie order. Built isolated core DLL under bin/projection_trial, leaving loaded production binaries unchanged.

Live standalone comparison on current reference sphere:20000 queries,8 passes with warmed seeds and alternating guard, median excluding first old51.806ms vs candidate30.858ms. Final positions, seeds and normals exactly equal (gui_projection_bounds.json). This benchmark uses serial aru_project, not the4-thread aru_relax or fullMaya edit. Broad geometry/degenerate/tie regression and full solver measurement remain required before production binary rollout. C++ source changed; shipping binaries still previous implementation.60fps remains unmet.


### 2026-09-17 BVH bounds validation and Maya v3 build

Added projection_bounds.py comparing old shipping core to isolated bounds-reuse candidate on sphere/cube/torus with duplicate and degenerate triangles.1024 queries exercise parallel relax threshold, six moving-query passes per mesh, alternating guard, carrying seeds. Every pass asserts exact projection positions/normals/seeds and three-iteration parallel relax output/seeds.18cases passed both Maya2024/2027 (projection_bounds_VERSION.log).2024 initial import ordering failed before Maya initialized; fixed initialization order and reran successfully.

Built aru_retopo_mesh_buffer_v3.mll for both versions using bounds-reuse source and enabled v3 for future native_backend.enable calls. Live16732 remains v2; no registered plugin hot swap. Existing native_graph regression (patch selection/subdivision edits, CP, solver settings, enable/disable Undo/Redo) passed both v3 builds (native_graph_v3_VERSION.log). Standalone test entry initialization corrected before importing project modules. Shipping standalone core remains previousv4; Maya v3 contains new code. Full large-scene v3 timing still required;60fps unproven/unmet.


### 2026-09-17 full-size native v2/v3 replay

Exported current native input arrays/reference and captured200EP relaxed guide positions without writing scene, native_relax_input.json. New native_relax_replay reconstructs reference and directly feeds identical typed arrays into a fresh mesh-buffer node. Alternates original/relaxed4268controls twelve times, evaluates46873output vertices/46528quads; no brush, write or viewport. Initial overlapping process timings discarded in favor of sequential isolated processes.

Sequential medians excluding first2: Maya2027 v2=46.758ms v3=30.646ms; Maya2024 v2=47.212ms v3=28.908ms. Both original and relaxed output SHA256 byte hashes match v2/v3 on each version. Reports native_relax_replay_VERSION_MAYA.json include native stage timings. Test setup initially passed Python nested lists to MFnMesh.create; corrected to MPointArray and reran. LiveGUI16732 remainsv2, not restarted or changed. Nativev3 improves the actual large relaxed input workload, but still exceeds16.7ms before all other work;60fps remains unmet.


### 2026-09-17 bounded parallelism and Maya v4

Added compile-time ARU_RETOPO_THREADS (standalone default4) and mesh-buffer build parameters. Candidate8/16 thread plugins measured sequentially on the same46873vertex200EP-relaxed input:2027 t8=19.414ms, t16=16.201ms versus v3 four-thread30.646ms. Both output hashes exactly match. Final projectionThreads caps by omp_get_num_procs, at most4 for n<8192 and configured max16 for larger inputs; no iteration/sample changes. Non-OpenMP builds return1.

Built mesh_buffer_v4 for2024/2027, loader updated for future fresh processes. Sequential final v4 replay medians:2027=16.011ms,2024=17.442ms. Original/relaxed byte hashes match v2 on each version. Native graph integration passed both (native_graph_v4_VERSION.log), including patch/subdivision changes and Undo/Redo. Live16732 stillv2; no registered-plugin hot reload. Small workloads remain at most4threads. Actual full brush calculation/write/display and tail-latency60fps still unmet; these timings are only native coordinate evaluation. Reports native_relax_replay_v4_VERSION.json retain all samples.


### 2026-09-17 sparse surface-binding copy

Current live brush profile captured without scene write (gui_curve_remaining_profile.json): Python callbacks32ms; deepcopy4269calls/~4ms, eager from_dict/~8ms remain visible in the old live data class. Disk _world_data now bypasses deepcopy for None surface bindings, copying actual bindings with one shared memo so aliases among nonempty bindings retain prior deepcopy semantics. This avoids recursive dispatch per unbound CV without sharing mutable binding data with cached source.

Both Maya2024/2027 numeric-data tests pass complete JSON equality under CP/transforms, nested binding ownership and lazy wrapper lifetime (relax_sparse_binding_VERSION.log). No claimed full-operation timing benefit yet. Live helper/data model not replaced in this change. Native v4 remains ready on disk; live integration and full60fps still incomplete.


### 2026-09-17 fresh GUI launch for v4 integration

Saved oldGUI16732 to D:/Dropbox/App/.codex/recovery/retopo-20260917/maya-before-v4-16732.ma (654203bytes, modified=false), then requested normal quit; process exit verified. New Maya2027 launched via the explicitly requested D:/Dropbox/App/DCC/bat/luncher/maya.bat --2027 --foreground, hidden helper cmd, logs TEMP/retopo-v4-maya-{out,err}.txt. NewPID48756 alive/responding. ComputerUse confirms splash currently loading renderSetup, before v4 integration. Do not diagnose as a v4 crash; no v4 has been loaded yet. MCP initial execute still pending (functions cell946); no duplicate launch.

Created separate byte-preserving restore copy maya-v4-restore-16732.ma by changing only exact mesh-buffer requiresv2->v4; original backup unchanged. Initial UTF8 read failed before any write because source is legacy encoded, then byte replacement succeeded. Restore copy has NOT been opened. FreshGUI full edit/display measurements remain pending. Goal active, not blocked or complete.


### 2026-09-17 restored-scene v4 validation while GUI starts

New tests/restore_v4.py preloads current registered plugins in disposable mayapy2027, opens byte-preserving v4 restore copy, confirms v4 loaded and46528generated quads with Native mesh ready. Passed (restore_v4_2027.log); no save to the backup/copy. Thus saved test scene migrates to v4 successfully outside GUI.

GUI48756 startup remained at renderSetup splash while launcher log advanced to Arnold plugin loading. Initial MCP execute cell946 ended with300s timeout, which does not establish Maya process exit/crash. No second GUI launched, no force kill. Fresh GUI full-render verification still pending; scene recovery files retained.60fps remains unmet.


### 2026-09-17 GUI v4 integration recovered

Autoload GUI48756 remained in renderSetup splash and could not activate its main workspace. Terminated that empty pre-scene process under existing user authorization and ran same official launcher with --2027 --foreground --no-autoload-plugins. NewPID43108 reached full workspace. This isolates startup issue to configuration involving autoload, not proof of a specific plugin defect. Full latest Python smoke meanwhile passed2024/2027 (smoke_v4_final_VERSION.log).

MCP request paused at visible Maya command-port security prompt; user had explicitly authorized all such loading/execution. ComputerUse refreshed after stale accessibility index error, clicked observed All Allow button, verified prompt disappeared and pending MCP call completed withPID43108. No security preferences file modified. Freshempty state checked, explicitly preloaded retopo guide/generator/plan/overlay and mesh-bufferv4, opened verified v4 restore copy. MCP confirms v4_loaded=true,46528faces, Native mesh ready; gpu_preview enabled modelPanel4. New GUI now uses current disk Python model/helpers and v4 binary without registered-class hotreload. Fullgesture/tumble performance/stability still pending;60fps not achieved.


### 2026-09-17 fresh v4 GUI full-path and camera check

GUI43108 now runs current disk Python + v4. Verified brush1546,1145 still selects200EP. Re-ran full undo-restored staged comparison: ordinary mesh median109.637ms, direct buffer91.705ms (warmup excluded); native projection typically14-16ms, full coordinate input/evaluation25-28ms, buffer redraw~19ms vs mesh35-41ms. One buffer sample151.694ms includes evaluation88.618ms. Latest report preserved as gui_buffer_relax_stages_v4.json; generic stages report overwritten by rerun. restored=true; temporary preview removed and ordinary foreground restored.

Captured viewport before and after Maya tumble command azimuth25/elevation10. Guide visibly moved with sphere/view rather than staying at original screen coordinates; guide outNetData unchanged, no crash in this check. Restored original camera world matrix within1e-10 and guide equality (gui_v4_tumble.json). This is ONE programmatic tumble plus captures, not continuous real UI drag/edit stability proof. Remaining full-path overhead means60fps not achieved.


### 2026-09-17 opportunistic plan JSON reuse

Plan compute now checks RetopoGuideData._PARSE_CACHE for exact input raw string; when already parsed by another guide evaluator, reuses read-only splines/positions. On miss it retains json.loads and does not construct expensive editor wrappers. All geometry transforms build new point arrays, preserving cached ownership. Existing key/stencil invalidation unchanged.

Native graph integration passed Maya2024/2027 (native_graph_plan_parse_VERSION.log), covering patch selection, subdivisions, CP and Undo/Redo. Live registered plan class not hot-reloaded. Cache-hit-specific performance and broad real operation speedup remain unmeasured; do not claim this change alone removes the9ms input stage. Goal remains active; full60fps unmet.


### 2026-09-17 plan cache branch verification and identity inverse transform

Explicit plan cache miss/hit integration now passed Maya2024/2027 (native_plan_cache_paths_VERSION.log). Instrumented json.loads confirms one decode on miss and zero on hit; statuses, full geometry comparisons and cached data ownership remain equal. This proves the branch behavior, not an actual full-edit timing improvement. Registered live plan class remains unchanged.

Relax now skips the final full-CV inverse world transform only when the world matrix is exactly identity. Every nonidentity transform retains the previous MPoint path. Fresh GUI43108 still holds the verified500patch/46528face scene; reloaded only the unregistered curve_net_relax helper. Alternating old/new calculation-only benchmark with200EP and4268CV,12samples/mode (first2excluded): old median28.255ms, new24.338ms. All complete output dictionaries exactly equal; scene outNetData unchanged. Includes old-path109/124ms outliers; not a tail latency guarantee. Report gui_relax_identity_transform.json. Write intercepted, so these measurements exclude brush weights, DG recompute and drawing and cannot establish60fps. Maya2024/2027 integrated smoke checks passed (smoke_identity_transform_VERSION.log), including transformed relax and Undo. Actual continuous gesture/display60fps remains unmet.


### 2026-09-17 copy normalized topology for relax snapshots

Profile of five calculation-only200EP relax calls identified repeated from_dict/classify/curve-chain traversal (gui_relax_after_identity_profile.txt). _world_data now calls _evaluated_copy on the exact parsed netData cache entry: owned evaluated position lists, copied mutable topology/curve chains/classifications, independent nested binding deepcopy, lazy EP/Handle wrappers. Source must be normalized and unmodified; legacy outNetData fallback remains unchanged. Wrong position count still rejected. No topology shared mutably and no cross-event evaluated snapshot cache.

Maya2024/2027 numeric tests passed CP/transforms plus explicit loop/standalone endpoint/derived graph equality, mutation isolation, lazy lifetime and invalid-count checks (relax_topology_copy_VERSION.log). GUI helper reloaded without touching registered nodes/native projector. Alternating twelve calculation-only samples/mode: median23.884ms before,23.208ms after, excluding first2; complete outputs exactly equal and scene unchanged. Benefit is small (~0.7ms), not the profiler's apparent multi-ms total. New-path101/144ms outliers remain; no tail-latency claim. Report gui_relax_topology_copy.json retains samples. Brush/write/DG/display excluded; full60fps still unmet.


### 2026-09-17 GC observation and numeric parse-cache lifetime

Current GUI43108 calculation-only32step measurement uses a simple no-write function (no unittest mock retaining call arguments).200EP median22.732ms, max132.214ms; that maximum includes generation2 collection108.382ms collecting212752objects. Another89.156ms sample includes64.776ms generation2 with0collected. GC settings/callbacks restored, no thresholds changed or GC disabled, guide outNetData unchanged. Report gui_relax_gc_current.json. Confirms residual stalls but does not attribute all collected objects to the tool.

from_json_cached now constructs normalized data with lazy_objects=True, deferring EP/Handle owners and cycles for numeric-only consumers. from_json retains prior eager behavior, public wrapper accessors materialize lazily. Eviction test establishes numeric cached data releases immediately without gc.collect; external EP still retains its owner. Both2024/2027 numeric/ownership and full smoke tests passed (relax_lazy_cache_VERSION.log, smoke_lazy_cache_VERSION.log). Class not reloaded into live registered nodes; no claimed GUI tail-latency improvement yet. Cache entries consumed by wrapper APIs can still form cycles; unrelated Maya live objects also affect full GC. Full60fps remains unmet.


### 2026-09-17 fresh-process full update benchmark

Added relax_full_update.py / run_relax_full_update.bat. Loads v4 restoration in disposable mayapy2027 with latest lazy parse cache and plan reuse; actual200EP brush weights exported from GUI to relax_benchmark_weights.json. Each of16samples performs real relax/write, evaluates native outPositions and outMesh, then Undo and verifies full guide equality; no viewport or brush-weight calculation timed. GC unchanged. First run median total72.705ms (write45.950, coordinates22.985, mesh3.786). Second run with a separate additional profiling sample: {'write_ms': 45.27125000095111, 'coordinate_ms': 22.602349999942817, 'mesh_ms': 4.031899999972666, 'total_ms': 71.99165000201901}. Warmup2excluded, medians of stages need not sum to total. Full latest samples in relax_full_update_2027.json. GUI registered class remains previous version.

Separate real-write profile (relax_full_write_profile.txt) identifies JSON serialization~6ms, endpoint/curve classification~3ms and many per-vector numpy.norm calls~6ms cumulative as further costs; profiling undercounts some wrapped/native calls and is not the benchmark wall clock. No claim of60fps or comparable GUI tail improvement. Full update is already over16.7ms before brush and rendering.


### 2026-09-17 retain classified topology through numeric writes

classify_endpoints now retains derived graph data for lazy numeric objects only when an exact immutable signature of CV count, all spline control indices and standalone EPs matches the completed classification. Wrapper dictionaries still reset as before; eager editor objects retain full rebuild behavior. _evaluated_copy carries the immutable classification signature along with its independent derived graph copies. Connectivity edits invalidate the signature, and newly loaded old objects with no signature rebuild conservatively.

Both2024/2027 numeric tests explicitly verify position-only reuse, rewiring, standalone EP changes and CV count changes against fresh classification. Full Maya smoke also passed (relax_classification_cache_VERSION.log, smoke_classification_cache_VERSION.log). Latest fresh2027 full update median71.044ms vs previous71.992ms, with write44.917ms, coordinates23.041ms, outMesh3.733ms. Small change within run variability, not a strong broad speedup claim. Previous report preserved as relax_full_update_before_classification_2027.json. Undo restored each sample; UI/brush excluded. Live registered classes not hot-reloaded. Full60fps remains unmet.


### 2026-09-17 specialize junction vector length

_smooth_junctions now uses sqrt(v.dot(v)) for known real3vectors, equivalent to numpy.linalg.norm's vector path without generic type/shape dispatch. Reuses the handle magnitude previously calculated twice. Preserved prechange direction function in tests/junction_norm_reference.py. Maya2024/2027 sparse/dense weights and manual handles produced exactly equal complete output data against the reference; existing batch-vs-scalar fit error<=4.45e-16 (junction_norm_VERSION.log).

GUI43108 helper reloaded (registered data class still previous version): alternating12samples/mode200EP calc-only median24.076ms->23.552ms, full output equality and unchanged scene. Large GC outliers still present. Report gui_relax_junction_norm.json. Fresh latest2027 real-write/native/outMesh median70.885ms vs previous71.044ms; too small to establish meaningful full-path speedup. Previous report retained in relax_full_update_before_norm_2027.json. Both measurements exclude viewport; no60fps claim. Need larger structural reduction of whole-data serialization/evaluation, not extrapolation from this local optimization.


### 2026-09-17 numeric edit preview input (not context-enabled yet)

Added hidden nonstorable editPreviewPositions doubleArray to guide node, absolute object-space positions. Empty or topology-length mismatch falls back to normal evaluation. Valid preview bypasses CP/handle propagation, returning the typed array directly or matching outNetData positions; dirty propagation includes numeric/JSON/legacy surface outputs and viewport notifications. Existing UI never writes it yet. This is groundwork for replacing per-drag full JSON writes; commit/cancel/tool-switch/save lifecycle still must be integrated before enabling context use.

Both2024/2027 smoke passed preview typed-vs-JSON equality, legacy-vs-modern output mesh, unchanged netData, clear, Undo/Redo, invalid-length fallback (smoke_numeric_preview_VERSION.log). Existing GUI registered node not hot-reloaded.

relax_full_update.py now supports ARU_RETOPO_PREVIEW_BENCH=1 in a disposable fresh2027 process. Each200EP step captures final numeric positions into input instead of serializing/writing netData; then native coordinates and outMesh evaluate; Undo restores every sample. First median55.529ms; final57.642ms (write34.670, coordinates19.492, mesh3.687) vs preceding full-write70.885ms. Final sample also commits complete metadata via ordinary write, clears preview, proves exact native mesh point equality and committed JSON equality, outside timed span. A test initially compared nested tuples with JSON lists and failed at metadata comparison, fixed by normalizing expected JSON, then passed. Report relax_numeric_preview_2027.json. Brush/render/stroke finalization excluded and each trial resets via Undo, not a continuous stroke. Preview context integration and60fps remain incomplete; no GUI frame-rate claim.


### 2026-09-17 owned numeric relax stroke lifecycle primitive

Added editor/curvenet/relax_preview.py RelaxPreview, not yet enabled by context. relax accepts an optional internal _writer callback, default ordinary write unchanged. Preview owns pending complete metadata while Maya carries numeric positions, so successive disjoint dabs retain previous binding/manual-handle edits. Each world snapshot re-evaluates positions/matrix; no stale camera/transform cache. Guards reject incompatible old plugins, pose-driven guides, existing previews and external netData changes. Commit optionally runs existing release refinement then full write and clears numeric preview; cancel clears preview with base JSON/CPs intact. Caller still owns Undo and must wire release/tool-change/save/error hooks before enabling interactive use.

New integrated test compares3disjoint dabs + final refinement against ordinary writes using translated/rotated guide and existing CP tweaks; complete committed JSON/evaluated output exactly match. Cancel idempotence, restored CP, one Undo/Redo and empty preview after commit pass on Maya2024/2027 (smoke_relax_preview_VERSION.log). Live GUI plugin/context not replaced. No new performance claim for continuous interactive use; full60fps remains unmet. Need context lifecycle integration including save and tool switching, then GUI benchmark.


### 2026-09-17 Shift drag numeric preview context integration

RetopoGuideContext now creates RelaxPreview on first real Shift drag when editPreviewPositions exists; old running plugin without attribute retains ordinary brush path. Each brush uses one fresh world snapshot and accumulates affected metadata. Release and tool exit commit/refine once. Context tracks its own Undo chunk so errors, exit and late release do not double-close; before scene clearing/stop_scriptjob and drag/press errors cancel. Per-stroke beforeSave callback is removed on every termination.

Actual-save lifecycle test exposed that commit commands issued during Maya beforeSave did not participate reliably in gesture Undo: original JSON/CP remained changed after Undo. Changed save interruption behavior to cancel the current in-flight numeric stroke, preserving last committed data and CPs for saving. Ordinary mouse release/tool exit still commit. This is an explicit interaction limitation, not silently claimed save-commit support. Future improvement could finalize before Maya starts save rather than inside beforeSave.

Both2024/2027 full smoke passed direct context press/drag/release, tool exit, actual file save callback, cancel and injected drag exception; no remaining preview/callback/open chunk; one Undo restores original evaluated data. Tests patch only screen brush weights/viewport refresh and synthetic press setup, not commit/cancel logic. Complete ordinary-vs-preview3dab output parity remains covered. Logs smoke_preview_context_VERSION.log contain an expected injected drag error. Current live GUI registered node remains older, so new interactive path not yet available there; no GUI mouse gesture/performance/stability claim and60fps remains unmet.


### 2026-09-17 continuous large-stroke verification and fresh preview GUI

Added relax_continuous.py / run_relax_continuous.bat:8consecutive fixed200EP dabs on500patch/46528quad scene, native outMesh evaluated each step, final standard release refinement. Ordinary median86.972ms/release106.527ms; RelaxPreview median63.578ms/release132.489ms. Final complete JSON and native mesh points exactly equal; one Undo restored original evaluated guide and cleared preview. Report relax_continuous_2027.json. No screen brush selection or viewport costs; release hitch remains and60fps unmet.

Saved liveGUI43108 to unique backup D:/Dropbox/App/.codex/recovery/retopo-20260917/maya-before-numeric-preview-43108-211137.ma (654649bytes,modifiedfalse). Requested normal deferred quit; MCP connection closed during quit, process absence verified. Started newGUI via official maya.bat --2027 --foreground --no-autoload-plugins with hidden helper. PID44444 reached workspace. Existing user authorization covers MCP prompt; ComputerUse observed All Allow, first stale accessibility index failed, refreshed screenshot and clicked observed button. Pending MCP cell1052 completed confirming44444. An old Autodesk error-report window was listed; not evidence of new process crashing.

Explicitly preloaded current guide/generator/plan/draw and v4 native plugin, opened saved backup. MCP confirms new editPreviewPositions exists,46528faces,Native mesh ready. No registered-class hotreload. GPU override reenabled. New scene is ready for GUI timing/mouse tests; these are not yet established by this turn.60fps remains active/unmet.


### 2026-09-17 GUI numeric stroke and single redraw on commit

Added gui_numeric_stroke.py: deferred8consecutive scripted screen brush calls (1546+4*i,1145), real brush selection, native evaluation and synchronous GPU redraw. Ordinary vs numeric full final netData exactly equal; each stroke undone and original guide verified. Initial ordinary median122.454ms/release142.962ms, numeric99.909ms/release288.784ms. This is not physical mouse input. Saved initial report gui_numeric_stroke_before_commit_draw.json.

RelaxPreview.commit suppresses intermediate refinement/write refresh and draws only after preview input clears. RetopoGuideAccessor.write gained keyword refresh=True preserving existing default; preview commit usesFalse. Both2024/2027 integrated smoke verify exactly one final refresh and unchanged continuous/commit/cancel/save/Undo behavior (smoke_preview_commit_draw_VERSION.log). Live unregistered accessor write method updated from source AST without reloading mesh caches or registered node classes; relax_preview and diagnostic helper reloaded. Latest ordinary124.764ms/release141.354ms, numeric94.219ms/release201.518ms, exact data equality/restoredtrue. Report gui_numeric_stroke.json. Single release samples are not tail-latency guarantees.

### 2026-09-17 direct GPU buffer plus continuous numeric preview

gui_numeric_stroke.run(direct_buffer=True) temporarily creates v2 buffer geometry override, connects native positions/topology, hides ordinary mesh and selects buffer in foreground pass. Cleanup restores foreground objects/mesh visibility, deletes diagnostic shape, verifies guide restoration. Report gui_numeric_stroke_direct.json exact_final_data/restoredtrue. Ordinary direct-buffer median96.787ms/release116.054ms; numeric direct-buffer79.266ms/release178.700ms. Numeric redraw median22.001ms, native coordinate evaluation19.196ms; numeric stroke still had160.81ms outlier. Previous normal mesh numeric94.219ms had35-47ms redraw. Comparison is sequential runs, not a physical gesture frame-rate test. Direct buffer remains diagnostic and cleanup returned normal mesh display.60fps unmet, even redraw alone is above16.7ms.


### 2026-09-17 one metadata snapshot per numeric dab

GUI profile of844bound CVs among4268CVs measured full binding deepcopy median3.576ms (preview_binding_copy_profile.json), no scene writes. RelaxPreview.world now passes pending metadata as _source to _world_data; positions are still read fresh from evaluated Maya output and matrix. _evaluated_copy owns all mutable metadata once, eliminating the discarded base snapshot metadata copy. Guarded stroke still checks unchanged raw netData. Removed the second full deepcopy in preview.world.

Both2024/2027 full smoke passed snapshot mutation isolation (mutable bary list, positions, manual handles), continuous exact output, context lifecycle and Undo. Initial test attempted to mutate immutable bary pair tuple and failed; fixed to mutate its mutable enclosing list, then passed. Logs smoke_preview_single_copy_VERSION.log contain expected injected drag-error traceback. GUI helper modules refreshed without registered-node or native-cache reload. Alternating20snapshot-only samples: median5.662ms->5.237ms, exact serialized data and unchanged scene. Small0.425ms saving, most metadata copy remains. Report preview_single_copy_profile.json.

Full direct-buffer brush rerun: {'ordinary': (97.46750000340398, 116.27459999726852), 'numeric': (78.6149999985355, 108.71079999924405)} (median,release ms); exact final data=True, restored=True. Saved prior run as gui_numeric_stroke_direct_before_single_copy.json. Sequential run variability applies, no tail-latency guarantee;60fps unmet.


### 2026-09-17 GPU guide controls with continuous numeric preview

gui_numeric_stroke gained scoped gpu_controls flag restored in finally with guide geometry dirtied again. Direct-buffer+GPU control run report gui_numeric_stroke_direct_gpu_controls.json: ordinary median92.220ms/release110.109ms; numeric74.300ms/release106.222ms. Numeric redraw17.373ms vs previous22ms, but numeric samples167/154ms still occurred. Final guide data exactly matched ordinary path; scene and original GPU_CONTROLS=False restored. This remains diagnostic, not a validated physical mouse/display parity claim.

Inspection found cn.ep_indices/handle_indices forced lazy cached data to instantiate full owning EP/Handle wrappers even in numeric compute. Lazy objects now return numeric index sets without constructing wrappers; eager editor objects retain original behavior. Cache eviction test now accesses both properties before checking immediate release and compares values to eager classification, including standalone EP and self-loop. New tests numeric_indices_VERSION.log and smoke_numeric_indices_VERSION.log cover numeric ownership and all existing interactions. Live data class not replaced yet; no claimed GC latency improvement. Full60fps remains unmet.


### 2026-09-17 parallel Maya route fitting with joined workers

Native route fitter v6 uses up to four std::async workers for independent curves (batches below 16 remain serial). All DAG/owner access occurs before workers; workers read immutable MMeshIntersector state, matrices and curve-local arrays. Futures are joined before returning, including exception cleanup. Closest-point thread safety is documented by Autodesk: https://help.autodesk.com/cloudhelp/2024/JPN/MAYA-API-REF/cpp_ref/class_m_mesh_intersector.html . Sampling, convergence and fitting arithmetic are unchanged. Python cache cleared before switching DLL in GUI; registered Maya nodes were not reloaded.

parallel_routes.py compares v4 versus v6 for 1/15/16/256 curves, draft/refined, negative nonuniform scaling and a degenerate curve, with nine repeated calls each. Exact array equality passed Maya 2024 and 2027. Synthetic 256-curve draft: 2027 50.695 -> 14.792ms; 2024 49.447 -> 13.460ms. This is isolated route work, not editing FPS.

An intermediate OpenMP v5 sped up isolated routes but regressed whole GUI editing: numeric median79.926ms, native stage23.603ms; immediately repeated serial v4 control73.460ms, native17.704ms. Report gui_numeric_stroke_parallel_routes.json. v5 is not selected by the runtime. Serial route instrumentation found 322-333 curves/dab, about6-7ms, refined384 curves about28ms (gui_route_batch_profile.json). Synthetic routes are considerably more expensive and do not predict GUI savings.

Joined-worker v6 GUI report gui_numeric_stroke_joined_routes.json: ordinary91.014ms, numeric69.208ms, release87.731ms. Native stage18.212ms; exact final guide data and Undo restoration passed. All GPU diagnostics restored original mesh display and GPU_CONTROLS flag. Measurement uses 8 scripted brush calls with synchronous redraw, not physical mouse input. Current loader uses v6 for both Maya versions. Whole editing60fps remains unachieved; residual spikes and rendering cost remain.


### 2026-09-17 specialized numeric binding snapshot copy

_evaluated_copy now uses _copy_surface_bindings: owned lists for numeric barycentric pairs; immutable numeric tuples can be shared, and nonstandard/legacy forms retain deepcopy. Shared bary/list-pair aliases are preserved inside the new snapshot without sharing mutable input. Numeric read tests passed Maya2024/2027, including aliases, mutable JSON pairs, legacy triples/dictionaries, CP/transforms and parse-cache isolation. Initial edit attempt failed on local cp932 decoding before modifying files; reapplied explicitly as UTF-8 and ran actual changed tests.

A read-only fresh snapshot has few bound CVs and showed no benefit (0.716->0.770ms whole snapshot). A no-write relaxation produced the representative844bound-CV pending state: binding-only median3.117->0.768ms over30alternating samples, exact equality (binding_copy_optimized.json). Full scripted GUI GPU diagnostic median69.208->67.219ms, release83.805ms; ordinary86.167ms. Exact final data and scene restoration passed (gui_numeric_stroke_binding_copy.json). No physical-event FPS claim;60fps still unmet.


### 2026-09-17 joined workers for junction sample projection

Latest GUI profiling found four position-only projection calls per relax dab, used by the junction length solver. v7 projector parallelizes batches of512or more points with up to four joined workers; smaller calls stay serial. The sampler, solver rounds and projection algorithm are unchanged. Each worker catches failures, and all workers finish before return. parallel_routes.py now compares v4/v7 point arrays exactly at0/1/511/512/5000points, transformed/negative-scaled meshes, and rejects a non-finite point in a parallel-size batch. Route regressions remain included. Both Maya2024/2027 passed.

v7 live GUI diagnostics: numeric65.631ms/release80.333ms, ordinary84.640ms/release162.349ms, compared with previous numeric67.219ms. Report gui_numeric_stroke_parallel_points.json verifies exact ordinary/numeric final data and Undo restoration; original GPU settings restored. Runtime loader now selects v7. Benchmarked scripted brush and synchronous redraw; physical interaction and60fps remain unverified/unachieved. Next priority is native mesh and rendering update scope, rather than extrapolating small solver savings to a60fps claim.


### 2026-09-17 native stage measurement and rejected worker-team experiment

GUI benchmark now reads the existing native computeMilliseconds immediately after outPositions evaluation and before redraw, outside the recorded redraw duration. gui_native_stage_breakdown.json: numeric median64.652ms; typical native transfer/stencil2.4-4.0ms, topology0.16-0.19ms, reference projection+relaxation13.7-15.5ms, final transfer0.61-0.69ms. One input-stage76ms spike remains. This distinguishes native projection cost from earlier broad stage totals.

Tried keeping one OpenMP team over all Jacobi iterations, both single swap/barrier and parity-indexed buffers. MSVC code generation terminated with -1073741571 (stack overflow) for both shapes. Neither produced a validated usable plugin. Reverted the experiment; production mesh buffer remains v4, and no GUI plugin replacement occurred. No speedup claimed. Next target remains exact projection search/work reduction; whole60fps unachieved.


### 2026-09-17 cache-hit diagnostics and rejected triangle bounds

Added opt-in -CacheStats build flag. Only diagnostic builds compile atomic counters and aru_cache_stats; ordinary builds have no counter overhead. Native replay can record counters with ARU_TEST_CACHE_STATS=1. Diagnostic replay output hashes exactly equal v4. Across223853projection calls per warmed update,167080are exact cache hits (74.64%),56773have changed query positions, and0miss solely because of a seed change after warmup. First update cold223853; second update additionally35383seed-only misses. Therefore removing seed checks would not help this steady-state workload and could change projection-guard semantics. Diagnostic timings include counter contention and must not be used as performance measurements.

Tried per-triangle AABB lower-bound rejection inside BVH leaves. Replay v5 measured24.046ms versus prior v4 approximately16ms; extra bounds loads/calculation outweighed saved triangle calculations. Reverted this candidate, retaining production algorithm and v4 loader. Diagnostic infrastructure and cache-stat JSON remain for further workload analysis. No whole-operation speedup claimed;60fps unmet.


### 2026-09-17 BVH leaf size and recursion-call comparison

Added compile-time ARU_RETOPO_LEAF_SIZE and build -LeafSize (default8unchanged). Sequential native replay2027 measured leaf2=21.187ms, leaf4=19.259ms, baseline8=17.402ms, leaf16=17.081ms; all output hashes exactly equal. The0.32ms difference for16is too small for a claim from one run, while smaller leaves clearly lose. Default8retained. Explicit caller-side lower-bound checks before recursive calls measured17.358ms and were reverted for no material benefit.

Second immediate build initially failed to write shared mesh_buffer.obj (permission denied). Build now uses a separate .obj_<binary stem> directory per output variant, and subsequent builds succeeded. No running Maya plugin changes; no whole-operation improvement claimed. The new build flags support controlled comparisons without editing production defaults. Whole60fps remains unachieved.


### 2026-09-17 draw-pass filtering and batched brush visibility

Added diagnostic filtered_base flag to gui_numeric_stroke. Its temporary MSceneRender object set excludes foreground guide/buffer shapes from the base pass; original operation restored in finally. Object-set rendering semantics checked against Autodesk MSceneRender reference (2025 API). Result numeric65.912ms, redraw17.313ms: no useful change versus existing passes. This remains a test-only snapshot of scene membership, not a production filter (dynamic scene/isolate behavior not verified).

Scoped helper timers reported22calls over the two8-dab strokes and cleanup: GPU positions median1.251ms, configure0.529ms, upload_indices0.078ms, cached_controls0.256ms (nested inside configure). Four control batches. These do not account for the entire17ms redraw; no evidence supports a major index-upload bottleneck.

make_visibility_test now supplies an optional many(points) method. Native surface metadata supplies closest-point normals in one call; existing facing and accelerated occlusion-ray code remains identical per point. Failure falls back to scalar visibility. brush_weights first selects candidates by screen radius, uses many when present, and retains compatibility with scalar visibility callables. Visibility tests passed2024/2027 across600queries,3views (including ortho),deformation and rotation, empty batches. GUI ordinary/numeric final data and Undo restoration passed.

Read-only20alternating measurements at200EP: scalar brush selection4.738ms, batched3.567ms, exactly equal weights (brush_visibility_batch_profile.json). Whole GUI numeric63.943ms/release79.143ms, ordinary83.528ms (gui_numeric_stroke_batch_visibility.json). Small gain only; whole60fps unmet. No registered nodes/native caches reloaded: only visibility function body updated in live editor module, then relax helper reloaded.


### 2026-09-17 break EP/Handle owner cycles

Data formerly held strong lists/maps of wrappers, each wrapper strongly owning its data. Even eager temporary parse objects therefore required cyclic GC after release. Internal lists now store numeric wrapper metadata and lookup maps are WeakValueDictionary; EP/Handle remain strong owners for callers and now support weak references. Accessors construct/reuse wrappers on demand, maintaining identity while a caller holds one. Public list accessors still return strong ordinary lists of wrappers. Duplicate handle side metadata is retained; handle_at retains last-side lookup behavior. No global GC settings changed.

Tests explicitly prove eager/lazy EP and Handle owners remain live while held externally, then release immediately without gc.collect; list accessors similarly release owners. Numeric cached-data tests and full Maya smoke passed2024/2027 (smoke_weak_wrappers_VERSION.log). This is an ownership fix, not yet evidence that all GUI spikes are gone. Live GUI44444 retains old wrapper classes; do not hot-reload class/slots or registered types. A fresh GUI is required before the next whole-stroke timing.60fps remains unmet.


### 2026-09-17 fresh GUI weak-wrapper validation

Saved GUI44444 scene before restart to .codex/recovery/retopo-20260917/maya-before-weak-wrappers-44444-221202.ma (655525bytes), normal deferred quit, verified process absent. Launched approved maya.bat --2027 --foreground --no-autoload-plugins; new PID50920. User-authorized MCP All Allow clicked on observed dialog, connected successfully. Preloaded guide/generator/plan/draw/native-v4 plugins and reopened backup, enabled GPU preview. A first lifetime probe omitted required splines key and failed after successful scene load; corrected probe passed, including immediate owner release in fresh process. No class hot reload.

Same8-dab200-206EP path,46528quads: ordinary median81.094ms/release162.127ms; numeric62.529ms/release81.432ms. Exact final data and Undo restored. Numeric samples59.45,62.22,62.38,62.91,136.46,62.85,62.53,61.69ms (gui_numeric_stroke_weak_wrappers.json). GC callbacks recorded503collections; three generation2scans lasted72.624ms(17collected),71.497ms(0collected),69.515ms(0collected). Thus cycles fixed are not sufficient to remove long frames: tracing live process objects remains expensive. No global GC settings changed. Next work must reduce transient allocation/update scope; no60fps claim. GPU diagnostic node/settings restored after run.


### 2026-09-17 reuse stroke-owned preview data

RelaxPreview now borrows its own pending data for internal edits, using _world_data(...,_reuse_source=True) only when the guide world matrix is exactly identity. Evaluated typed coordinates are refreshed into owned rows; bindings/topology and the owner are retained across dabs. Public world() still returns a fully independent snapshot. Nonidentity transforms retain copied snapshots, avoiding world-space pending state on an empty brush. Any edit exception cancels the numeric preview so partly mutated pending data cannot commit. Normal relax's pre-move snapshot now copies only the positions list: the movement phase replaces changed rows instead of mutating them.

Full smoke passed2024/2027. Added identity-transform tests for actual owner reuse, independent public snapshots, empty-brush preservation, partial-data-edit failure cancellation, ordinary/numeric exact output and Undo. Existing transformed/CP/lifecycle cases remain covered. Live50920 only helper modules reloaded, with preview input verified empty first.

GUI report gui_numeric_stroke_reused_preview.json: numeric median58.808ms/release79.124ms versus prior62.529ms; ordinary80.335ms/release85.860ms. Exact final guide data and Undo restoration passed. GC callbacks counted413collections versus503in prior run (whole ordinary+numeric comparison). Three generation2scans still took67-77ms with0/18objects collected, so long-frame problem remains. Numeric sample136.1ms still occurred. No global GC changes or physical60fps claim; goal remains unmet.


### 2026-09-17 remove native busy-waiting and balance projection blocks

Added draw main-thread/process CPU timers to GUI diagnostics. Windows thread CPU accounting is quantized at15.625ms here; numeric redraw wall17.397ms consumed process CPU median250ms, indicating parallel CPU activity even after native compute. A controlled25ms idle interval in standalone replay consumed median468.75ms process CPU with v4, versus0ms with joined std::async workers. This is direct evidence of avoidable idle CPU activity; no global runtime environment or GC settings changed.

First joined/static-range candidate preserved exact output but native17.159->21.641ms and whole GUI64.160ms, worse than prior58.808ms. Then changed parallelFor to claim128-row blocks via a local atomic cursor, up to16workers for large batches and4for smaller batches. This spreads expensive spatially clustered projection misses across available cores. Workers are joined between Jacobi iterations, preserving arithmetic/order per vertex and caches. Stencil catches task creation failures rather than leaking C++ exceptions across its C ABI. Dynamic replay2027=11.225ms,2024=11.129ms; both hashes exactly equal v4 for original/relaxed poses.

GUI old50920saved maya-before-joined-50920-222511.ma, normal quit, new49428started through approved MCP launcher. Used byte-preserving isolated scene copies replacing only required plugin names. Static joined plugin was replaced with dynamic only after disabling override, clearing scene, and normal successful unload; no duplicate registered type ids. Dynamic GUI numeric57.537ms/release71.700ms, native16.901ms, redraw16.943ms/process CPU15.625ms. Ordinary79.091ms. Exact final data/Undo restored (gui_numeric_stroke_dynamic_workers.json). Improved CPU consumption substantially; whole-frame improvement remains modest,60fps unmet.

Built dynamic implementation as aru_retopo_mesh_buffer_v6 for2024/2027 and made it the new-session backend default. Existing registered versions are reused instead of trying to register another plugin with identical type id. Existing native nodes/scenes are not silently replaced. Native graph integration tests cover patch edits, CP, solver settings, subdivisions, enable/disable and Undo/Redo (native_graph_v6_VERSION.log). CurrentGUI49428still uses equivalent diagnostic dynamic binary and restored ordinary display after benchmarks.


### Owned relax adjacency cache (2026-09-17)

`curve_net_relax._relax_topology` retains immutable neighbor, incident-handle,
and junction-branch maps on the owned guide snapshot. Exact spline tuples,
standalone endpoints, and CV count invalidate the cache; position and manual
handle changes do not. Manual-handle filtering remains live at junction use.
Neighbor accumulation keeps the original set iteration order, including the
original self-loop handle behavior. No sampling or fit iterations changed.

Maya 2024 and 2027 full smoke suites passed (`smoke_topology_cache_*.log`),
including explicit cache reuse/invalidation and read-only-map checks. GUI
500-patch scripted 8-dab test: numeric median 55.941 ms, max 57.506 ms;
ordinary median 80.155 ms. Final ordinary/numeric data matched exactly and
Undo restored the scene. Evidence: `gui_numeric_stroke_topology_cache.json`.
The preceding dynamic-worker measurement was 57.537 ms; this small difference
is one run, not a controlled proof of a sustained whole-tool speedup. Physical
mouse input is not covered. The 16.7 ms / 60 fps goal remains unmet.


### Post-cache stage profile and copy safety

Scoped GUI wrappers (`gui_relax_stage_profile.py/.json`) locate remaining
numeric costs: world snapshot median 1.451 ms, brush weights 3.798 ms,
route fit 4.409 ms (native fitting included), junction smoothing 9.357 ms
(includes junction length fit 4.035 ms). Numeric write includes evaluation and
redraw and is 33.144 ms. Nested timings must not be added together. These
samples include stroke release in helper call summaries, so they are attribution
evidence rather than another whole-frame FPS benchmark. All wrappers restore
via ExitStack and the underlying GUI test restores scene/Undo.

The immutable MappingProxyType graph initially prevented deepcopy of a warmed
guide. An immutable tuple cache now returns itself from deepcopy; geometry and
spline lists still copy independently. Tests cover warm-copy ownership and
copy-only topology invalidation. Full smoke suites pass on 2024 and 2027
(smoke_topology_copy_VERSION.log). Junction reference tests pass on both:
exact direction-stage output, six batch/scalar cases max error 4.44e-16
(junction_topology_cache_VERSION.log). 60 fps remains unachieved.


### Batched junction directions

Normal normalization, branch tangent projection, and final handle-direction
blending now operate on batches. Three-component dot products use stacked
matrix multiplication; greedy opposite-branch pairing, tie order, thresholds,
manual-handle filtering, and last-write behavior remain unchanged. Fitting
sample count and iterations are unchanged.

Maya 2024/2027 reference direction outputs match exactly for dense and sparse
weights, manual handles, degenerate routes, self loops, shared handles and
zero weights at three blend amounts. Batch/scalar length-fit tolerance remains
4.44e-16 max. Full Maya smoke suites passed both versions.

Scoped GUI junction median fell from 9.357 to 6.559 ms (length fitting included).
The unprofiled 500-patch eight-dab numeric stroke median is 53.102 ms, max
126.441 ms, release 70.454 ms; ordinary median 78.939 ms. Thus latency spikes
remain and the 60 fps goal is not achieved. Exact final data and Undo restoration
passed. Evidence: gui_relax_stage_batched_vectors.json,
gui_numeric_stroke_batched_vectors.json, junction_vectors_VERSION.log,
smoke_junction_vectors_VERSION.log. Benchmarks use scripted screen coordinates,
not physical mouse input.


### Guide-render isolation

Added scoped viewport Python profile (`gui_draw_profile.py/.txt`) and a
`hide_guides=True` diagnostic option to `gui_numeric_stroke.run`; the latter
restores guide visibility in finally and is not a product setting or proposed
quality reduction. The existing benchmark still verifies final data and Undo.

Same 500-patch fixture: numeric median 53.102 ms with guides versus 42.628 ms
with guide shape hidden; redraw median 16.550 versus 7.316 ms, native evaluation
16.503 versus 15.456 ms. Evidence:
gui_numeric_stroke_direct_gpu_controls_no_guides.json. All data equality and
restoration checks passed. This isolates roughly 9 ms to visible guide work,
but cannot separate GPU execution from Maya submission overhead by itself.

Viewport-only Python cProfile reports updateDG ~2.3 ms/call, geometry populate
~1.7 ms/call, render item update ~0.7 ms/call. Profiling callback attribution is
not the full refresh wall time; do not add nested entries or claim a GPU-only
measurement. This suggests moving guide snapshot/buffer preparation out of
Python is a worthwhile next structural change. Guides remain visible after
the diagnostic; the hidden-guide result is not a usable achieved performance.


### Draw topology reuse

`gpu_guides.sync_topology` now owns a per-override snapshot of spline tuples,
endpoint/handle sets and endpoint types. Exact topology, standalone EP and CV
count/type keys rebuild it; position updates retain those containers. Guide
positions, manual handles and selection are still read fresh. Unit/integration
coverage checks ownership, reuse, spline removal, standalone addition and CP
updates. Full Maya smoke suites pass on 2024/2027.

Live Maya retained the registered override class and replaced only its updateDG
method with the disk implementation, using live module globals. No registered
class or native plugin was reloaded. GUI exact final data/Undo passed. Numeric
median 52.262 ms, redraw median 16.485 ms, compared with preceding 53.102/16.550.
The small whole-frame difference is not proof of sustained speedup. Evidence:
gui_numeric_stroke_draw_topology.json, smoke_draw_topology_VERSION.log.
The 16.7 ms target remains unmet; guide rendering still needs structural work.


### Rejected per-call shared worker team experiment

A candidate parallelStages created one joined team for initial projection and
all Jacobi rounds, with condition-variable barriers and the same 128-row block
scheduler. It retained all arithmetic and joined workers before returning.
Built only as diagnostic aru_retopo_mesh_buffer_stages.mll for 2027; never
loaded in the live GUI. Standalone replay exact hashes matched v6. Candidate
11.424 ms versus immediately rerun v6 11.718 ms; prior v6/dynamic was 11.225 ms.
This is no convincing sustained gain for the added barrier/error complexity.
Reverted this experiment from cpp/retopo.cpp; production build still v6.
Reproduction patch: retopo_stages_candidate.patch. Evidence:
native_relax_replay_stages_2027.json and native_relax_replay_v6_2027.json.
The whole-tool 60 fps goal remains unmet; no new whole-GUI speedup is claimed.


### Rejected unchanged-neighborhood solver reuse

Candidate tracked exact stage-output changes and skipped neighbor averaging
when target, current vertex, all neighbors and projection seed were unchanged.
Exact adjacency, guide weights and strength invalidated history; count,
iterations and guard already invalidated projection cache. Built only as
aru_retopo_mesh_buffer_frontier.mll for a disposable Maya 2027 process.

Original/200-EP relaxed replay hashes match v6 exactly. Candidate 12.986 ms
versus v6 11.718 ms: dependency checks added more cost than the skipped math.
Added ARU_TEST_LOCAL_CVS to native_relax_replay.py, which limits the modified
pose to N changed CVs and writes separate _localN reports. For one CV, hashes
also match exactly: candidate 5.791 ms versus v6 5.756 ms. Neither workload
supports adopting this candidate. Production cpp source restored unchanged;
reproduction patch retopo_frontier_candidate.patch. No live GUI plugin changed.
Evidence native_relax_replay_{frontier,v6}_2027{,_local1}.json.
The 60 fps whole-edit goal remains unmet.


### User-facing native mesh update wiring

RetopoWindow now exposes a fast mesh-update toggle. New UI-created generators
use the native backend when a matching binary or already registered node type
is available. Loading an existing generator reflects its actual backend without
changing it. Toggle failure restores the checkbox to actual scene state; backend
operations retain Undo. This exposes the previously diagnostic/script-only
mesh path; it does not claim a new timing improvement or enable experimental
GPU buffer preview automatically.

Installer module text and the studio Aru_RetopoTool.mod now add separate
MAYAVERSION/PLATFORM-conditioned native module entries for 2024 and 2027, so
saved scene requirements can resolve the matching v6 MLL by name. Conditions
follow Autodesk's module-description format:
https://help.autodesk.com/cloudhelp/2022/ENU/Maya-SDK/Distributing-Maya-Plug-ins/DistributingUsingModules/Maya-module-paths-folders-and.html

Native graph tests on both versions cover UI handler on/off, failure recovery,
Undo, coordinate parity, patch/settings changes, and save -> new scene ->
unload native plugin -> reopen by file requirement. Passed logs:
native_ui_reopen_2024.log and native_ui_reopen_2027.log. UI handler tests use a
minimal toggle stand-in, not physical widget clicks; visual UI interaction is
not proved by them. New UI/native path is available on disk; live diagnostic
Maya's existing window was not replaced. The 60 fps whole-tool goal is unmet.


### Actual MMB handler measurement and batched spline screen picking

Added gui_point_drag.py: selects visible EP645 near screen1546,1145, executes
8 real context _drag_impl calls with only draggerContext mouse queries scripted,
then _release_impl. Uses current viewport display, not the temporary direct GPU
buffer/controls diagnostic setup. Scoped state/optionVar restoration and one
Undo restore the exact evaluated guide data. This is not physical input.

Baseline point-drag median229.919ms, spline screen search ~138ms, release1352ms
(gui_point_drag_scalar.json). Thus earlier ~52ms relax measurements must NOT be
used as point-drag results.

New screen_hit.py batches the same25 Bezier samples per curve, uses Maya's
existing exact short-pixel projection helper, vectorizes segment distance math,
and visits qualifying segments in original order with unchanged endpoint,
visibility and tie rules. Scalar reference retained. Full smoke2024/2027 passed,
including100 exact synthetic picking cases with missing projections, exclusions,
visibility and duplicate-curve ties. GUI29 screen queries match exactly:
scalar141.088ms -> batched61.197ms (gui_screen_hit.json).

Isolated whole-handler rerun after standalone tests finished:
median144.378ms, search58.184ms, commit+display71.686ms, release1258.631ms;
changed=True and restored=True (gui_point_drag_batched_hit.json). Initial new
run overlapped standalone tests and was not used for this comparison. Much
work remains in point write/display and release, beyond remaining search cost.
The whole-tool 60fps objective is still unmet.


### Native exact screen projection

Added stateless maya_screen.cpp / build_maya_screen.ps1 and Maya2024/2027
aru_retopo_maya_screen_v1.dll. It calls the same M3dView::worldToView API with
short output coordinates, ignores the inclusion bool like the Python path,
and retains per-point MStatus failures. PyDLL calls stay on Python's main
thread; no camera or MObject survives the call. Missing binaries, batch mode,
and non-finite arrays retain the existing Python fallback.

Screen hit detection consumes native coordinate/validity arrays directly,
avoiding tens of thousands of Python tuples. GUI2027 exact projection parity
passed4468 points including offscreen/behind-camera positions, two perspective
camera rotations and an orthographic view. Original camera restored via Undo.
Native GUI29 hit queries exactly match the scalar reference: scalar140.034ms,
new batch7.465ms versus prior Python batch61.197ms. Full smoke2024/2027 passed;
2024 DLL built but interactive native screen API runtime is not yet verified on
2024 (standalone smoke deliberately uses fallback). Synthetic100-case picking
parity also passed interactively with native projection isolated by a mock.

Actual handler8-dab measurement: median91.177ms, search6.381ms,
commit/display67.905ms, release1213.129ms. Guide changed and exact Undo restored.
Compare prior144.378ms and original229.919ms. Evidence:
gui_screen_projection.json, gui_screen_hit_native_array.json,
gui_point_drag_native_screen.json, smoke_native_screen_VERSION.log.
60fps remains unmet, especially point commit/display and release.


### MMB release attribution and single compaction redraw

Extended gui_point_drag.py to record release stages and topology counts. The
16px test path attaches EP645 to spline889 at t=.4166667 on release: CVs4268
->4270 and splines1589->1590. Its ~1.2s release is a topology-changing attachment,
not a normal position-only release. Before change: patch transfer100ms,
first redraw1033ms (including DG topology rebuild), second redraw17ms.

prune_orphan_cvs_and_write now writes compacted data with refresh=False,
restores CP/skin indices, trims arrays, then redraws once. No-orphan writes keep
the existing behavior. Full smoke2024/2027 tests assert exactly one draw after
CP restoration/trimming and exact Undo restoration. Live handler confirmed one
release redraw, exact scene restoration and same topology counts; median drag
90.092ms, release1230.825ms. Rebuild variance dominates: no claimed whole-release
speedup. Evidence gui_point_drag_release_profile.json,
gui_point_drag_single_commit_draw.json, smoke_commit_redraw_VERSION.log.
The duplicated draw is removed, but topology rebuild remains the release
bottleneck and whole-edit60fps is not achieved.


### Numeric EP point-drag preview and ephemeral Undo data

PointPreview owns draft metadata during EP MMB movement and writes only typed
positions per dab. The existing handle fit, symmetry, hover and final topology
edit still run. Release takes owned data without intermediate redraw; tool exit
commits the last draft. Save/cancel/drag error clears preview and its callback.
Older plugins, pose-driven guides and first-dab orphan compaction retain the
legacy path. Main context methods were updated in place in the live diagnostic
session; no registered Maya node class was reloaded.

Dense GUI parity initially exposed a pre-existing CP offset on vertex0. Legacy
point writes clear it before release compaction; numeric take now clears CPs
before that same compaction snapshots/restores them. Added nonzero-CP coverage.

Additional Redo tests exposed ephemeral coordinates resurrecting after a save
callback canceled a stroke (save callback commands were not in Undo). Both
RelaxPreview and PointPreview now set transient arrays via API MPlug writes;
one empty->empty undoable anchor preserves a canceled stroke's Undo boundary.
Final metadata/CP changes remain ordinary undoable commands. No populated
transient coordinate array is recorded for Redo.

Full smoke2024/2027 passed legacy final-release parity, exact legacy-draft tool
exit, save callback, cancel, injected error, nonzero CP, Undo and Redo. Relax
lifecycle tests also now cover Redo and empty transient data after every ending.
Dense GUI final-data SHA256 exactly matches legacy and Undo restores source:
legacy87.613ms -> numeric55.649ms median, release1235.161ms (topology-changing
attachment still rebuilds the full plan). The earlier command-based preview
was63.580ms. Evidence gui_point_drag_numeric_preview.json,
gui_point_drag_legacy.json, smoke_point_preview_VERSION.log. Both measurements
include normal current viewport rendering, not temporary GPU-buffer diagnostics.
60fps remains unmet; physical mouse interaction and dense mirrored preview
parity still require broader verification.


### Separate mesh construction, viewport rendering, and latest relax timings

2027 live 500-patch scene, sequential scripted GUI handler benchmarks. These
include stage probes and are not directly interchangeable with unprobed results.
Point display modes (controls0/normal, controls1/normal, controls1/direct) gave
64.361 / 59.708 / 36.595ms median. Native coordinate evaluation was
8.259 / 8.080 / 8.003ms, outMesh construction 4.558 / 4.120 / 0.001ms,
and refresh 38.815 / 34.275 / 16.261ms. Thus MFnMesh construction alone
is not the main normal-vs-direct difference: downstream viewport work dominates.
The existing mesh buffer already copies a cached topology template; this was
not a newly implemented optimization.

Added optional filtered_base to gui_point_display.py: excludes foreground and
guide shapes from only the base pass, preserving their dedicated passes and
restoring the prior operation in finally. This yielded 65.037 / 59.360 /
34.300ms. Direct refresh 14.732ms, normal GPU-controls refresh 34.857ms.
All six cases exactly match final SHA256
7a67d0f39a94d505df97af4e8d42788e9770520607e14d2ba30b648e97a01ff7
and restore source. This small diagnostic improvement does not justify claiming
60fps or production-ready direct rendering. Evidence gui_point_display.json,
gui_point_display_filtered.json.

Reloaded gui_numeric_stroke to capture current ephemeral preview implementation.
Normal display numeric relax median 73.604ms (ordinary 102.018ms), native
coordinate evaluation 16.756ms and refresh 36.558ms. Direct GPU controls with
filtered base numeric relax median 52.384ms (ordinary 76.042ms), coordinate
16.549ms and refresh 17.320ms. Both comparisons have exact ordinary/numeric
final metadata parity and exact scene restoration. Evidence gui_numeric_stroke.json
and gui_numeric_stroke_direct_gpu_controls_filtered_base.json. Earlier 53.1ms
must not be presented as the current normal-display relax result. No physical
mouse input verification was performed; no display diagnostic remains enabled.
60fps is still unmet. Primary remaining work is production lifecycle integration
and validation of direct GPU rendering, plus reducing coordinate and guide work.


### Owned direct GPU display session (2026-09-18)

Added gpu_buffer_preview.BufferPreview and gpu_preview.enable(panel,
direct_buffer=True), explicit opt-in only. Temporary sibling shapes inherit the
normal output parent transform and connect to native typed arrays. API-created
nodes/connections and visibility changes do not enter the user Undo queue.
Session closure restores visibility and the original foreground selection,
deletes temporary shapes and removes all callback IDs. Before save/new/open and
Undo/Redo close the session. A closed session currently requires explicit
re-enabling; this is not yet an automatic editing-mode/default UI feature.
Instanced meshes, driven/locked/hidden visibility and non-native meshes retain
the ordinary path. Existing compatible registered preview type is reused.

Standalone lifecycle tests passed on Maya2024 and2027: close twice, real Undo
and Redo with an independent user marker, save/reopen (no serialized preview
shape, original visibility restored), new scene, locked visibility fallback,
and sibling parent inheritance. Initial dense test found foreground selections
can contain transforms instead of shapes; expanding their descendant shapes
fixed this, and the regression now uses a transformed parent selection.

Dense2027 real scripted point handler with GPU controls: median36.317ms,
topology-changing release1197.151ms, exact legacy final hash
7a67d0f39a94d505df97af4e8d42788e9770520607e14d2ba30b648e97a01ff7.
Undo restored source and closed the GPU session with no transient nodes left.
Evidence tests/gpu_buffer_lifecycle_VERSION.log and gui_buffer_session.json.
No physical mouse/camera stability claim and no60fps claim. User-facing default
and physical interaction/camera validation remain incomplete.


### Incremental GPU guide curve sampling (2026-09-18)

GPU guide positions now retain an owned control-position snapshot and float32
curve samples, recomputing only splines incident to changed controls. Topology,
control count and sampling resolution changes invalidate the cache. Returned
vertex arrays are still fresh: prior caller buffers cannot change underneath a
consumer. Source arrays may mutate in place without invalidation bugs.
Tests compare the new output bit-for-bit with the original full matmul evaluator,
check zero-motion reuse, same-count connectivity reorder and old-buffer ownership.
Full Maya smoke suites passed2024/2027 (smoke_gpu_partial_VERSION.log).

On the live1589-spline data, one changed control resampled3 splines. Isolated
400-call sampling medians: original full evaluator0.929ms, partial0.563ms;
float32 outputs exactly equal (gpu_partial_micro.json). Scripted dense point
handler36.317ms before versus35.999ms after, same final hash and exact source
Undo restoration, GPU session closed. This is a small stage improvement, not
evidence for a major whole-edit speedup or60fps. Evidence
 gui_buffer_session_before_partial.json and gui_buffer_session.json.
Existing numeric-relax direct-display stage medians identify the next solver
bottleneck: input/stencil3.063ms, topology validation0.165ms,
reference projection+relaxation12.646ms, output0.646ms.


### Surface-owned sleeping worker candidate (2026-09-18)

Rejected seed-triangle skip experiment: exact output hashes, but sequential
native replay12.103ms baseline versus13.289ms candidate. Source was restored
before the next experiment; diagnostic seedskip binary is not a release build.

Added optional ARU_RETOPO_SLEEPING_TEAM / build_mesh_buffer.ps1 -SleepingTeam.
Each Surface owns a fixed worker team that sleeps on a condition variable
between synchronous calls; generation barriers finish each Jacobi iteration.
Work remains dynamically claimed in128-row chunks. Surface destruction joins
workers; no global static pool survives plugin unload, and no idle spin loop is
introduced. Default build and existing live Maya remain on the joined-v6 path.
aru_stencil also retains its previous implementation. This candidate still needs
a fresh GUI session and whole-edit stability/performance validation.

Sequential dense replay (46873 vertices) exact two-pose hashes match v6:
2027 continuous v6 12.725ms / sleeping10.911ms;
2024 continuous v6 12.823ms / sleeping11.226ms.
2027 with25ms waits: v6 13.869ms / sleeping13.753ms, both median idle process CPU
0ms at the process timer resolution. Do not infer the continuous gain applies
unchanged to spaced user input. One-CV2027 replay6.048ms /5.453ms, hashes exact.
Evidence native_relax_replay_{v6,sleepteam}_{2024,2027}.json, *_2027_idle.json,
*_2027_local1.json. No brush or display work is included in these numbers.

native_graph.py now accepts ARU_TEST_BUFFER_VERSION (defaultv6), allowing the
same graph/Undo/Redo/CP/patch/solver/subdivision/cache-ownership/save/reopen
suite to run against candidates without changing release defaults. This suite
passed sleepteam2024/2027, including plugin unload and scene-driven reload.
The dense replay also cleared its scene and uninitialized Maya successfully.
60fps remains unproven and unmet; candidate is not yet the product default.


### Sleeping-team candidate in live GPU editing (2026-09-18)

Saved live Maya49428 to recovery/maya-before-sleepteam-20260918-001216.ma.
Made a byte-preserving copy changing only the requires line from dynamic to
sleepteam (Maya ASCII contained non-UTF8 localized strings). Cleared the scene,
unloaded the old native plugin and loaded sleepteam, then reopened the copy.
Never registered two versions of the same node type simultaneously. Original
backup remains untouched; current GUI runs the candidate binary.

Dense GPU point handler median34.268ms, exact legacy final hash and exact Undo
restoration; owned GPU session closed. Evidence gui_buffer_session_sleepteam.json.
Direct GPU controls/filtered-base numeric relax median50.142ms, native evaluation
13.562ms and refresh16.166ms; exact ordinary/numeric final metadata parity and
source restoration. Evidence gui_numeric_stroke_sleepteam.json. Earlier comparable
relax52.384ms remains in gui_numeric_stroke_before_sleepteam.json. These gains do
not establish60fps. Topology-changing release remains about1.2seconds.

Added gui_gpu_orbit.py. Initial test incorrectly assumed cmds.orbit is undoable;
Undo raised with an empty queue, and an additional Undo in finally prevented
session cleanup. This was a test-harness failure, not evidence of a renderer
crash. Closed its owned session, reopened the saved candidate scene to restore
the original camera, replaced Undo with saved MFnTransform transformation
restoration, and nested cleanup so it always closes the display session.
Corrected60-frame scripted orbit passed: median4.316ms, maximum12.544ms,
zero guide-geometry resampling calls, camera and guide restored, no temporary
preview nodes, ordinary mesh visible. Evidence gui_gpu_orbit.json. This only
establishes this scripted camera path; physical input and visual screenshot
verification of camera tracking remain outstanding. No claim that camera-only
4.3ms is whole-edit performance.


### Native GPU callback timing and stable-index candidate (2026-09-18)

Added optional ARU_BUFFER_TIMING C ABI counters for updateDG, updateRenderItems
and populateGeometry; normal builds contain no timers. build_buffer_preview.ps1
accepts BinaryName and Timing. gui_buffer_timing.py measures these inside real
scripted point drag after explicitly evaluating native coordinates.
Timing baseline: native7.945ms, refresh15.023ms. C++ callbacks median
1.023 /0.005 /0.216ms respectively, each called once per dab. Therefore the
remaining refresh time is not primarily C++ buffer upload cost.

Added optional ARU_BUFFER_STABLE_INDICES / -StableIndices candidate. It reports
isIndexingDirty only for changed topology/count, recovery from invalid data,
or newly created items. populateGeometry still fills every item Maya supplies;
it does not assume a false dirty flag guarantees reuse. Contract checked against
https://help.autodesk.com/cloudhelp/2024/ENU/MAYA-API-REF/cpp_ref/class_m_h_w_render_1_1_m_px_geometry_override.html
The flag stays opt-in, defaultv2 behavior unchanged pending broader topology tests.
Candidate: native7.788ms, refresh13.626ms; C++ callbacks1.023 /0.005 /0.054ms;
whole instrumented point median33.742ms, final legacy hash exact, Undo restored.
Evidence gui_buffer_timing_baseline.json, gui_buffer_timing.json, gui_buffer_session.json.
The reduction is modest; no60fps claim. Surface+edges were visible in a current
MCP viewport capture; this distant full-scene view is not a close-up occlusion
or component-selection verification.

Unloading v2 initially returned 'plugin in use' despite no live preview nodes.
Did not force unload: cleared a saved diagnostic scene, unloaded normally,
loaded timing then indices diagnostic versions and reopened byte-preserved copies.
Live Maya now has sleepteam native and indices preview plugins, no temporary
preview shapes and ordinary mesh visible. Both defaults remain unchanged on disk.


### Stable-index topology validation and current relax breakdown

Extended timing-only preview diagnostics to expose the actual last uploaded
surface/edge index counts and hashes, plus current render-item enable flags.
gui_buffer_topology.py uses a disposable GUI locator and compares uploaded
buffers against independently constructed Maya triangulation and sorted unique
edges. Eight cases passed2027: quad, two triangles, same-count connectivity
rewrite, empty, restored quad, invalid index, recovery, position-only edit.
Empty/invalid cases disabled both items; valid cases had exact expected counts
and hashes. This verifies callbacks fed new topology to GPU buffers, not just
that the generator output changed. Subdivision changes and2024 GUI rendering
still need separate coverage before enabling this candidate by default.

The test originally passed tuple lists directly to MFnMesh.create; corrected its
reference builder to MPointArray. It then passed all cases. Restored the dense
scene from its backup after the disposable test. Diagnostic GPU tests now reuse
an already registered compatible preview type instead of attempting a duplicate
registration ofv2 when a candidate is loaded.

Current numeric-relax stage medians (nested, not additive): world data1.073ms,
brush weights3.523ms, route fitting4.820ms (native fit_routes2.668ms), junction
smoothing6.363ms (junction lengths4.186ms), write including evaluation+refresh
29.570ms. _check0.207ms per call. Evidence gui_relax_stage_profile.json.
Remaining significant non-display work is route/junction fitting;60fps unmet.
Current Maya retains sleepteam native and topology diagnostic preview plugin,
with the dense scene restored and temporary preview shapes cleaned up.


### Junction fitting: rejected normal equations, retained sparse gather

Tried replacing per-curve SVD with a two-variable regularized normal-equation
inverse. Standalone junction comparisons passed2024/2027 (six sparse/dense/manual
cases, maximum scalar-reference error4.44e-16), but GUI junction fitting
4.186ms ->4.161ms and smoothing6.363ms ->6.451ms showed no useful gain.
Reverted this solver candidate in both source and live Maya. Original SVD,
four projection rounds, fifteen samples and all quality parameters remain.
The initial bare2024 mayapy attempt lacked NumPy; reran successfully through
run_junction_batch.bat with the standard Maya environment.

Added scoped gui_junction_profile.py. Eighteen fitting calls spent about46ms
in72 native point projections,15ms in NumPy array conversion and7ms in pinv.
The dominant avoidable Python conversion gathered the entire4268-CV network
before selecting touched splines. Now sparse selections convert only their
four-control rows; selections with4*curve_count >= total_CVs retain the original
bulk conversion to avoid expanding too many shared endpoints. No arithmetic,
manual/shared-handle behavior or projection policy changed.

Both standalone junction suites passed after this change. GUI junction fitting
median3.649ms, smoothing5.960ms versus4.186/6.363ms baseline. Whole numeric
stroke50.123ms remains around50ms; do not claim a significant whole-stroke gain.
Ordinary/numeric final data exact and source Undo restoration verified.
Evidence junction_sparse_gather_VERSION.log, gui_relax_stage_sparse_gather.json,
gui_junction_profile.txt and gui_relax_stage_before_twocol.json.
60fps remains unmet; native projection calls and display still dominate.


### Sleeping worker candidate for Maya curve projector

Added optional ARU_PROJECTOR_SLEEPING_TEAM / build_maya_projector.ps1
-SleepingTeam -BinaryName. A Projector-owned AruProjectionTeam sleeps between
calls and joins on accelerator destruction; no static workers or OpenMP idle
spin. Bulk points use128-row jobs, route fits use one-curve jobs for balanced
variable work. Existing serial thresholds (512 points /16 routes) and all fitting
parameters remain. Default build/library remainsv7. Shared worker header is
sleeping_projection_team.h; native mesh-buffer candidate remains independent.
Factored Python DLL binding initialization into _load_library(path) for controlled
candidate tests; normal library() still resolves exactly the v7 binary.

projector_team.py passed2024/2027 exact output equality for point counts
1/511/512/4096 and route counts1/15/16/200, both draft/final fit settings, against
an anisotropically scaled and translated reference. Accelerator clear/destruction
and standalone shutdown passed. Both variants median measured idle CPU0ms over
50ms wait. Candidate point projection alone was not faster in this randomized
case (2027 4096points6.0959 ->6.1494ms); route200 draft4.385 ->4.166ms.
Do not characterize this as a universal large speedup.

GUI dense numeric brush with same GPU/native-display candidates:
prior v7 points_array0.406ms, fit_routes2.656ms, junction lengths3.649ms;
sleeping points_array0.354ms, fit_routes2.455ms, junction lengths3.298ms;
adjacent restored-v7 points_array0.420ms, fit_routes2.624ms, lengths4.021ms.
Whole strokes50.123 /47.299 /51.348ms respectively, but write/refresh varied
31.989 /29.770 /32.642ms, so do not attribute all whole-stroke change to workers.
All compared runs exact ordinary/numeric final data and source restoration.
Evidence projector_team_VERSION.json/log, gui_relax_before_projector_team.json,
gui_relax_projector_team.json, gui_relax_projector_team_adjacent_baseline.json.
Live GUI was returned to v7 projector after comparison; candidate remains opt-in.
60fps remains unmet, no default promotion or publishing performed.


### Normals-only array consumer without metadata-list construction

Factored native surface buffer retrieval into _surface_buffers and added
normals_array. The native query/face/bary computation itself is unchanged, but
normal-only consumers no longer construct discarded Python positions, face
integers, barycentric tuple lists and per-row normal lists. Junction smoothing
consumes an owned contiguous normal array directly; tangent relaxation converts
the one normal array to lists for unchanged downstream scalar arithmetic.
Fallback obtains the exact same Maya normals as surface_hits fallback.

New integration checks cover exact native/fallback normals on nonuniformly
scaled reference, empty input, contiguous owned storage and result mutation.
Full smoke2024/2027 and junction comparison suites passed. GUI ordinary/numeric
final data exact and source restored, whole numeric stroke51.040ms; no clear
whole-stroke improvement over adjacent baseline51.348ms. Isolated alternating
200-query120-call comparison: full metadata normal extraction0.295ms versus
normals_array0.096ms, exact normal values. Evidence normals_array_micro.json,
gui_relax_normals_array.json, smoke_normals_array_VERSION.log and
junction_normals_array_VERSION.log. Retained for the demonstrated local cost
reduction; no major whole-edit speedup or60fps claim.


### Fused native screen-space picking candidate

Investigated bulk model/projection matrix projection with integer-boundary,
short-range and eye-plane fallback to M3dView.worldToView. All4468-point camera
cases and50000 random extreme/offscreen points matched, but native50k timing
0.842ms original versus1.557ms matrix candidate was worse. Not adopted.
The Matrix build switch remains diagnostic only; fused picker uses original
worldToView, not the matrix shortcut.

Added aru_maya_screen_segments to evaluate the same25 Bezier samples, exact
Maya pixel projection and segment distance in one C++ call, emitting compact
candidate indices/t/distance in original traversal order. Python still performs
visibility checks and best-hit selection in exactly that order. No tolerance,
sampling resolution, endpoint exclusion or visibility policy was relaxed.
Python uses the export when available; pre-existingv1 DLLs and batch/missing-DLL
conditions keep the original NumPy path. screen_segments DLL built2024/2027;
interactive candidate runtime validated2027 only so far.

29 scalar-reference cases passed exactly. Added gui_fused_hit.py:360 comparisons
against prior NumPy implementation across two perspective orientations and one
orthographic view, four tolerances, pointer offsets and alternating EP exclusions.
All selected spline,t,world hit tuples matched exactly. Median fused/NumPy times
2.556/5.103ms,2.827/5.065ms,2.371/4.839ms respectively. Camera restored by Undo.
Dense actual point handler median31.793ms, same legacy final hash and exact source
Undo restoration, GPU session closed. Evidence gui_fused_hit.json,
gui_buffer_session_fused_hit.json, screen_matrix_stress.json and gui_screen_hit.json.
Fallback smoke suites passed2024/2027. Current Maya uses segments DLL via the
module's temporary library handle; on-disk default filename remainsv1.
60fps remains unmet; display, native mesh evaluation and relax fitting remain.

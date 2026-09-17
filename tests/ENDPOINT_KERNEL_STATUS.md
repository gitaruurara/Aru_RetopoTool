# Fused endpoint surface relaxation candidate

Adopted in local standard source and 2024/2027 endpoints DLLs. GitHub remains f1ace39 until the next push.

Candidate combines EP first projection, normal at projected point, ordered neighbor average, tangential displacement, final projection/binding in one joined C++ call. It preserves projection order; only discarded first-query metadata is omitted. Local Python packing includes weighted EPs and neighbors only, preserving their adjacency order. Four native workers above 64 EPs; all scene ownership checks before workers, immutable intersector queries only.

Raw sphere/cube, reflection/nonuniform transform, 0/1/63/64/500 EP, smooth on/off: 40 exact cases per Maya 2024 and 2027 passed. Initial full-array candidate continuous 200 EP stroke passed exact guide and mesh plus Undo; local packing GUI passed whole coordinate hashes and Undo.

Local packing GUI, same 500 patches / 46,528 faces, viewport 1600x1000, brush (841,688), scripted real brush handler plus synchronous redraw:
gui_endpoint_kernel: [(4, 40.45439999026712), (8, 39.894199988339096), (8, 37.22110000671819), (4, 38.90109999338165)]
gui_endpoint_kernel_reverse: [(8, 39.406100011547096), (4, 41.26959999848623), (4, 42.07590001169592), (8, 38.63690000434872)]
In reports label 4 means standard, 8 means fused EP candidate (not eight workers). Mean trial medians: {4: 40.67524999845773, 8: 38.789575002738275}.
The historical candidate measurements above preceded integration. See release validation below. No physical input latency or 60 FPS claim.

## Release validation

Production ABI `aru_maya_relax_endpoints_v1` includes neighbor-array length validation before worker access. Python returns None for missing accelerator/export; relax retains its existing implementation as fallback. Nonfinite/invalid input raises rather than writing incomplete outputs. No point/handle mutation occurs inside the C++ call.

Both 2024/2027 release cases passed exact 40-case parity, retained output ownership, reference transform and mesh deformation invalidation, nonfinite point/weight rejection, invalid neighbor rejection, missing accelerator, empty input and old tangents DLL. Actual old-DLL relaxation integration passed projection/topology/Undo/Shift checks. Both full Maya smoke suites passed, including symmetry and hard-surface tests.

Disposable GUI PID 38780 loaded actual standard functions plus endpoints DLL (native mesh still certificates, same solver source as certified): numeric relax 38.563/38.870/38.753 ms, point 27.312 ms. All final guide and full mesh hashes match the retained pre-endpoint baseline. Undo restored input. This is a source-method integration measurement, not a freshly launched entire release bundle. See gui_endpoint_integrated.json.

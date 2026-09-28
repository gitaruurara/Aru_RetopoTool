# Route worker count trial (not adopted)

2027 candidate `aru_retopo_maya_projector_routes8.dll` uses RouteWorkers=8; standard remains 4.
Raw route/binding parity passed for zero, one, 15, 16 and 500 curves, draft/refined, sphere/cube and transformed geometry. Continuous 200 EP / eight-dab edit restored Undo and exact guide/mesh coordinates.

Whole CPU edit medians in alternating trials (no viewport):
- four workers: 45.90, 37.88, 45.99 ms
- eight workers: 46.82, 46.43, 44.96 ms

No consistent whole-edit improvement, so no default change or GUI FPS claim. The timings differ from earlier sessions; only within-run comparisons are meaningful.
Results: route_workers_cases_2027.json, route_workers_stroke_2027.json.
Build: cpp/build_maya_projector.ps1 -MayaVersion 2027 -BinaryName aru_retopo_maya_projector_routes8.dll -RouteWorkers 8.
The standard distribution was pushed separately as f1ace39, including production binaries only.

GUI ABBA comparison at 1600x1000, same brush (841,688), 500 patches, ~46k faces: 4 workers 40.801/40.119 ms; 8 workers 40.126/39.824 ms. Exact final guide/mesh hashes, nonempty brush, Undo all passed. Only ~0.5 ms difference in the mean of trial medians; retain 4 until stronger benefit. GUI report: gui_route_workers.json.

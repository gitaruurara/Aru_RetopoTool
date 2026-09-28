# Batched visibility: adopted 2026-09-18

Production files: cpp/maya_visibility.cpp, cpp/build_maya_visibility.ps1,
editor/curvenet/maya_visibility.py, curve_net_edit.make_visibility_test.
Maya 2024/2027 dedicated DLLs are present (aru_retopo_maya_visibility.dll).

The many-points path requests only normals via the already-validated normals
API, avoiding unused position/face/barycentric Python objects. Visibility rays
then run in one serial C++ call on the Python main thread. Uses identical Maya
closestIntersection parameters, float source/direction conversion, normal lift,
front/back dot rule, orthographic direction and perspective ray length. PyDLL
retains the GIL; no scene APIs run on added worker threads. Missing DLLs or
failed native calls retain the old per-point path. Scalar visibility unchanged.

Validation on Maya 2024 AND 2027:
- 600 points x 3 views x 3 deformation/rotation states match unaccelerated
  scalar Maya results; both perspective and orthographic cameras, occlusion.
- Root and DAG instance, negative/nonuniform scale and translation, three
  views, occlusion on/off: another 7,200 matching classifications per version.
- Empty queries; simulated missing DLL correctly falls back to scalar results.
- Full integration smoke suites pass: smoke_visibility_2024/2027.log.

GUI isolated Maya 2027, same 500-patch / 46,528-face scene, 1600x1000,
first brush dab affects 443 EP. Native rays alone: baseline 44.121 / 44.277 ms,
candidate 42.632 / 43.484. Normal-only query + native rays: baseline 43.133 /
45.080, candidate 41.718 / 41.285. ABBA, exact guide/mesh output hashes and
Undo restoration; 32 native batch calls recorded for each candidate experiment.
See gui_visibility.json and gui_visibility_normals.json.

Then loaded ONLY the adopted function definitions (draw updateDG and visibility)
from standard source into disposable PID 38780, without replacing live Maya
node types or reloading callback-owning modules. Production visibility DLL path
is recorded in gui_visibility_integrated.json. Integrated relax medians:
40.357 / 39.713 / 39.100 ms; point median 27.117 ms. All final guide/complete
mesh-coordinate hashes and point final hash match the retained baseline.
Native mesh buffer in this GUI remains the certificate candidate whose identical
solver was integrated earlier; production certified MLL tests are recorded
separately. No claim that a fresh whole-GUI launch of the production bundle was
measured here. No 2024 GUI FPS claim. These are scripted handlers + synchronous
GPU redraw, not physical mouse latency. 60 FPS remains unmet.

Next priorities from current per-stage profiling: route fitting (~7.3 ms),
junction fitting (~5.3 ms), and remaining mesh/draw/update cost. Timing scopes
are nested and cannot simply be summed. Prior fixed-coordinate empty selections
must never be counted as a valid speed result; GUI brush tests now reject them.

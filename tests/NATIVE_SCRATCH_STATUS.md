# Persistent native relaxation scratch buffers

Surface retains target/current/next vectors instead of allocating and zeroing
three vertex-sized arrays for every aru_relax call. resize handles count changes;
every current and target row is overwritten before use, and every next row is
written in each iteration. Subdivision/projection arithmetic and order unchanged.
Enabled with ReuseScratch in the scratch binary, together with SleepingTeam,
InputCache and IncrementalStencil. No extra worker threads or approximations.

Separate-process recorded dense-scene replay: 46,873 vertices / 46,528 faces.
2027 broad change: 10.103 -> 9.144 ms; one CV: 4.196 -> 3.192 ms.
2024 broad change (candidate measured first): 10.340 -> 9.597 ms.
Old/new pose hashes exactly match in each comparison. Native graph tests pass
2024/2027, including DG/serial/parallel evaluation, subdivision count changes,
0/5/3 relaxation iterations, empty selection, retained output ownership,
Undo/Redo and scene save/reopen.

Default native_backend and viewport_session now select the scratch binary for
new sessions. Both Maya versions built. An already registered older node plugin
is never force-unloaded; the user's open Maya was left alone. Existing saved
scenes may still require their original plugin version.

Timings measure native coordinate evaluation only, excluding brush, write,
draw and display. Whole-frame 60 FPS remains unmet/unverified for this change.

# Native input cache candidate

Build: cpp/build_mesh_buffer.ps1 -MayaVersion 2027 -SleepingTeam -InputCache
-BinaryName aru_retopo_mesh_buffer_inputcache.mll (also built for 2024).
This is a separate candidate; the default and live Maya plugin remain unchanged.

Reference vertices/triangles and adjacency/anchor arrays are reused only in normal
DG contexts while their inputs are clean. setDependentsDirty and preEvaluation
invalidate them. Vertex count also invalidates adjacency. Non-normal contexts
force a rebuild and leave the cache dirty for the next normal evaluation. Invalid
inputs leave dirty flags set, allowing recovery when valid input is restored.

native_input_cache.py passed in 2024/2027: animated reference transforms, mesh
vertex edits/Undo, empty mesh failure/recovery, subdivisions, DG/serial/parallel.
native_graph.py also passed both versions: data ownership, solver/guide settings,
enable/disable Undo/Redo, subdivisions, scene save/reopen and plugin lookup.

Recorded 500-patch replay, 46,873 vertices, native coordinate evaluation only:
2027 candidate 10.524 ms, adjacent sleeping-team baseline 10.968 ms median.
2024 candidate 11.015 ms. Both pose hashes match the existing CPU baseline exactly.
This small timing difference does not establish 60 FPS or a whole-editor speedup.
Interactive deployment and non-normal context regression coverage remain pending.

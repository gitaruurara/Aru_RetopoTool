# Native coordinate pipeline

With NumericPipeline enabled, subdivision coordinates remain in an owned
std::vector through projection, relaxation and finite-value validation. Create
MDoubleArray once at output instead of converting refined -> Maya -> C++ -> Maya
and copying again for validation. Cached stencilValues stay separate from the
mutable projection buffer; published MFnDoubleArrayData remains independently
owned. Mesh output still uses its existing safe copy path.

Built numeric binaries for 2024 and 2027 using SleepingTeam, InputCache,
IncrementalStencil, ReuseScratch and NumericPipeline. Both native_graph suites
pass: retained output ownership, DG/serial/parallel evaluation, subdivisions,
solver settings, empty patches, Undo/Redo, save/reopen.

46,873 vertex / 46,528 face recorded replay vs scratch baseline:
2027 broad: 9.624 -> 8.830 ms; one CV: 3.110 -> 2.463 ms.
2024 broad: 9.376 -> 8.719 ms. Pose hashes exactly match per comparison.
Timings cover coordinate evaluation only, excluding editing and drawing.

Default native_backend and viewport_session select numeric for new sessions.
No live artist-session reload and no claim of whole-interaction 60 FPS.

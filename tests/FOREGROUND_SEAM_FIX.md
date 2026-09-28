# Foreground and symmetry seam fix ? 2026-09-18

## Reproduction and fix
- The current Toriel scene has retopo geometry around world Y=180?193 and Isolate Select enabled. The locator reported no geometry bounds. The filtered VP2 foreground pass omitted it, leaving the ordinary depth-tested base drawing visible through parts of the reference surface.
- The native preview now returns bounds from the actual positions. Isolate copies are enabled and index buffers are selected by primitive type instead of a name which Maya can change for a copy.
- Current-scene guide data copied into memory reproduced center EP26 drifting from X=0 to X=0.1992921084 on one relax step. Applying the existing symmetry constraint to the endpoint itself keeps X=0; the source scene guide data was unchanged.
- Surface projection is checked again for seam crossing, after projection as well as before it.

## Validation
- Maya 2024 and 2027: preview bounds at an off-origin location and after moving positions; center relax in world and transformed object space; projection crossing in both directions.
- Maya 2027 existing symmetry_editing.py: EP/handle drag, seam lock, manual handles, mirrored patches, repeated mirroring, Undo/Redo.
- Maya 2027 existing soft_move.py: falloff, fixed weights, surface projection, symmetry, center strokes, unchanged topology.
- GPU check in the existing scene used the exact final native preview implementation (only temporary node type/name changed), including stable index buffers. The fixed foreground faces are visible in foreground_fix_current.png. Scratch nodes were removed afterward.
- Both production bin/2024 and bin/2027 aru_retopo_buffer_preview_fast.mll were rebuilt/replaced. Loaded old DLL images were preserved as *_before_bounds.mll; Maya must restart to use the new native node implementation.
- Existing edits to mirror tolerance, mirror endpoint matching and gpu_preview.py were preserved.
- The artist scene was not saved or replaced. Current camera and selection were restored. Python symmetry fixes were reloaded; native display changes take effect after restart.

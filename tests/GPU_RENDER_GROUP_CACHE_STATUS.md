# GPU control render-group reuse

configure_controls previously rebuilt the style-to-index grouping and uint32
arrays every render-item update even when cached_controls returned unchanged
classification. render_control_groups now retains these arrays using the owned
cached classification tuple as its identity key. Position changes use fresh
vertices but reuse indices. Selection, mirror, manual handles, style and topology
still invalidate through cached_controls. Arrays are marked read-only.

Maya smoke suites pass 2024 and 2027, including exact reference group contents,
position-only reuse and selection/style/topology invalidation. Dense fixture
isolated group preparation median: 2027 0.199 -> 0.049 ms; 2024 0.167 -> 0.040 ms.
These timings exclude Maya render-item API calls and GPU drawing. Index buffers
are still uploaded when populateGeometry requests them; this change only avoids
rebuilding the Python/NumPy source arrays. No artist-session reload or whole
interactive-frame measurement was performed. 60 FPS remains unmet.

# Merged center boundary patch repair

Merged symmetry endpoints left duplicate coincident Bezier splines. Native halfedge traversal treated these as separate edges and lost adjacent regions.

Region extraction now collapses only geometrically coincident splines with shared endpoint IDs, including reversed orientation, and maps native results back to original spline IDs. Distinct curves sharing endpoints remain intact. Saved selections and patch transfer canonicalize equivalent boundary IDs. Guide data is not rewritten.

Validation: Maya 2024 and 2027 pass the merged-seam fill/remove/Undo/Redo integration test, 16 existing core/region tests, and existing patch-transfer test. The captured scene fixture recovers 22 regions versus 14 before, and generates 368 quads at subdivision 2. Current interactive patch candidates rebuild successfully. No scene save was performed.

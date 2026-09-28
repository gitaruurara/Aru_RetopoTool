# Remove leftover curves after merging endpoints

Endpoint welding now removes collapsed splines and coalesces newly shared endpoint pairs, preferring the pre-existing destination boundary. Oriented spline ancestry preserves confirmed patches through border welds, spline reindexing, and CV compaction. Local-edit transfer receives the same ancestry. Symmetric drag-release merges both sides; endpoint lookup excludes coincident dragged points when finding the destination partner.

Validation: Maya 2024/2027 pass physical weld tests with differently shaped/reversed boundaries, confirmed and unconfirmed adjacent patches, real commit/compaction, Undo/Redo, collapsed edges, and real symmetric release. Existing 16 core/region tests, legacy duplicate patch tests, and patch-transfer tests pass in Maya 2027.

Current scene repaired: 160 -> 152 splines, no duplicate endpoint pairs or orphan controls. All 62 confirmed patches remain (984 quads). Backup: merge_leftover_repair_backup.json. No scene file was saved.

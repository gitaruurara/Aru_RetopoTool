# Symmetric manual handle editing

Fixed asymmetric behavior in four paths:
- A merged seam handle no longer stops mirror lookup at itself before checking its duplicate partner.
- Moving an endpoint translates fixed handles on both the driving and mirrored endpoint.
- Releasing a handle fits the driving spline once and mirrors its controls and manual flags, avoiding independent refit drift.
- Reset Manual Handles includes the mirrored handle before filtering fixed flags, including a selected automatic handle with a fixed counterpart.

Maya 2024 and 2027 pass real handle drag/release, fixed-handle EP following, reset Undo/Redo, both driving sides, world/object symmetry and reciprocal seam tests. Existing symmetry editing tests pass in Maya 2027. The current scene previously had eight nonreciprocal handle mappings; after reload it has none. Scene guide data was not rewritten or saved.

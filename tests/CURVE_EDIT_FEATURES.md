# Curve editing validation

- Left click on a guide curve inserts a point; successive curve clicks connect and split filled patches.
- Ctrl + middle click inserts a guide loop with a yellow hover preview. Traversal follows quad patches and supports symmetry.
- Ctrl + Shift + middle drag extrudes boundary curves. Native output overlay routing and preview lifetime are corrected.
- Ctrl + middle drag over a patch retains loop reduction; surviving rows are redistributed.

Validated with Maya 2024 and Maya 2027 standalone: click insertion, patch splitting, symmetric loop insertion, native preview routing, gesture routing, extrusion cancel/commit, Undo/Redo, repeated reduction spacing, general patch interpolation, and native stencil parity. Existing 21 core/region/local-edit tests also pass.

Live Maya viewport confirmed the extrusion preview (extrude_preview_fixed.png). Updated code was reloaded into the existing editor. Validation preview geometry was not committed and the scene was not saved.

# Owned preview snapshot experiment

The Maya input data MObject is copied during evaluation, so object identity is
not a useful cache key. The first prototype always fell back and was replaced.
The tested candidate tracks editPreviewPositions attribute-set and connection
changes, ignores output evaluation notifications, and only reuses a pending
owned snapshot for an identity guide transform and unconnected preview input.

Maya 2024 and 2027 state tests passed: public copy ownership, external same-size
numeric writes, transform changes, connected upstream edits, cancellation and
node deletion. Callbacks are removed on commit/cancel and monkeypatch restore.
500-patch / 200-EP eight-dab standalone comparison had exactly equal final
metadata, guide coordinates and mesh coordinates, with Undo restored.

GUI 2027 PID 48640 / 500-patch scene / normal direct GPU controls: baseline
42.4328 ms, candidate 42.8654 ms numeric brush median including synchronous
redraw. Candidate reused 8 snapshots, fell back once, and saw no invalidations.
Both ordinary-versus-numeric final-data checks and Undo restoration passed.
See gui_owned_snapshot.json. No physical mouse latency measurement.

Not promoted: no full interaction improvement. Production remains unchanged.
The next large target is fusing guide solve/transfer, not bypassing evaluation
with increasingly complex Python cache ownership. 60 FPS is not achieved.

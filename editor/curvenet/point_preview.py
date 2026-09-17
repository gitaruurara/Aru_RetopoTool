"""Owned position-only EP drag; release may change topology after take()."""
from maya import cmds
from .relax_preview import RelaxPreview
from .curve_net_relax import _evaluated_copy
from . import curve_net_edit as edit
from .curve_net_data import RetopoGuideData


class PointPreview(RelaxPreview):
    def read(self):
        self._check()
        if self.pending is None:
            base=RetopoGuideData.from_json_cached(self.raw)
            # Own editable containers while reusing the already classified cache.
            # Use base positions: evaluating CP offsets here would change legacy
            # point-drag behavior and apply offsets a second time at release.
            self.pending=_evaluated_copy(base,[v for p in base.positions for v in p])
        return self.pending

    def commit(self):
        super().commit(refine=False)

    def take(self):
        """Return owned metadata for the final topology edit, without drawing."""
        self._check()
        pending=self.pending
        # Legacy point writes already cleared CP offsets before release-time
        # compaction. Do the same before that code snapshots/remaps CPs.
        if pending is not None:edit._reset_control_points(self.node,len(pending.positions))
        self._set_positions([])
        self.pending=None;self.closed=True
        return pending

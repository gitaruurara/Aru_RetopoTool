"""Explicit lifetimes for data handles owned by Maya plugs."""
from contextlib import contextmanager


@contextmanager
def plug_handle(plug):
    """MPlug.asMDataHandle transfers cleanup responsibility to the caller."""
    handle = plug.asMDataHandle()
    try:
        yield handle
    finally:
        plug.destructHandle(handle)


def double3_array_values(plug):
    """Copy existing logical elements from one evaluated, owned plug handle."""
    import maya.api.OpenMaya as om
    values={}
    with plug_handle(plug) as handle:
        array=om.MArrayDataHandle(handle)
        try:
            for physical in range(len(array)):
                array.jumpToPhysicalElement(physical)
                # outputValue is the supported element accessor for a handle
                # returned by MPlug.asMDataHandle (inputValue is not).
                values[array.elementLogicalIndex()]=array.outputValue().asDouble3()
        finally:
            del array
    # A plug-level array handle does not evaluate dirty child connections.
    # Refresh only connected elements through plugs; keep the common unconnected
    # tweak array on the single-snapshot path.
    connected=set()
    for connection in om.MFnDependencyNode(plug.node()).getConnections():
        if not connection.isDestination:continue
        element=connection
        while element.isChild:element=element.parent()
        if element.isElement and element.array()==plug:
            connected.add(element.logicalIndex())
        elif element==plug:
            plug.evaluateNumElements()
            connected.update(plug.getExistingArrayAttributeIndices())
    for index in connected:
        element=plug.elementByLogicalIndex(index)
        values[index]=tuple(element.child(axis).asDouble() for axis in range(3))
    return values


class ReferenceMeshSnapshot:
    """Owned mesh copies invalidated by dirtiness of this input plug only."""
    def __init__(self, plug):
        import maya.api.OpenMaya as om
        self.plug = plug
        self.attribute = plug.attribute()
        self.revision = 0
        self.cached_revision = -1
        self.cached = None
        self.callback = om.MNodeMessage.addNodeDirtyPlugCallback(plug.node(), self._dirty)

    def _dirty(self, node, plug, *unused):
        if plug.attribute() == self.attribute:
            self.revision += 1

    def read(self):
        import maya.api.OpenMaya as om
        if self.cached is not None and self.cached_revision == self.revision:
            return self.cached
        revision = self.revision
        with plug_handle(self.plug) as handle:
            mesh = om.MFnMesh(handle.asMeshTransformed())
            points = tuple((p.x, p.y, p.z) for p in mesh.getPoints())
            _, indices = mesh.getTriangles()
            triangles = tuple(indices)
        self.cached = (points, triangles)
        self.cached_revision = revision
        return self.cached

    def close(self):
        import maya.api.OpenMaya as om
        if self.callback is not None:
            om.MMessage.removeCallback(self.callback)
            self.callback = None
        self.cached = None
        self.cached_revision = -1

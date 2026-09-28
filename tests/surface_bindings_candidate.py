"""Not adopted: isolated allocation savings did not improve full stroke."""
from Aru_RetopoTool.editor.curvenet.maya_projector import get_projector, surface_hits, _surface_buffers
def surface_bindings(mesh_fn, queries):
    """Read face/barycentric bindings without unused position/normal lists."""
    if len(queries) == 0:
        return []
    projector = get_projector(mesh_fn)
    if projector is None:
        return [(face, bary) for _position, _normal, face, bary in surface_hits(mesh_fn, queries)]
    output, metadata = _surface_buffers(projector, queries)
    return [(int(meta[0]), [(int(meta[i+1]), float(row[i+6]))
                           for i in range(meta[4])])
            for row, meta in zip(output, metadata)]



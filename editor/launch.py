"""Retopology-only entry points for inherited guide editor menus."""
def load_plugin():
    from Aru_RetopoTool.guides import load
    load()

def show_curvenet_ui():
    from Aru_RetopoTool import show
    return show()

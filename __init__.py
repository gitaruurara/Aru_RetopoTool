"""Curve-guided surface retopology for Maya."""
__version__ = "0.1.0"
import os as _os
import sys as _sys
_dependencies = _os.path.join(_os.path.dirname(__file__), '_deps', 'py{}{}'.format(*_sys.version_info[:2]))
if _os.path.isdir(_dependencies) and _dependencies not in _sys.path:
    _sys.path.insert(0, _dependencies)


def show():
    from .ui import show as open_window
    return open_window()

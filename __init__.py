"""Curve-guided surface retopology for Maya."""
__version__ = "0.1.0"
import os as _os
import sys as _sys
_dependencies = _os.path.join(_os.path.dirname(__file__), '_deps', 'py{}{}'.format(*_sys.version_info[:2]))
if _os.path.isdir(_dependencies) and _dependencies not in _sys.path:
    _sys.path.insert(0, _dependencies)

# Maya's bundled NumPy matches its Python ABI. A project-wide PYTHONPATH may
# otherwise shadow it with binaries built for a different Maya/Python version.
# Resolve it once without permanently reordering the host's package search path.
if 'maya' in _sys.modules and 'numpy' not in _sys.modules and not _os.path.isdir(_dependencies):
    _maya_site = _os.path.join(_os.environ.get('MAYA_LOCATION', ''), 'Python', 'Lib', 'site-packages')
    if _os.path.isfile(_os.path.join(_maya_site, 'numpy', '__init__.py')):
        import importlib as _importlib
        _saved_path = list(_sys.path)
        try:
            _sys.path.insert(0, _maya_site)
            _importlib.import_module('numpy')
        finally:
            _sys.path[:] = _saved_path


def show():
    from .ui import show as open_window
    window=open_window()
    from maya import cmds
    if not cmds.about(batch=True):
        from . import viewport_session
        viewport_session.start()
    return window

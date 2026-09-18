"""Dependency failures must preserve an already active viewport session."""
from contextlib import ExitStack
from unittest.mock import patch
from Aru_RetopoTool import viewport_session as session


def run():
    for failure in ('file','core','projector','visibility','screen'):
        with ExitStack() as stack:
            stack.enter_context(patch.object(session,'_active',True))
            stack.enter_context(patch.object(session.cmds,'modelPanel',return_value=True))
            stack.enter_context(patch.object(session.cmds,'pluginInfo',return_value=[]))
            stack.enter_context(patch.object(session.Path,'is_file',return_value=failure!='file'))
            for owner,name,kind in ((session.native_core,'library','core'),
                                    (session.maya_projector,'library','projector'),
                                    (session.maya_visibility,'library','visibility'),
                                    (session.maya_screen,'load_library','screen')):
                stack.enter_context(patch.object(owner,name,side_effect=RuntimeError(kind) if failure==kind else None))
            mutations=[stack.enter_context(patch.object(owner,name)) for owner,name in (
                (session,'stop'),(session.cmds,'loadPlugin'),(session.native_backend,'enable'),
                (session.gpu_preview,'enable'),(session.gpu_preview,'disable'))]
            before=(session.native_backend.BINARY_NAME,session.gpu_guides.GPU_CONTROLS,session.maya_screen._LIB)
            try:session.start('testModelPanel')
            except RuntimeError as exc:
                if failure!='file':assert str(exc)==failure
            else:raise AssertionError('Dependency failure was ignored: '+failure)
            for mutation in mutations:mutation.assert_not_called()
            assert session.active()
            assert before==(session.native_backend.BINARY_NAME,session.gpu_guides.GPU_CONTROLS,session.maya_screen._LIB)
    print('PASS viewport dependency preflight preserves active session and scene')

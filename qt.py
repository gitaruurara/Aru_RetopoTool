"""Use the studio Qt wrapper when available, or a standalone Maya-owned window."""
try:
    from Aru_lib.core.Qt import *
except ImportError:
    try:
        from PySide6.QtCore import *
        from PySide6.QtGui import *
        from PySide6.QtWidgets import *
        from shiboken6 import wrapInstance
    except ImportError:
        from PySide2.QtCore import *
        from PySide2.QtGui import *
        from PySide2.QtWidgets import *
        from shiboken2 import wrapInstance

    def getMayaMainWindow():
        from maya import OpenMayaUI
        ptr=OpenMayaUI.MQtUtil.mainWindow()
        if not ptr:raise RuntimeError('Open the tool in interactive Maya.')
        return wrapInstance(int(ptr),QMainWindow)

    class AruMainWindow(QMainWindow):
        def __init__(self,parent=None,object_name=None):
            super().__init__(parent or getMayaMainWindow(),Qt.Window)
            self.setObjectName(object_name or type(self).__name__)
            self.setProperty('saveWindowPref',True)

        def show_and_raise(self):
            self.show();self.raise_();self.activateWindow();return self

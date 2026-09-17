"""Maya 上の Qt ウィンドウ表示ヘルパ (3 つの UI で共通)。

macOS の既知の問題:
  * 親を持つ QWidget ウィンドウを raise しても Maya メインウィンドウの裏に回る
    → Qt.Tool フラグを付けると親の上に留まる。
  * 黄色ボタンで Dock に収納 (最小化) されると show()/raise_() では戻らない。
  * ディスプレイ構成が変わると画面外に残る。
"""
from __future__ import annotations

try:
    from PySide6 import QtCore, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtWidgets


def maya_main_window():
    try:
        import maya.OpenMayaUI as omui
        try:
            from shiboken6 import wrapInstance
        except ImportError:
            from shiboken2 import wrapInstance
        ptr = omui.MQtUtil.mainWindow()
        if ptr:
            return wrapInstance(int(ptr), QtWidgets.QWidget)
    except Exception:
        pass
    return None


def find_window(object_name: str):
    app = QtWidgets.QApplication.instance()
    if app is None:
        return None
    for w in app.topLevelWidgets():
        if w.objectName() == object_name:
            return w
    return None


def bring_to_front(window) -> None:
    if window.isMinimized():
        window.setWindowState(
            (window.windowState() & ~QtCore.Qt.WindowMinimized)
            | QtCore.Qt.WindowActive)
    window.showNormal()
    g = window.frameGeometry()
    if not any(s.geometry().intersects(g) for s in QtWidgets.QApplication.screens()):
        screen = QtWidgets.QApplication.primaryScreen()
        if screen is not None:
            window.move(screen.availableGeometry().center() - g.center() + g.topLeft())
    window.raise_()
    window.activateWindow()


def show_tool_window(window) -> None:
    """Maya メインウィンドウの上に留まるツールウィンドウとして表示する。"""
    window.setWindowFlags(window.windowFlags() | QtCore.Qt.Tool)
    bring_to_front(window)
    # macOS では表示直後の activateWindow が無視されることがある
    QtCore.QTimer.singleShot(100, lambda w=window: bring_to_front(w))


def show_dockable(name: str, label: str, factory, close_command: str = "",
                  width: int = 720, height: int = 460):
    """Maya の workspaceControl にウィジェットを格納して表示する。

    Maya ネイティブのパネルなのでメインウィンドウの裏に回らず、ドックもできる。
    *factory(parent)* が中身の QWidget を返す。既にあれば作り直す。
    """
    import maya.cmds as cmds
    import maya.OpenMayaUI as omui
    try:
        from shiboken6 import wrapInstance
    except ImportError:
        from shiboken2 import wrapInstance

    if cmds.workspaceControl(name, q=True, exists=True):
        cmds.deleteUI(name)
    kwargs = dict(label=label, retain=False, floating=True,
                  initialWidth=width, initialHeight=height)
    if close_command:
        kwargs["closeCommand"] = close_command
    cmds.workspaceControl(name, **kwargs)
    ptr = omui.MQtUtil.findControl(name)
    host = wrapInstance(int(ptr), QtWidgets.QWidget)
    content = factory(host)
    lay = host.layout()
    if lay is None:
        lay = QtWidgets.QVBoxLayout(host)
        lay.setContentsMargins(0, 0, 0, 0)
    lay.addWidget(content)
    cmds.workspaceControl(name, e=True, restore=True)
    return content

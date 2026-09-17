"""
Aru_RetopoTool.editor — 共通ロガー
================================
パッケージ全体で使える logging.Logger を提供する。

- Maya Script Editor へのストリーム出力 (INFO 以上)
- ファイルハンドラー (DEBUG 以上) — ログは
  ``<TEMP>/Aru_RetopoTool.editor.log`` に書き出される

Usage
-----
::

    from Aru_RetopoTool.editor.logger import get_logger
    log = get_logger(__name__)      # or get_logger("PCDeformer")
    log.info("hello %s", "world")
    log.debug("detailed stuff: %.4f", value)
"""

from __future__ import annotations

import logging
import os
import tempfile

_PACKAGE = "Aru_RetopoTool.editor"
_LOG_FILE = os.path.join(tempfile.gettempdir(), "Aru_RetopoTool.editor.log")
_ROOT_LOGGER_NAME = _PACKAGE

# 初期化済みフラグ — 二重にハンドラーを追加しないため
_initialized = False


def _ensure_root() -> logging.Logger:
    """パッケージルートのロガーにハンドラーを付与する (一度だけ)。"""
    global _initialized
    root = logging.getLogger(_ROOT_LOGGER_NAME)

    if _initialized:
        return root

    root.setLevel(logging.DEBUG)
    root.propagate = False           # Maya の root logger に流さない

    fmt = logging.Formatter(
        "[%(name)s] %(levelname)s  %(message)s",
        datefmt="%H:%M:%S",
    )
    fmt_file = logging.Formatter(
        "%(asctime)s [%(name)s] %(levelname)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # ---- Maya Script Editor handler (INFO) ---------------------------
    # Maya 環境でなくても動くよう try/except で守る
    try:
        _add_maya_handler(root, fmt)
    except Exception:
        # Maya 外 (pytest, standalone) — stderr で代替
        sh = logging.StreamHandler()
        sh.setLevel(logging.INFO)
        sh.setFormatter(fmt)
        root.addHandler(sh)

    # ---- File handler (DEBUG) ----------------------------------------
    try:
        fh = logging.FileHandler(_LOG_FILE, mode="a", encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt_file)
        root.addHandler(fh)
    except Exception:
        root.warning("Failed to open log file: %s", _LOG_FILE)

    _initialized = True
    root.info("Log file: %s", _LOG_FILE)
    return root


class _MayaHandler(logging.Handler):
    """Maya Script Editor に出力する logging Handler."""

    def emit(self, record: logging.LogRecord) -> None:
        import maya.OpenMaya as om
        msg = self.format(record)
        if record.levelno >= logging.ERROR:
            om.MGlobal.displayError(msg)
        elif record.levelno >= logging.WARNING:
            om.MGlobal.displayWarning(msg)
        else:
            om.MGlobal.displayInfo(msg)


def _add_maya_handler(logger: logging.Logger, fmt: logging.Formatter) -> None:
    import maya.OpenMaya  # noqa: F401 — 存在確認
    mh = _MayaHandler()
    mh.setLevel(logging.INFO)
    mh.setFormatter(fmt)
    logger.addHandler(mh)


def get_logger(name: str | None = None) -> logging.Logger:
    """名前付き子ロガーを返す。

    Parameters
    ----------
    name : ``"PCDeformer"`` など短い名前。
           ``None`` ならルートロガーを返す。

    Returns
    -------
    logging.Logger
    """
    _ensure_root()
    if name is None or name == _ROOT_LOGGER_NAME:
        return logging.getLogger(_ROOT_LOGGER_NAME)
    # すでに Aru_RetopoTool.editor. プレフィクスがあればそのまま使う
    if name.startswith(_ROOT_LOGGER_NAME + "."):
        return logging.getLogger(name)
    return logging.getLogger(f"{_ROOT_LOGGER_NAME}.{name}")


def get_log_path() -> str:
    """ログファイルのフルパスを返す。"""
    return _LOG_FILE

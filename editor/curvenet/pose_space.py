# -*- coding: utf-8 -*-
"""RetopoGuide Pose Space — blendShape ターゲットを poseInterpolator で駆動する
==============================================================================

ポーズ依存の補正 (PSD) は Maya 標準の仕組みだけで組む:

  joint ──▶ poseInterpolator.output[i] ──▶ blendShape.w[target] ──▶ retopoGuide (frontOfChain) ──▶ skinCluster

blendShape ターゲットの作り方は ``blend_target`` (controlPoints のスカルプトを
レスト空間に戻して点デルタとして書く) をそのまま使い、本モジュールは
「ポーズの登録とターゲットへの接続」だけを受け持つ。

Pose Editor の「ポーズの追加」と同じく、新しいポーズを足すと同じ
poseInterpolator の他のポーズはそのポーズ位置で重み 0 になる (RBF は
サンプル点で厳密)。したがって新規ターゲットには「スカルプト差分」に加えて
「登録時点で効いていた他ポーズの寄与」も焼き込む必要がある。
``add_pose_corrective()`` がこれをやる。
"""

from __future__ import annotations

import maya.cmds as cmds

from Aru_RetopoTool.editor.curvenet import blend_target as _bt
from Aru_RetopoTool.editor.curvenet.curve_net_edit import _resolve_curvenet_shape

__all__ = [
    "load_plugin",
    "pi_shape", "pi_transform", "drivers",
    "list_pose_interpolators", "pose_interpolators_for",
    "create_pose_interpolator",
    "pose_names", "pose_index", "pose_type", "pose_weight",
    "add_pose", "update_pose", "go_to_pose", "delete_pose", "rename_pose",
    "target_for_pose", "connect_pose_to_target",
    "add_pose_corrective", "update_pose_corrective",
    "list_poses",
]

POSE_TYPES = ("swingandtwist", "swing", "twist")
_POSE_TYPE_IDX = {n: i for i, n in enumerate(POSE_TYPES)}
NEUTRAL_POSES = ("neutral", "neutralSwing", "neutralTwist")
_EPS = 1.0e-6


def load_plugin():
    if not cmds.pluginInfo("poseInterpolator", q=True, loaded=True):
        cmds.loadPlugin("poseInterpolator", quiet=True)


# ---------------------------------------------------------------------------
# ノードの解決
# ---------------------------------------------------------------------------
def pi_shape(node):
    """poseInterpolator のシェイプ名 (transform / shape どちらを渡してもよい)。"""
    if not node or not cmds.objExists(node):
        return ""
    if cmds.nodeType(node) == "poseInterpolator":
        return node
    kids = cmds.listRelatives(node, shapes=True, type="poseInterpolator",
                              fullPath=False) or []
    return kids[0] if kids else ""


def pi_transform(node):
    shape = pi_shape(node)
    if not shape:
        return ""
    par = cmds.listRelatives(shape, parent=True) or []
    return par[0] if par else shape


def drivers(pi):
    shape = pi_shape(pi)
    if not shape:
        return []
    try:
        return cmds.poseInterpolator(shape, q=True, drivers=True) or []
    except Exception:
        out = []
        for i in (cmds.getAttr(shape + ".driver", mi=True) or []):
            src = cmds.listConnections(
                "%s.driver[%d].driverMatrix" % (shape, i), s=True, d=False) or []
            out.extend(src)
        return out


def list_pose_interpolators():
    return [pi_transform(s) for s in (cmds.ls(type="poseInterpolator") or [])]


def pose_interpolators_for(joint):
    """*joint* をドライバに持つ poseInterpolator (transform) のリスト。"""
    if not joint:
        return []
    want = {joint, joint.split("|")[-1]}
    out = []
    for pi in list_pose_interpolators():
        if any(d in want or d.split("|")[-1] in want for d in drivers(pi)):
            out.append(pi)
    return out


def create_pose_interpolator(joint, name="", neutral=True, twist_axis=0):
    """*joint* をドライバにした poseInterpolator を作って transform 名を返す。

    Pose Editor の「ポーズインターポレータの作成」と同じく、既定で
    neutral / neutralSwing / neutralTwist の 3 ポーズを登録する (これが無いと
    レストポーズで補正がゼロにならない)。ポーズを付けた状態から呼ばれることが
    多いので、ニュートラルはドライバの rotate を一時的に 0 にして記録する
    (ジョイントのレストは jointOrient が持っている)。
    """
    load_plugin()
    if not cmds.objExists(joint):
        raise RuntimeError("ドライバが見つかりません: %s" % joint)
    name = name or (joint.split("|")[-1] + "_poseInterpolator")
    cmds.select(joint, r=True)
    tpl = cmds.poseInterpolator(name=name)[0]
    shape = pi_shape(tpl)
    for i in (cmds.getAttr(shape + ".driver", mi=True) or []):
        cmds.setAttr("%s.driver[%d].driverTwistAxis" % (shape, i), int(twist_axis))
    if neutral:
        saved = _zero_rotation(joint)
        try:
            for pname, ptype in zip(NEUTRAL_POSES, POSE_TYPES):
                cmds.poseInterpolator(shape, e=True, addPose=pname)
                idx = pose_index(tpl, pname)
                cmds.setAttr("%s.pose[%d].poseType" % (shape, idx), _POSE_TYPE_IDX[ptype])
        finally:
            _restore_rotation(joint, saved)
    return tpl


def _zero_rotation(joint):
    """rotate を 0 にして元の値を返す (接続済みで書けない軸は触らない)。"""
    saved = {}
    for ax in ("rotateX", "rotateY", "rotateZ"):
        plug = joint + "." + ax
        try:
            if cmds.getAttr(plug, settable=True):
                saved[ax] = cmds.getAttr(plug)
                cmds.setAttr(plug, 0.0)
        except Exception:
            pass
    if len(saved) < 3:
        cmds.warning("[RetopoGuide] %s の rotate が接続されているため、ニュートラルポーズを"
                     "現在の姿勢で記録しました。レストポーズで作り直すことを勧めます。" % joint)
    return saved


def _restore_rotation(joint, saved):
    for ax, v in saved.items():
        try:
            cmds.setAttr(joint + "." + ax, v)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# ポーズ
# ---------------------------------------------------------------------------
def pose_names(pi):
    shape = pi_shape(pi)
    if not shape:
        return []
    return cmds.poseInterpolator(shape, q=True, poseNames=True) or []


def pose_index(pi, name):
    shape = pi_shape(pi)
    for i in (cmds.getAttr(shape + ".pose", mi=True) or []):
        if cmds.getAttr("%s.pose[%d].poseName" % (shape, i)) == name:
            return i
    return -1


def pose_type(pi, idx):
    try:
        return POSE_TYPES[int(cmds.getAttr("%s.pose[%d].poseType" % (pi_shape(pi), idx)))]
    except Exception:
        return POSE_TYPES[0]


def pose_weight(pi, idx):
    try:
        return float(cmds.getAttr("%s.output[%d]" % (pi_shape(pi), idx)))
    except Exception:
        return 0.0


def add_pose(pi, name, ptype="swingandtwist"):
    """現在のドライバ姿勢でポーズを登録してインデックスを返す。"""
    shape = pi_shape(pi)
    if not shape:
        raise RuntimeError("poseInterpolator が見つかりません: %s" % pi)
    if not name:
        raise RuntimeError("ポーズ名が空です。")
    name = name.replace("|", "_").replace(":", "_")
    if pose_index(pi, name) >= 0:
        raise RuntimeError("同名のポーズがあります: %s" % name)
    cmds.poseInterpolator(shape, e=True, addPose=name)
    idx = pose_index(pi, name)
    if idx < 0:
        raise RuntimeError("ポーズを追加できませんでした: %s" % name)
    cmds.setAttr("%s.pose[%d].poseType" % (shape, idx),
                 _POSE_TYPE_IDX.get(ptype, 0))
    return idx


def update_pose(pi, name):
    """ポーズの登録姿勢を現在のドライバ姿勢で置き換える。"""
    cmds.poseInterpolator(pi_transform(pi), e=True, updatePose=name)


def go_to_pose(pi, name):
    cmds.poseInterpolator(pi_transform(pi), e=True, goToPose=name)


def rename_pose(pi, old, new):
    new = new.replace("|", "_").replace(":", "_")
    shape = pi_shape(pi)
    cmds.poseInterpolator(shape, e=True, rename=(old, new))
    # 対応するターゲットの別名も揃える
    idx = pose_index(pi, new)
    for bs, widx in _connected_targets(pi, idx):
        try:
            cmds.aliasAttr(new, "%s.weight[%d]" % (bs, widx))
        except Exception:
            pass


def delete_pose(pi, name, delete_target=True):
    """ポーズを削除する。既定で繋がっていた blendShape ターゲットも消す。"""
    import maya.mel as mel
    if delete_target:
        # Pose Editor と同じ手順 (ターゲットグループも消す)
        mel.eval('poseInterpolatorDeletePose("%s", "%s")' % (pi_transform(pi), name))
    else:
        cmds.poseInterpolator(pi_transform(pi), e=True, deletePose=name)


def _connected_targets(pi, idx):
    """``output[idx]`` が繋がる ``(blendShape, weightIndex)`` のリスト。"""
    out = []
    if idx < 0:
        return out
    plugs = cmds.listConnections("%s.output[%d]" % (pi_shape(pi), idx),
                                 s=False, d=True, p=True, type="blendShape") or []
    for p in plugs:
        node, _, attr = p.partition(".")
        widx = _weight_index(node, attr)
        if widx is not None:
            out.append((node, widx))
    return out


def _weight_index(bs, attr):
    """``weight[3]`` / 別名 ``poseA`` のどちらからでも weight インデックスを引く。"""
    if attr.startswith("weight[") or attr.startswith("w["):
        try:
            return int(attr[attr.index("[") + 1:attr.index("]")])
        except ValueError:
            return None
    names = cmds.listAttr(bs + ".w", multi=True) or []
    idx = cmds.getAttr(bs + ".w", mi=True) or []
    for n, i in zip(names, idx):
        if n == attr:
            return i
    return None


def target_for_pose(pi, idx, bs):
    """ポーズ *idx* が駆動している *bs* のターゲット (weight インデックス) か None。"""
    for node, widx in _connected_targets(pi, idx):
        if _bt._long_name(node) == _bt._long_name(bs):
            return widx
    return None


def connect_pose_to_target(pi, idx, bs, widx):
    cmds.connectAttr("%s.output[%d]" % (pi_shape(pi), idx),
                     "%s.weight[%d]" % (bs, widx), force=True)


def list_poses(pi, bs=None):
    """UI 用: ``[(idx, name, type, weight, target_widx or None), ...]``。"""
    shape = pi_shape(pi)
    out = []
    if not shape:
        return out
    for i in (cmds.getAttr(shape + ".pose", mi=True) or []):
        name = cmds.getAttr("%s.pose[%d].poseName" % (shape, i))
        tgt = target_for_pose(pi, i, bs) if bs else None
        out.append((i, name, pose_type(pi, i), pose_weight(pi, i), tgt))
    return out


# ---------------------------------------------------------------------------
# メイン API
# ---------------------------------------------------------------------------
def _resolve(node_name):
    shape = _bt._long_name(_resolve_curvenet_shape(node_name))
    if not shape:
        raise RuntimeError("retopoGuideNode が見つかりません。")
    parents = cmds.listRelatives(shape, parent=True, fullPath=True) or []
    if not parents:
        raise RuntimeError("retopoGuideNode の親トランスフォームがありません。")
    return shape, parents[0]


def _driven_contribution(pi, bs, skip_idx=None):
    """同じ poseInterpolator が駆動するターゲットの、現在の重み付き点デルタ合計。"""
    acc = {}
    for i in (cmds.getAttr(pi_shape(pi) + ".pose", mi=True) or []):
        if i == skip_idx:
            continue
        widx = target_for_pose(pi, i, bs)
        if widx is None:
            continue
        w = float(cmds.getAttr("%s.weight[%d]" % (bs, widx)) or 0.0)
        if abs(w) < _EPS:
            continue
        for k, d in _bt.read_point_deltas(bs, widx).items():
            old = acc.get(k)
            acc[k] = ([old[0] + w * d[0], old[1] + w * d[1], old[2] + w * d[2]]
                      if old else [w * d[0], w * d[1], w * d[2]])
    return acc


def add_pose_corrective(node_name="", joint="", pose_name="", ptype="swingandtwist",
                        pi=None, twist_axis=0):
    """現在のポーズ + スカルプト (controlPoints) を新規ポーズターゲットとして登録する。

    Parameters
    ----------
    node_name : retopoGuideNode (シェイプ / トランスフォーム)。省略時は選択から。
    joint : ドライバジョイント。*pi* を渡す場合は省略可。
    pose_name : ポーズ名 (= ターゲット名)。
    ptype : "swingandtwist" / "swing" / "twist"。
    pi : 既存の poseInterpolator。None なら *joint* のものを探し、無ければ作る。

    Returns
    -------
    (poseInterpolator transform, pose index, blendShape, target name)
    """
    shape, xf = _resolve(node_name)
    if not pose_name:
        raise RuntimeError("ポーズ名を入力してください。")
    if pi is None:
        if not joint:
            raise RuntimeError("ドライバジョイントを指定してください。")
        found = pose_interpolators_for(joint)
        pi = found[0] if found else create_pose_interpolator(joint, twist_axis=twist_axis)
    if pose_index(pi, pose_name) >= 0:
        raise RuntimeError("同名のポーズがあります: %s" % pose_name)

    # 1) スカルプト (ポーズ空間) を取り出してクリア。blendShape を新規作成すると
    #    Maya が非ゼロの controlPoints を tweak ノードへ移してしまうので必ず先に。
    #    一緒に、今効いている同 PI の他ポーズの寄与 (レスト空間) も控えておく。
    #    ポーズを足すとそれらの重みはこの姿勢で 0 になるので、新ターゲットへ引き継ぐ。
    bs = _bt.find_blend_shape(shape)
    carried = _driven_contribution(pi, bs) if bs else {}
    raw = _bt.take_control_point_deltas(shape)
    bs = _bt.ensure_blend_shape(shape)

    # 2) ポーズを登録してターゲットを繋ぐ (この姿勢で重み 1)。引き継ぎ分を入れた
    #    時点で出力は「スカルプト前」と同じ形に戻る。
    idx = add_pose(pi, pose_name, ptype)
    widx, tname = _bt.add_empty_target(bs, xf, pose_name)
    _bt.write_point_deltas(bs, widx, carried)
    connect_pose_to_target(pi, idx, bs, widx)

    # 3) スカルプトをこのターゲット経由でレスト空間に直して加算
    local = _bt.localize_by_probe(shape, bs, widx, raw)
    for k, v in local.items():
        old = carried.get(k)
        carried[k] = ([old[0] + v[0], old[1] + v[1], old[2] + v[2]] if old else list(v))
    _bt.write_point_deltas(bs, widx, carried)
    return pi_transform(pi), idx, bs, tname


def update_pose_corrective(node_name="", pi=None, pose_name="", additive=True,
                           update_driver=False):
    """既存ポーズのターゲットへ現在のスカルプト (controlPoints) を焼き込む。

    差分はターゲットの現在の重み込みでレスト空間に直すので、重みが 1 でない
    姿勢でも「今の姿勢でスカルプトどおり」になる。重みが 0.5 未満は別の
    ポーズの領域なので中止する。
    """
    shape, xf = _resolve(node_name)
    if pi is None or pose_index(pi, pose_name) < 0:
        raise RuntimeError("ポーズが見つかりません: %s" % pose_name)
    idx = pose_index(pi, pose_name)
    if update_driver:
        update_pose(pi, pose_name)
    w = pose_weight(pi, idx)
    if w < 0.5:
        raise RuntimeError(
            "ポーズ '%s' の重みが %.2f です。「ポーズへ移動」してからスカルプトしてください。"
            % (pose_name, w))
    raw = _bt.take_control_point_deltas(shape)
    if not raw:
        raise RuntimeError("controlPoints に編集がありません。先にカーブネットをスカルプトしてください。")
    bs = _bt.ensure_blend_shape(shape)

    widx = target_for_pose(pi, idx, bs)
    if widx is None:
        widx, _tname = _bt.add_empty_target(bs, xf, pose_name)
        connect_pose_to_target(pi, idx, bs, widx)
    local = _bt.localize_by_probe(shape, bs, widx, raw)
    if additive:
        merged = _bt.read_point_deltas(bs, widx)
        for k, v in local.items():
            old = merged.get(k)
            merged[k] = ([old[0] + v[0], old[1] + v[1], old[2] + v[2]] if old else list(v))
    else:
        merged = local
    n = _bt.write_point_deltas(bs, widx, merged)
    return bs, widx, n

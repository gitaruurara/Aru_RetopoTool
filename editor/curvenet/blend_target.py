# -*- coding: utf-8 -*-
"""RetopoGuide BlendShape Target — スカルプトを Maya 標準の blendShape へ渡す
================================================================================

Pixar の論文 (de Goes et al. 2022) §3 は、プロファイルカーブの制御点を
「スキニングやスカルプティングなどの**既存のリギング技術**」で動かすと述べ、
§1 では従来のリグが「**補正ブレンドシェープと組み合わせたスキニング**」で
できていると書いている。つまりポーズ依存の補正は独自機構を作るのではなく、
DCC 標準のブレンドシェープに委ねるのが論文の立場である。

点デルタ方式
------------
ターゲットの持ち方には 2 通りある。

  (a) ジオメトリ複製を ``inputGeomTarget`` に繋ぐ
  (b) 差分だけを ``inputTargetItem[6000].inputPointsTarget`` に書く

Maya の Shape Editor が扱うのは (b) で、「ターゲットの追加」で作られる空
ターゲットもこの形である。このモジュールは (b) を採る。利点は 3 つ:

  * 隠しジオメトリがシーンに増えない
  * Shape Editor がターゲットの追加・リネーム・並べ替え・ウェイト駆動を
    そのまま担当できる
  * Shape Editor で先に作った空ターゲットへ、後からスカルプトを焼ける

なお ``inputGeomTarget`` に接続が残っていると点デルタは完全に無視される
(実測で確認済み) ので、焼き込み前に必ず切る。

処理の流れ
----------
  1. 現在のポーズでスカルプトされた ``controlPoints`` (ワールド空間) を読む
  2. ``controlPoints`` をクリアしてから変形後 CV 位置を読む
     (クリアしないとスカルプト分が二重に入り、局所回転を誤る)
  3. CV ごとの局所回転 ``R`` でレスト空間に戻す (``R^T · delta``)
  4. その差分をターゲットの ``inputPointsTarget`` に書く

blendShape は ``frontOfChain`` で作る。こうするとターゲットの差分はレスト
空間で加算されてから skinCluster に通るため、補正が自動的にポーズと一緒に
回転する (=ポーズスペースデフォーメーション)。実測では腕を 60 度曲げた
ときに補正ベクトルが 57.3 度回転し、大きさは 1.000 倍のまま保たれる。

想定ワークフロー
----------------
  A. カーブネットを選択 → Shape Editor で「ブレンドシェイプの作成」
  B. 「ターゲットの追加」→ そのターゲットをダブルクリックして編集状態にする
  C. コンポーネントモードでカーブネットを編集する
     → 変位はそのままターゲットに入る (Maya 標準の tweak 経路)

C が成立するのは ``curve_net_node.tweakUsing()`` が、Maya から渡される
tweak の書き込み先 (``MArrayDataHandle``) をそのまま使っているため。
編集モード中はこのハンドルがターゲットを指すので、プラグイン側で
「焼き込む」処理は要らない。

このモジュールが受け持つのは、その経路に乗らなかったぶんの後始末:

  * ``create_blend_target()`` — 編集モードに入らずにスカルプトしたものを
    新規ターゲットとして確定する
  * ``bake_to_target()`` — 同じものを既存ターゲットへ移す
  * ``ensure_front_of_chain()`` — Shape Editor が作る blendShape は
    チェーン末尾に付くので、ポーズスペースになるよう前へ出す
"""

from __future__ import annotations

import json

import maya.cmds as cmds

from Aru_RetopoTool.editor.curvenet import sculpt_pose as _sp
from Aru_RetopoTool.editor.curvenet.curve_net_data import RetopoGuideData
from Aru_RetopoTool.editor.curvenet.curve_net_edit import _resolve_curvenet_shape

__all__ = [
    "read_control_point_deltas",
    "localize_deltas",
    "find_blend_shape",
    "ensure_blend_shape",
    "is_front_of_chain",
    "ensure_front_of_chain",
    "list_blend_targets",
    "add_empty_target",
    "read_point_deltas",
    "write_point_deltas",
    "current_sculpt_deltas",
    "create_blend_target",
    "bake_to_target",
    "selected_shape_editor_target",
    "bake_to_selected_target",
]

_EPS = 1.0e-9

# inputTargetItem のインデックス。5000 + weight*1000 で、weight=1.0 が 6000。
_ITEM_FULL = 6000


def _long_name(node):
    """短縮名をフルパスに正規化する (同名ノードがあっても曖昧にならない)。"""
    if not node:
        return node
    try:
        found = cmds.ls(node, long=True) or []
    except Exception:
        return node
    return found[0] if found else node


# ---------------------------------------------------------------------------
# controlPoints の読み書き
# ---------------------------------------------------------------------------
def read_control_point_deltas(shape):
    """``controlPoints`` の非ゼロ要素を ``{idx: [x, y, z]}`` で返す。"""
    out = {}
    for i in (cmds.getAttr(shape + ".controlPoints", mi=True) or []):
        try:
            v = cmds.getAttr("%s.controlPoints[%d]" % (shape, i))[0]
        except Exception:
            continue
        if max(abs(c) for c in v) > _EPS:
            out[int(i)] = [float(v[0]), float(v[1]), float(v[2])]
    return out


def _clear_control_points(shape):
    for i in (cmds.getAttr(shape + ".controlPoints", mi=True) or []):
        for c in "xyz":
            try:
                cmds.setAttr("%s.controlPoints[%d].%sValue" % (shape, i, c),
                             0.0)
            except Exception:
                pass


def _deformed_positions(shape):
    """``outNetData`` から現在の変形後 CV 位置を読む。

    呼び出し側で ``controlPoints`` を 0 にしてから使うこと。そうしないと
    スカルプト分が混ざったものが返る。
    """
    raw = cmds.getAttr(shape + ".outNetData")
    if not raw:
        return None
    try:
        return [list(p) for p in json.loads(raw)["positions"]]
    except Exception:
        return None


# ---------------------------------------------------------------------------
# ローカル化
# ---------------------------------------------------------------------------
def localize_deltas(base_positions, deformed_positions, splines, delta_map):
    """ワールド空間のスカルプト差分をレスト空間に変換する。

    ``controlPoints`` はポーズ後のワールド空間オフセットなので、そのまま
    ``frontOfChain`` の blendShape ターゲットにすると skinCluster で二重に
    回転してしまう。CV ごとの局所回転 ``R`` の転置を掛けて戻しておく。
    """
    if not delta_map:
        return {}
    if deformed_positions is None:
        return {int(k): list(v) for k, v in delta_map.items()}

    rots = _sp.compute_cv_rotations(base_positions, deformed_positions,
                                    splines)
    out = {}
    for idx, d in delta_map.items():
        idx = int(idx)
        if idx < 0 or idx >= len(base_positions):
            continue
        rot = rots[idx] if idx < len(rots) else _sp._identity()
        local = _sp._mat_apply(_sp._mat_transpose(rot), list(d))
        out[idx] = [local[0], local[1], local[2]]
    return out


def current_sculpt_deltas(shape):
    """現在の ``controlPoints`` をレスト空間に直した ``{idx: [x,y,z]}``。

    副作用として ``controlPoints`` をクリアする (焼き込み後は不要なため)。
    スカルプトが無ければ空の辞書を返す。
    """
    shape = _long_name(shape)
    delta_map = read_control_point_deltas(shape)
    if not delta_map:
        return {}

    raw = cmds.getAttr(shape + ".netData")
    if not raw:
        raise RuntimeError("netData が空です。")
    net = RetopoGuideData.from_json(raw)
    base_positions = [list(p) for p in net.positions]

    _clear_control_points(shape)
    deformed = _deformed_positions(shape)
    return localize_deltas(base_positions, deformed, net.splines, delta_map)


def take_control_point_deltas(shape):
    """``controlPoints`` の非ゼロ要素 (ポーズ空間) を返してクリアする。"""
    shape = _long_name(shape)
    delta_map = read_control_point_deltas(shape)
    if delta_map:
        _clear_control_points(shape)
    return delta_map


def localize_by_probe(shape, bs, widx, delta_map):
    """ポーズ空間の差分をターゲット *widx* の数値ヤコビアンでレスト空間へ変換する。

    ``localize_deltas`` は隣接 CV から局所回転を推定するので、ウェイトが混ざる
    CV では数 % ずれる。ここではターゲットの点デルタを実際に動かして
    「ターゲット空間の単位変位 → 出力の変位」を CV ごとに測り (3 回評価)、
    その逆行列を掛ける。skinCluster (LBS) はデルタに対して線形なので厳密で、
    間に何が挟まっていてもチェーンをまるごと扱える。ターゲットの現在の重み
    (poseInterpolator の出力) もヤコビアンに含まれるので、重み 1 でない姿勢でも
    「今の姿勢でスカルプトどおりになる」差分が出る。

    ターゲットの重みが 0 のときは測れないので呼び出し側で保証すること。
    """
    if not delta_map:
        return {}
    shape = _long_name(shape)
    keys = sorted(int(k) for k in delta_map)
    saved = read_point_deltas(bs, widx)

    raw = cmds.getAttr(shape + ".netData") or ""
    diag = 1.0
    try:
        pts = json.loads(raw)["positions"]
        lo = [min(p[k] for p in pts) for k in range(3)]
        hi = [max(p[k] for p in pts) for k in range(3)]
        diag = max(sum((hi[k] - lo[k]) ** 2 for k in range(3)) ** 0.5, 1e-3)
    except Exception:
        pass
    eps = diag * 0.01

    base = _deformed_positions(shape)
    if base is None:
        return {int(k): list(v) for k, v in delta_map.items()}
    cols = []
    try:
        for axis in range(3):
            probe = {k: list(v) for k, v in saved.items()}
            for k in keys:
                d = probe.get(k, [0.0, 0.0, 0.0])
                d[axis] += eps
                probe[k] = d
            write_point_deltas(bs, widx, probe)
            cur = _deformed_positions(shape)
            cols.append({k: [(cur[k][c] - base[k][c]) / eps for c in range(3)]
                         for k in keys if k < len(cur) and k < len(base)})
    finally:
        write_point_deltas(bs, widx, saved)

    out = {}
    for k in keys:
        d = list(delta_map[k])
        if not all(k in c for c in cols):
            out[k] = d
            continue
        # J の列 = 各軸の単位変位に対する出力変位
        m = [[cols[c][k][r] for c in range(3)] for r in range(3)]
        inv = _inv3(m)
        if inv is None:
            out[k] = d
            continue
        out[k] = [sum(inv[r][c] * d[c] for c in range(3)) for r in range(3)]
    return out


def _inv3(m):
    a, b, c = m[0]
    d, e, f = m[1]
    g, h, i = m[2]
    det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    if abs(det) < 1e-9:
        return None
    inv = [[(e * i - f * h), -(b * i - c * h), (b * f - c * e)],
           [-(d * i - f * g), (a * i - c * g), -(a * f - c * d)],
           [(d * h - e * g), -(a * h - b * g), (a * e - b * d)]]
    return [[v / det for v in row] for row in inv]


# ---------------------------------------------------------------------------
# blendShape ヘルパ
# ---------------------------------------------------------------------------
def find_blend_shape(shape):
    """シェイプのヒストリにある blendShape ノード名 (無ければ None)。"""
    shape = _long_name(shape)
    for h in (cmds.listHistory(shape) or []):
        try:
            if cmds.nodeType(h) == "blendShape":
                return h
        except Exception:
            continue
    return None


def ensure_blend_shape(shape):
    """retopoGuide に blendShape が無ければ ``frontOfChain`` で作って返す。

    ``frontOfChain`` が要点。差分をレスト空間で加算してから skinCluster に
    通すことで、補正がポーズと一緒に回る。
    """
    shape = _long_name(shape)
    bs = find_blend_shape(shape)
    if bs:
        ensure_front_of_chain(shape, bs)
        return bs
    parents = cmds.listRelatives(shape, parent=True, fullPath=True) or []
    if not parents:
        raise RuntimeError("retopoGuideNode の親トランスフォームがありません。")
    xf = parents[0]
    return cmds.blendShape(xf, frontOfChain=True,
                           name=xf.split("|")[-1] + "_blendShape")[0]


def is_front_of_chain(shape, bs):
    """blendShape が skinCluster より上流に入っているか。"""
    hist = cmds.listHistory(_long_name(shape)) or []
    if bs not in hist:
        return False
    bi = hist.index(bs)
    return not [h for h in hist[bi + 1:]
                if cmds.nodeType(h) == "skinCluster"]


def ensure_front_of_chain(shape, bs):
    """blendShape を skinCluster より上流へ並べ替える。

    Shape Editor の「ブレンドシェイプの作成」はデフォーマチェーンの末尾に
    足すため、そのままだと差分がポーズ後の空間に加算されてしまい、補正が
    ポーズと一緒に回らない。論文が言うポーズスペースの補正にするには
    skinCluster より前に置く必要があるので、必要なら自動で直す。

    Returns
    -------
    並べ替えを行ったら True。
    """
    shape = _long_name(shape)
    parents = cmds.listRelatives(shape, parent=True, fullPath=True) or []
    if not parents:
        return False
    xf = parents[0]

    moved = False
    for _ in range(8):
        hist = cmds.listHistory(shape) or []
        if bs not in hist:
            return moved
        bi = hist.index(bs)
        # bs より後ろ (=より上流) にある skinCluster は、bs が後掛けに
        # なっていることを意味する
        late = [h for h in hist[bi + 1:]
                if cmds.nodeType(h) == "skinCluster"]
        if not late:
            return moved
        try:
            # reorderDeformers(A, B, geo) は A を B の後段 (下流) に置く。
            # skinCluster を後段にすることで blendShape が前段になる。
            cmds.reorderDeformers(late[0], bs, xf)
            moved = True
        except Exception:
            return moved
    return moved


def list_blend_targets(node_name=""):
    """retopoGuide に付いている blendShape ターゲット名のリストを返す。"""
    shape = _long_name(_resolve_curvenet_shape(node_name))
    if not shape:
        return []
    bs = find_blend_shape(shape)
    if not bs:
        return []
    return cmds.listAttr(bs + ".w", multi=True) or []


def _next_weight_index(bs):
    idx = cmds.getAttr(bs + ".w", mi=True) or []
    return (max(idx) + 1) if idx else 0


def _unique_target_name(xf, bs=None):
    stem = xf.split("|")[-1] + "_target"
    used = set(cmds.listAttr(bs + ".w", multi=True) or []) if bs else set()
    i = 1
    while ("%s%d" % (stem, i)) in used or cmds.objExists("%s%d" % (stem, i)):
        i += 1
    return "%s%d" % (stem, i)


def _item_plug(bs, widx):
    return ("%s.inputTarget[0].inputTargetGroup[%d].inputTargetItem[%d]"
            % (bs, int(widx), _ITEM_FULL))


def target_index(bs, target):
    """ターゲット名または番号を weight インデックスに解決する。"""
    idx = cmds.getAttr(bs + ".w", mi=True) or []
    if isinstance(target, int):
        if target in idx:
            return target
        raise RuntimeError("ターゲット番号 %d がありません。" % target)
    names = cmds.listAttr(bs + ".w", multi=True) or []
    for n, i in zip(names, idx):
        if n == target:
            return i
    raise RuntimeError("ターゲット '%s' が見つかりません。" % target)


def _detach_geom_target(bs, widx):
    """``inputGeomTarget`` の接続を切る。

    接続が残っていると ``inputPointsTarget`` は完全に無視される。Shape
    Editor 由来の空ターゲットには最初から接続が無いが、``blendShape -target``
    で作ったものには付くので必ず通す。
    """
    plug = _item_plug(bs, widx) + ".inputGeomTarget"
    for c in (cmds.listConnections(plug, s=True, d=False, p=True) or []):
        try:
            cmds.disconnectAttr(c, plug)
        except Exception:
            pass


def add_empty_target(bs, xf, target_name=""):
    """ジオメトリを持たない空ターゲットを追加し ``(widx, 名前)`` を返す。

    Shape Editor の「ターゲットの追加」と同じ形のものを作る。
    """
    widx = _next_weight_index(bs)
    name = target_name or _unique_target_name(xf, bs)

    # inputTargetItem に触ると multi 要素が生成される。この経路なら
    # 一時的にもジオメトリ接続が作られないので DG サイクルが起きない。
    try:
        cmds.setAttr(_item_plug(bs, widx) + ".inputPointsTarget", 0,
                     type="pointArray")
        cmds.setAttr(_item_plug(bs, widx) + ".inputComponentsTarget", 0,
                     type="componentList")
        cmds.setAttr("%s.weight[%d]" % (bs, widx), 0.0)
    except Exception:
        pass

    if widx not in (cmds.getAttr(bs + ".w", mi=True) or []):
        # 直接生成に失敗したら、自己ターゲットを作ってから接続を切る
        cmds.blendShape(bs, edit=True, target=(xf, widx, xf, 1.0))
        _detach_geom_target(bs, widx)

    cur = cmds.listAttr(bs + ".w", multi=True) or []
    idx = cmds.getAttr(bs + ".w", mi=True) or []
    alias = None
    for n, i in zip(cur, idx):
        if i == widx:
            alias = n
            break
    if alias != name:
        try:
            cmds.aliasAttr(name, "%s.weight[%d]" % (bs, widx))
        except Exception:
            name = alias or name
    return widx, name


# ---------------------------------------------------------------------------
# 点デルタの読み書き
# ---------------------------------------------------------------------------
def read_point_deltas(bs, widx):
    """ターゲットの点デルタを ``{idx: [x, y, z]}`` で返す。"""
    item = _item_plug(bs, widx)
    try:
        pts = cmds.getAttr(item + ".inputPointsTarget") or []
        comps = cmds.getAttr(item + ".inputComponentsTarget") or []
    except Exception:
        return {}

    out = {}
    flat = []
    for c in comps:
        # "vtx[3]" / "vtx[3:7]" のどちらも来る
        body = c[c.find("[") + 1:c.rfind("]")]
        if ":" in body:
            a, b = body.split(":")
            flat.extend(range(int(a), int(b) + 1))
        else:
            flat.append(int(body))
    for i, idx in enumerate(flat):
        if i >= len(pts):
            break
        p = pts[i]
        out[int(idx)] = [float(p[0]), float(p[1]), float(p[2])]
    return out


def write_point_deltas(bs, widx, delta_map):
    """ターゲットの点デルタを丸ごと差し替える。"""
    _detach_geom_target(bs, widx)
    item = _item_plug(bs, widx)

    keys = sorted(int(k) for k in delta_map
                  if max(abs(c) for c in delta_map[k]) > _EPS)
    if not keys:
        cmds.setAttr(item + ".inputPointsTarget", 0, type="pointArray")
        cmds.setAttr(item + ".inputComponentsTarget", 0, type="componentList")
        return 0

    pts = [tuple(float(c) for c in delta_map[k][:3]) for k in keys]
    comps = ["vtx[%d]" % k for k in keys]
    cmds.setAttr(item + ".inputPointsTarget", len(pts), *pts,
                 type="pointArray")
    cmds.setAttr(item + ".inputComponentsTarget", len(comps), *comps,
                 type="componentList")
    return len(keys)


# ---------------------------------------------------------------------------
# Shape Editor 連携
# ---------------------------------------------------------------------------
def selected_shape_editor_target(bs=None):
    """Shape Editor で選択中のターゲットを ``(blendShape, widx)`` で返す。

    見つからなければ ``None``。Shape Editor が開いていない、あるいは
    ターゲットが選択されていない場合も ``None`` になる。
    """
    import maya.mel as mel

    raw = []
    for expr in ("getShapeEditorTreeviewSelection(24)",
                 "getShapeEditorTreeviewSelection(27)",
                 "getShapeEditorTreeviewSelection(12)"):
        try:
            got = mel.eval(expr)
        except Exception:
            continue
        if got:
            raw = got if isinstance(got, (list, tuple)) else [got]
            break

    for entry in raw:
        # "blendShape1.3" 形式
        text = str(entry)
        if "." not in text:
            continue
        node, _, tail = text.rpartition(".")
        if not cmds.objExists(node) or cmds.nodeType(node) != "blendShape":
            continue
        if bs and _long_name(node) != _long_name(bs):
            continue
        try:
            return node, int(tail)
        except ValueError:
            try:
                return node, target_index(node, tail)
            except Exception:
                continue
    return None


# ---------------------------------------------------------------------------
# メイン API
# ---------------------------------------------------------------------------
def bake_to_target(node_name="", target=None, additive=True, weight=None):
    """現在のスカルプトを既存の blendShape ターゲットへ焼き込む。

    通常はターゲット編集モード (Shape Editor の「ターゲットの編集」) 中に
    カーブネットを編集すれば Maya が自動でターゲットへ入れてくれるので、
    この関数は使わなくてよい。編集モードに入らずにスカルプトしてしまった
    ものを後からターゲットへ移したいとき用の入口。

    Parameters
    ----------
    node_name : retopoGuideNode のシェイプ名またはトランスフォーム名。
                省略時は optionVar / アクティブ選択から自動取得。
    target : ターゲット名 (str) か weight インデックス (int)。
             ``None`` なら Shape Editor の選択、それも無ければ最後の
             ターゲット。
    additive : True なら既存の点デルタに加算する。False なら置き換え。
               スカルプト中はターゲットのウェイトを 1.0 にしておくのが前提
               (Shape Editor の編集モードと同じ) なので既定は加算。
    weight : 焼き込み後に設定するウェイト値。``None`` なら変更しない。

    Returns
    -------
    (blendShape ノード名, ターゲット名, 焼き込んだ点数) のタプル。
    """
    shape = _long_name(_resolve_curvenet_shape(node_name))
    if not shape:
        raise RuntimeError("retopoGuideNode が見つかりません。")

    bs = find_blend_shape(shape)
    if not bs:
        raise RuntimeError(
            "blendShape がありません。"
            "先に「現在のスカルプトを新規ターゲットにする」を実行するか、"
            "Shape Editor でブレンドシェイプを作成してください。")

    # デフォーマの並べ替えは tweak を動かしうるので、スカルプト差分の
    # 読み取りを先に済ませる。
    local_map = current_sculpt_deltas(shape)
    if not local_map:
        raise RuntimeError(
            "controlPoints に編集がありません。"
            "先にカーブネットをスカルプトしてください。")

    # Shape Editor から作られた blendShape はチェーンの末尾に付くので、
    # ポーズスペースになるよう skinCluster より前へ移す。
    if ensure_front_of_chain(shape, bs):
        cmds.warning("blendShape '%s' を skinCluster より前に移動しました "
                     "(補正をポーズと一緒に回すため)。" % bs)

    if target is None:
        sel = selected_shape_editor_target(bs)
        if sel:
            bs, widx = sel
        else:
            idx = cmds.getAttr(bs + ".w", mi=True) or []
            if not idx:
                raise RuntimeError("ターゲットが 1 つもありません。")
            widx = max(idx)
    else:
        widx = target_index(bs, target)

    if additive:
        merged = read_point_deltas(bs, widx)
        for k, v in local_map.items():
            old = merged.get(k)
            merged[k] = ([old[0] + v[0], old[1] + v[1], old[2] + v[2]]
                         if old else list(v))
    else:
        merged = local_map

    count = write_point_deltas(bs, widx, merged)

    names = cmds.listAttr(bs + ".w", multi=True) or []
    idx = cmds.getAttr(bs + ".w", mi=True) or []
    tname = next((n for n, i in zip(names, idx) if i == widx), str(widx))
    if weight is not None:
        try:
            cmds.setAttr("%s.%s" % (bs, tname), float(weight))
        except Exception:
            pass
    return bs, tname, count


def bake_to_selected_target(node_name=""):
    """Shape Editor で選択中のターゲットへ焼き込む (メニューからの入口)。"""
    return bake_to_target(node_name, target=None, additive=True)


def active_sculpt_target(shape):
    """ターゲット編集モード中の ``(blendShape, widx)``。

    Shape Editor で「ターゲットの編集」に入る (= ``cmds.sculptTarget``) と
    blendShape の ``inputTarget[0].sculptTargetIndex`` に、編集中ターゲットの
    weight インデックスが入る。編集モードでなければ ``(None, None)``。
    """
    shape = _long_name(shape)
    if not shape:
        return None, None
    bs = find_blend_shape(shape)
    if not bs:
        return None, None
    try:
        widx = cmds.getAttr(bs + ".inputTarget[0].sculptTargetIndex")
    except Exception:
        return None, None
    if widx is None or int(widx) < 0:
        return None, None
    widx = int(widx)
    if widx not in (cmds.getAttr(bs + ".w", mi=True) or []):
        return None, None
    return bs, widx


def create_blend_target(node_name="", target_name="", weight=1.0):
    """現在のスカルプトを新しい blendShape ターゲットとして確定する。

    blendShape が無ければ ``frontOfChain`` で作成し、空ターゲットを追加して
    そこへ点デルタを書き込む。ジオメトリの複製は作らないので、Shape Editor
    からは普通のターゲットとして見える。

    Parameters
    ----------
    node_name : retopoGuideNode のシェイプ名またはトランスフォーム名。
                省略時は optionVar / アクティブ選択から自動取得。
    target_name : 作成するターゲットの名前。省略時は自動採番。
    weight : 作成直後に設定するウェイト値。

    Returns
    -------
    (blendShape ノード名, ターゲット名) のタプル。

    Raises
    ------
    RuntimeError : retopoGuide が見つからない / スカルプトされていない場合。
    """
    shape = _long_name(_resolve_curvenet_shape(node_name))
    if not shape:
        raise RuntimeError("retopoGuideNode が見つかりません。")

    parents = cmds.listRelatives(shape, parent=True, fullPath=True) or []
    if not parents:
        raise RuntimeError("retopoGuideNode の親トランスフォームがありません。")
    xf = parents[0]

    if not read_control_point_deltas(shape):
        raise RuntimeError(
            "controlPoints に編集がありません。"
            "先にカーブネットをスカルプトしてください。")

    # blendShape を作ると Maya が tweak ノードを挿入してシェイプの
    # controlPoints を移してしまうので、デルタの読み取りを必ず先に済ませる。
    local_map = current_sculpt_deltas(shape)
    if not local_map:
        raise RuntimeError("スカルプト差分をレスト空間へ変換できませんでした。")

    bs = ensure_blend_shape(shape)
    widx, tname = add_empty_target(bs, xf, target_name)
    write_point_deltas(bs, widx, local_map)

    try:
        cmds.setAttr("%s.%s" % (bs, tname), float(weight))
    except Exception:
        pass
    return bs, tname

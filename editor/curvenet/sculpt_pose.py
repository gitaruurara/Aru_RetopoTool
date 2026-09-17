# -*- coding: utf-8 -*-
"""ポーズスペース・スカルプト (PSD) の数学。

論文 §3「リギング」より:

    実装はスキニングやスカルプティングなどの既存のリギング技術に基づいて
    制御点をポーズするだけでカーブネットをアーティキュレートする機能も
    提供する。

つまりカーブネットの CV は「点数の少ない普通のジオメトリ」であり、
その補正スカルプトは普通の **ポーズスペースデフォーム (PSD)** として
振る舞うべきである。Pixar のデモで見られる

    腕を曲げる → その状態でカーブネットを微調整 → 角度を変えると
    シェイプに追従しながら戻り、同じ角度に戻すと同じ編集が復活する

はまさに PSD の挙動である。

旧実装は ``envelope = smoothstep(|スキン変位| / ref)`` という
「変位の大きさ」だけの関数だったため、以下が壊れていた:

  1. 逆方向に曲げても変位の大きさは同じ → 補正が全効きしてしまう
  2. 別の軸で回しても同じ → 補正が全効きしてしまう
  3. 補正がワールド空間の定数ベクトル → シェイプに追従しない

本モジュールは代わりに **CV ごとの局所回転** をポーズ記述子として使う。

  * スカルプト時の回転ベクトル ``q`` を記録しておく
  * 評価時の回転ベクトル ``r`` と比べて重みを決める
      - 進行度   ``t = (r·q)/(q·q)``  … 同じ軸で深く曲げると t>1
      - 横ずれ   ``perp = |r - t q| / |q|`` … 別軸だと大きくなる
      - ``w = smoothstep(clamp(t,0,1)) * (1 - smoothstep(perp/tol))``
  * オフセット自体も ``R_now R_sculpt^T`` で回してシェイプに追従させる

回転ベクトルを使うのが要点。回転角に対して線形なので「同じ軸でもっと
深く曲げた」が ``t`` の増加として素直に出る。変位ベクトルを直接使うと、
弦ベクトルの向きが回転角の半分だけ回ってしまい、45 度と 90 度が
22.5 度ずれた別ポーズだと誤判定されてしまう。
"""

from __future__ import annotations

import math

# 横ずれの許容量 (|q| に対する比)。これを超えると補正は完全に消える。
POSE_FALLOFF_DEFAULT = 0.5

# 記録された回転がこれ未満なら「バインドポーズでのスカルプト」とみなし、
# ポーズ信号が無いのでレスト編集として常時適用する。
POSE_MIN_ROT = 1.0e-3

_EPS = 1.0e-12


# ----------------------------------------------------------------------
# ベクトル / 行列 (3x3 を「行のリスト」で表す)
# ----------------------------------------------------------------------
def _sub(a, b):
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return [a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0]]


def _length(a):
    return math.sqrt(_dot(a, a))


def _normalize(a):
    n = _length(a)
    if n < _EPS:
        return None
    return [a[0] / n, a[1] / n, a[2] / n]


def _identity():
    return [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]


def _mat_apply(m, v):
    return [_dot(m[0], v), _dot(m[1], v), _dot(m[2], v)]


def _mat_transpose(m):
    return [[m[0][0], m[1][0], m[2][0]],
            [m[0][1], m[1][1], m[2][1]],
            [m[0][2], m[1][2], m[2][2]]]


def _mat_mul(a, b):
    bt = _mat_transpose(b)
    return [[_dot(a[r], bt[c]) for c in range(3)] for r in range(3)]


def _perpendicular(a):
    """``a`` に直交する適当な単位ベクトル。"""
    ref = [1.0, 0.0, 0.0] if abs(a[0]) < 0.9 else [0.0, 1.0, 0.0]
    return _normalize(_cross(a, ref)) or [0.0, 1.0, 0.0]


def _min_rotation(a, b):
    """単位ベクトル ``a`` を ``b`` に写す最小回転行列。

    論文が孤立カーブの変形グラジェントに使うのと同じ「静止タンジェント
    からの最小回転」。
    """
    v = _cross(a, b)
    s = _length(v)
    c = _dot(a, b)
    if s < 1.0e-9:
        if c > 0.0:
            return _identity()
        # 180 度: 適当な直交軸まわりの反転
        return _rotvec_to_matrix([x * math.pi for x in _perpendicular(a)])
    k = [[0.0, -v[2], v[1]],
         [v[2], 0.0, -v[0]],
         [-v[1], v[0], 0.0]]
    kk = _mat_mul(k, k)
    f = (1.0 - c) / (s * s)
    return [[(1.0 if r == cc else 0.0) + k[r][cc] + kk[r][cc] * f
             for cc in range(3)] for r in range(3)]


def _basis(a, b):
    """``a``, ``b`` から正規直交基底 (行 = 基底ベクトル) を作る。

    ワールド座標を局所座標に写す行列。``a``, ``b`` が平行なら None。
    """
    e0 = _normalize(a)
    if e0 is None:
        return None
    d = _dot(b, e0)
    t = [b[0] - e0[0] * d, b[1] - e0[1] * d, b[2] - e0[2] * d]
    e1 = _normalize(t)
    if e1 is None:
        return None
    return [e0, e1, _cross(e0, e1)]


def _rotvec_to_matrix(q):
    """回転ベクトル (軸 × 角) → 回転行列 (ロドリゲス)。"""
    angle = _length(q)
    if angle < 1.0e-12:
        return _identity()
    ax = [q[0] / angle, q[1] / angle, q[2] / angle]
    c = math.cos(angle)
    s = math.sin(angle)
    t = 1.0 - c
    x, y, z = ax
    return [[t * x * x + c,     t * x * y - s * z, t * x * z + s * y],
            [t * x * y + s * z, t * y * y + c,     t * y * z - s * x],
            [t * x * z - s * y, t * y * z + s * x, t * z * z + c]]


def _matrix_to_rotvec(m):
    """回転行列 → 回転ベクトル (軸 × 角)。"""
    tr = m[0][0] + m[1][1] + m[2][2]
    c = max(-1.0, min(1.0, (tr - 1.0) * 0.5))
    angle = math.acos(c)
    if angle < 1.0e-9:
        return [0.0, 0.0, 0.0]
    s = math.sin(angle)
    if s < 1.0e-9:
        # 角度が pi 付近: R = I + 2 aa^T - 2I の対角から軸を取る
        d = [max(0.0, (m[i][i] + 1.0) * 0.5) for i in range(3)]
        i = max(range(3), key=lambda k: d[k])
        ax = [0.0, 0.0, 0.0]
        ax[i] = math.sqrt(d[i])
        if ax[i] > 1.0e-9:
            for k in range(3):
                if k != i:
                    ax[k] = (m[i][k] + m[k][i]) * 0.25 / ax[i]
        ax = _normalize(ax) or [1.0, 0.0, 0.0]
        return [x * angle for x in ax]
    f = angle / (2.0 * s)
    return [(m[2][1] - m[1][2]) * f,
            (m[0][2] - m[2][0]) * f,
            (m[1][0] - m[0][1]) * f]


def _smoothstep01(x):
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    return x * x * (3.0 - 2.0 * x)


# ----------------------------------------------------------------------
# CV ごとの局所回転
# ----------------------------------------------------------------------
def build_adjacency(splines, count):
    """スプラインの制御ポリゴンから CV の隣接リストを作る。"""
    adj = [set() for _ in range(count)]
    for sp in (splines or []):
        idx = [i for i in sp if 0 <= i < count]
        for k in range(len(idx) - 1):
            a, b = idx[k], idx[k + 1]
            if a != b:
                adj[a].add(b)
                adj[b].add(a)
    return [sorted(s) for s in adj]


def compute_cv_rotations(base_positions, deformed_positions, splines):
    """CV ごとの局所回転行列のリストを返す。

    隣接 CV へのオフセットがレストからどう回ったかで推定する。隣接が
    1 つ (または全て平行) の場合は最小回転、2 つ以上あって独立なら
    正規直交基底同士の変換として求める。
    """
    n = min(len(base_positions), len(deformed_positions))
    if n <= 0:
        return []
    adj = build_adjacency(splines, n)
    out = []
    for i in range(n):
        pairs = []
        for k in adj[i]:
            if k >= n:
                continue
            a = _sub(base_positions[k], base_positions[i])
            b = _sub(deformed_positions[k], deformed_positions[i])
            if _length(a) > 1.0e-9 and _length(b) > 1.0e-9:
                pairs.append((a, b))
        if not pairs:
            out.append(_identity())
            continue

        a0, b0 = pairs[0]
        rot = None
        if len(pairs) > 1:
            n0 = _normalize(a0)
            best = None
            for a1, b1 in pairs[1:]:
                n1 = _normalize(a1)
                if n1 is None or n0 is None:
                    continue
                # 平行に近い組は基底が作れないので除外
                sep = _length(_cross(n0, n1))
                if best is None or sep > best[0]:
                    best = (sep, a1, b1)
            if best is not None and best[0] > 0.1:
                fa = _basis(a0, best[1])
                fb = _basis(b0, best[2])
                if fa is not None and fb is not None:
                    rot = _mat_mul(_mat_transpose(fb), fa)
        if rot is None:
            na = _normalize(a0)
            nb = _normalize(b0)
            rot = _min_rotation(na, nb) if (na and nb) else _identity()
        out.append(rot)
    return out


# ----------------------------------------------------------------------
# ポーズ重み
# ----------------------------------------------------------------------
def pose_weight(cur_rotvec, sculpt_rotvec, tol=POSE_FALLOFF_DEFAULT):
    """スカルプト時のポーズにどれだけ近いかを 0..1 で返す。

    * バインドポーズ (r=0)          → 0
    * スカルプトしたポーズ (r=q)    → 1
    * 逆方向 (r=-q)                 → 0
    * 同じ軸でさらに深く (r=2q)     → 1 のまま保持
    * 別の軸 (r⊥q)                  → 0
    """
    q2 = _dot(sculpt_rotvec, sculpt_rotvec)
    if q2 < POSE_MIN_ROT * POSE_MIN_ROT:
        # スカルプト時にそもそも回転していない = ポーズ信号が無い。
        # レスト編集として常時適用する (捨ててしまうより自然)。
        return 1.0
    t = _dot(cur_rotvec, sculpt_rotvec) / q2
    if t <= 0.0:
        return 0.0
    w = _smoothstep01(t if t < 1.0 else 1.0)
    if tol > 1.0e-6:
        perp = [cur_rotvec[k] - t * sculpt_rotvec[k] for k in range(3)]
        d = _length(perp) / math.sqrt(q2)
        w *= 1.0 - _smoothstep01(d / tol if d < tol else 1.0)
    return w


def rotvec_at(base_positions, deformed_positions, splines, index):
    """1 つの CV の現在の回転ベクトルを返す (記録用)。"""
    rots = compute_cv_rotations(base_positions, deformed_positions, splines)
    if index < 0 or index >= len(rots):
        return [0.0, 0.0, 0.0]
    return _matrix_to_rotvec(rots[index])


def rotvecs(base_positions, deformed_positions, splines):
    """全 CV の現在の回転ベクトルを返す (記録用)。"""
    return [_matrix_to_rotvec(m) for m in
            compute_cv_rotations(base_positions, deformed_positions, splines)]


# ----------------------------------------------------------------------
# 適用
# ----------------------------------------------------------------------
def legacy_envelopes(base_positions, deformed_positions, ref_fraction):
    """ポーズ未記録の CP 用の後方互換エンベロープ (変位の大きさ基準)。"""
    n = min(len(base_positions), len(deformed_positions))
    if n <= 0:
        return []
    frac = float(ref_fraction)
    if frac <= 0.0:
        return [1.0] * n
    lo = [1e30] * 3
    hi = [-1e30] * 3
    for p in base_positions:
        for k in range(3):
            if p[k] < lo[k]:
                lo[k] = p[k]
            if p[k] > hi[k]:
                hi[k] = p[k]
    diag = math.sqrt(sum((hi[k] - lo[k]) ** 2 for k in range(3)))
    ref = max(diag * frac, 1.0e-4)
    out = []
    for i in range(n):
        d = _sub(deformed_positions[i], base_positions[i])
        out.append(_smoothstep01(_length(d) / ref))
    return out

# ----------------------------------------------------------------------
# 多ターゲット PSD (1 CV に複数ポーズ)
# ----------------------------------------------------------------------
# 論文 §3「リギング」は制御点のポーズ付けを「スキニングやスカルプティング
# などの既存のリギング技術」に委ねている。§1 が言うようにその実体は
# 「補正ブレンドシェープと組み合わせたスキニング」であり、本質的に
# 多ポーズ対応である。よって 1 CV につき任意個のポーズを保持する。
#
# 基底関数に pose_weight をそのまま使い、係数を解いて各記録ポーズで
# 厳密に元のスカルプトが再現されるようにする:
#
#     E(r) = Σ_k c_k · pose_weight(r, q_k)
#     制約   E(q_j) = e_j   (全 j)
#
# ターゲットが 1 つのときは c_1 = e_1 となり従来と完全に一致する。
# オフセット e_k は CV のローカルフレームで保持するのでシェイプに追従する。

# ポーズがこの角度 (rad) 以内なら同一ポーズとみなして置き換える
POSE_MERGE_TOL = 0.05

# 連立方程式の正則化 (ほぼ同一のポーズが混ざったときの保険)
POSE_SOLVE_RIDGE = 1.0e-6


def _solve_linear(mat, rhs, ridge=POSE_SOLVE_RIDGE):
    """``mat`` (n x n) ``X`` = ``rhs`` (n x m) を Gauss-Jordan で解く。"""
    n = len(mat)
    if n == 0:
        return []
    m = len(rhs[0])
    aug = [list(mat[i]) + list(rhs[i]) for i in range(n)]
    for i in range(n):
        aug[i][i] += ridge
    for col in range(n):
        piv = col
        for r in range(col + 1, n):
            if abs(aug[r][col]) > abs(aug[piv][col]):
                piv = r
        if abs(aug[piv][col]) < 1.0e-12:
            continue
        if piv != col:
            aug[col], aug[piv] = aug[piv], aug[col]
        inv = 1.0 / aug[col][col]
        for k in range(col, n + m):
            aug[col][k] *= inv
        for r in range(n):
            if r == col:
                continue
            f = aug[r][col]
            if f == 0.0:
                continue
            for k in range(col, n + m):
                aug[r][k] -= f * aug[col][k]
    return [[aug[i][n + j] for j in range(m)] for i in range(n)]


def _residual(mat, coeffs, rhs):
    """``mat`` ``coeffs`` - ``rhs`` の最大絶対誤差。"""
    worst = 0.0
    for j in range(len(mat)):
        for c in range(len(rhs[j])):
            acc = 0.0
            for k in range(len(coeffs)):
                acc += mat[j][k] * coeffs[k][c]
            diff = abs(acc - rhs[j][c])
            if diff > worst:
                worst = diff
    return worst


def solve_target_coeffs(targets, pose_falloff=POSE_FALLOFF_DEFAULT):
    """``targets`` = [(q, e)] から基底係数を解く。

    ``e`` は CV ローカルフレームでのオフセット。

    まず正則化なしで解き、記録ポーズを厳密に再現できなかった場合だけ
    リッジを足して解き直す。常にリッジを足すと再現誤差が残り、
    「同じ角度に戻すと同じ編集が復元される」という要件を満たせない。
    """
    n = len(targets)
    if n == 0:
        return []
    mat = [[pose_weight(targets[j][0], targets[k][0], pose_falloff)
            for k in range(n)] for j in range(n)]
    rhs = [list(targets[j][1]) for j in range(n)]

    coeffs = _solve_linear(mat, rhs, 0.0)
    scale = 1.0
    for row in rhs:
        for v in row:
            if abs(v) > scale:
                scale = abs(v)
    if coeffs and _residual(mat, coeffs, rhs) <= 1.0e-7 * scale:
        return coeffs
    return _solve_linear(mat, rhs, POSE_SOLVE_RIDGE)


def eval_target_blend(cur_rotvec, targets, coeffs,
                      pose_falloff=POSE_FALLOFF_DEFAULT):
    """現在のポーズにおけるローカル空間オフセットを返す。"""
    out = [0.0, 0.0, 0.0]
    for k in range(min(len(targets), len(coeffs))):
        w = pose_weight(cur_rotvec, targets[k][0], pose_falloff)
        if w <= 1.0e-12:
            continue
        c = coeffs[k]
        out[0] += w * c[0]
        out[1] += w * c[1]
        out[2] += w * c[2]
    return out


def commit_target(targets, q, e, tol=POSE_MERGE_TOL):
    """ターゲットを追加する。近いポーズが既にあれば置き換える。"""
    for k in range(len(targets)):
        if _length(_sub(list(q), list(targets[k][0]))) <= tol:
            targets[k] = (list(q), list(e))
            return targets
    targets.append((list(q), list(e)))
    return targets


def unpack_targets(rows):
    """[[qx,qy,qz,ex,ey,ez], ...] → [(q, e)]"""
    out = []
    for row in rows or []:
        if len(row) >= 6:
            out.append(([float(row[0]), float(row[1]), float(row[2])],
                        [float(row[3]), float(row[4]), float(row[5])]))
    return out


def pack_targets(targets):
    """[(q, e)] → [[qx,qy,qz,ex,ey,ez], ...]"""
    return [[float(q[0]), float(q[1]), float(q[2]),
             float(e[0]), float(e[1]), float(e[2])] for q, e in targets]


def pending_target(q, delta, stored, pose_falloff=POSE_FALLOFF_DEFAULT):
    """編集中の ``controlPoints`` を確定用ターゲット値に変換する。

    ユーザは「今表示されている形」からドラッグするので、そのポーズでの
    目標値は「既存ターゲットの寄与 + ドラッグ量」になる。
    """
    coeffs = solve_target_coeffs(stored, pose_falloff)
    base_local = eval_target_blend(list(q), stored, coeffs, pose_falloff)
    rq_t = _mat_transpose(_rotvec_to_matrix(list(q)))
    dl = _mat_apply(rq_t, [float(delta[0]), float(delta[1]), float(delta[2])])
    return [base_local[k] + dl[k] for k in range(3)]


def sculpt_offsets(base_positions, deformed_positions, splines,
                   delta_map, pose_map,
                   pose_falloff=POSE_FALLOFF_DEFAULT,
                   legacy_fraction=0.35,
                   target_map=None):
    """実際に適用すべきワールド空間のスカルプトオフセットを返す。

    Parameters
    ----------
    delta_map : {idx: (dx, dy, dz)}
        ``controlPoints`` に入っている編集中の生オフセット。
    pose_map : {idx: (qx, qy, qz)}
        そのオフセットをスカルプトしたときの CV の回転ベクトル。
    target_map : {idx: [[qx,qy,qz,ex,ey,ez], ...]}
        確定済みの多ポーズターゲット。``e`` はローカルフレーム。

    ``pose_map`` にも ``target_map`` にも無いインデックスは後方互換の
    大きさ基準エンベロープで扱う。

    Returns
    -------
    {idx: [dx, dy, dz]}  重みとフレーム追従を適用済み
    """
    delta_map = delta_map or {}
    target_map = target_map or {}
    keys = set(delta_map) | set(target_map)
    if not keys:
        return {}

    need_rot = any((i in pose_map) or (i in target_map) for i in keys)
    rots = (compute_cv_rotations(base_positions, deformed_positions, splines)
            if need_rot else [])
    legacy = None
    out = {}

    for idx in sorted(keys):
        if idx < 0 or idx >= len(base_positions):
            continue
        d = delta_map.get(idx)
        q = pose_map.get(idx)
        stored = unpack_targets(target_map.get(idx))

        if not stored and q is None:
            # ポーズ未記録 (旧シーン) → 従来の大きさ基準
            if d is None:
                continue
            if legacy is None:
                legacy = legacy_envelopes(base_positions, deformed_positions,
                                          legacy_fraction)
            w = legacy[idx] if idx < len(legacy) else 0.0
            if w > 1.0e-9:
                out[idx] = [d[0] * w, d[1] * w, d[2] * w]
            continue

        rot = rots[idx] if idx < len(rots) else _identity()
        r = _matrix_to_rotvec(rot)

        work = [(list(qk), list(ek)) for qk, ek in stored]
        if d is not None and q is not None and _length(list(d)) > 1.0e-12:
            e = pending_target(q, d, work, pose_falloff)
            work = commit_target(work, list(q), e)
        if not work:
            continue

        coeffs = solve_target_coeffs(work, pose_falloff)
        local = eval_target_blend(r, work, coeffs, pose_falloff)
        v = _mat_apply(rot, local)
        if abs(v[0]) + abs(v[1]) + abs(v[2]) > 1.0e-12:
            out[idx] = [v[0], v[1], v[2]]

    return out

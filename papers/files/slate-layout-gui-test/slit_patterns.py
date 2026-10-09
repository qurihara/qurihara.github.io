#!/usr/bin/env python3
# ★この複製（gui/slit_patterns.py）は、ブラウザの Pyodide で動かすために、幾何演算の前に座標を 1e-6mm の格子に丸めている（_snap）。
#   Pyodide の GEOS は、丸めないと buffer と intersection で "non-noded intersection" の致命的な例外を出す（2026-10-09 に実際に起きた）。
#   リポジトリ直下の slit_patterns.py（設計スクリプトが使う正本）は変えていない。結果の一致は gui/verify_core.py で確かめる。
import shapely
def _snap(g): return shapely.set_precision(g, 1e-6)
# 分割タッチボタンのスリット形状ライブラリ（2D・ボタン中心が原点・+y が Pico 側＝奥）。
#  ボタンは直径 s の面取り円柱を「切り欠き経路（cut path）」で幅 w のスリットに削って2領域に分ける。
#  ここでは経路を shapely の LineString / Polygon 境界として定義し、
#   ・cutter … 経路を w/2 で膨らませたスリット領域（円柱から差し引く。埋め材はこれと円柱の交差）
#   ・A, B   … 円板から cutter を除いた2領域（A=信号側・B=GND側）
#   ・via    … 各領域で最も太い場所（内接円の中心）＝via を立てる位置と、その内接半径
#   ・coverage … 上面の任意点に半径ρの指を置いたとき両領域に触れるために必要なρの最大値
#  を返す。設計スクリプト（design_stl_v2.py --slit <name>）はこの結果だけを使う。
#
#  パターン一覧（--slit で指定）
#   straight      … 現行。水平一直線（比較基準）
#   ─ 上面全域どこを触れても導通させる系（要望2）
#   meander       … 水平の蛇行。上下2つの「くし」が互い違いに噛み合う。ピッチ p（既定5mm）
#   zigzag        … 三角波の蛇行。くしの歯が三角形。ピッチ p
#   spiral        … S字の二重らせん（アルキメデス）。中心で反転する1本の曲線で2つの渦巻き帯に分ける
#   radial        … 放射くし（太陽型）。中心ハブ＋放射スポーク(A) と 外周リング＋内向きの歯(B)
#   ─ 下半分だけ導通し、上半分は指を置いて休んでも導通しない系（要望3）
#   lower_meander … 蛇行を下半分に限定。上半分は丸ごと A（信号）で、B は下半分の横向きの歯
#   lower_fan     … 下半分に放射状の扇の歯(B)。外周の帯で歯を連結。上半分は丸ごと A
#   lower_arcs    … 下半分に同心の弧(B)。真下の背骨で弧を連結。上半分は丸ごと A
import math
import numpy as np
from shapely.geometry import LineString, Polygon, Point, MultiPolygon, box
from shapely.ops import unary_union
import shapely.affinity as aff
try:
    from shapely.ops import polylabel as _polylabel
except Exception:   # 古い shapely
    _polylabel = None

FULL = ("meander", "zigzag", "spiral", "radial")
LOWER = ("lower_meander", "lower_fan", "lower_arcs")
PATTERNS = ("straight",) + FULL + LOWER
# 参照用ラベル（cosense・論文・会話で使う短い識別子）。規則: <ID>[/<弧角度>][F]（F=非導電の埋め材あり）。
#   既定値以外のピッチ・フィレット・面取りは "-p4" "-f0.5" "-c0" を後ろに付ける。例: B7/240F、B1-p4、B7F
LABELS = {"straight": "B0", "meander": "B1", "zigzag": "B2", "spiral": "B3", "radial": "B4",
          "lower_meander": "B5", "lower_fan": "B6", "lower_arcs": "B7"}
def label(name, arc=180.0, fill=False, p=5.0, fillet=0.8, cham=0.4):
    L = LABELS[name]
    if name == "lower_arcs": L += "/%g" % arc
    if fill: L += "F"
    if p != 5.0: L += "-p%g" % p
    if fillet != 0.8: L += "-f%g" % fillet
    if cham != 0.4: L += "-c%g" % cham
    return L
SPINE = 2.5      # 蛇行の折返しが外周に残す連結幅（mm）＝くしの背の太さ
RIM = 2.5        # 外周の帯の幅（radial / lower_fan）
EXT = 3.0        # 経路が円の外へはみ出す長さ（外縁で確実に切り離す）


def _halfw(r, y):
    return math.sqrt(max(r * r - y * y, 0.0))


def _rin(r, w):
    return r - SPINE - w / 2          # 折返し弧の半径（外周に SPINE 幅の背を残す）


def _serpentine(r, w, rows):
    """rows（y座標の列）を順に折り返す蛇行経路。折返しは半径 _rin の弧に沿う（歯を縁まで伸ばす）。
    最初と最後の行は円の外へ抜ける。"""
    R = _rin(r, w)
    def xt(y): return math.sqrt(max(R * R - y * y, 1.0))
    pts = []
    d = 1  # +1: 左→右
    for i, y in enumerate(rows):
        ynext = rows[i + 1] if i + 1 < len(rows) else None
        if i == 0:
            pts.append((-d * (r + EXT), y))
        if ynext is None:
            pts.append((d * (r + EXT), y))
            break
        a0, a1 = math.atan2(y, d * xt(y)), math.atan2(ynext, d * xt(ynext))
        if d < 0 and a1 - a0 > math.pi: a1 -= 2 * math.pi   # 左側は角度が ±π をまたぐ
        if d < 0 and a0 - a1 > math.pi: a0 -= 2 * math.pi
        for a in np.linspace(a0, a1, 10):
            pts.append((R * math.cos(a), R * math.sin(a)))
        d = -d
    return LineString(pts)


def _rows_full(r, p, w=1.0):
    ymax = _rin(r, w) - 1.0
    n = int((2 * ymax) // p) + 1
    return [(i - (n - 1) / 2) * p for i in range(n)]


def _rows_lower(r, p, w=1.0):
    """下半分を y=0 から折返し弧の内側まで、ピッチ p 以下の等間隔で埋める行。"""
    ymax = _rin(r, w) - 1.0
    n = int(math.ceil(ymax / p)) + 1
    step = ymax / (n - 1)
    return [-step * i for i in range(n)]


def _zigzag(r, w, rows):
    """三角波：各行の折返し点を交互の側に置き、斜めに結ぶ。最初は左外から入り、最後は外へ抜ける。"""
    R = _rin(r, w)
    def xt(y): return math.sqrt(max(R * R - y * y, 1.0))
    pts = [(-(r + EXT), rows[0])]
    d = 1
    for i in range(len(rows) - 1):
        y = rows[i]
        pts.append((d * xt(y), y))
        d = -d
    pts.append((d * xt(rows[-1]), rows[-1]))
    pts.append((d * (r + EXT), rows[-1]))
    return LineString(pts)


def _spiral(r, w, p):
    b = p / math.pi                     # 隣り合う巻き（別の腕）の間隔が p
    tmax = (r + EXT) / b
    t = np.linspace(0, tmax, 400)
    arm = np.c_[b * t * np.cos(t), b * t * np.sin(t)]
    path = np.vstack([-arm[::-1], arm[1:]])   # 反対の腕（点対称）→中心→この腕
    return LineString(path)


#  領域を Polygon で与える系（radial / lower_fan / lower_arcs）は、その境界を中心に幅 w のスリットが
#  削られるので、導電として残る歯の幅は「多角形の幅 − w」になる。以下は残る幅 T_MIN 以上を確保する。
T_MIN = 2.2      # 導電の歯として残す最小幅（0.4mmノズルで壁2本＋充填が入る）


def _wedge(a0, a1, R):
    return Polygon([(0, 0)] + [(R * math.cos(math.radians(a)), R * math.sin(math.radians(a))) for a in np.linspace(a0, a1, 80)])


def _radial_regionA(r, w, n=None):
    if n is None: n = max(5, int(round(2 * math.pi * 0.62 * r / 8.0)))   # φ24→6本・φ30→7本
    hub = Point(0, 0).buffer(0.30 * r, resolution=64)
    sw = max(T_MIN + w, 3.6)                                # スポーク幅（削られて残るのは sw−w）
    spokes = []
    L = r - RIM - w / 2
    for k in range(n):
        a = 2 * math.pi * k / n + math.pi / 2
        rect = box(0, -sw / 2, L, sw / 2)
        spokes.append(aff.rotate(rect, math.degrees(a), origin=(0, 0)))
    return unary_union([hub] + spokes)


def _lower_fan_regionB(r, w, n=None):
    """下半分の扇：外周帯(B)から中心へ向かう扇形の歯(B)。歯は角度一定の扇形なので、先端まで A の
    ポケットが閉じずに残る（長方形の歯だと先端で隣どうしが接して A が孤立した）。"""
    if n is None: n = 3 if r < 14 else 4                    # φ24→3本・φ30→4本
    A0, A1 = 186.0, 354.0                                   # 外周帯の角度範囲（下半分・真横は避ける）
    band = (Point(0, 0).buffer(r + EXT, resolution=96).difference(Point(0, 0).buffer(r - RIM, resolution=96))
            ).intersection(_wedge(A0, A1, r + EXT + 1))
    pitch = (A1 - A0) / n
    half = pitch / 4                                        # 歯の半角（歯とポケットが同じ角幅）
    # 先端半径：先端での歯の幅（2·Ri·sin(half)）からスリット w を引いて T_MIN 以上残る位置
    inner = max(0.26 * r, (T_MIN + w) / (2 * math.sin(math.radians(half))))
    teeth = []
    for k in range(n):
        a = A0 + pitch * (k + 0.5)
        sec = _wedge(a - half, a + half, r + EXT).difference(Point(0, 0).buffer(inner, resolution=64))
        teeth.append(sec)
    return unary_union([band] + teeth)


def _lower_arcs_regionB(r, w, p, arc=180.0):
    """下半分の同心弧。arc は弧の角度範囲（度・真下 270° を中心）。180 でちょうど半円。"""
    t = max(T_MIN, (p - 2 * w) / 2)                         # 残る歯の幅（B の弧も A の弧も同じ）
    sw = t + w + 0.6                                        # 背骨の幅（GND via が入るよう少し太く）
    spine = box(-sw / 2, -(r + EXT), sw / 2, -0.12 * r)
    period = 2 * (t + w)                                    # B弧・スリット・A弧・スリット で1周期
    wedge = _wedge(270 - arc / 2, 270 + arc / 2, r + EXT)   # 弧の角度範囲（既定 180°＝半円）
    arcs = []
    k = 0
    while True:
        # 一番外の B 弧は外周（縁）まで届かせる＝縁に細い A の帯を残さない。内側の縁だけをスリットで切る。
        outer = (r + EXT) if k == 0 else (r - k * period + w / 2)
        inner = r - k * period - t - w / 2
        if inner < 0.22 * r: break
        ring = Point(0, 0).buffer(outer, resolution=96).difference(Point(0, 0).buffer(inner, resolution=96))
        arcs.append(ring.intersection(wedge))
        k += 1
    return unary_union([spine] + arcs)


def cut_path(name, r, w=1.0, p=5.0, arc=180.0):
    """切り欠き経路（LineString）または領域境界（Polygon の boundary）を返す。"""
    if name == "straight":
        return LineString([(-(r + EXT), 0), (r + EXT, 0)])
    if name == "meander":
        return _serpentine(r, w, _rows_full(r, p, w))
    if name == "zigzag":
        return _zigzag(r, w, _rows_full(r, p, w))
    if name == "spiral":
        return _spiral(r, w, p)
    if name == "radial":
        return _radial_regionA(r, w).boundary
    if name == "lower_meander":
        return _serpentine(r, w, _rows_lower(r, p, w))
    if name == "lower_fan":
        return _lower_fan_regionB(r, w).boundary
    if name == "lower_arcs":
        return _lower_arcs_regionB(r, w, p, arc).boundary
    raise ValueError("unknown slit pattern: %s" % name)


def pad_mesh(pat, s, a, b, cx=0.0, cy=0.0, rimcham=0.4, cham=0.4, steps=4, want_fill=False):
    """スリット設計 pat（build の結果）から、ボタンの導電立体（と埋め材）を作る。
    面取り円柱（上縁 rimcham の45°面取り）に対し、領域 A・B を押し出したものを交差させる。
    スリット壁の上縁は、天面側の薄い層ほど領域を内側へ縮めて（階段 steps 段）45°の面取り cham を付ける。
    埋め材（want_fill）は「円柱 − ボタン」なので、スリットと面取りの分だけ天面側が広い V 字断面になる。
    戻り値 (pad, fill)。fill は want_fill=False なら None。"""
    import trimesh
    from trimesh import creation
    r = s / 2; h = b - a
    prof = [[0, 0], [r, 0], [r, h - rimcham], [r - rimcham, h], [0, h]]
    body = creation.revolve(prof, sections=96); body.apply_translation([cx, cy, a])
    def ext(poly, za, zb):
        gs = list(poly.geoms) if hasattr(poly, "geoms") else [poly]
        outm = []
        for g in gs:
            if g.is_empty or g.area < 1e-6: continue
            # 丸め処理で頂点が密になった多角形（φ30で700点超）は押し出しが体積にならないことがある。
            # 0.02mm で間引くと解消する（形状誤差は無視できる）。それでも駄目なら縮小→拡大で整える。
            g2 = g.simplify(0.02, preserve_topology=True)
            m = creation.extrude_polygon(g2, zb - za)
            if not m.is_volume:
                g2 = g.buffer(-0.01).buffer(0.01)
                for g3 in (list(g2.geoms) if hasattr(g2, "geoms") else [g2]):
                    if g3.is_empty or g3.area < 1e-6: continue
                    m3 = creation.extrude_polygon(g3, zb - za); m3.apply_translation([cx, cy, za]); outm.append(m3)
                continue
            m.apply_translation([cx, cy, za]); outm.append(m)
        return outm
    regs = [q for q in (pat["A"], pat["B"]) if q is not None]
    parts = []
    z0 = b - cham if cham > 0 else b
    for q in regs: parts += ext(q, a - 0.5, z0 + 0.01)
    if cham > 0:
        for i in range(1, steps + 1):
            off = cham * i / steps
            za = b - cham + cham * (i - 1) / steps; zb = b - cham + cham * i / steps
            for q in regs: parts += ext(q.buffer(-off, join_style=1), za - 0.01, zb + (0.5 if i == steps else 0.01))
    parts_u = trimesh.boolean.union(parts)
    pad = trimesh.boolean.intersection([body, parts_u])
    fill = body.difference(pad) if want_fill else None
    return pad, fill


def pick_via(region, prefer, min_clear, step=0.5, xrange=None):
    """region 内で prefer に最も近く、境界からの余裕が min_clear 以上の点を返す（無ければ None）。
    xrange=(xmin,xmax) を与えると x をその範囲に限る（くし型配線は via の x 順序に依存するため、
    via をボタン中心付近に留める／同じ x 列のボタンでは左右に振り分ける、のに使う）。"""
    px, py = prefer
    minx, miny, maxx, maxy = region.bounds
    if xrange is not None:
        minx, maxx = max(minx, xrange[0]), min(maxx, xrange[1])
    if (minx <= px <= maxx) and region.contains(Point(px, py)) and region.boundary.distance(Point(px, py)) >= min_clear:
        return (px, py)
    cands = []
    for x in np.arange(minx, maxx + 1e-9, step):
        for y in np.arange(miny, maxy + step, step):
            q = Point(x, y)
            if region.contains(q) and region.boundary.distance(q) >= min_clear:
                cands.append((math.hypot(x - px, y - py) + 0.3 * abs(x - px), x, y))   # x のずれは重めに罰する
    if not cands:
        return None
    cands.sort()
    return (cands[0][1], cands[0][2])


def build(name, s, w=1.0, p=5.0, sig_hint=None, arc=180.0, fillet=0.8):
    """直径 s のボタンに対するスリット設計を返す。
    arc    … lower_arcs の弧の角度範囲（度）
    fillet … 導電領域の凸角（歯の先端など）を丸める半径（mm）。角の分だけスリットが局所的に広がる。
             0 で無効。指や導電スリーブが引っかかる尖りを無くすため既定 0.8。
    dict(cutter=Polygon, A=Polygon(信号), B=Polygon(GND), sig=(x,y), gnd=(x,y), sig_r, gnd_r,
         rho_full, rho_lower, rest_clear, n_regions)"""
    r = s / 2
    disc = Point(0, 0).buffer(r, resolution=96)
    path = cut_path(name, r, w, p, arc)
    cutter = _snap(path.buffer(w / 2, cap_style=1, join_style=1)).intersection(_snap(disc.buffer(EXT)))
    regions = _snap(disc).difference(_snap(cutter))
    polys = list(regions.geoms) if isinstance(regions, MultiPolygon) else [regions]
    # 歯の先端などに取り残される小片（面積<8mm²）は導電の孤立島にせず、スリット側（非導電）に吸収する
    slivers = [q for q in polys if q.area < 8.0]
    if slivers:
        cutter = _snap(unary_union([_snap(cutter)] + [_snap(q.buffer(0.05)) for q in slivers]))
        regions = _snap(disc).difference(cutter)
        polys = list(regions.geoms) if isinstance(regions, MultiPolygon) else [regions]
    if fillet > 0:
        # 凸角の丸め：各領域を fillet だけ縮めてから同じだけ膨らませる（開口処理）。凸角は半径 fillet の
        # 円弧になり、凹角（スリットの外側の角）は変わらない。外周（円）は元の円板との交差で保つ。
        rounded = [_snap(_snap(q.buffer(-fillet, join_style=1)).buffer(fillet, join_style=1)).intersection(_snap(disc)) for q in polys]
        rounded = [q for q in rounded if not q.is_empty]
        cutter = _snap(disc.buffer(EXT)).difference(_snap(unary_union(rounded)))
        regions = _snap(disc).difference(_snap(cutter))
        polys = list(regions.geoms) if isinstance(regions, MultiPolygon) else [regions]
    polys = [q for q in polys if q.area > 1.0]
    if len(polys) != 2:
        print("  [%s φ%.0f] 領域が %d 個: %s" % (name, s, len(polys),
              ", ".join("面積%.0f@(%.1f,%.1f)" % (q.area, q.centroid.x, q.centroid.y) for q in polys)))
    hint = Point(sig_hint) if sig_hint is not None else Point(0, 0.45 * r)
    if name in LOWER:
        # 上半分（休息域）を含む領域を A（信号）にする
        A = max(polys, key=lambda q: q.intersection(box(-r, 1.0, r, r)).area)
    elif name == "radial":
        A = min(polys, key=lambda q: q.centroid.distance(Point(0, 0)))  # ハブ側
    else:
        inside = [q for q in polys if q.contains(hint)]
        A = inside[0] if inside else max(polys, key=lambda q: q.area)
    others = [q for q in polys if q is not A]
    B = max(others, key=lambda q: q.area) if others else None

    def _label(q):
        if _polylabel is not None:
            pt = _polylabel(q, tolerance=0.05)
        else:
            pt = q.representative_point()
        return (pt.x, pt.y), q.boundary.distance(pt)

    sig, sig_r = _label(A)
    gnd, gnd_r = _label(B) if B is not None else ((0, -0.45 * r), 0.0)

    # 被覆評価：格子点ごとに ρ(p)=max(dist(p,A),dist(p,B))
    xs = np.arange(-r + 0.25, r, 0.5)
    pts = [(x, y) for x in xs for y in xs if x * x + y * y <= (r - 0.3) ** 2]
    rho = np.array([max(A.distance(Point(q)), B.distance(Point(q)) if B is not None else 99) for q in pts])
    ys = np.array([q[1] for q in pts])
    rho_full = float(rho.max()); worst = pts[int(rho.argmax())]
    # 有効域（下半分系）：真下 270° を中心に角度 arc_eff の扇（lower_arcs は arc、他は 180）。縁から 0.5mm 内側は除く
    arc_eff = arc if name == "lower_arcs" else 180.0
    ang = np.degrees(np.arctan2(ys, np.array([q[0] for q in pts]))) % 360.0
    dang = np.abs(((ang - 270.0) + 180.0) % 360.0 - 180.0)
    active = (dang <= arc_eff / 2 - 2.0)
    rho_lower = float(rho[active].max()) if active.any() else float("nan")
    # 休息域の安全余裕：上半分の中央 (0, r/2) に置いた指の中心から B までの距離
    rest_clear = float(B.distance(Point(0, r / 2))) if B is not None else 0.0
    return dict(name=name, r=r, w=w, p=p, arc=arc, fillet=fillet, cutter=cutter, A=A, B=B, sig=sig, gnd=gnd, sig_r=sig_r, gnd_r=gnd_r,
                rho_full=rho_full, rho_lower=rho_lower, rest_clear=rest_clear, n_regions=len(polys), worst=worst)


if __name__ == "__main__":
    import sys
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon as MPoly, Circle
    # 使い方: python slit_patterns.py [直径] [ピッチ] [出力png] [フィレット半径] [lower_arcsの弧角度]
    s = float(sys.argv[1]) if len(sys.argv) > 1 else 24.0
    p = float(sys.argv[2]) if len(sys.argv) > 2 else 5.0
    out = sys.argv[3] if len(sys.argv) > 3 else "images/slit_patterns_%dmm.png" % int(s)
    fil = float(sys.argv[4]) if len(sys.argv) > 4 else 0.8
    arc = float(sys.argv[5]) if len(sys.argv) > 5 else 180.0
    names = list(PATTERNS)
    fig, axes = plt.subplots(2, 4, figsize=(16, 8.6))
    for ax, name in zip(axes.flat, names):
        d = build(name, s, 1.0, p, arc=arc, fillet=fil)
        for q, cc in ((d["A"], "#185FA5"), (d["B"], "#C77B23")):
            if q is None: continue
            for g in (q.geoms if hasattr(q, "geoms") else [q]):
                ax.add_patch(MPoly(list(g.exterior.coords), fc=cc, ec="none", alpha=0.85))
                for h in g.interiors: ax.add_patch(MPoly(list(h.coords), fc="white", ec="none"))
        ax.add_patch(Circle(d["sig"], d["sig_r"], fill=False, ec="#0b3d73", lw=1.2, ls="--"))
        ax.add_patch(Circle(d["gnd"], d["gnd_r"], fill=False, ec="#7a4610", lw=1.2, ls="--"))
        ax.plot(*d["sig"], "o", color="#0b3d73", ms=4); ax.plot(*d["gnd"], "o", color="#7a4610", ms=4)
        ax.set_xlim(-s / 2 - 1, s / 2 + 1); ax.set_ylim(-s / 2 - 1, s / 2 + 1); ax.set_aspect("equal"); ax.axis("off")
        sub = ("regions=%d  contact dia >= %.1fmm" % (d["n_regions"], 2 * d["rho_full"]) if name not in LOWER
               else "regions=%d  lower half: contact dia >= %.1fmm\nrest zone center -> B: %.1fmm" % (d["n_regions"], 2 * d["rho_lower"], d["rest_clear"]))
        ax.set_title("%s  %s\n%s" % (label(name, arc, False, p, fil, 0.4), name, sub), fontsize=9)
        ax.plot(*d["worst"], "x", color="red", ms=7, mew=2)
        print("%-14s regions=%d  ρ_full=%.2f (worst at %.1f,%.1f) ρ_lower=%.2f rest_clear=%.2f  via r: sig %.2f gnd %.2f" % (
            name, d["n_regions"], d["rho_full"], d["worst"][0], d["worst"][1], d["rho_lower"], d["rest_clear"], d["sig_r"], d["gnd_r"]))
    fig.suptitle("slit patterns for φ%.0f button (slit %.1fmm, pitch %.1fmm, fillet %.1fmm, arc %.0f°) — blue=A(signal) orange=B(GND), dashed=via clearance" % (s, 1.0, p, fil, arc))
    fig.tight_layout(); fig.savefig(out, dpi=110); print("saved", out)

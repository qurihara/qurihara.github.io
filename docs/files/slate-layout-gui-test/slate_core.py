# slate のレイアウト評価の中核（2026-10-09）。design_stl_v2.py（v3.1.2 以降）の「配線・交差の検査・抵抗の安全率」の計算を、
# メッシュ生成と matplotlib を使わない純粋な関数に写したもの。numpy と shapely（slit_patterns.py 経由）だけに依存するので、
# ブラウザの Pyodide でも、サーバの CPython でも同じ結果を返す。GUI（gui/slate_layout.html）は、ボタンを動かすたびにこれを呼ぶ。
# 正しさは、design_stl_v2.py --rtable の表と一致することで確かめる（gui/verify_core.py）。
# 入力（layout）は JSON にできる辞書：
#   {"buttons": {"L": {"x": 28, "y": 101, "size": 24, "type": "round"}, ..., "thumb": {..., "type": "qwall", "rot": 157.8, "conn": 0, "wh": 13.3}},
#    "slit": "lower_arcs", "slit_arc": 240, "slit_pitch": 5, "pico_cx": 120, "l3": 5.0, "skin": 0.36, "margin": 7, "ctrl_gap": 4, "ctrl_pitch": 13}
#   座標は design_stl_v2.py の btn 辞書と同じ生の値（DX/DY で板の左下へ寄せる前）。
# 出力は辞書：ok、errors（設計不可の理由）、warnings、board（X0,X1,Y0,Y1,DX,DY）、buttons（正規化後の座標・via・GP・pin）、routes、ctrl、
#   pico（cx, sig_y, far_y, pins）、crossings、via_hits、sf（ボタンごとの抵抗の表）、worst。座標はすべて正規化後（板の左下が原点に近い）。
import math
from collections import defaultdict
import numpy as np
import slit_patterns as sp

W_SIG = 1.2; WALL = 0.6; PITCH = 2.54; ROW = 17.78; CTRL_D = 10.0; CTRL_R = CTRL_D / 2
VIA_R = 1.1; LAND_R = 0.9; SLIT = 1.0; GND_W = 24.0; SLIT_FILLET = 0.8
GPIO_PIN_TOP = {2: 4, 3: 5, 4: 6, 5: 7, 6: 9, 7: 10, 8: 11, 9: 12, 10: 14, 11: 15, 12: 16, 13: 17, 14: 19, 15: 20}
PIN_BOT = {16: 21, 17: 22, 18: 24, 19: 25, 20: 26, 21: 27}
GND_PIN_TOP, GND_PIN_TOP2 = 3, 18
LABEL = {"L": "L", "D": "D", "R": "R", "Up": "UP", "c1t": "LK", "c1b": "LP", "c2t": "MK", "c2b": "MP", "c3t": "HK", "c3b": "HP", "c4t": "KK", "c4b": "PP", "thumb": "THU", "palm": "PALM"}
CTRL_DEF = [("u1", 21, "A2"), ("u2", 20, "A1"), ("u3", 19, "ST"), ("u4", 18, "SEL")]
K_EFF = 220.0; RPU = 50e3; VDD = 3.3; VIL = 0.35 * VDD; RTH = RPU * VIL / (VDD - VIL); RC_TYP = 5e3; SF_TGT = 1.5
_SLIT_CACHE = {}; _VIA_CACHE = {}

def standard_layout(ver="v3.1.2"):
    """標準モデルのレイアウト（design_stl_v2.py の btn 辞書と同じ生の座標）。"""
    b = {"L": (28, 101), "D": (58, 101), "R": (84, 87), "Up": (91, 31 + 12), "c1t": (110, 70), "c1b": (111, 100), "c2t": (137, 82), "c2b": (137, 113),
         "c3t": (165, 81), "c3b": (167, 112), "c4t": (194, 76), "c4b": (196, 107)}
    L = {"buttons": {n: {"x": x, "y": y, "size": (30.0 if n == "Up" else 24.0), "type": "round"} for n, (x, y) in b.items()},
         "slit": "lower_arcs", "slit_arc": 240.0, "slit_pitch": 5.0, "pico_cx": 120.0, "l3": 5.0, "skin": 0.36, "margin": 7.0, "ctrl_gap": 4.0, "ctrl_pitch": 13.0}
    if ver in ("v3.3", "v3.4"):
        L["ctrl_gap"], L["ctrl_pitch"] = 6.0, 14.0
        for n in ("c2t", "c3t", "c4t"): L["buttons"][n]["arc"] = 305.0
    if ver == "v3.3":
        L["buttons"]["palm"] = {"x": round((137 + 165) / 2, 1), "y": 43, "size": 30.0, "type": "dna", "rot": 0.0}
    if ver == "v3.4":
        tx, ty = 58, round((43 + 70) / 2, 1)
        rot = round(math.degrees(math.atan2(43 - ty, 91 - tx)) + 180.0, 1)
        L["buttons"]["thumb"] = {"x": tx, "y": ty, "size": 24.0, "type": "qwall", "rot": rot, "conn": 0.0, "wh": 13.3}
    return L

def rotv(vx, vy, deg):
    a = math.radians(deg); return (vx * math.cos(a) - vy * math.sin(a), vx * math.sin(a) + vy * math.cos(a))

def qwall_ext(b):
    """qwall の占有範囲（円柱中心基準・回転後）：(xmin,xmax,ymin,ymax)。"""
    d = b["size"]; face = b.get("conn"); conn_l = 12.0; shift = 12.0; wt = 6.0
    lx0 = -d / 2; lx1 = (face if face is not None else d / 2 + conn_l - shift) + wt; ly = d / 2
    a = math.radians(b.get("rot", -90.0))
    pts = [(lx * math.cos(a) - yy * math.sin(a), lx * math.sin(a) + yy * math.cos(a)) for lx in (lx0, lx1) for yy in (-ly, ly)]
    return (min(p[0] for p in pts), max(p[0] for p in pts), min(p[1] for p in pts), max(p[1] for p in pts))

def qwall_rects(b, x, y):
    d = b["size"]; R = d / 2; face = b.get("conn"); xf = (face if face is not None else R + 12.0 - 12.0); xb = xf + 6.0; a = math.radians(b.get("rot", -90.0))
    def w(px, py): return (x + px * math.cos(a) - py * math.sin(a), y + px * math.sin(a) + py * math.cos(a))
    return ([w(0, -R), w(xf, -R), w(xf, R), w(0, R)], [w(xf, -R), w(xb, -R), w(xb, R), w(xf, R)])

def seg_dist(a, b, c, d):
    """線分 ab と線分 cd の最短距離（design_stl_v2.py と同じ式。numpy を使わない形に写した。結果は同じ）。"""
    ax, ay = a; bx, by = b; cx, cy = c; dx, dy = d
    d1x, d1y = bx - ax, by - ay; d2x, d2y = dx - cx, dy - cy; rx, ry = ax - cx, ay - cy
    A = d1x * d1x + d1y * d1y; E = d2x * d2x + d2y * d2y; F = d2x * rx + d2y * ry
    def cl(t): return 0. if t < 0. else (1. if t > 1. else t)
    if A <= 1e-9 and E <= 1e-9: return math.hypot(rx, ry)
    if A <= 1e-9: s_ = 0.; t_ = cl(F / E)
    else:
        C = d1x * rx + d1y * ry
        if E <= 1e-9: t_ = 0.; s_ = cl(-C / A)
        else:
            B = d1x * d2x + d1y * d2y; den = A * E - B * B; s_ = cl((B * F - C * E) / den) if den > 1e-9 else 0.; t_ = (B * s_ + F) / E
            if t_ < 0: t_ = 0.; s_ = cl(-C / A)
            elif t_ > 1: t_ = 1.; s_ = cl((B - C) / A)
    return math.hypot((ax + d1x * s_) - (cx + d2x * t_), (ay + d1y * s_) - (cy + d2y * t_))
def segs(r): return [(r[i], r[i + 1]) for i in range(len(r) - 1)]

def footprint(b, x, y):
    """幾何の重なりの検査に使う占有形（shapely）。"""
    from shapely.geometry import Point, Polygon
    from shapely.ops import unary_union
    r = b["size"] / 2; t = b.get("type", "round")
    if t == "qwall":
        cr, wr = qwall_rects(b, x, y)
        return unary_union([Point(x, y).buffer(r, resolution=24), Polygon(cr), Polygon(wr)])
    if t.startswith("onenail"):
        h = 12.5; a = math.radians(b.get("rot", -90.0))
        def w(px, py): return (x + px * math.cos(a) - py * math.sin(a), y + px * math.sin(a) + py * math.cos(a))
        return Polygon([w(-h, -h), w(h, -h), w(h, h), w(-h, h)])
    return Point(x, y).buffer(r, resolution=24)

def evaluate(layout):
    errors = []; warnings = []; viol = []
    B = {n: dict(v) for n, v in layout["buttons"].items()}
    if not B: return {"ok": False, "errors": ["ボタンが 1 つも無い"], "warnings": []}
    if len(B) > 14: errors.append("主ボタンは 14 個まで（GP2〜GP15）。いま %d 個" % len(B))
    LAB = dict(LABEL)
    for n, b in B.items():
        b.setdefault("size", 24.0); b.setdefault("type", "round")
        if "label" in b: LAB[n] = b["label"]
        if b["type"] == "qwall": b.setdefault("rot", -90.0)
        elif b["type"].startswith("onenail"): b.setdefault("rot", -90.0)
        else: b.setdefault("rot", 0.0)
    slit = layout.get("slit", "lower_arcs"); slit_arc = float(layout.get("slit_arc", 240.0)); slit_pitch = float(layout.get("slit_pitch", 5.0))
    PICO_CX = float(layout.get("pico_cx", 120.0)); PICO_GAP = float(layout.get("pico_gap", 0.0)); L3_T = float(layout.get("l3", 5.0)); SKIN = float(layout.get("skin", 0.36)); MX = float(layout.get("margin", 7.0))
    cgap = float(layout.get("ctrl_gap", 4.0)); cpitch = float(layout.get("ctrl_pitch", 13.0))
    # ---- 正規化（板の左下へ寄せる）----
    DX = 15 - min(b["x"] - b["size"] / 2 for b in B.values()); DY = 14 - min(b["y"] - b["size"] / 2 for b in B.values())
    btn = {n: (b["x"] + DX, b["y"] + DY) for n, b in B.items()}
    if "pico_cx_raw" in layout: PICO_CX = round(float(layout["pico_cx_raw"]) + DX, 2)   # GUI はボタンと同じ生の座標で Pico の位置を持つ
    def br(n): return B[n]["size"] / 2
    # ---- 幾何の重なり（design_stl_v2.py には無い検査。GUI のために足した）----
    fps = {n: (footprint(B[n], *btn[n]) if B[n]["type"] in ("qwall", "onenail", "onenail_high") else None) for n in B}
    names = list(B)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            ni, nj = names[i], names[j]
            if fps[ni] is None and fps[nj] is None: g = math.hypot(btn[ni][0] - btn[nj][0], btn[ni][1] - btn[nj][1]) - br(ni) - br(nj)
            else:
                from shapely.geometry import Point as _Pt
                g = (fps[ni] if fps[ni] is not None else _Pt(*btn[ni]).buffer(br(ni), resolution=24)).distance(fps[nj] if fps[nj] is not None else _Pt(*btn[nj]).buffer(br(nj), resolution=24))
            if g < 2.0: errors.append("%s と %s の間隔が %.1fmm（2mm 以上にする）" % (LAB.get(names[i], names[i]), LAB.get(names[j], names[j]), g)); viol.append({"type": "overlap", "a": ni, "b": nj, "gap": round(g, 2)})
            elif g < 4.0: warnings.append("%s と %s の間隔が %.1fmm（実績は 4mm 以上）" % (LAB.get(names[i], names[i]), LAB.get(names[j], names[j]), g))
    # ---- via の位置 ----
    grp = defaultdict(list)
    for n in B: grp[round(btn[n][0])].append(n)
    sig_via = {}; gnd_via = {}; slit_info = {}
    for gx, ns in grp.items():
        ns.sort(key=lambda n: btn[n][1])
        for k, n in enumerate(ns):
            off = (k - (len(ns) - 1) / 2) * 3.0 if len(ns) > 1 else 0.0
            x, y = btn[n]; sig_via[n] = (x + off, y + br(n) * 0.45); gnd_via[n] = (x, y - br(n) * 0.45)
    for n, b in B.items():
        t = b["type"]; x, y = btn[n]
        if t == "qwall" or t.startswith("onenail"):
            d = rotv(0, 1, b["rot"])
            if abs(d[0]) > 0.5: d = (-1.0, 0.0)
            s = b.get("sig", 1); d = (d[0] * s, d[1] * s)
            sig_via[n] = (x + d[0] * br(n) * 0.45, y + d[1] * br(n) * 0.45); gnd_via[n] = (x - d[0] * br(n) * 0.45, y - d[1] * br(n) * 0.45)
        elif t == "dna":
            d = rotv(0, 1, b["rot"]); sig_via[n] = (x + d[0] * br(n) * 0.45, y + d[1] * br(n) * 0.45); gnd_via[n] = (x - d[0] * br(n) * 0.45, y - d[1] * br(n) * 0.45)
        elif t.startswith("nail"):
            d = rotv(0, 1, b["rot"]); sig_via[n] = (x + d[0] * br(n) * 0.6, y + d[1] * br(n) * 0.6); gnd_via[n] = (x - d[0] * br(n) * 0.6, y - d[1] * br(n) * 0.6)
    if slit != "straight":
        minc = VIA_R + WALL + 0.1
        for gx, ns in grp.items():
            ns.sort(key=lambda n: btn[n][1])
            for k, n in enumerate(ns):
                if B[n]["type"] != "round": continue
                off = (k - (len(ns) - 1) / 2) * 3.0 if len(ns) > 1 else 0.0
                arc = float(B[n].get("arc", slit_arc)); key = (slit, B[n]["size"], slit_pitch, arc)
                if key not in _SLIT_CACHE: _SLIT_CACHE[key] = sp.build(slit, B[n]["size"], SLIT, slit_pitch, arc=arc, fillet=SLIT_FILLET)
                d = _SLIT_CACHE[key]
                if d["n_regions"] != 2: errors.append("%s：スリット %s（φ%g・弧 %g°）で領域が %d 個になる" % (LAB.get(n, n), slit, B[n]["size"], arc, d["n_regions"])); continue
                xr = (-3.0, 3.0) if len(ns) == 1 else ((-6.0, -1.0) if off < 0 else (1.0, 6.0))
                vkey = key + (off, xr)
                if vkey not in _VIA_CACHE: _VIA_CACHE[vkey] = (sp.pick_via(d["A"], (off, d["sig"][1]), minc, xrange=xr), sp.pick_via(d["B"], (off, d["gnd"][1]), minc, xrange=(-6.0, 6.0)))
                spv, gpv = _VIA_CACHE[vkey]
                if spv is None or gpv is None: errors.append("%s：via（半径 %.1f＋壁 %.1f）の入る場所が無い" % (LAB.get(n, n), VIA_R, WALL)); continue
                x, y = btn[n]; sig_via[n] = (x + spv[0], y + spv[1]); gnd_via[n] = (x + gpv[0], y + gpv[1])
                slit_info[n] = {"rho_full": 2 * d["rho_full"], "rho_lower": 2 * d["rho_lower"], "rest_clear": d["rest_clear"]}
    if errors: return {"ok": False, "errors": errors, "warnings": warnings, "violations": viol}
    # ---- GPIO と Pico ----
    near = sorted(B, key=lambda n: (btn[n][0], btn[n][1])); btn_gpio = {n: 2 + i for i, n in enumerate(near)}
    pin1_x = PICO_CX - (20 - 1) * PITCH / 2
    def px_top(p): return pin1_x + (p - 1) * PITCH
    def px_bot(p): return pin1_x + (40 - p) * PITCH
    back_edge = max(y + br(n) for n, (x, y) in btn.items())
    LANE0 = round(back_edge - 5, 1); LANE_STEP = 1.9   # v2.1 以降（COMPACT）：信号レーンをボタンの真下にも通して隙間を詰める
    PICO_SIG_Y = round(LANE0 + LANE_STEP * 14 + 2 + PICO_GAP, 1); PICO_FAR_Y = PICO_SIG_Y + ROW   # pico_gap：Pico をボタン列からさらに奥へ離す量
    def lane_near(gp): return LANE0 + LANE_STEP * (gp - 2)
    cx0 = round(px_top(20) + LAND_R + CTRL_R + cgap, 1)
    ctrl = [(u, g, round(cx0 + cpitch * i, 1), lab) for i, (u, g, lab) in enumerate(CTRL_DEF)]
    ctrl_size = {u: CTRL_D for u, g, lab in CTRL_DEF}
    if "ctrl" in layout:   # 制御ボタンを JSON で指定（0〜4 個・位置は Pico の行の上で自由・大きさ φ10〜24）。gp は 21・20・19・18 のどれか
        ctrl = []; ctrl_size = {}
        for i, e in enumerate(layout["ctrl"]):
            x = round(float(e["x_raw"]) + DX, 1) if "x_raw" in e else float(e["x"])
            ctrl.append((e.get("name", "u%d" % (i + 1)), int(e["gp"]), x, e.get("label", "C%d" % (i + 1)))); ctrl_size[ctrl[-1][0]] = float(e.get("size", CTRL_D))
        if len(ctrl) > 4: errors.append("制御ボタンは 4 個まで（Pico の奥エッジの GP18〜21）")
        gps = [g for n, g, x, lab in ctrl]
        if len(set(gps)) != len(gps) or any(g not in PIN_BOT for g in gps): errors.append("制御ボタンの GP が重複しているか、18〜21 の範囲外")
        px_lo, px_hi = px_top(1) - LAND_R - 1.0, px_top(20) + LAND_R + 1.0
        for n, g, x, lab in ctrl:
            r = ctrl_size[n] / 2
            if x + r > px_lo and x - r < px_hi: errors.append("制御ボタン %s が Pico の端子の列と重なる（Pico の左右に置く）" % lab); viol.append({"type": "ctrl_pico", "a": "ctrl:" + n, "depth": round(min(x + r - px_lo, px_hi - (x - r)), 2)})
        for i in range(len(ctrl)):
            for j in range(i + 1, len(ctrl)):
                g = abs(ctrl[i][2] - ctrl[j][2]) - ctrl_size[ctrl[i][0]] / 2 - ctrl_size[ctrl[j][0]] / 2
                if g < 2.0: errors.append("制御ボタン %s と %s の間隔が %.1fmm（2mm 以上にする）" % (ctrl[i][3], ctrl[j][3], g)); viol.append({"type": "overlap", "a": "ctrl:" + ctrl[i][0], "b": "ctrl:" + ctrl[j][0], "gap": round(g, 2)})
        if errors: return {"ok": False, "errors": errors, "warnings": warnings, "violations": viol}
    ctrl_sig_via = {n: (x, PICO_SIG_Y - 1.5) for n, g, x, lab in ctrl}   # COMPACT：上端レーンとの近接を避けて中央寄り
    ctrl_gnd_via = {n: (x + 3.0, PICO_SIG_Y + ctrl_size[n] / 2 * 0.45) for n, g, x, lab in ctrl}; ctrl_gnd_via = {n: (x + 3.0, PICO_SIG_Y + CTRL_R * 0.45) for n, g, x, lab in ctrl}
    # ---- L3 配線 ----
    def hits(ax, ay, bx, by, obst):
        m = W_SIG / 2 + VIA_R + WALL
        for (vx, vy) in obst:
            if abs(ay - by) < 1e-6:
                if abs(vy - ay) < m and min(ax, bx) - m <= vx <= max(ax, bx) + m: return True
            else:
                if abs(vx - ax) < m and min(ay, by) - m <= vy <= max(ay, by) + m: return True
        return False
    def up_to_lane(n, lane):
        x, y = sig_via[n]; obst = [gnd_via[m] for m in B] + [sig_via[m] for m in B if m != n]
        if not hits(x, y, x, lane, obst): return [(x, y), (x, lane)]
        for d in [i * 0.4 for i in range(1, 220)]:
            for ex in (x + d, x - d):
                if not hits(x, y, ex, y, obst) and not hits(ex, y, ex, lane, obst): return [(x, y), (ex, y), (ex, lane)]
        return [(x, y), (x, lane)]
    lane_rank = {n: i for i, n in enumerate(near)}
    left = [n for n in near if sig_via[n][0] < px_top(GPIO_PIN_TOP[btn_gpio[n]])]
    pos = [lane_rank[n] for n in left]
    for n, p in zip(left, reversed(pos)): lane_rank[n] = p
    signal_routes = {}
    for n in near:
        gp = btn_gpio[n]; lane = lane_near(2 + lane_rank[n]); pxx = px_top(GPIO_PIN_TOP[gp])
        signal_routes[n] = up_to_lane(n, lane) + [(pxx, lane), (pxx, PICO_SIG_Y)]
    ctrl_routes = {}
    for i, (n, g, x, lab) in enumerate(ctrl):
        lane = PICO_SIG_Y + ROW * (0.25 + 0.14 * i); pxx = px_bot(PIN_BOT[g])
        ctrl_routes[n] = [ctrl_sig_via[n], (x, lane), (pxx, lane), (pxx, PICO_FAR_Y)]
    routes = {**signal_routes, **ctrl_routes}; rn = list(routes); cross = []
    for i in range(len(rn)):
        for j in range(i + 1, len(rn)):
            for a, b in segs(routes[rn[i]]):
                for c, d in segs(routes[rn[j]]):
                    if seg_dist(a, b, c, d) < W_SIG + WALL: cross.append((rn[i], rn[j], round(seg_dist(a, b, c, d), 2)))
    gvia_hit = []
    for n, r in signal_routes.items():
        for a, b in segs(r):
            for m, (vx, vy) in gnd_via.items():
                if n == m: continue
                if seg_dist(a, b, (vx, vy), (vx, vy)) < W_SIG / 2 + VIA_R + WALL: gvia_hit.append((n, "GNDvia:" + m))
    cross = sorted(set(cross)); gvia_hit = sorted(set(gvia_hit))
    # ---- 板の外形 ----
    xs0 = [x - br(n) for n, (x, y) in btn.items()] + [btn[n][0] + qwall_ext(B[n])[0] for n in B if B[n]["type"] == "qwall"] + [btn[n][0] - 12.5 for n in B if B[n]["type"].startswith("onenail")] + [px_top(1) - 4] + [x - ctrl_size[n] for n, g, x, l in ctrl]
    xs1 = [x + br(n) for n, (x, y) in btn.items()] + [btn[n][0] + qwall_ext(B[n])[1] for n in B if B[n]["type"] == "qwall"] + [btn[n][0] + 12.5 for n in B if B[n]["type"].startswith("onenail")] + [x + ctrl_size[n] for n, g, x, l in ctrl] + [px_top(20) + 4]
    ys0 = [y - br(n) for n, (x, y) in btn.items()] + [btn[n][1] + qwall_ext(B[n])[2] for n in B if B[n]["type"] == "qwall"] + [btn[n][1] - 12.5 for n in B if B[n]["type"].startswith("onenail")]
    X0 = round(min(xs0) - MX, 1); X1 = round(max(xs1) + MX, 1); Y0 = round(min(ys0) - 8, 1)
    TIE_UP_Y = round(PICO_FAR_Y + PITCH + LAND_R + 1.6 + 3.0 / 2, 1)   # 結束バンド口（v2.4 以降）の上側の口のぶん板を奥へ広げる
    Y1 = round(max(PICO_FAR_Y + 6, TIE_UP_Y + 3.0 / 2 + 2.5), 1)
    # ---- 抵抗モデル（v2.8 以降）----
    Z = [0.0, 1.0, 1.36, 1.36 + L3_T, 1.36 + L3_T + 0.72, 1.36 + L3_T + 0.72 + 2.5]; Z = [z + SKIN for z in Z]; VIA_TOP = Z[4] + 0.05
    busy = round((min(v[1] for v in gnd_via.values()) + max(v[1] for v in gnd_via.values())) / 2, 1)
    gx0, gx1 = X0 + GND_W / 2 + 1, X1 - GND_W / 2 - 1
    gnet = [[(gx0, busy), (gx1, busy)]]
    for n in B: gnet.append([(gnd_via[n][0], busy), (gnd_via[n][0], gnd_via[n][1])])
    for n, g, x, lab in ctrl: gnet.append([(ctrl_gnd_via[n][0], busy), (ctrl_gnd_via[n][0], ctrl_gnd_via[n][1])])
    for phys in (GND_PIN_TOP, GND_PIN_TOP2): gnet.append([(px_top(phys), busy), (px_top(phys), PICO_SIG_Y)])
    import heapq
    def gkey(p): return (round(p[0], 1), round(p[1], 1))
    gadj = {}
    def gadd(a, b): gadj.setdefault(gkey(a), []).append((gkey(b), math.dist(a, b))); gadj.setdefault(gkey(b), []).append((gkey(a), math.dist(a, b)))
    jxs = sorted({round(r[0][0], 1) for r in gnet[1:]} | {round(gnet[0][0][0], 1), round(gnet[0][1][0], 1)})
    for a, b in zip(jxs, jxs[1:]): gadd((a, busy), (b, busy))
    for r in gnet[1:]: gadd((r[0][0], busy), (r[1][0], r[1][1]))
    gsrc = [gkey((px_top(p), PICO_SIG_Y)) for p in (GND_PIN_TOP, GND_PIN_TOP2)]
    gdist = {s: 0.0 for s in gsrc if s in gadj}; pq = [(0., s) for s in gdist]; heapq.heapify(pq)
    while pq:
        d, u = heapq.heappop(pq)
        if d > gdist.get(u, 1e18): continue
        for v, w in gadj[u]:
            nd = d + w
            if nd < gdist.get(v, 1e18): gdist[v] = nd; heapq.heappush(pq, (nd, v))
    gvia_all = {**{n: gnd_via[n] for n in B}, **{cn: ctrl_gnd_via[cn] for cn, g, x, lab in ctrl}}
    AV = math.pi * VIA_R ** 2; As = W_SIG * (Z[3] - Z[2]); Ag = GND_W * (Z[1] - Z[0]); rvs = K_EFF * (VIA_TOP - Z[2]) / AV; rvg = K_EFF * (VIA_TOP - Z[0]) / AV
    def plen(pts): return sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))
    ctrl_gpio = {n: g for n, g, x, lab in ctrl}; ctrl_label = {n: lab for n, g, x, lab in ctrl}
    sf = []
    for n, rt in routes.items():
        Ls = plen(rt); Rs = K_EFF * Ls / As; Lg = gdist.get(gkey(gvia_all[n]), float("inf")); Rg = K_EFF * Lg / Ag
        Rlow = Rs + rvs + rvg + Rg + RC_TYP; gp = btn_gpio.get(n, ctrl_gpio.get(n)); phys = GPIO_PIN_TOP.get(gp, PIN_BOT.get(gp))
        sf.append({"n": n, "label": LAB.get(n, ctrl_label.get(n, n)), "gp": gp, "pin": phys, "Ls": round(Ls, 1), "Lg": round(Lg, 1),
                   "Rsig_k": round((Rs + rvs) / 1e3, 2), "Rgnd_k": round((Rg + rvg) / 1e3, 2), "Rlow_k": round(Rlow / 1e3, 2), "SF": round(RTH / Rlow, 3)})
    sf.sort(key=lambda r: r["gp"]); worst = min(sf, key=lambda r: r["SF"])
    if cross: errors.append("配線の交差 %d 件：%s" % (len(cross), "・".join("%s と %s" % (LAB.get(a, a), LAB.get(b, b)) for a, b, d in cross[:6]))); viol += [{"type": "cross", "a": a, "b": b, "d": d} for a, b, d in cross]
    if gvia_hit: errors.append("配線が GND via に接触 %d 件：%s" % (len(gvia_hit), "・".join("%s が %s" % (LAB.get(a, a), LAB.get(b.split(':')[1], b)) for a, b in gvia_hit[:6]))); viol += [{"type": "via_hit", "a": a, "b": b.split(":")[1]} for a, b in gvia_hit]
    if worst["SF"] < SF_TGT: errors.append("抵抗の安全率が不足：%s が SF %.2f（目標 %.1f 以上）" % (worst["label"], worst["SF"], SF_TGT)); viol.append({"type": "sf", "a": worst["n"], "SF": worst["SF"]})
    elif worst["SF"] < 1.8: warnings.append("安全率の余裕が小さい：%s が SF %.2f" % (worst["label"], worst["SF"]))
    out = {"ok": not errors, "errors": errors, "warnings": warnings, "violations": viol,
           "board": {"X0": X0, "X1": X1, "Y0": Y0, "Y1": Y1, "DX": round(DX, 2), "DY": round(DY, 2), "W": round(X1 - X0, 1), "H": round(Y1 - Y0, 1)},
           "buttons": {n: {"x": btn[n][0], "y": btn[n][1], "size": B[n]["size"], "type": B[n]["type"], "rot": B[n]["rot"], "label": LAB.get(n, n), "gp": btn_gpio[n], "pin": GPIO_PIN_TOP[btn_gpio[n]],
                           "sig_via": sig_via[n], "gnd_via": gnd_via[n], "qwall": (qwall_rects(B[n], *btn[n]) if B[n]["type"] == "qwall" else None), "slit": slit_info.get(n)} for n in B},
           "routes": {n: [list(p) for p in r] for n, r in routes.items()},
           "ctrl": [{"n": n, "gp": g, "x": x, "y": PICO_SIG_Y, "size": ctrl_size[n], "label": lab, "sig_via": ctrl_sig_via[n], "gnd_via": ctrl_gnd_via[n]} for n, g, x, lab in ctrl],
           "pico": {"cx": PICO_CX, "sig_y": PICO_SIG_Y, "far_y": PICO_FAR_Y, "lane0": LANE0, "gap": PICO_GAP, "x_lo": px_top(1) - LAND_R - 1.0, "x_hi": px_top(20) + LAND_R + 1.0, "top": [[px_top(p), PICO_SIG_Y] for p in range(1, 21)], "bot": [[px_bot(p), PICO_FAR_Y] for p in range(21, 41)]},
           "crossings": cross, "via_hits": gvia_hit, "sf": sf, "worst": worst, "Z": Z}
    return out


def classify(r):
    """evaluate の結果を 1 文字の符号に：O=設計できる・G=幾何（重なり・端子の列）・X=配線の交差や via への接触・S=安全率の不足・E=その他。"""
    if r["ok"]: return "O"
    e = " ".join(r["errors"])
    if "間隔" in e or "端子の列" in e or "重なる" in e: return "G"
    if "交差" in e or "接触" in e: return "X"
    if "安全率" in e: return "S"
    return "E"

def scan(layout, target, points):
    """対象 target（主ボタンの名前・"ctrl:<name>"・"pico"）を points（生の座標 [[x,y],...]。制御ボタンと Pico は x だけ使う）の各位置に置いて
    評価し、[[x, y, 符号, 最悪の SF], ...] を返す。layout は変更しない。"""
    import copy
    out = []
    for x, y in points:
        L = copy.deepcopy(layout)
        if target == "pico": L["pico_cx_raw"] = x
        elif target.startswith("ctrl:"):
            for e in L.get("ctrl", []):
                if e.get("name") == target[5:]: e["x_raw"] = x
        else:
            L["buttons"][target]["x"] = x; L["buttons"][target]["y"] = y
        try: r = evaluate(L); out.append([x, y, classify(r), (r.get("worst") or {}).get("SF")])
        except Exception as ex: out.append([x, y, "E", None])
    return out

def scan_json(s):
    import json
    o = json.loads(s)
    return json.dumps(scan(o["layout"], o["target"], o["points"]))


# ===================== 自動制約解消（α版・2026-10-10）=====================
#  利用者が置いたもの（fixed）は動かさず、違反に関わるボタン（主ボタンは 8 方向 5mm・10mm、制御ボタンは左右 5mm・10mm）を 1 つ動かした案を
#  すべて評価し、罰則が最も減る 1 手を返す。罰則＝重なりの深さ・交差の数・via への接触の数・安全率の不足分・元の位置からの移動量の合計。
#  収束しないことがあるので、呼ぶ側が手数と評価回数の上限を持つ。
def penalty(r, L, L0):
    p = 0.0
    for v in r.get("violations", []):
        t = v["type"]
        if t == "overlap": p += 10 + max(0.0, 2.0 - v["gap"]) * 2
        elif t == "ctrl_pico": p += 10 + v["depth"]
        elif t == "cross": p += 8
        elif t == "via_hit": p += 8
        elif t == "sf": p += 20 * (SF_TGT - v["SF"])
        else: p += 10
    disp = sum(math.hypot(L["buttons"][n]["x"] - L0["buttons"][n]["x"], L["buttons"][n]["y"] - L0["buttons"][n]["y"]) for n in L["buttons"] if n in L0["buttons"])
    c0 = {e["name"]: e for e in L0.get("ctrl", [])}
    disp += sum(abs(e.get("x_raw", 0) - c0[e["name"]].get("x_raw", 0)) for e in L.get("ctrl", []) if e["name"] in c0)
    return p + 0.05 * disp

def resolve_step(layout, fixed, layout0=None, steps=(5.0, 10.0)):
    """1 手だけ進める。戻り値 dict(ok, done, move=(対象, dx, dy), penalty, errors, layout)。done=True は、設計できる状態になった（ok）か、どの 1 手でも罰則が減らない（ok=False）。"""
    import copy
    L0 = layout0 if layout0 is not None else layout
    r = evaluate(layout)
    if r["ok"]: return {"ok": True, "done": True, "move": None, "penalty": 0.0, "errors": [], "layout": layout, "evals": 1}
    p0 = penalty(r, layout, L0); fixed = set(fixed or [])
    cand = set()
    for v in r.get("violations", []):
        for k in ("a", "b"):
            if k in v and v[k] not in fixed: cand.add(v[k])
    if not cand: cand = {n for n in layout["buttons"] if n not in fixed} | {"ctrl:" + e["name"] for e in layout.get("ctrl", []) if "ctrl:" + e["name"] not in fixed}
    best = None; nev = 1
    for n in sorted(cand):
        moves = [(dx, dy) for st in steps for dx, dy in ((st, 0), (-st, 0), (0, st), (0, -st), (st, st), (st, -st), (-st, st), (-st, -st))] if not n.startswith("ctrl:") else [(dx, 0) for st in steps for dx in (st, -st)]
        for dx, dy in moves:
            L2 = copy.deepcopy(layout)
            if n.startswith("ctrl:"):
                for e in L2.get("ctrl", []):
                    if e["name"] == n[5:]: e["x_raw"] = e.get("x_raw", 0) + dx
            else: L2["buttons"][n]["x"] += dx; L2["buttons"][n]["y"] += dy
            r2 = evaluate(L2); nev += 1; p2 = penalty(r2, L2, L0)
            if best is None or p2 < best[0]: best = (p2, n, dx, dy, L2, r2)
    if best is None or best[0] >= p0 - 1e-9: return {"ok": False, "done": True, "move": None, "penalty": p0, "errors": r["errors"], "layout": layout, "evals": nev}
    p2, n, dx, dy, L2, r2 = best
    return {"ok": r2["ok"], "done": r2["ok"], "move": [n, dx, dy], "penalty": p2, "errors": r2["errors"], "layout": L2, "evals": nev}

def resolve_step_json(s):
    import json
    o = json.loads(s)
    try: return json.dumps(resolve_step(o["layout"], o.get("fixed", []), o.get("layout0")), ensure_ascii=False)
    except Exception as e:
        import traceback
        return json.dumps({"ok": False, "done": True, "move": None, "errors": ["自動制約解消の途中で例外：%s" % e], "trace": traceback.format_exc()}, ensure_ascii=False)

def evaluate_json(s):
    import json
    try:
        return json.dumps(evaluate(json.loads(s)), ensure_ascii=False)
    except Exception as e:
        import traceback
        return json.dumps({"ok": False, "errors": ["評価の途中で例外：%s" % e], "warnings": [], "trace": traceback.format_exc()}, ensure_ascii=False)

if __name__ == "__main__":
    import json, sys
    ver = sys.argv[1] if len(sys.argv) > 1 else "v3.1.2"
    r = evaluate(standard_layout(ver))
    print("ok", r["ok"], r["errors"], r["warnings"]); print("board", r["board"])
    for row in r["sf"]: print("  %-5s GP%-3d pin%-3d %6.0f %6.2f %6.0f %6.2f %6.2f %5.2f" % (row["label"], row["gp"], row["pin"], row["Ls"], row["Rsig_k"], row["Lg"], row["Rgnd_k"], row["Rlow_k"], row["SF"]))

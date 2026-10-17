"""截面几何与截面特性。

预制小箱梁、预制 T 梁中梁跨中截面取自浙江省交通运输厅《装配式预应力混凝土
T梁通用图》《装配式预应力混凝土小箱梁通用图》（浙交〔2024〕140 号，2024 年 11 月）：
T 梁 20/25/30/40 m，小箱梁 25/30 m。理想化处理：不计 2% 横坡与 r=5 cm 圆弧倒角，
小箱梁箱内顶角倒角按 15 cm × 7 cm 计。现浇箱梁截面尺寸在题目中给出。
截面特性由多边形（外轮廓减去内孔）按格林公式精确计算。
"""


def polygon_props(pts):
    """多边形面积、形心 y、对自身形心水平轴的惯性矩。pts 按逆时针给出 (x, y)。"""
    A = Sy = Ixx = 0.0
    n = len(pts)
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        c = x0 * y1 - x1 * y0
        A += c / 2
        Sy += (y0 + y1) * c / 6
        Ixx += (y0**2 + y0 * y1 + y1**2) * c / 12
    return A, Sy, Ixx


def section_props(outer, holes=()):
    """外轮廓减去若干内孔后的 A (m^2)、形心高度 yc (m, 自梁底)、I (m^4)。"""
    A, Sy, Ixx = polygon_props(outer)
    for h in holes:
        a, s, i = polygon_props(h)
        A, Sy, Ixx = A - a, Sy - s, Ixx - i
    yc = Sy / A
    return {'A': A, 'yc': yc, 'I': Ixx - A * yc**2, 'h': max(p[1] for p in outer)}


# ---------------- 预制小箱梁（中梁，跨中） ----------------
# 浙江 2024 通用图（先简支后连续，0°）图号 25LX162500-04、30LX162500-04 C-C 截面
SMALL_BOX = {
    25: {'h': 1.40, 'web_slope': 3.5, 'haunch_len': 0.201, 'haunch_rise': 0.062},
    30: {'h': 1.60, 'web_slope': 4.0, 'haunch_len': 0.192, 'haunch_rise': 0.063},
}
SMALL_BOX_COMMON = {'b_top': 2.40, 't_tip': 0.18, 'b_bot': 1.00, 't_bot': 0.18,
                    't_top': 0.18, 't_web': 0.20, 'chamfer': (0.15, 0.07)}
SMALL_BOX_HEIGHT = {k: v['h'] for k, v in SMALL_BOX.items()}


def small_box_geometry(span_class):
    d = {**SMALL_BOX_COMMON, **SMALL_BOX[span_class]}
    h, n = d['h'], d['web_slope']
    y_w = h - d['t_tip'] - d['haunch_rise']          # 腹板外侧顶点高度（加腋下缘）
    x_w = d['b_bot'] / 2 + y_w / n                    # 腹板外侧顶点半宽
    x_f = x_w + d['haunch_len']                       # 加腋外端半宽
    bt = d['b_top'] / 2
    outer = [(-d['b_bot'] / 2, 0), (d['b_bot'] / 2, 0), (x_w, y_w), (x_f, h - d['t_tip']),
             (bt, h - d['t_tip']), (bt, h), (-bt, h), (-bt, h - d['t_tip']),
             (-x_f, h - d['t_tip']), (-x_w, y_w)]
    # 箱室：腹板水平厚 t_web，内侧线与外侧线平行
    yb, yt = d['t_bot'], h - d['t_top']
    xi = lambda y: d['b_bot'] / 2 + y / n - d['t_web']
    cx, cy = d['chamfer']
    hole = [(-xi(yb), yb), (xi(yb), yb), (xi(yt - cy), yt - cy), (xi(yt - cy) - cx, yt),
            (-xi(yt - cy) + cx, yt), (-xi(yt - cy), yt - cy)]
    return outer, [hole]


# ---------------- 预制 T 梁（中梁，跨中） ----------------
# 浙江 2024 通用图（简支 T 梁，0°）设计说明第 2 节与一般构造图（二）
T_GIRDER = {
    20: {'h': 1.35, 'bulb_h': 0.20},
    25: {'h': 1.70, 'bulb_h': 0.20},
    30: {'h': 2.00, 'bulb_h': 0.20},
    40: {'h': 2.50, 'bulb_h': 0.35},
}
T_GIRDER_COMMON = {'b_top': 1.80, 't_tip': 0.18, 't_root': 0.27, 'flat_len': 0.20,
                   't_web': 0.20, 'b_bulb': 0.60, 'bulb_trans': 0.20}
T_GIRDER_HEIGHT = {k: v['h'] for k, v in T_GIRDER.items()}


def t_girder_geometry(span_class):
    d = {**T_GIRDER_COMMON, **T_GIRDER[span_class]}
    h = d['h']
    bf, tw, bb = d['b_top'] / 2, d['t_web'] / 2, d['b_bulb'] / 2
    yb, yt = d['bulb_h'], d['bulb_h'] + d['bulb_trans']
    x_h = bf - d['flat_len']                           # 加腋外端半宽
    outer = [(-bb, 0), (bb, 0), (bb, yb), (tw, yt), (tw, h - d['t_root']), (x_h, h - d['t_tip']),
             (bf, h - d['t_tip']), (bf, h), (-bf, h), (-bf, h - d['t_tip']), (-x_h, h - d['t_tip']),
             (-tw, h - d['t_root']), (-tw, yt), (-bb, yb)]
    return outer, []


# ---------------- 现浇单箱单室箱梁 ----------------
def cast_box_geometry(B_top, B_bot, h, t_top, t_bot, t_web, t_cant_root, t_cant_tip):
    """腹板竖直；翼缘悬臂根部厚 t_cant_root、端部厚 t_cant_tip。"""
    c = (B_top - B_bot) / 2
    outer = [(-B_bot / 2, 0), (B_bot / 2, 0), (B_bot / 2, h - t_cant_root),
             (B_top / 2, h - t_cant_tip), (B_top / 2, h), (-B_top / 2, h),
             (-B_top / 2, h - t_cant_tip), (-B_bot / 2, h - t_cant_root)]
    hole = [(-B_bot / 2 + t_web, t_bot), (B_bot / 2 - t_web, t_bot),
            (B_bot / 2 - t_web, h - t_top), (-B_bot / 2 + t_web, h - t_top)]
    assert c > 0
    return outer, [hole]


def girder_section(girder_type, span_class):
    geo = {'small_box': small_box_geometry, 't_girder': t_girder_geometry}[girder_type]
    return section_props(*geo(span_class))

"""截面特性计算工具（供大模型调用，也供知识图谱复算校验）。

输入为实例层中的截面几何（单位 m），输出面积 A、形心高度 yc、惯性矩 I。
几何按多边形（外轮廓减内孔）表示，用格林公式积分。
"""

SCHEMAS = {
    'small_box': ['h', 'b_top', 't_tip', 'haunch_len', 'haunch_rise', 'b_bottom', 't_bottom',
                  't_top', 't_web', 'web_slope', 'chamfer_w', 'chamfer_h'],
    't_girder': ['h', 'b_flange', 't_tip', 't_root', 'flat_len', 't_web', 'b_bulb', 'bulb_h', 'bulb_trans'],
    'cast_box': ['B_top', 'B_bot', 'h', 't_top', 't_bot', 't_web', 't_cant_root', 't_cant_tip'],
}
DESCRIPTIONS = {
    'small_box': '预制小箱梁中梁：梁高 h，顶宽 b_top，翼缘端部厚 t_tip，近腹板加腋长 haunch_len、增厚 haunch_rise，'
                 '底宽 b_bottom、底板厚 t_bottom，顶板厚 t_top，腹板水平厚 t_web，腹板外侧坡度 1:web_slope，'
                 '箱内顶角倒角 chamfer_w × chamfer_h',
    't_girder': '预制 T 梁中梁：梁高 h，翼缘宽 b_flange，外侧 flat_len 范围厚 t_tip、至腹板线性增厚到 t_root，'
                '腹板厚 t_web，马蹄宽 b_bulb、竖直段高 bulb_h、过渡段高 bulb_trans',
    'cast_box': '现浇单箱单室：顶宽 B_top、底宽 B_bot、梁高 h、顶板厚 t_top、底板厚 t_bot、竖直腹板厚 t_web、'
                '悬臂根部厚 t_cant_root、端部厚 t_cant_tip',
}


def _poly(pts):
    A = Sy = Ixx = 0.0
    for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
        c = x0 * y1 - x1 * y0
        A += c / 2
        Sy += (y0 + y1) * c / 6
        Ixx += (y0 * y0 + y0 * y1 + y1 * y1) * c / 12
    return A, Sy, Ixx


def outline(stype, g):
    """返回 (外轮廓, [内孔])，坐标原点在梁底中点，逆时针。"""
    if stype == 't_girder':
        h, bf, tw, bb = g['h'], g['b_flange'] / 2, g['t_web'] / 2, g['b_bulb'] / 2
        y1, y2 = g['bulb_h'], g['bulb_h'] + g['bulb_trans']
        xh = bf - g['flat_len']
        right = [(bb, 0), (bb, y1), (tw, y2), (tw, h - g['t_root']), (xh, h - g['t_tip']),
                 (bf, h - g['t_tip']), (bf, h)]
        return _mirror(right), []
    if stype == 'small_box':
        h, n = g['h'], g['web_slope']
        yw = h - g['t_tip'] - g['haunch_rise']
        xw = g['b_bottom'] / 2 + yw / n
        right = [(g['b_bottom'] / 2, 0), (xw, yw), (xw + g['haunch_len'], h - g['t_tip']),
                 (g['b_top'] / 2, h - g['t_tip']), (g['b_top'] / 2, h)]
        yb, yt = g['t_bottom'], h - g['t_top']
        xin = lambda y: g['b_bottom'] / 2 + y / n - g['t_web']
        cw, ch = g['chamfer_w'], g['chamfer_h']
        hole_r = [(xin(yb), yb), (xin(yt - ch), yt - ch), (xin(yt - ch) - cw, yt)]
        return _mirror(right), [_mirror(hole_r)]
    if stype == 'cast_box':
        h, Bt, Bb = g['h'], g['B_top'] / 2, g['B_bot'] / 2
        right = [(Bb, 0), (Bb, h - g['t_cant_root']), (Bt, h - g['t_cant_tip']), (Bt, h)]
        hole_r = [(Bb - g['t_web'], g['t_bot']), (Bb - g['t_web'], h - g['t_top'])]
        return _mirror(right), [_mirror(hole_r)]
    raise ValueError(f'未知截面类型: {stype}')


def _mirror(right):
    """右半轮廓（自下而上、x > 0）接其镜像逆序，得到逆时针闭合多边形。"""
    return right + [(-x, y) for x, y in reversed(right)]


def properties(stype, geometry):
    missing = [k for k in SCHEMAS[stype] if geometry.get(k) is None]
    if missing:
        raise ValueError(f'截面几何缺少参数: {missing}')
    try:
        geometry = {**geometry, **{k: float(geometry[k]) for k in SCHEMAS[stype]}}
    except (TypeError, ValueError):
        raise ValueError(f'截面几何参数须为数值（单位 m）: { {k: geometry[k] for k in SCHEMAS[stype]} }')
    if any(geometry[k] <= 0 for k in ('h', 'web_slope') if k in geometry):
        raise ValueError('截面几何无效：梁高 h（及腹板坡度 web_slope）须为正数')
    outer, holes = outline(stype, geometry)
    A, Sy, Ixx = _poly(outer)
    for hpts in holes:
        a, s, i = _poly(hpts)
        A, Sy, Ixx = A - a, Sy - s, Ixx - i
    if not A > 1e-9:
        raise ValueError(f'截面几何无效：积分所得面积 A = {A:.4g} m²，不为正；请检查各尺寸（单位 m）及其相互关系')
    yc = Sy / A
    return {'A': A, 'yc': yc, 'I': Ixx - A * yc * yc, 'h': geometry['h']}

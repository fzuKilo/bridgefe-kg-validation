"""基准所用规范条文的可执行形式。

条文号按 JTG D60-2015、JTG 3362-2018 整理，正式发布前须由专家逐条核对
（条文号、适用条件与数值）。单位：N、m、Pa，另有注明者除外。
"""
import math

CLAUSES = {
    'JTG3362-3.1.5': 'JTG 3362-2018 第 3.1.5 条 表 3.1.5：混凝土弹性模量 Ec',
    'JTGD60-4.2.1': 'JTG D60-2015 第 4.2.1 条 表 4.2.1：常用材料重度（钢筋混凝土、预应力混凝土 25.0~26.0 kN/m3）',
    'JTGD60-4.3.1-lane': 'JTG D60-2015 第 4.3.1 条：公路-I 级车道荷载 qk=10.5 kN/m，Pk 按计算跨径线性内插；公路-II 级取 0.75 倍',
    'JTGD60-4.3.1-lanes': 'JTG D60-2015 第 4.3.1 条 表 4.3.1-4：按桥面行车道宽度确定设计车道数',
    'JTGD60-4.3.1-xi': 'JTG D60-2015 第 4.3.1 条 表 4.3.1-5：横向车道布载系数',
    'JTGD60-4.3.2': 'JTG D60-2015 第 4.3.2 条：冲击系数 mu 按结构基频 f 计算',
    'JTG3362-8.7-Ee': 'JTG 3362-2018 第 8.7 节：板式橡胶支座抗压弹性模量 Ee=5.4GeS^2，体积模量 Eb=2000 MPa',
    'JTG3362-8.7-Ge': 'JTG 3362-2018 第 8.7 节：板式橡胶支座剪变模量 Ge=1.0 MPa',
}

# 混凝土弹性模量 (MPa)
EC_TABLE = {'C25': 2.80e4, 'C30': 3.00e4, 'C35': 3.15e4, 'C40': 3.25e4, 'C45': 3.35e4,
            'C50': 3.45e4, 'C55': 3.55e4, 'C60': 3.60e4, 'C65': 3.65e4, 'C70': 3.70e4,
            'C75': 3.75e4, 'C80': 3.80e4}

GAMMA_PC = 26.0e3        # 预应力混凝土重度取表 4.2.1 上限 (N/m^3)
G_ACC = 9.81             # 重力加速度 (m/s^2)
GE_STANDARD = 1.0e6      # 支座剪变模量 (Pa)
EB_RUBBER = 2000.0e6     # 橡胶体积模量 (Pa)


def concrete_E(grade):
    return EC_TABLE[grade] * 1e6


def lane_load(load_class, L0):
    """车道荷载 (qk N/m, Pk N)。L0 为计算跨径 (m)。"""
    if L0 <= 5:
        Pk = 270e3
    elif L0 >= 50:
        Pk = 360e3
    else:
        Pk = 2 * (L0 + 130) * 1e3
    qk = 10.5e3
    factor = {'I': 1.0, 'II': 0.75}[load_class]
    return qk * factor, Pk * factor


def design_lanes(W, two_way):
    """设计车道数，W 为桥面行车道宽度 (m)。"""
    if two_way:
        for lim, n in [(6.0, None), (14.0, 2), (21.0, 4), (28.0, 6), (35.0, 8), (42.0, 10)]:
            if W < lim:
                if n is None:
                    raise ValueError('双向行驶行车道宽度不应小于 6.0 m')
                return n
    else:
        for lim, n in [(7.0, 1), (10.5, 2), (14.0, 3), (17.5, 4), (21.0, 5),
                       (24.5, 6), (28.0, 7), (31.5, 8)]:
            if W < lim:
                return n
    raise ValueError('桥面过宽，超出表 4.3.1-4 范围')


XI = {1: 1.20, 2: 1.00, 3: 0.78, 4: 0.67, 5: 0.60, 6: 0.55, 7: 0.52, 8: 0.50}


def impact_factor(f):
    if f < 1.5:
        return 0.05
    if f > 14.0:
        return 0.45
    return 0.1767 * math.log(f) - 0.0157


def bearing_stiffness(a, b, t1, n_layers, Ge=GE_STANDARD):
    """矩形板式橡胶支座单个支座刚度。

    a、b 为有效平面尺寸 (m)，t1 为单层橡胶厚 (m)，n_layers 为橡胶层数。
    返回 (Kv 竖向 N/m, Kh 剪切 N/m, S 形状系数, Ee Pa)。
    """
    Ae = a * b
    te = t1 * n_layers
    S = a * b / (2 * t1 * (a + b))
    Ee = 5.4 * Ge * S**2
    Kv = Ae / (te * (1 / Ee + 1 / EB_RUBBER))
    Kh = Ge * Ae / te
    return Kv, Kh, S, Ee

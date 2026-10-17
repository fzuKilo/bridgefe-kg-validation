"""BridgeFE-Bench 响应层参考答案：独立编写的 OpenSeesPy 单梁模型。

输入为已解析的模型规格 spec（由决策层参考答案组装）：
  spans        各跨计算跨径 (m)
  girder       {'E','A','I','w','m'}  主梁（全桥合并截面）
  supports     每条支承线 {'Kv','Kh','pier'}，Kh=0 表示纵向滑动；
               或 {'rigid': True, 'fix_x': bool}（球形支座，竖向刚性）；
               pier 为 None（支承于刚性基础）或 {'H','E','A','I','m'}
  lane         {'load_class','n_lanes','xi'}

建模约定（与 rules.json 一致）：主梁为二维弹性梁单元，每跨 N_PER_SPAN 个单元；
支座为 zeroLength 弹簧（竖向 Kv、纵向 Kh，转动自由），支座与墩顶均位于主梁轴线标高；
墩柱为弹性梁单元，墩底固结；质量为一致质量矩阵。
"""
import math

import numpy as np
import openseespy.opensees as ops

from code_provisions import impact_factor, lane_load

N_PER_SPAN = 20      # 偶数，保证跨中有节点
N_PER_PIER = 10
N_MODES = 30


class Model:
    def __init__(self, spec):
        self.spec = spec
        self.build()

    # ---------------- 建模 ----------------
    def build(self):
        s = self.spec
        g = s['girder']
        ops.wipe()
        ops.model('basic', '-ndm', 2, '-ndf', 3)
        ops.geomTransf('Linear', 1)
        ops.geomTransf('Linear', 2)          # 墩柱

        # 主梁节点
        self.x = [0.0]
        self.support_gnode = [1]
        self.mid_gnode = []
        ops.node(1, 0.0, 0.0)
        tag = 1
        for L in s['spans']:
            x0 = self.x[-1]
            for i in range(1, N_PER_SPAN + 1):
                tag += 1
                xi = x0 + L * i / N_PER_SPAN
                ops.node(tag, xi, 0.0)
                self.x.append(xi)
                if i == N_PER_SPAN // 2:
                    self.mid_gnode.append(tag)
            self.support_gnode.append(tag)
        self.n_gnode = tag
        self.girder_eles = list(range(1, self.n_gnode))
        for e in self.girder_eles:
            ops.element('elasticBeamColumn', e, e, e + 1, g['A'], g['E'], g['I'], 1,
                        '-mass', g['m'], '-cMass')

        # 支座与墩柱
        mat = 1
        ele = self.n_gnode
        node = self.n_gnode
        self.bearing_eles = []
        self.pier_eles = []
        self._pier_mass = {}
        for k, sup in enumerate(s['supports']):
            gnode = self.support_gnode[k]
            xs = self.x[gnode - 1]
            if sup.get('rigid'):                       # 球形支座：竖向刚性、转动自由
                ops.fix(gnode, 1 if sup['fix_x'] else 0, 1, 0)
                self.bearing_eles.append((None, None, gnode, None))
                continue
            node += 1
            top = node
            ops.node(top, xs, 0.0)
            pier = sup['pier']
            if pier is None:
                ops.fix(top, 1, 1, 1)
            else:
                prev = top
                for j in range(1, N_PER_PIER + 1):
                    node += 1
                    ops.node(node, xs, -pier['H'] * j / N_PER_PIER)
                    ele += 1
                    ops.element('elasticBeamColumn', ele, node, prev, pier['A'], pier['E'],
                                pier['I'], 2, '-mass', pier['m'], '-cMass')
                    self.pier_eles.append(ele)
                    self._pier_mass[ele] = pier['m']
                    prev = node
                ops.fix(node, 1, 1, 1)
            mats, dirs = [], []
            if sup['Kh'] > 0:
                ops.uniaxialMaterial('Elastic', mat, sup['Kh'])
                mats.append(mat); dirs.append(1); mat += 1
            ops.uniaxialMaterial('Elastic', mat, sup['Kv'])
            mats.append(mat); dirs.append(2); mat += 1
            ele += 1
            ops.element('zeroLength', ele, top, gnode, '-mat', *mats, '-dir', *dirs)
            self.bearing_eles.append((ele, top, gnode, sup['Kv']))

        ops.timeSeries('Constant', 1)
        self.pattern_tag = 0

    # ---------------- 工具 ----------------
    def _setup_static(self):
        ops.wipeAnalysis()
        ops.system('BandGeneral')
        ops.numberer('RCM')
        ops.constraints('Plain')
        ops.integrator('LoadControl', 1.0)
        ops.algorithm('Linear')
        ops.analysis('Static')

    def _solve(self, add_loads):
        """在新荷载模式下求解一次线性静力问题。"""
        if self.pattern_tag:
            ops.remove('loadPattern', self.pattern_tag)
        ops.reset()
        self.pattern_tag += 1
        ops.pattern('Plain', self.pattern_tag, 1)
        add_loads()
        ok = ops.analyze(1)
        if ok != 0:
            raise RuntimeError('静力分析失败')

    def moment_at(self, gnode):
        """主梁节点处弯矩（下缘受拉为正），取该节点左侧单元 j 端。"""
        if gnode == 1:
            return -ops.eleResponse(1, 'localForce')[2]
        return ops.eleResponse(gnode - 1, 'localForce')[5]

    def sections(self):
        """车道荷载控制截面：各跨跨中（正弯矩）与中间支点（负弯矩）。"""
        secs = [('span', k + 1, n) for k, n in enumerate(self.mid_gnode)]
        secs += [('support', k, n) for k, n in enumerate(self.support_gnode) if 0 < k < len(self.support_gnode) - 1]
        return secs

    # ---------------- 自重 ----------------
    def self_weight(self):
        w = self.spec['girder']['w']
        self._setup_static()
        self._solve(lambda: ops.eleLoad('-ele', *self.girder_eles, '-type', '-beamUniform', -w))
        R = []
        ops.reactions()
        for ele, top, gnode, Kv in self.bearing_eles:
            if ele is None:
                R.append(ops.nodeReaction(gnode, 2))
            else:
                R.append(Kv * (ops.nodeDisp(top, 2) - ops.nodeDisp(gnode, 2)))
        M_mid = [self.moment_at(n) for n in self.mid_gnode]
        M_sup = [self.moment_at(n) for n in self.support_gnode[1:-1]]
        return R, M_mid, M_sup

    # ---------------- 模态 ----------------
    def vertical_frequencies(self, n=3):
        ops.wipeAnalysis()
        lam = ops.eigen(N_MODES)
        # 按节点从属质量加权：主梁竖向动能占全结构平动动能一半以上者为竖向弯曲振型
        mass = {}
        for e in self.girder_eles:
            share = self.spec['girder']['m'] * (self.x[e] - self.x[e - 1]) / 2
            for nd in (e, e + 1):
                mass[nd] = mass.get(nd, 0.0) + share
        for e in self.pier_eles:
            nd_i, nd_j = ops.eleNodes(e)
            yi, yj = ops.nodeCoord(nd_i)[1], ops.nodeCoord(nd_j)[1]
            pm = self._pier_mass[e] * abs(yj - yi) / 2
            for nd in (nd_i, nd_j):
                mass[nd] = mass.get(nd, 0.0) + pm
        out = []
        for i, l in enumerate(lam, 1):
            total = girder_v = 0.0
            for nd, mn in mass.items():
                ux, uy = ops.nodeEigenvector(nd, i, 1), ops.nodeEigenvector(nd, i, 2)
                total += mn * (ux**2 + uy**2)
                if nd <= self.n_gnode:
                    girder_v += mn * uy**2
            if girder_v > 0.5 * total:
                out.append(math.sqrt(l) / (2 * math.pi))
            if len(out) == n:
                break
        if len(out) < n:
            raise RuntimeError('未找到足够的竖向振型，请增加 N_MODES')
        return out

    # ---------------- 车道荷载 ----------------
    def _point_load_influence(self, ele, xi, gnodes):
        """单位竖向集中力作用于单元 ele 的相对位置 xi 时各截面弯矩。"""
        self._solve(lambda: ops.eleLoad('-ele', ele, '-type', '-beamPoint', -1.0, xi))
        return [self.moment_at(n) for n in gnodes]

    def lane_moments(self, f1):
        """车道荷载各控制截面弯矩（含冲击、车道数与横向折减）。

        弹性梁单元内弯矩影响线为三次多项式：每个单元取 4 个加载点精确拟合，
        均布荷载 qk 满布于同号影响线区段（解析积分），集中荷载 Pk 置于各跨
        最不利纵坐标处，Pk 按所在跨计算跨径取值，取各跨中的最不利者。
        """
        s = self.spec
        lane = s['lane']
        mu = impact_factor(f1)
        amp = (1 + mu) * lane['n_lanes'] * lane['xi']
        qk = lane_load(lane['load_class'], s['spans'][0])[0]   # qk 与跨径无关
        secs = self.sections()
        gnodes = [sec[2] for sec in secs]
        self._setup_static()

        pts = np.array([0.0, 1 / 3, 2 / 3, 1.0])
        V_inv = np.linalg.inv(np.vander(pts, 4, increasing=True))
        cache = {}

        def infl(e, xi):
            key = (e, xi) if 0 < xi < 1 else ((e, 0.0) if xi == 0 else (e + 1, 0.0))
            if key not in cache:
                if key[0] == self.n_gnode:          # 末端节点：最后一个单元 j 端
                    cache[key] = self._point_load_influence(self.n_gnode - 1, 1.0, gnodes)
                else:
                    cache[key] = self._point_load_influence(key[0], key[1], gnodes)
            return cache[key]

        n_sec = len(secs)
        area = np.zeros(n_sec)
        peak = [[(0.0, None)] * len(s['spans']) for _ in range(n_sec)]
        for e in self.girder_eles:
            k = (e - 1) // N_PER_SPAN                 # 所在跨
            x0, x1 = self.x[e - 1], self.x[e]
            Le = x1 - x0
            Y = np.array([infl(e, xi) for xi in pts])  # 4 x n_sec
            C = V_inv @ Y                              # 三次式系数（局部坐标 t∈[0,1]）
            for j, (kind, _, _) in enumerate(secs):
                c = C[:, j] * (1.0 if kind == 'span' else -1.0)
                area[j] += Le * _positive_integral(c)
                t, y = _cubic_max(c)
                if y > peak[j][k][0]:
                    peak[j][k] = (y, x0 + t * Le)

        results = []
        for j, (kind, idx, gnode) in enumerate(secs):
            sign = 1.0 if kind == 'span' else -1.0
            best, best_x = 0.0, None
            for k, L in enumerate(s['spans']):
                Pk = lane_load(lane['load_class'], L)[1]
                if Pk * peak[j][k][0] > best:
                    best, best_x = Pk * peak[j][k][0], peak[j][k][1]
            M = sign * amp * (qk * area[j] + best)
            results.append({'section': kind, 'index': idx, 'x_m': self.x[gnode - 1],
                            'M_lane_kNm': M / 1e3, 'Pk_position_m': best_x})
        return mu, results


def _positive_integral(c):
    """∫_0^1 max(p(t), 0) dt，p 为三次多项式（系数升幂）。"""
    roots = [r.real for r in np.roots(c[::-1]) if abs(r.imag) < 1e-12 and 0 < r.real < 1] \
        if np.any(c[1:]) else []
    knots = [0.0] + sorted(roots) + [1.0]
    P = np.polynomial.Polynomial(c).integ()
    total = 0.0
    for a, b in zip(knots, knots[1:]):
        part = P(b) - P(a)
        if part > 0:
            total += part
    return total


def _cubic_max(c):
    """三次多项式在 [0,1] 上的最大值及位置。"""
    cand = [0.0, 1.0]
    d = np.polynomial.Polynomial(c).deriv()
    if np.any(d.coef):
        cand += [r.real for r in d.roots() if abs(r.imag) < 1e-12 and 0 < r.real < 1]
    p = np.polynomial.Polynomial(c)
    t = max(cand, key=p)
    return t, float(p(t))


def solve_reference(spec):
    """计算响应层参考答案（单位 kN、kN·m、Hz）。"""
    m = Model(spec)
    R, M_mid, M_sup = m.self_weight()
    freqs = m.vertical_frequencies(3)
    mu, lane = m.lane_moments(freqs[0])
    pos = [r for r in lane if r['section'] == 'span']
    neg = [r for r in lane if r['section'] == 'support']
    p = max(pos, key=lambda r: r['M_lane_kNm'])
    out = {
        'self_weight_support_reactions_kN': [r / 1e3 for r in R],
        'self_weight_midspan_moments_kNm': [v / 1e3 for v in M_mid],
        'self_weight_support_moments_kNm': [v / 1e3 for v in M_sup],
        'vertical_frequencies_Hz': freqs,
        'first_vertical_frequency_Hz': freqs[0],
        'impact_factor_mu': mu,
        'lane_moments_by_section': lane,
        'lane_max_positive_moment_kNm': p['M_lane_kNm'],
        'lane_max_positive_moment_location': f"span {p['index']} midspan",
    }
    if neg:
        n = min(neg, key=lambda r: r['M_lane_kNm'])
        out['lane_max_negative_moment_kNm'] = n['M_lane_kNm']
        out['lane_max_negative_moment_location'] = f"support {n['index']}"
    else:
        out['lane_max_negative_moment_kNm'] = None
        out['lane_max_negative_moment_location'] = 'not applicable (simply supported)'
    return out

"""A 档（单跨简支梁）响应层参考答案：解析解。

自重反力与跨中弯矩为静定结果；一阶竖向频率按两端竖向弹簧支承
（支座竖向刚度 Kv、弯矩为零）的 Euler-Bernoulli 梁精确频率方程求解；
车道荷载跨中最大弯矩 = (1+mu)·n·xi·(qk L^2/8 + Pk L/4)。
"""
import math

import numpy as np
from scipy.optimize import brentq

from code_provisions import impact_factor, lane_load


def spring_supported_frequency(L, E, I, m, k_left, k_right):
    """两端竖向弹簧、转动自由的简支梁一阶竖向频率 (Hz)。"""
    EI = E * I

    def det(omega):
        b = (omega**2 * m / EI) ** 0.25
        s, c, sh, ch = math.sin(b * L), math.cos(b * L), math.sinh(b * L), math.cosh(b * L)
        # W = C1 sin + C2 cos + C3 sinh + C4 cosh
        # x=0: W''=0；EI W''' + k_left W = 0
        # x=L: W''=0；EI W''' - k_right W = 0
        M = np.array([
            [0, -1, 0, 1],
            [EI * b**3 * (-1), k_left, EI * b**3, k_left],
            [-s, -c, sh, ch],
            [EI * b**3 * (-c) - k_right * s, EI * b**3 * s - k_right * c,
             EI * b**3 * ch - k_right * sh, EI * b**3 * sh - k_right * ch],
        ])
        # 按行归一，避免数值溢出
        M = M / np.abs(M).max(axis=1, keepdims=True)
        return np.linalg.det(M)

    w_rigid = (math.pi / L) ** 2 * math.sqrt(EI / m)
    grid = np.linspace(0.3 * w_rigid, 1.05 * w_rigid, 4000)
    vals = [det(w) for w in grid]
    for i in range(len(grid) - 1):
        if np.sign(vals[i]) != np.sign(vals[i + 1]):
            return brentq(det, grid[i], grid[i + 1], xtol=1e-14) / (2 * math.pi)
    raise RuntimeError('未找到一阶频率')


def solve_tier_a(spec):
    L = spec['spans'][0]
    g = spec['girder']
    lane = spec['lane']
    f_rigid = math.pi / (2 * L**2) * math.sqrt(g['E'] * g['I'] / g['m'])
    if all(s.get('rigid') for s in spec['supports']):
        f1 = f_rigid                                     # 刚性支承（球形支座）
    else:
        kl, kr = spec['supports'][0]['Kv'], spec['supports'][1]['Kv']
        f1 = spring_supported_frequency(L, g['E'], g['I'], g['m'], kl, kr)
    mu = impact_factor(f1)
    qk, Pk = lane_load(lane['load_class'], L)
    M_lane = (1 + mu) * lane['n_lanes'] * lane['xi'] * (qk * L**2 / 8 + Pk * L / 4)
    return {
        'self_weight_support_reactions_kN': [g['w'] * L / 2 / 1e3] * 2,
        'self_weight_midspan_moments_kNm': [g['w'] * L**2 / 8 / 1e3],
        'first_vertical_frequency_Hz': f1,
        'first_vertical_frequency_rigid_supports_Hz': f_rigid,
        'impact_factor_mu': mu,
        'lane_max_positive_moment_kNm': M_lane / 1e3,
        'lane_max_positive_moment_location': 'span 1 midspan',
        'lane_max_negative_moment_kNm': None,
        'lane_max_negative_moment_location': 'not applicable (simply supported)',
    }

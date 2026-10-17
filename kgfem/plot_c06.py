"""贯穿算例 C06：有限元模型图与结构响应图（英文），并输出响应对比表数据。
python -m kgfem.plot_c06 [--out 目录]

模型取自 C5 运行（DeepSeek-V4-Flash，runs_ablation_single/C5/C06_r3）生成的脚本；未经校验的对照模型取自
gpt-6-luna 的 C4 运行（runs_luna/C4/C06_r3，桥台形状系数 9.09、横向折减系数 1.0）。曲线由同一脚本重算：
自重挠度与弯矩、前三阶竖弯振型，以及沿主梁逐节点的车道荷载弯矩包络（与生成器的影响线方法相同）。
"""
import argparse
import contextlib
import io
import json
import math
import os
import sys

import matplotlib
matplotlib.use('Agg')
matplotlib.rcParams['pdf.fonttype'] = 42   # 嵌入 TrueType 字体（期刊要求）
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyBboxPatch, Polygon

from .plot_ablation import INK, INK2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
C5 = os.path.join(ROOT, 'runs_ablation_single', 'C5', 'C06_r3', 'C06_model.py')
C4 = os.path.join(ROOT, 'runs_luna', 'C4', 'C06_r3', 'C06_model.py')
REF = os.path.join(ROOT, 'bridgefe_bench', 'problems', 'C06.json')
BLUE, ORANGE, PURPLE, GRAY = '#2a78d6', '#d9822b', '#8b5cc4', '#8a8984'


def analyse(script):
    """执行生成的脚本（只建模与模态），再在同一命名空间中计算完整曲线。"""
    src = open(script, encoding='utf-8').read()
    ns = {'__name__': 'c06'}
    argv = sys.argv
    sys.argv = ['x', 'modal']
    with contextlib.redirect_stdout(io.StringIO()):
        exec(compile(src, script, 'exec'), ns)
    sys.argv = argv
    ops, IR = ns['ops'], ns['IR']
    ng = IR['n_girder_nodes']
    X = np.array(ns['X'])
    out = {'IR': IR, 'x': X, 'freqs': ns['result']['vertical_frequencies_Hz']}

    # 振型（与生成器相同的竖向判别），按峰值归一化
    ops.wipeAnalysis()
    lam = ops.eigen(30)
    mass = {}
    for e in IR['elements']:
        (xi, yi), (xj, yj) = ops.nodeCoord(e['nodes'][0]), ops.nodeCoord(e['nodes'][1])
        share = e['mass'] * math.hypot(xj - xi, yj - yi) / 2
        for n in e['nodes']:
            mass[n] = mass.get(n, 0.0) + share
    modes = []
    for i in range(1, len(lam) + 1):
        tot = gv = 0.0
        for n, m in mass.items():
            ux, uy = ops.nodeEigenvector(n, i, 1), ops.nodeEigenvector(n, i, 2)
            tot += m * (ux * ux + uy * uy)
            if n <= ng:
                gv += m * uy * uy
        if gv > 0.5 * tot:
            v = np.array([ops.nodeEigenvector(n, i, 2) for n in range(1, ng + 1)])
            v = v / v[np.argmax(np.abs(v))]
            modes.append((math.sqrt(lam[i - 1]) / (2 * math.pi), v))
        if len(modes) == 3:
            break
    out['modes'] = modes

    # 自重
    ns['setup_static']()
    w = IR['self_weight']['w']
    G = ns['GIRDER']
    ns['static'](lambda: ops.eleLoad('-ele', *[e['id'] for e in G], '-type', '-beamUniform', -w))
    out['defl_mm'] = np.array([ops.nodeDisp(n, 2) * 1000 for n in range(1, ng + 1)])
    out['M_sw'] = np.array([ns['moment'](n) for n in range(1, ng + 1)])
    out['reactions'] = ns['reactions']()

    # 车道荷载包络：逐节点影响线，正、负分别取最不利
    L = IR['lane']
    amp = (1 + L['mu']) * L['n_lanes'] * L['xi']
    nodes = list(range(1, ng + 1))
    t = np.array([0.0, 1 / 3, 2 / 3, 1.0])
    Vinv = np.linalg.inv(np.vander(t, 4, increasing=True))
    nsp = len(IR['spans'])
    area = {1: np.zeros(ng), -1: np.zeros(ng)}
    peak = {1: np.zeros((ng, nsp)), -1: np.zeros((ng, nsp))}
    for e in G:
        x0, x1 = X[e['nodes'][0] - 1], X[e['nodes'][1] - 1]
        Y = []
        for xi in t:
            ns['static'](lambda: ops.eleLoad('-ele', e['id'], '-type', '-beamPoint', -1.0, xi))
            Y.append([ns['moment'](n) for n in nodes])
        C = Vinv @ np.array(Y)
        for s in range(ng):
            for sign in (1, -1):
                c = C[:, s] * sign
                p = np.polynomial.Polynomial(c)
                r = sorted(z.real for z in p.roots() if abs(z.imag) < 1e-12 and 0 < z.real < 1) if np.any(c[1:]) else []
                P = p.integ()
                knots = [0.0] + r + [1.0]
                area[sign][s] += (x1 - x0) * sum(max(P(b) - P(a), 0.0) for a, b in zip(knots, knots[1:]))
                cand = [0.0, 1.0] + ([z.real for z in p.deriv().roots() if abs(z.imag) < 1e-12 and 0 < z.real < 1]
                                     if np.any(p.deriv().coef) else [])
                j = e['span'] - 1
                peak[sign][s, j] = max(peak[sign][s, j], max(p(z) for z in cand))
    env = {}
    for sign in (1, -1):
        conc = np.max(np.array([float(L['Pk'][str(j + 1)]) for j in range(nsp)]) * peak[sign], axis=1)
        env[sign] = sign * amp * (L['qk'] * area[sign] + conc)
    out['env_pos'], out['env_neg'] = env[1], env[-1]
    return out


def style():
    plt.rcParams.update({'font.sans-serif': ['Arial', 'Helvetica', 'DejaVu Sans'], 'axes.unicode_minus': True,
                         'font.size': 7.5, 'axes.edgecolor': INK2, 'axes.labelcolor': INK, 'xtick.color': INK2,
                         'ytick.color': INK2, 'axes.linewidth': 0.6, 'xtick.major.width': 0.6,
                         'ytick.major.width': 0.6})


def _axes(ax, X, IR, ylabel):
    sx = [X[n - 1] for n in IR['support_nodes']]
    for x in sx:
        ax.axvline(x, color='#e4e3df', lw=0.6, zorder=0)
    ax.axhline(0, color=INK2, lw=0.5, zorder=1)
    ax.set_xticks(sx)
    ax.set_xlim(sx[0], sx[-1])
    ax.set_ylabel(ylabel)
    for s in ('top', 'right'):
        ax.spines[s].set_visible(False)


def fig_responses(r5, r4):
    X, IR = r5['x'], r5['IR']
    fig, axs = plt.subplots(2, 2, figsize=(7.2, 4.6))
    (a, b), (c, d) = axs
    a.plot(X, r5['defl_mm'], color=BLUE, lw=1.4)
    i = int(np.argmin(r5['defl_mm']))
    a.annotate(f"{r5['defl_mm'][i]:.1f} mm", (X[i], r5['defl_mm'][i]), xytext=(0, -11), textcoords='offset points',
               ha='center', fontsize=6.5, color=INK)
    _axes(a, X, IR, 'Deflection (mm)')
    a.set_title('(a) Girder deflection under self-weight', loc='left', fontsize=8, color=INK)
    a.set_ylim(min(r5['defl_mm']) * 1.35, 2)

    M = r5['M_sw'] / 1000
    b.plot(X, M, color=BLUE, lw=1.4)
    b.fill_between(X, M, 0, color=BLUE, alpha=0.12, lw=0)
    for n in IR['mid_nodes']:
        b.annotate(f'{M[n - 1]:.2f}', (X[n - 1], M[n - 1]), xytext=(0, 3), textcoords='offset points', ha='center',
                   fontsize=6.3, color=INK)
    for n in IR['support_nodes'][1:-1]:
        b.annotate(f'{M[n - 1]:.2f}', (X[n - 1], M[n - 1]), xytext=(0, -9), textcoords='offset points', ha='center',
                   fontsize=6.3, color=INK)
    _axes(b, X, IR, 'Moment (MN m), sagging +')
    b.set_title('(b) Girder moment under self-weight', loc='left', fontsize=8, color=INK)
    b.set_ylim(M.min() * 1.25, M.max() * 1.35)

    for (f, v), col, ls in zip(r5['modes'], (BLUE, ORANGE, PURPLE), ('-', '--', '-.')):
        c.plot(X, v, color=col, lw=1.3, ls=ls, label=f'{f:.2f} Hz')
    _axes(c, X, IR, 'Normalized mode shape')
    c.set_ylim(-1.25, 1.25)
    c.legend(loc='lower left', fontsize=6.5, frameon=False, ncol=3, handlelength=2.2, bbox_to_anchor=(0.0, -0.02))
    c.set_title('(c) First three vertical modes', loc='left', fontsize=8, color=INK)
    c.set_xlabel('Distance along girder (m)')

    d.plot(X, r4['env_pos'] / 1000, color=GRAY, lw=1.2, label='C4, gpt-6-luna (ξ = 1.0; abutment Kv −14%)')
    d.plot(X, r4['env_neg'] / 1000, color=GRAY, lw=1.2)
    d.plot(X, r5['env_pos'] / 1000, color=BLUE, lw=1.4, label='C5 (= reference model)')
    d.plot(X, r5['env_neg'] / 1000, color=BLUE, lw=1.4)
    j = int(np.argmax(r4['env_pos']))
    ratio = r4['env_pos'].max() / r5['env_pos'].max() - 1
    d.annotate(f'+{ratio:.0%}', (X[j], r4['env_pos'][j] / 1000), xytext=(10, 4), textcoords='offset points',
               fontsize=6.5, color=INK, arrowprops=dict(arrowstyle='-', color=INK2, lw=0.5))
    _axes(d, X, IR, 'Moment (MN m), sagging +')
    d.set_title('(d) Lane-load moment envelope with impact', loc='left', fontsize=8, color=INK)
    d.set_xlabel('Distance along girder (m)')
    d.legend(loc='lower center', fontsize=6.3, frameon=False, ncol=1, bbox_to_anchor=(0.5, -0.02))
    d.set_ylim(r4['env_neg'].min() / 1000 * 1.6, r4['env_pos'].max() / 1000 * 1.25)
    fig.tight_layout(h_pad=1.2, w_pad=1.5)
    return fig


def _sci(v):
    m, e = f'{v:.2e}'.split('e')
    return f'{m}$\\times$10$^{{{int(e)}}}$'


def fig_model(r5):
    """示意立面：水平按比例，竖向放大；数值均取自生成的中间表示。"""
    IR = r5['IR']
    N = {n['id']: n for n in IR['nodes']}
    fig, ax = plt.subplots(figsize=(7.2, 3.1))
    ax.axis('off')
    k = 11.6 / 140.0
    X = lambda x: 0.2 + x * k
    ys = 0.075                                   # 桥墩竖向比例（单位/米）
    yb = -0.42                                   # 支座下端
    gn = [N[i] for i in range(1, IR['n_girder_nodes'] + 1)]
    ax.plot([X(n['x']) for n in gn], [0] * len(gn), color=BLUE, lw=2.2, zorder=3)
    ax.scatter([X(n['x']) for n in gn], [0] * len(gn), s=5, facecolor='white', edgecolor=BLUE, lw=0.5, zorder=4)

    def zig(x0, y0, x1, y1, n=8, amp=0.07):
        t = np.linspace(0, 1, 2 * n + 1)
        off = np.array([0] + [(-1) ** i * amp for i in range(2 * n - 1)] + [0])
        dx, dy = x1 - x0, y1 - y0
        L = math.hypot(dx, dy)
        ux, uy = dx / L, dy / L
        ax.plot(x0 + dx * t - uy * off, y0 + dy * t + ux * off, color=ORANGE, lw=0.9, zorder=5)

    def ground(x, y, w=0.36):
        ax.plot([x - w / 2, x + w / 2], [y, y], color=INK, lw=0.8, zorder=5)
        for q in range(5):
            xx = x - w / 2 + 0.03 + q * (w - 0.06) / 4
            ax.plot([xx, xx - 0.06], [y, y - 0.08], color=INK, lw=0.5, zorder=5)

    for b in IR['bearings']:
        x = X(N[b['girder_node']]['x'])
        zig(x, -0.03, x, yb + 0.02)
        pier = [n for n in IR['nodes'] if n['role'] == 'pier' and abs(n['x'] - N[b['girder_node']]['x']) < 1e-6]
        if b['long'] == 'free':
            for dx in (-0.07, 0.07):
                ax.add_patch(plt.Circle((x + dx, yb - 0.05), 0.045, fc='white', ec=INK, lw=0.6, zorder=6))
            base = yb - 0.1
        else:
            base = yb
            zig(x - 0.42, -0.2, x - 0.02, -0.2, n=5, amp=0.05)
            ax.plot([x - 0.44, x - 0.44], [-0.32, -0.08], color=INK, lw=0.9)
        if pier:
            ax.plot([x - 0.18, x + 0.18], [base, base], color=INK, lw=1.0, zorder=5)
            H = -min(n['y'] for n in pier)
            ytop, ybot = base, base - H * ys
            ax.plot([x, x], [ytop, ybot], color='#5f5e5a', lw=1.6, zorder=3)
            m = len(pier)
            ax.scatter([x] * (m + 1), np.linspace(ytop, ybot, m + 1), s=4, facecolor='white', edgecolor='#5f5e5a',
                       lw=0.5, zorder=4)
            ground(x, ybot)
            pk = 1 + [bb['support'] for bb in IR['bearings']].index(b['support']) - 1
            left = b['support'] == len(IR['bearings']) - 2
            ax.text(x + (-0.12 if left else 0.1), ybot + 0.05, f"Pier {b['support']}\nH = {H:g} m",
                    ha='right' if left else 'left', va='bottom', fontsize=6.2, color=INK2, linespacing=1.15)
        else:
            ground(x, base)
            ax.text(x, base - 0.14, f"Abutment {b['support']}", ha='center', va='top', fontsize=6.2, color=INK2)
    sxs = [N[n]['x'] for n in IR['support_nodes']]
    for x0, x1, L in zip(sxs, sxs[1:], IR['spans']):
        ax.text(X((x0 + x1) / 2), 0.1, f'{L:g} m', ha='center', va='bottom', fontsize=6.5, color=INK2)

    b = {bb['support']: bb for bb in IR['bearings']}
    g = [e for e in IR['elements'] if e['role'] == 'girder'][0]
    p = [e for e in IR['elements'] if e['role'] == 'pier'][0]
    L = IR['lane']
    fs = 6.1

    def note(x, y, txt, to, ha='left'):
        ax.text(x, y, txt, ha=ha, va='top', fontsize=fs, color=INK, linespacing=1.3, zorder=6)
        if to:
            ax.plot([to[0][0], to[1][0]], [to[0][1], to[1][1]], color=INK2, lw=0.5, zorder=2)

    note(0.15, 1.28, 'Pier 1 bearings (fixed): zeroLength\n'
         f"$K_v$ = {_sci(b[1]['Kv'])} kN/m, $K_h$ = {_sci(b[1]['Kh'])} kN/m",
         ((X(30) - 0.2, -0.18), (1.6, 0.66)))
    note(4.0, 1.28, f"Girder: elasticBeamColumn, {IR['mesh']} elements per span, consistent mass\n"
         f"A = {g['A']:.2f} m$^2$, I = {g['I']:.3f} m$^4$, $E_c$ = {g['E'] / 1e6:.1f} GPa, w = "
         f"{IR['self_weight']['w']:.1f} kN/m", ((X(52), 0.0), (5.0, 0.66)))
    note(12.4, 1.28, 'Pier 2, 3 bearings (sliding)\n'
         f"$K_v$ = {_sci(b[2]['Kv'])} kN/m, $K_h$ = 0", ((X(110) + 0.06, -0.12), (9.9, 0.66)), ha='right')
    note(0.15, -0.95, f"Abutment bearings (sliding)\n$K_v$ = {_sci(b[0]['Kv'])} kN/m, $K_h$ = 0",
         None)
    note(6.6, -1.14, f"Piers: two Ø1.6 m columns merged (MR-06)\nA = {p['A']:.2f} m$^2$, I = {p['I']:.3f} m$^4$, "
         f"$E_c$ = {p['E'] / 1e6:.1f} GPa, fixed at base", ((X(70), -1.44), (6.55, -1.44)))
    note(6.6, -1.9, f"Lane load (JTG D60-2015): {L['n_lanes']} lanes, ξ = {L['xi']:g}, $q_k$ = {L['qk']:g} kN/m,\n"
         f"$P_k$ = {L['Pk']['1']:g} / {L['Pk']['2']:g} kN; μ = {L['mu']:.3f} from $f_1$ = {r5['freqs'][0]:.2f} Hz",
         None)
    ax.set_xlim(0, 12.5)
    ax.set_ylim(-2.75, 1.4)
    return fig


def table(r5, r4):
    ref = json.load(open(REF, encoding='utf-8'))['reference_responses']
    rows = [('Abutment 0 reaction, self-weight (kN)', ref['self_weight_support_reactions_kN'][0],
             r5['reactions'][0], r4['reactions'][0]),
            ('Pier 2 reaction, self-weight (kN)', ref['self_weight_support_reactions_kN'][2], r5['reactions'][2],
             r4['reactions'][2]),
            ('Span 1 midspan moment, self-weight (kN m)', ref['self_weight_midspan_moments_kNm'][0],
             r5['M_sw'][r5['IR']['mid_nodes'][0] - 1], r4['M_sw'][r4['IR']['mid_nodes'][0] - 1]),
            ('Pier 2 moment, self-weight (kN m)', ref['self_weight_support_moments_kNm'][1],
             r5['M_sw'][r5['IR']['support_nodes'][2] - 1], r4['M_sw'][r4['IR']['support_nodes'][2] - 1]),
            ('f1 (Hz)', ref['first_vertical_frequency_Hz'], r5['freqs'][0], r4['freqs'][0]),
            ('Lane max positive moment (kN m)', ref['lane_max_positive_moment_kNm'],
             max(r5['env_pos'][n - 1] for n in r5['IR']['mid_nodes']),
             max(r4['env_pos'][n - 1] for n in r4['IR']['mid_nodes'])),
            ('Lane max negative moment (kN m)', ref['lane_max_negative_moment_kNm'],
             min(r5['env_neg'][n - 1] for n in r5['IR']['support_nodes'][1:-1]),
             min(r4['env_neg'][n - 1] for n in r4['IR']['support_nodes'][1:-1]))]
    return [(n, a, b, c, c / a - 1) for n, a, b, c in rows]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join(ROOT, 'paper_figures'))
    a = ap.parse_args()
    r5, r4 = analyse(C5), analyse(C4)
    style()
    for name, fig in (('fig_c06_model_en', fig_model(r5)), ('fig_c06_responses_en', fig_responses(r5, r4))):
        p = os.path.join(a.out, name)
        fig.savefig(p + '.png', dpi=300, facecolor='white', bbox_inches='tight', pad_inches=0.04)
        fig.savefig(p + '.pdf', facecolor='white', bbox_inches='tight', pad_inches=0.04)
        plt.close(fig)
        print(p)
    rows = table(r5, r4)
    for r in rows:
        print('%-45s %12.4f %12.4f %12.4f %+8.3f%%' % (r[0], r[1], r[2], r[3], 100 * r[4]))
    json.dump([list(r) for r in rows], open(os.path.join(a.out, 'c06_response_table.json'), 'w'), indent=1)
    ext = {'defl_min_mm': float(r5['defl_mm'].min()), 'x_defl_min': float(r5['x'][np.argmin(r5['defl_mm'])]),
           'sum_reactions': float(sum(r5['reactions'])), 'freqs': [m[0] for m in r5['modes']],
           'env_ratio': float(r4['env_pos'].max() / r5['env_pos'].max() - 1),
           'env_neg_ratio': float(r4['env_neg'].min() / r5['env_neg'].min() - 1)}
    print(ext)


if __name__ == '__main__':
    main()

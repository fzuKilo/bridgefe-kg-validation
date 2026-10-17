"""论文用典型桥梁示意图（按数据集中的实际题目绘制）。

Fig. 1  各档典型桥梁立面：A07、B08、C06、S03
Fig. 2  典型横截面（小箱梁、T 梁、现浇箱梁）与单梁有限元模型示意
输出：figures/fig_typical_bridges.png、figures/fig_sections_fe.png（600 dpi）
"""
import json
import os

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Polygon, Rectangle

import sections as sec

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'figures')

plt.rcParams.update({
    'font.family': 'Arial', 'font.size': 7.5, 'axes.linewidth': 0.6,
    'savefig.dpi': 600, 'hatch.linewidth': 0.5,
})
INK = '#1a1a1a'
CONCRETE = '#d9d9d9'
PIER = '#bfbfbf'
ACCENT = '#c0392b'     # 固定支座 / 弹簧
MUTED = '#6b6b6b'


def load(pid):
    with open(os.path.join(ROOT, 'problems', f'{pid}.json'), encoding='utf-8') as fh:
        return json.load(fh)['parameters']


# ---------------- 立面构件 ----------------
def bearing(ax, x, y, kind, s):
    """固定支座：实心三角；滑动支座：空心三角 + 滚轴。y 为梁底。"""
    tri = [(x, y), (x - 0.6 * s, y - s), (x + 0.6 * s, y - s)]
    if kind in ('elastomeric', 'spherical_fixed'):
        ax.add_patch(Polygon(tri, closed=True, fc=ACCENT, ec=ACCENT, lw=0.6, zorder=5))
        return y - s
    ax.add_patch(Polygon(tri, closed=True, fc='white', ec=INK, lw=0.6, zorder=5))
    r = 0.16 * s
    for dx in (-0.3 * s, 0.3 * s):
        ax.add_patch(Circle((x + dx, y - s - r), r, fc='white', ec=INK, lw=0.5, zorder=5))
    return y - s - 2 * r


def ground(ax, x0, x1, y, depth):
    ax.add_patch(Rectangle((x0, y - depth), x1 - x0, depth, fc='none', ec='none',
                           hatch='////', lw=0, zorder=1))
    ax.plot([x0, x1], [y, y], color=INK, lw=0.6, zorder=2)


def abutment(ax, x, y_top, side, w, h):
    """桥台：梯形块。side=-1 左台，+1 右台。"""
    xs = [x - side * 0.3 * w, x + side * 0.9 * w, x + side * 0.9 * w, x - side * 0.6 * w]
    ys = [y_top, y_top, y_top - h, y_top - h]
    ax.add_patch(Polygon(list(zip(xs, ys)), closed=True, fc=PIER, ec=INK, lw=0.6, zorder=3))
    return y_top - h


def span_dims(ax, xs, y, spans, fs=7):
    for x0, x1, L in zip(xs, xs[1:], spans):
        ax.annotate('', xy=(x0, y), xytext=(x1, y),
                    arrowprops=dict(arrowstyle='<->', lw=0.5, color=INK, shrinkA=0, shrinkB=0))
        ax.annotate(f'{L:g} m', xy=((x0 + x1) / 2, y), xytext=(0, 1.5), textcoords='offset points',
                    ha='center', va='bottom', fontsize=fs)



def elevation(ax, p, girder_h, ve, pier_scale=1.0, label_every=1, joint=False):
    """绘制立面，返回数据范围 (x0, x1, y0, y1)。"""
    spans = p['spans']
    xs = [0.0]
    for L in spans:
        xs.append(xs[-1] + L)
    total = xs[-1]
    hg = girder_h * ve
    s = 0.9 * ve                       # 支座符号尺寸
    # 主梁
    ax.add_patch(Rectangle((0, 0), total, hg, fc=CONCRETE, ec=INK, lw=0.7, zorder=4))
    if joint:                          # 先简支后连续：中墩处现浇连续段
        for x in xs[1:-1]:
            ax.add_patch(Rectangle((x - 0.9, 0), 1.8, hg, fc='white', ec=INK, lw=0.5,
                                   hatch='xxxx', zorder=5))
    lowest = 0.0
    for k, x in enumerate(xs):
        kind = p['bearings'][k]['kind']
        yb = bearing(ax, x, 0.0, kind, s)
        if k in (0, len(xs) - 1):
            yb2 = abutment(ax, x, yb, -1 if k == 0 else 1, 2.2 * ve, 3.2 * ve)
            ground(ax, x - 2.6 * ve if k == 0 else x - 0.7 * ve,
                   x + 0.7 * ve if k == 0 else x + 2.6 * ve, yb2, 0.8 * ve)
            lowest = min(lowest, yb2 - 0.8 * ve)
        else:
            if p['piers']:
                H = p['piers'][k - 1]['H'] * pier_scale
                bw = 1.2 * ve
                ax.add_patch(Rectangle((x - 1.1 * ve, yb - 0.5 * ve), 2.2 * ve, 0.5 * ve,
                                       fc=PIER, ec=INK, lw=0.6, zorder=3))
                ax.add_patch(Rectangle((x - bw / 2, yb - 0.5 * ve - H), bw, H,
                                       fc=PIER, ec=INK, lw=0.6, zorder=3))
                yf = yb - 0.5 * ve - H
                ground(ax, x - 2.2 * ve, x + 2.2 * ve, yf, 0.8 * ve)
                lowest = min(lowest, yf - 0.8 * ve)
                ax.text(x + bw / 2 + 0.5 * ve, yf + H / 2, f"H = {p['piers'][k - 1]['H']:g} m",
                        ha='left', va='center', fontsize=6.5, color=MUTED)
            else:
                bw = 1.0 * ve
                ax.add_patch(Rectangle((x - 1.1 * ve, yb - 0.5 * ve), 2.2 * ve, 0.5 * ve,
                                       fc=PIER, ec=INK, lw=0.6, zorder=3))
                ax.add_patch(Rectangle((x - bw / 2, yb - 0.5 * ve - 2.6 * ve), bw, 2.6 * ve,
                                       fc=PIER, ec=INK, lw=0.6, zorder=3))
                ground(ax, x - 1.8 * ve, x + 1.8 * ve, yb - 3.1 * ve, 0.8 * ve)
                lowest = min(lowest, yb - 3.9 * ve)
        if k % label_every == 0 or k == len(xs) - 1:
            name = f'A{k}' if k in (0, len(xs) - 1) else f'P{k}'
            ax.text(x, hg + 1.0 * ve, name, ha='center', va='bottom', fontsize=6.5, color=MUTED)
    span_dims(ax, xs, hg + 3.6 * ve, spans, fs=7 if len(spans) < 8 else 6.5)
    ax.axis('off')
    return -3.5 * ve, total + 3.5 * ve, lowest, hg + 3.6 * ve + 2.2 * ve


def legend_axes(ax):
    items = [('elastomeric', 'Longitudinally fixed bearing'),
             ('sliding', 'Longitudinally movable bearing'), ('joint', 'Cast-in-place continuity joint')]
    ax.set_xlim(0, 10)
    ax.set_ylim(-4.6, 0.6)
    for i, (kind, text) in enumerate(items):
        y = -1.3 * i
        if kind == 'joint':
            ax.add_patch(Rectangle((0.15, y - 0.75), 0.4, 0.75, fc='white', ec=INK, lw=0.5, hatch='xxxx'))
        else:
            bearing(ax, 0.35, y, kind, 0.55)
        ax.text(0.9, y - 0.35, text, va='center', fontsize=7)
    ax.text(0.15, -4.25, 'A: abutment   P: pier\nGirder depth and bearings not to scale;\npier heights to scale',
            va='center', fontsize=6.5, color=MUTED)
    ax.axis('off')


def fig_typical_bridges():
    A, B, C, S = load('A07'), load('B08'), load('C06'), load('S03')
    W = 7.0                         # 可用宽度 (in)
    fig = plt.figure(figsize=(7.2, 10))
    def fixed_txt(p):
        ks = [k for k, b in enumerate(p['bearings']) if b['kind'] in ('elastomeric', 'spherical_fixed')]
        return ' and '.join(f'P{k}' for k in ks)

    def spans_txt(p):
        L = p['spans']
        if len(set(L)) == 1:
            return f"{len(L)} × {L[0]:g} m"
        out, i = [], 0
        while i < len(L):
            j = i
            while j + 1 < len(L) and L[j + 1] == L[i]:
                j += 1
            out.append(f"{j - i + 1} × {L[i]:g}" if j > i else f"{L[i]:g}")
            i = j + 1
        return ' + '.join(out) + ' m'

    gname = {'small_box': 'small box girders', 't_girder': 'T girders'}
    num = {3: 'three', 4: 'four', 5: 'five', 6: 'six', 7: 'seven'}
    specs = [
        (A, sec.girder_section(A['girder']['type'], A['girder']['span_class'])['h'], 2.2,
         f"(a) Tier A: single-span simply supported girder\n({A['id']}; {A['spans'][0]:g} m; "
         f"{num[A['girder']['n']]} precast {gname[A['girder']['type']]})", dict(joint=False)),
        (B, sec.girder_section(B['girder']['type'], B['girder']['span_class'])['h'], 2.2,
         f"(b) Tier B: precast girders made continuous ({B['id']}; {spans_txt(B)}; "
         f"{gname[B['girder']['type']]}; fixed bearings at {fixed_txt(B)})", dict(joint=True)),
        (C, C['girder']['box']['h'], 2.0,
         f"(c) Tier C: cast-in-place continuous box girder on piers of unequal height "
         f"({C['id']}; {' + '.join(f'{L:g}' for L in C['spans'])} m)", dict(joint=False)),
        (S, 1.4, 2.4,
         f"(d) Scalability unit: ten spans made continuous ({S['id']}; {spans_txt(S)}; "
         f"fixed bearings at {fixed_txt(S)})", dict(joint=True)),
    ]
    axes, ext = [], []
    for p, h, ve, title, kw in specs:
        ax = fig.add_axes([0, 0, 1, 1])
        ext.append(elevation(ax, p, h, ve, **kw))
        axes.append(ax)
    widths = [e[1] - e[0] for e in ext]
    s_main = W / max(widths[1], widths[2])      # (a)(b)(c) 同一比例尺
    s_long = W / widths[3]
    scales = [s_main, s_main, s_main, s_long]
    title_h, gap = 0.36, 0.12
    boxes, y = [], 0.0                          # 自顶向下累积 (in)
    for e, sc in zip(ext, scales):
        y += title_h
        h_in = (e[3] - e[2]) * sc
        boxes.append((y, (e[1] - e[0]) * sc, h_in))
        y += h_in + gap
    H = y
    fig.set_size_inches(7.2, H)
    left = 0.1
    for ax, e, (top, w_in, h_in), (_, _, _, title, _) in zip(axes, ext, boxes, specs):
        ax.set_xlim(e[0], e[1])
        ax.set_ylim(e[2], e[3])
        ax.set_position([left / 7.2, 1 - (top + h_in) / H, w_in / 7.2, h_in / H])
        fig.text(left / 7.2, 1 - (top - title_h + 0.04) / H, title, ha='left', va='top', fontsize=8)
    # 图例放在 (a) 右侧
    top, w_in, h_in = boxes[0]
    lx = left + w_in + 0.5
    lax = fig.add_axes([lx / 7.2, 1 - (top + h_in) / H, (7.1 - lx) / 7.2, h_in / H])
    legend_axes(lax)
    fig.savefig(os.path.join(OUT, 'fig_typical_bridges.png'), pad_inches=0.03)
    plt.close(fig)


# ---------------- 横截面 ----------------
def draw_section(ax, outer, holes, dx=0.0, fc=CONCRETE):
    ax.add_patch(Polygon([(x + dx, y) for x, y in outer], closed=True, fc=fc, ec=INK, lw=0.6))
    for h in holes:
        ax.add_patch(Polygon([(x + dx, y) for x, y in h], closed=True, fc='white', ec=INK, lw=0.5))


def hdim(ax, x0, x1, y, text, above=True):
    ax.annotate('', xy=(x0, y), xytext=(x1, y),
                arrowprops=dict(arrowstyle='<->', lw=0.45, color=INK, shrinkA=0, shrinkB=0))
    ax.text((x0 + x1) / 2, y + (0.08 if above else -0.08), text, ha='center',
            va='bottom' if above else 'top', fontsize=6.5)


def vdim(ax, x, y0, y1, text):
    ax.annotate('', xy=(x, y0), xytext=(x, y1),
                arrowprops=dict(arrowstyle='<->', lw=0.45, color=INK, shrinkA=0, shrinkB=0))
    ax.text(x + 0.12, (y0 + y1) / 2, text, ha='left', va='center', fontsize=6.5)


def precast_row(ax, gtype, cls, n, deck_w, title):
    outer, holes = (sec.small_box_geometry if gtype == 'small_box' else sec.t_girder_geometry)(cls)
    top_w = 2.40 if gtype == 'small_box' else 1.80
    spacing = (deck_w - top_w) / (n - 1) if n > 1 else 0
    # 以桥面全宽均布 n 片梁，边梁翼缘外缘与桥面边缘对齐
    xs = [-deck_w / 2 + top_w / 2 + i * spacing for i in range(n)]
    h = max(p[1] for p in outer)
    for i, x in enumerate(xs):
        draw_section(ax, outer, holes, dx=x)
        if i < n - 1:
            gap0, gap1 = x + top_w / 2, xs[i + 1] - top_w / 2
            ax.add_patch(Rectangle((gap0, h - 0.18), gap1 - gap0, 0.18, fc='white', ec=MUTED,
                                   lw=0.4, ls=(0, (2, 1.5))))
    props = sec.section_props(outer, holes)
    hdim(ax, -deck_w / 2, deck_w / 2, h + 0.35, f'{deck_w:g} m')
    vdim(ax, deck_w / 2 + 0.3, 0, h, f'{h:g} m')
    ax.text(-deck_w / 2, -0.35,
            f'{n} girders; spine beam: A = {n} × {props["A"]:.3f} m$^2$, I = {n} × {props["I"]:.3f} m$^4$',
            ha='left', va='top', fontsize=6.5, color=MUTED)
    ax.text(deck_w / 2, -0.35, 'wet joints (dashed) neglected', ha='right', va='top', fontsize=6.5,
            color=MUTED)
    ax.set_title(title, loc='left', fontsize=8, pad=2)
    ax.set_xlim(-deck_w / 2 - 0.3, deck_w / 2 + 1.6)
    ax.set_ylim(-1.0, h + 0.9)
    ax.set_aspect('equal')
    ax.set_anchor('NW')
    ax.axis('off')


def box_row(ax, box, title):
    outer, holes = sec.cast_box_geometry(**box)
    draw_section(ax, outer, holes)
    h, B, Bb = box['h'], box['B_top'], box['B_bot']
    hdim(ax, -B / 2, B / 2, h + 0.35, f'{B:g} m')
    hdim(ax, -Bb / 2, Bb / 2, -0.3, f'{Bb:g} m', above=False)
    vdim(ax, B / 2 + 0.3, 0, h, f'{h:g} m')
    props = sec.section_props(outer, holes)
    ax.text(-B / 2, -0.62, f'A = {props["A"]:.3f} m$^2$, I = {props["I"]:.3f} m$^4$', ha='left', va='top',
            fontsize=6.5, color=MUTED)
    ax.set_title(title, loc='left', fontsize=8, pad=2)
    ax.set_xlim(-B / 2 - 0.3, B / 2 + 1.6)
    ax.set_ylim(-1.0, h + 0.9)
    ax.set_aspect('equal')
    ax.set_anchor('NW')
    ax.axis('off')


# ---------------- 有限元模型示意 ----------------
def spring(ax, x0, y0, x1, y1, n=5, amp=0.18, color=ACCENT):
    import numpy as np
    t = np.linspace(0, 1, 2 * n + 3)
    xs = x0 + (x1 - x0) * t
    ys = y0 + (y1 - y0) * t
    dx, dy = y1 - y0, -(x1 - x0)
    L = (dx**2 + dy**2) ** 0.5
    dx, dy = dx / L, dy / L
    off = [0] + [amp * (1 if i % 2 else -1) for i in range(1, len(t) - 1)] + [0]
    off[1] = off[-2] = 0
    ax.plot(xs + dx * np.array(off), ys + dy * np.array(off), color=color, lw=0.7)


def fe_panel(ax):
    Ls = [8.0, 10.0, 8.0]
    xs = [0, 8, 18, 26]
    y = 0.0
    ax.plot([0, 26], [y, y], color=INK, lw=1.4, zorder=3)
    import numpy as np
    for x0, L in zip(xs, Ls):
        for t in np.linspace(0, 1, 9):
            ax.add_patch(Circle((x0 + L * t, y), 0.13, fc='white', ec=INK, lw=0.6, zorder=4))
    kinds = ['sliding', 'elastomeric', 'sliding', 'sliding']
    for k, x in enumerate(xs):
        ax.add_patch(Circle((x, y), 0.17, fc=INK, ec=INK, zorder=5))
        # 竖向弹簧 Kv
        spring(ax, x, y - 0.2, x, y - 1.6)
        ax.add_patch(Circle((x, y - 1.75), 0.15, fc=INK, ec=INK, zorder=5))
        # 纵向弹簧或自由
        if kinds[k] == 'elastomeric':
            # 纵向弹簧 Kh：主梁节点刚臂 —— 弹簧 —— 墩顶节点刚臂
            yk = y - 0.75
            ax.plot([x - 0.35, x - 0.35], [y, yk], color=INK, lw=0.9)
            ax.plot([x - 1.8, x - 1.8, x], [yk, y - 1.75, y - 1.75], color=INK, lw=0.9)
            spring(ax, x - 1.8, yk, x - 0.35, yk, n=4, amp=0.13)
        if k in (0, 3):
            ground(ax, x - 0.8, x + 0.8, y - 1.9, 0.35)
        else:
            H = 3.6 if k == 1 else 2.4
            ax.plot([x, x], [y - 1.75, y - 1.75 - H], color=INK, lw=1.1)
            for t in np.linspace(0, 1, 5)[1:-1]:
                ax.add_patch(Circle((x, y - 1.75 - H * t), 0.1, fc='white', ec=INK, lw=0.5, zorder=4))
            ground(ax, x - 0.8, x + 0.8, y - 1.75 - H, 0.35)
    # 标注
    ax.annotate('Girder: elasticBeamColumn\n(20 elements per span, consistent mass)', xy=(12.6, 0.05),
                xytext=(10.0, 1.3), fontsize=6.5, ha='left', va='bottom',
                arrowprops=dict(arrowstyle='-', lw=0.4, color=MUTED))
    ax.annotate('Bearing: zeroLength\nvertical spring $K_v$', xy=(26.1, -0.9), xytext=(27.4, -0.3),
                fontsize=6.5, ha='left', va='center', arrowprops=dict(arrowstyle='-', lw=0.4, color=MUTED))
    ax.annotate('Fixed bearing: longitudinal\nspring $K_h = G_e A_e / t_e$', xy=(7.1, -0.62), xytext=(-1.2, 1.3),
                fontsize=6.5, ha='left', va='bottom', arrowprops=dict(arrowstyle='-', lw=0.4, color=MUTED))
    ax.annotate('Sliding bearing:\nlongitudinal DOF free', xy=(18.1, -0.9), xytext=(19.6, -2.6),
                fontsize=6.5, ha='left', va='center', arrowprops=dict(arrowstyle='-', lw=0.4, color=MUTED))
    ax.annotate('Pier: elasticBeamColumn,\nfixed at base (Tier C)', xy=(8.05, -3.6), xytext=(9.4, -4.3),
                fontsize=6.5, ha='left', va='center', arrowprops=dict(arrowstyle='-', lw=0.4, color=MUTED))
    ax.text(26, -2.75, 'Rigid support\n(Tiers A, B)', ha='center', va='top', fontsize=6.5, color=MUTED)
    ax.set_title('(d) Spine-beam FE idealization used for the reference models', loc='left', fontsize=8, pad=2)
    ax.set_xlim(-1.5, 32.5)
    ax.set_ylim(-6.0, 2.4)
    ax.set_aspect('equal')
    ax.set_anchor('NW')
    ax.axis('off')


def fig_sections_fe():
    C = json.load(open(os.path.join(ROOT, 'problems', 'C06.json'), encoding='utf-8'))['parameters']
    fig = plt.figure(figsize=(7.2, 7.0))
    ax1 = fig.add_axes([0.03, 0.80, 0.94, 0.17])
    precast_row(ax1, 'small_box', 30, 4, 12.5, '(a) Precast small box girders, 30 m span class (e.g., S01)')
    ax2 = fig.add_axes([0.03, 0.59, 0.94, 0.19])
    precast_row(ax2, 't_girder', 40, 6, 16.0, '(b) Precast T girders, 40 m span class (e.g., B06)')
    ax3 = fig.add_axes([0.03, 0.41, 0.94, 0.16])
    box_row(ax3, C['girder']['box'], '(c) Cast-in-place single-cell box girder (C06)')
    ax4 = fig.add_axes([0.03, 0.00, 0.94, 0.38])
    fe_panel(ax4)
    fig.savefig(os.path.join(OUT, 'fig_sections_fe.png'), bbox_inches='tight', pad_inches=0.05)
    plt.close(fig)


if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True)
    fig_typical_bridges()
    fig_sections_fe()
    print('saved to', OUT)

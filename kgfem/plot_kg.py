"""知识图谱可视化：python -m kgfem.plot_kg [--lang en|zh] [--kg 运行导出的 *_kg.json] [--out 目录]

图 KG-1 图谱模式（节点类型与关系类型，取自 build_knowledge_graph 与一次运行导出的实例层、决策层）；
图 KG-2 一座桥（默认贯穿算例 C06，DeepSeek-V4-Flash 的 C5 运行）的图谱：(a) 实例层；(b) 决策层及其溯源子图（决策—依据—槽位）。
画法沿用知识图谱文献的有向带标签图：节点按层着色，边标注关系类型；节点、边与数值均取自图谱，不手工添加。
"""
import argparse
import collections
import json
import os

import matplotlib
matplotlib.use('Agg')
matplotlib.rcParams['pdf.fonttype'] = 42   # 嵌入 TrueType 字体（期刊要求）
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.path import Path
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Patch

from .kg.knowledge import build_knowledge_graph
from .plot_ablation import INK, INK2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_KG = os.path.join(ROOT, 'runs_ablation_single', 'C5', 'C06_r3', 'C06_kg.json')
SCHEMA_KG = os.path.join(ROOT, 'runs_luna', 'C5', 'C05_r1', 'C05_kg.json')   # 含决策→前置决策的 BASED_ON 边

LAYER_STYLE = {                                  # 填充, 描边
    'rule': ('#dbe9fb', '#2a78d6'),
    'code': ('#fbe8d6', '#d9822b'),
    'constraint': ('#eeedea', '#8a8984'),
    'instance': ('#dcefe2', '#3a8f57'),
    'decision': ('#ebe3f6', '#8b5cc4'),
}
EDGE = '#6b6a66'

T = {
    'en': {
        'layers': {'rule': 'Modeling-rule layer', 'code': 'Design-code layer', 'constraint': 'Constraint layer',
                   'instance': 'Instance layer', 'decision': 'Decision layer'},
        'a': '(a) Instance layer of problem {pid}', 'b': '(b) Decision layer and provenance (12 of the {nd} decisions of {pid})',
        'cols': ['Instance component', 'Accepted decision', 'Rule / clause (evidence)', 'Decision slot'],
        'bridge': 'Bridge {pid}\ncast-in-place continuous', 'deck': 'Deck\n{W:g} m, {n} lanes, Class {c}',
        'girder': 'GirderSystem\n{t}, {conc}', 'span': 'Span {j}\nL = {L:g} m',
        'sl': 'SupportLine {k}\n{kind}', 'abutment': 'abutment', 'pier': 'pier',
        'bear': 'BearingGroup {k}\n{t}, {m} × {a:g}×{b:g}', 'fixed': 'fixed', 'slide': 'sliding',
        'piern': 'Pier {k}\nH = {H:g} m, {nc} × D{D:g}',
        'titles': {
            'MR-00': 'input priority', 'MR-02': 'girder section', 'MR-03': 'laminated bearing',
            'MR-04': 'bearing count', 'MR-07': 'dead load and mass', 'JTGD60-4.2.1': 'unit weight',
            'JTG3362-3.1.5': 'concrete modulus', 'JTG3362-8.7-S': 'shape factor S',
            'JTG3362-8.7-Kv': 'vertical stiffness', 'JTG3362-8.7-Kh': 'shear stiffness',
            'JTGD60-4.3.1-Pk': 'lane load Pk', 'JTGD60-4.3.2': 'impact factor μ(f1)', 'MR-06': 'pier'},
        'leg_rel': 'Relation',
        'omit': '{n} HAS edges from Bridge to spans and support lines not drawn',
    },
    'zh': {
        'layers': {'rule': '建模规则层', 'code': '规范层', 'constraint': '约束层',
                   'instance': '实例层', 'decision': '决策层'},
        'a': '(a) 算例 {pid} 的实例层', 'b': '(b) 决策层及其溯源（{pid} 的 {nd} 项决策中的 12 项）',
        'cols': ['实例构件', '已接受的决策', '依据（规则 / 条文）', '决策槽位'],
        'bridge': '桥梁 {pid}\n现浇连续', 'deck': '桥面\n行车道 {W:g} m，{n} 车道，公路-{c} 级',
        'girder': '主梁体系\n{t}，{conc}', 'span': '第 {j} 跨\nL = {L:g} m',
        'sl': '支承线 {k}\n{kind}', 'abutment': '桥台', 'pier': '桥墩',
        'bear': '支座组 {k}\n{t}，{m} × {a:g}×{b:g}', 'fixed': '固定', 'slide': '滑动',
        'piern': '桥墩 {k}\nH = {H:g} m，{nc} × D{D:g}',
        'titles': {
            'MR-00': '输入优先', 'MR-02': '主梁截面特性', 'MR-03': '板式橡胶支座模拟',
            'MR-04': '支座数量与并联', 'MR-07': '恒载与质量', 'JTGD60-4.2.1': '材料重度',
            'JTG3362-3.1.5': '混凝土弹性模量', 'JTG3362-8.7-S': '形状系数 S',
            'JTG3362-8.7-Kv': '竖向刚度', 'JTG3362-8.7-Kh': '剪切刚度',
            'JTGD60-4.3.1-Pk': '车道荷载 Pk', 'JTGD60-4.3.2': '冲击系数 μ(f1)', 'MR-06': '桥墩模拟'},
        'leg_rel': '关系',
        'omit': '桥梁到各跨与支承线的 {n} 条 HAS 边未画出',
    },
}


# ---------------------------------------------------------------- 绘图基元
class Canvas:
    def __init__(self, ax):
        self.ax = ax
        self.box = {}

    def node(self, key, x, y, w, h, layer, text, fs=6.5, bold_first=True):
        fill, line = LAYER_STYLE[layer]
        self.ax.add_patch(FancyBboxPatch((x - w / 2, y - h / 2), w, h, boxstyle='round,pad=0,rounding_size=0.12',
                                         fc=fill, ec=line, lw=0.9, zorder=3))
        lines = text.split('\n')
        if bold_first and len(lines) > 1:
            dy = 0.5 * 0.17 * fs / 6.5
            self.ax.text(x, y + dy, lines[0], ha='center', va='center', fontsize=fs, color=INK,
                         fontweight='bold', zorder=4)
            self.ax.text(x, y - dy, '\n'.join(lines[1:]), ha='center', va='center', fontsize=fs - 0.6,
                         color=INK, zorder=4, linespacing=1.15)
        else:
            self.ax.text(x, y, text, ha='center', va='center', fontsize=fs, color=INK, zorder=4,
                         fontweight='bold' if bold_first else None, linespacing=1.15)
        self.box[key] = (x, y, w, h)

    def _clip(self, key, toward):
        """从方框中心指向 toward 的射线与方框边界的交点。"""
        x, y, w, h = self.box[key]
        dx, dy = toward[0] - x, toward[1] - y
        if dx == 0 and dy == 0:
            return x, y
        s = min((w / 2) / abs(dx) if dx else 1e9, (h / 2) / abs(dy) if dy else 1e9)
        return x + dx * s, y + dy * s

    def port(self, key, side, x=None):
        bx, by, w, h = self.box[key]
        return {'l': (bx - w / 2, by), 'r': (bx + w / 2, by),
                't': (bx if x is None else x, by + h / 2), 'b': (bx if x is None else x, by - h / 2)}[side]

    def edge(self, a, b, label=None, rad=0.0, color=EDGE, ls='-', lw=0.8, fs=5.6, lpos=0.5, loff=(0, 0),
             pa=None, pb=None):
        pa = pa or self._clip(a, self.box[b][:2])
        pb = pb or self._clip(b, self.box[a][:2])
        self.ax.add_patch(FancyArrowPatch(pa, pb, arrowstyle='-|>', mutation_scale=6.5, lw=lw, color=color,
                                          linestyle=ls, connectionstyle=f'arc3,rad={rad}', zorder=2,
                                          shrinkA=0.5, shrinkB=0.5))
        if label:
            mx, my = pa[0] + (pb[0] - pa[0]) * lpos, pa[1] + (pb[1] - pa[1]) * lpos
            if rad:                       # arc3 的中点偏移：垂直于弦、长度 rad·|弦|
                dx, dy = pb[0] - pa[0], pb[1] - pa[1]
                mx, my = mx + rad * dy * 0.5, my - rad * dx * 0.5
            self.ax.text(mx + loff[0], my + loff[1], label, ha='center', va='center', fontsize=fs, color=INK2,
                         zorder=5, bbox=dict(fc='white', ec='none', pad=0.6))

    def region(self, x0, y0, x1, y1, layer, label, lx=None, ha='left'):
        _, line = LAYER_STYLE[layer]
        self.ax.add_patch(FancyBboxPatch((x0, y0), x1 - x0, y1 - y0, boxstyle='round,pad=0,rounding_size=0.18',
                                         fc='none', ec=line, lw=0.8, ls=(0, (4, 2.5)), zorder=1))
        self.ax.text(x0 + 0.15 if lx is None else lx, y1 - 0.12, label, ha=ha, va='top', fontsize=7,
                     color=line, fontweight='bold', zorder=5)


def load_run(path):
    with open(path, encoding='utf-8') as fh:
        d = json.load(fh)
    d['pid'] = os.path.basename(path).split('_')[0]
    for n in d['nodes']:                      # 旧版导出中主梁节点的 type 被主梁类型覆盖（已在 instance.py 修正）
        if n['id'] == 'inst:girder':
            n['girder_type'] = n.get('girder_type', n['type'])
            n['type'] = 'GirderSystem'
    return d


# ---------------------------------------------------------------- 图 KG-1：模式
def fig_schema(run, L):
    kg = build_knowledge_graph()
    static = collections.Counter(v['type'] for v in kg.nodes.values())
    ntype = {n['id']: n['type'] for n in run['nodes']}
    ntype.update({k: v['type'] for k, v in kg.nodes.items()})
    edges = collections.Counter((ntype[s], r, ntype[t]) for s, r, t in kg.edges)
    edges.update((ntype[s], r, ntype[t]) for s, r, t in run['edges'])

    fig, ax = plt.subplots(figsize=(7.2, 4.5))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 7.5)
    ax.set_aspect('equal')
    ax.axis('off')
    c = Canvas(ax)

    pos = {  # 类型: (x, y, 层)
        'Bridge': (1.1, 6.3, 'instance'), 'Deck': (3.7, 6.3, 'instance'),
        'GirderSystem': (3.7, 4.9, 'instance'), 'Span': (2.2, 3.5, 'instance'),
        'SupportLine': (1.1, 2.1, 'instance'), 'BearingGroup': (3.7, 2.1, 'instance'),
        'Pier': (3.7, 0.75, 'instance'),
        'Decision': (6.05, 3.6, 'decision'), 'Constraint': (6.05, 0.95, 'constraint'),
        'ModelingRule': (8.5, 6.0, 'rule'), 'DecisionTemplate': (10.75, 6.5, 'rule'),
        'DecisionSlot': (10.75, 4.4, 'rule'), 'ComponentConcept': (8.6, 3.55, 'rule'),
        'CodeClause': (8.6, 1.2, 'code'),
    }
    c.region(0.2, 0.2, 4.6, 7.3, 'instance', L['layers']['instance'])
    c.region(4.95, 2.45, 7.4, 5.45, 'decision', L['layers']['decision'])
    c.region(4.95, 0.2, 7.4, 1.95, 'constraint', L['layers']['constraint'])
    c.region(7.6, 2.85, 11.85, 7.3, 'rule', L['layers']['rule'])
    c.region(7.6, 0.2, 11.85, 2.45, 'code', L['layers']['code'], lx=11.7, ha='right')
    for t, (x, y, layer) in pos.items():
        n = static.get(t)
        c.node(t, x, y, max(1.6, 0.112 * len(t) + 0.2), 0.56, layer, f'{t}\nn = {n}' if n else t, fs=6.4, bold_first=True)

    seen = set()
    style = {  # (源, 关系, 目标): (弧度, 标签位置, 标签偏移)
        ('ModelingRule', 'GOVERNS', 'DecisionSlot'): (-0.18, 0.5, (0, 0)),
        ('ModelingRule', 'SUPPORTS', 'DecisionSlot'): (0.18, 0.5, (0, 0)),
        ('CodeClause', 'GOVERNS', 'DecisionSlot'): (-0.2, 0.55, (0, 0)),
        ('CodeClause', 'SUPPORTS', 'DecisionSlot'): (0.2, 0.55, (0, 0)),
        ('CodeClause', 'ACTS_ON', 'ComponentConcept'): (0.0, 0.55, (0, 0)),
        ('BearingGroup', 'SUPPORTS', 'GirderSystem'): (0.0, 0.2, (0, 0)),
        ('Decision', 'BASED_ON', 'ModelingRule'): (0.0, 0.5, (0, 0)),
        ('Decision', 'BASED_ON', 'CodeClause'): (0.0, 0.55, (0, 0)),
        ('Span', 'BETWEEN', 'SupportLine'): (0.0, 0.5, (0, 0)),
        ('Bridge', 'HAS', 'SupportLine'): (0.0, 0.5, (0, 0)),
    }
    for (s, r, t) in sorted(edges):
        if s == t:                                # 决策之间的 BASED_ON（前置决策）画成自环
            x, y = pos[s][:2]
            loop = Path([(x + 0.8, y + 0.14), (x + 1.45, y + 0.5), (x + 1.45, y - 0.5), (x + 0.8, y - 0.14)],
                        [Path.MOVETO, Path.CURVE4, Path.CURVE4, Path.CURVE4])
            ax.add_patch(FancyArrowPatch(path=loop, arrowstyle='-|>', mutation_scale=6.5, lw=0.8, color=EDGE,
                                         zorder=2))
            ax.text(x + 1.05, y - 0.5, r, ha='center', va='center', fontsize=5.6, color=INK2, zorder=5,
                    bbox=dict(fc='white', ec='none', pad=0.6))
            continue
        rad, lp, lo = style.get((s, r, t), (0.0, 0.5, (0, 0)))
        if r == 'CONCERNS':                        # 扇形边只在一条上标注
            lab = r if t == 'GirderSystem' else None
            lp = 0.45
        elif r == 'HAS':
            lab = r if t in ('Deck', 'SupportLine') else None
        else:
            lab = r
        c.edge(s, t, lab, rad=rad, lpos=lp, loff=lo)
        seen.add((s, r, t))
    return fig


# ---------------------------------------------------------------- 图 KG-2：一座桥的图谱
DEC_ROWS = ['girder.A', 'girder.gamma', 'girder.w', 'girder.Ec',
            'support.1.bearing', 'support.1.dofs', 'support.1.S', 'support.1.Kv', 'support.1.Kh',
            'pier.1.I', 'lane.Pk.2', 'lane.mu']


def _fmt(v, unit):
    if isinstance(v, dict):
        if 'count' in v:
            return f"{v['type']}, n = {v['count']}"
        return ', '.join(f'{k[:4]}.: {x}' for k, x in v.items())
    if isinstance(v, float):
        if abs(v) >= 1e5:
            m, e = f'{v:.2e}'.split('e')
            s = f'{m}×10$^{{{int(e)}}}$'
        elif abs(v) >= 100:
            s = f'{v:,.0f}'.replace(',', ' ')
        else:
            s = f'{v:.3g}'
    else:
        s = str(v)
    unit = {'m^2': 'm$^2$', 'm^4': 'm$^4$', 'kN/m^3': 'kN/m$^3$', '-': ''}.get(unit, unit)
    return f'{s} {unit}'.strip()


def fig_instance(run, L):
    N = {n['id']: n for n in run['nodes']}
    E = [tuple(e) for e in run['edges']]
    kg = build_knowledge_graph()

    pid = run.get('pid', '')
    nd = sum(1 for n in run['nodes'] if n['layer'] == 'decision')
    fig = plt.figure(figsize=(7.2, 8.9))
    axa = fig.add_axes([0.0, 0.565, 1.0, 0.435])
    axb = fig.add_axes([0.0, 0.0, 1.0, 0.56])
    for ax, (y0, y1) in ((axa, (-0.45, 6.15)), (axb, (0, 7.9))):
        ax.set_xlim(0, 12)
        ax.set_ylim(y0, y1)
        ax.set_aspect('equal')
        ax.axis('off')

    # ---------------- (a) 实例层：按桥梁立面排布（主梁—支座—跨—支承线—桥墩）
    c = Canvas(axa)
    axa.text(0.1, 6.1, L['a'].format(pid=pid), ha='left', va='top', fontsize=8, color=INK, fontweight='bold')
    sls = sorted((n for n in run['nodes'] if n['type'] == 'SupportLine'), key=lambda n: n['index'])
    ns = len(sls)
    xs = [0.95 + k * (10.1 / (ns - 1)) for k in range(ns)]
    w, h = 1.55, 0.54
    yb, yg, yz, yspan, ys, yp = 5.3, 4.4, 3.35, 2.3, 1.3, 0.25
    g = N['inst:girder']
    n_gir = g.get('count_per_span') or 1
    c.node('inst:bridge', 6.0, yb, 2.3, h, 'instance', L['bridge'].format(pid=pid))
    dk = N['inst:deck']
    c.node('inst:deck', 10.1, yb, 2.9, h, 'instance',
           L['deck'].format(W=dk['carriageway_width_m'], n=dk['design_lanes'], c=dk['load_class']))
    gname = {'en': {'cast_box': 'cast-in-place box', 'small_box': 'precast small box', 't_girder': 'precast T'},
             'zh': {'cast_box': '现浇箱梁', 'small_box': '预制小箱梁', 't_girder': '预制 T 梁'}}[
        'en' if L is T['en'] else 'zh']
    gtxt = L['girder'].format(t=gname.get(g.get('girder_type'), g.get('girder_type', '')), conc=g.get('concrete', ''))
    c.node('inst:girder', 6.0, yg, 11.5, 0.44, 'instance', gtxt.replace('\n', ' — ' if L is T['en'] else '，'),
           bold_first=False)
    for n in run['nodes']:
        if n['type'] == 'SupportLine':
            k = n['index']
            c.node(n['id'], xs[k], ys, w, h, 'instance', L['sl'].format(k=k, kind=L[n['kind']]))
        elif n['type'] == 'BearingGroup':
            k = n['support']
            m = n.get('per_line') or (n.get('per_girder_end') or 0) * n_gir
            c.node(n['id'], xs[k], yz, 1.85, h, 'instance',
                   L['bear'].format(k=k, t=L['slide'] if n['sliding'] else L['fixed'], m=m, a=n['a_mm'], b=n['b_mm']),
                   fs=5.9)
        elif n['type'] == 'Pier':
            k = n['support']
            c.node(n['id'], xs[k], yp, 1.75, h, 'instance',
                   L['piern'].format(k=k, H=n['height_m'], D=n['diameter_m'], nc=n['n_columns']), fs=6.1)
        elif n['type'] == 'Span':
            j = n['index']
            c.node(n['id'], (xs[j - 1] + xs[j]) / 2, yspan, 1.3, h, 'instance', L['span'].format(j=j, L=n['length']))
    omitted = 0
    for s_, r, t in E:
        if s_ not in c.box or t not in c.box:
            continue
        if r == 'HAS':
            if t == 'inst:deck':
                c.edge(s_, t, r, pa=c.port(s_, 'r'), pb=c.port(t, 'l'))
            elif t == 'inst:girder':
                c.edge(s_, t, r, pa=c.port(s_, 'b'), pb=c.port(t, 't', x=6.0))
            else:
                omitted += 1
        elif r == 'SPANS':                     # 主梁画成通长条，SPANS 从其下缘竖直指向各跨
            x = c.box[t][0]
            c.edge(s_, t, r if t == 'inst:span:1' else None, pa=c.port(s_, 'b', x=x), pb=c.port(t, 't'), lpos=0.3)
        elif r == 'SUPPORTS':
            x = c.box[s_][0]
            c.edge(s_, t, r if s_ == 'inst:bearing:0' else None, pa=c.port(s_, 't'), pb=c.port(t, 'b', x=x))
        elif r == 'AT':
            c.edge(s_, t, r if s_ == 'inst:bearing:0' else None, pa=c.port(s_, 'b'), pb=c.port(t, 't'), lpos=0.3)
        elif r == 'UNDER':
            c.edge(s_, t, r if s_ == 'inst:pier:1' else None, pa=c.port(s_, 't'), pb=c.port(t, 'b'))
        elif r == 'BETWEEN':
            left = c.box[t][0] < c.box[s_][0]
            c.edge(s_, t, r if s_ == 'inst:span:1' and not left else None, lpos=0.55,
                   pa=c.port(s_, 'b', x=c.box[s_][0] + (-0.3 if left else 0.3)), pb=c.port(t, 't'))
    if omitted:
        axa.text(0.15, -0.4, L['omit'].format(n=omitted), ha='left', va='bottom', fontsize=5.8, color=INK2,
                 style='italic')

    # ---------------- (b) 决策层与溯源
    c = Canvas(axb)
    axb.text(0.1, 7.85, L['b'].format(pid=pid, nd=nd), ha='left', va='top', fontsize=8, color=INK, fontweight='bold')
    X = [0.95, 3.95, 7.15, 10.6]
    W = [1.7, 2.4, 2.5, 2.0]
    for x, t in zip(X, L['cols']):
        axb.text(x, 7.42, t, ha='center', va='center', fontsize=6.8, color=INK2)
    top, dy, bh = 6.95, 0.555, 0.44
    y_of = {s: top - i * dy for i, s in enumerate(DEC_ROWS)}
    from .kg.validator import slot_pattern
    evid = {}
    for s in DEC_ROWS:
        did = f'dec:{s}'
        n = N[did]
        c.node(did, X[1], y_of[s], W[1], bh, 'decision', f"{s}\n{_fmt(n['value'], n['unit'])}", fs=6.2)
        ev = [t for a, r, t in E if a == did and r == 'BASED_ON' and not t.startswith('dec:')]
        evid[s] = ev[0]
    for s, e in evid.items():
        if e not in c.box:
            node = kg.get(e)
            c.node(e, X[2], y_of[s], W[2], bh, node['layer'], f"{e}\n{L['titles'].get(e, '')}", fs=6.2)
        p = slot_pattern(s)
        sid = f'slot:{p}'
        if sid not in c.box:
            c.node(sid, X[3], y_of[s], W[3], bh, 'rule', p, fs=6.2, bold_first=False)
    # 实例构件放在其决策的中间高度
    groups = collections.defaultdict(list)
    for s in DEC_ROWS:
        tgt = [t for a, r, t in E if a == f'dec:{s}' and r == 'CONCERNS'][0]
        groups[tgt].append(y_of[s])
    names = {'inst:girder': L['girder'].split('\n')[0], 'inst:bearing:1': L['bear'].split('\n')[0].format(k=1),
             'inst:pier:1': L['piern'].split('\n')[0].format(k=1), 'inst:span:2': L['span'].split('\n')[0].format(j=2),
             'inst:deck': L['deck'].split('\n')[0]}
    has_prereq = any(r == 'BASED_ON' and t.startswith('dec:') and s_[4:] in y_of and t[4:] in y_of
                     for s_, r, t in E)
    for tgt, ys in groups.items():
        c.node(tgt, X[0], sum(ys) / len(ys), W[0], bh, 'instance', names[tgt], fs=6.4, bold_first=False)

    shown = set(c.box)
    # 依据层内部的 GOVERNS / SUPPORTS（只画两端都在图中的边，全部取自图谱）
    for s, r, t in kg.edges:
        if s in shown and t in shown and r in ('GOVERNS', 'SUPPORTS'):
            c.edge(s, t, color=LAYER_STYLE['rule'][1] if r == 'GOVERNS' else '#8fb3e0',
                   ls='-' if r == 'GOVERNS' else (0, (3, 2)), lw=0.75, pa=c.port(s, 'r'), pb=c.port(t, 'l'))
    for s, r, t in E:
        if s in shown and t in shown:
            if r == 'CONCERNS':
                c.edge(s, t, color=LAYER_STYLE['instance'][1], lw=0.7, pa=c.port(s, 'l'), pb=c.port(t, 'r'))
            elif r == 'BASED_ON' and t.startswith('dec:'):        # 前置决策：在决策列左侧画弧
                ys, yt = y_of[s[4:]], y_of[t[4:]]
                x0 = X[1] - W[1] / 2
                axb.add_patch(FancyArrowPatch((x0, ys), (x0, yt), arrowstyle='-|>', mutation_scale=6.5, lw=0.75,
                                              color=LAYER_STYLE['decision'][1],
                                              connectionstyle=f'arc3,rad={-0.4 if ys < yt else 0.4}',
                                              linestyle=(0, (3, 2)), zorder=2))
            elif r == 'BASED_ON':
                c.edge(s, t, color=LAYER_STYLE['decision'][1], lw=0.75, pa=c.port(s, 'r'), pb=c.port(t, 'l'))

    rel = [('CONCERNS', LAYER_STYLE['instance'][1], '-'),
           ('BASED_ON → rule / clause', LAYER_STYLE['decision'][1], '-'),
           ('BASED_ON → prerequisite decision', LAYER_STYLE['decision'][1], (0, (3, 2))),
           ('GOVERNS', LAYER_STYLE['rule'][1], '-'), ('SUPPORTS', '#8fb3e0', (0, (3, 2)))]
    if L is T['zh']:
        rel = [('CONCERNS（决策→构件）', rel[0][1], rel[0][2]), ('BASED_ON（决策→规则 / 条文）', rel[1][1], rel[1][2]),
               ('BASED_ON（决策→前置决策）', rel[2][1], rel[2][2]), ('GOVERNS（主依据）', rel[3][1], rel[3][2]),
               ('SUPPORTS（辅助依据）', rel[4][1], rel[4][2])]
    if not has_prereq:
        rel = rel[:2] + rel[3:]
    handles = [Line2D([], [], color=col, ls=ls, lw=1.0, label=lab) for lab, col, ls in rel]
    handles += [Patch(fc=LAYER_STYLE[k][0], ec=LAYER_STYLE[k][1], lw=0.8, label=L['layers'][k])
                for k in ('instance', 'decision', 'rule', 'code')]
    axb.legend(handles=handles, loc='upper center', bbox_to_anchor=(0.5, 0.075), ncol=3, fontsize=6.3, frameon=False,
               handlelength=2.4, columnspacing=1.4)
    return fig


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--lang', choices=['en', 'zh'], nargs='*', default=['en', 'zh'])
    ap.add_argument('--kg', default=DEFAULT_KG)
    ap.add_argument('--schema-kg', default=SCHEMA_KG)
    ap.add_argument('--out', default=os.path.join(ROOT, 'paper_figures'))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    run = load_run(a.kg)
    schema_run = load_run(a.schema_kg)
    for lang in a.lang:
        if lang == 'zh':
            plt.rcParams['font.sans-serif'] = ['PingFang SC', 'Heiti SC', 'Arial Unicode MS']
        else:
            plt.rcParams['font.sans-serif'] = ['Arial', 'Helvetica', 'DejaVu Sans']
        plt.rcParams['axes.unicode_minus'] = False
        L = T[lang]
        for name, fn in (('fig_kg_schema', fig_schema), ('fig_kg_instance', fig_instance)):
            fig = fn(schema_run if fn is fig_schema else run, L)
            p = os.path.join(a.out, f'{name}_{lang}')
            fig.savefig(p + '.png', dpi=300, facecolor='white', bbox_inches='tight', pad_inches=0.04)
            fig.savefig(p + '.pdf', facecolor='white', bbox_inches='tight', pad_inches=0.04)
            plt.close(fig)
            print(p)


if __name__ == '__main__':
    main()

"""框架图（论文图 4）与冲击系数耦合图（论文图 7），与 plot_kg 的图 5、图 6 同一画法：
python -m kgfem.plot_framework [--out 目录]

图 4：三条泳道——大模型智能体（工作流提示词、13 个工具）、建模阶段（各阶段的校验与回路上限）、知识图谱（五层）。
图 7：冲击系数的规范—模型双向耦合，数值取自贯穿算例 C06 的 C5 运行（DeepSeek-V4-Flash）。
工具名、约束编号、条文公式与回路上限均取自代码（kgfem/agent/tools.py、kgfem/kg/knowledge.py、kgfem/agent/session.py）。
"""
import argparse
import json
import os

import matplotlib
matplotlib.use('Agg')
matplotlib.rcParams['pdf.fonttype'] = 42   # 嵌入 TrueType 字体（期刊要求）
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

from . import plot_kg
from .plot_ablation import INK, INK2
from .plot_kg import EDGE, LAYER_STYLE, Canvas

plot_kg.LAYER_STYLE.update({'agent': ('#d8efed', '#2a8c88'), 'neutral': ('#f4f3f0', '#8a8984'),
                            'model': ('#f4f3f0', '#5f5e5a')})
ROOT = plot_kg.ROOT
RUN = os.path.join(ROOT, 'runs_ablation_single', 'C5', 'C06_r3', 'C06_session.json')

TOOLS = [('Instance', 'get_input_schema, write_instance,\nquery_component'),
         ('Knowledge', 'query_knowledge, retrieve_clause,\nexecute_formula, compute_section_properties'),
         ('Decision', 'declare_decisions, propose_decision,\ndecision_status'),
         ('Model', 'run_modal_analysis, generate_model,\nfinish')]


def textbox(ax, x, y, w, h, layer, title, lines, fs=5.9, title_fs=6.6, align='left'):
    """标题加粗居中、正文左对齐的方框。"""
    fill, line = LAYER_STYLE[layer]
    ax.add_patch(FancyBboxPatch((x - w / 2, y - h / 2), w, h, boxstyle='round,pad=0,rounding_size=0.12',
                                fc=fill, ec=line, lw=0.9, zorder=3))
    ax.text(x, y + h / 2 - 0.1, title, ha='center', va='top', fontsize=title_fs, color=INK, fontweight='bold', zorder=4)
    if lines:
        tx = x - w / 2 + 0.14 if align == 'left' else x
        ax.text(tx, y + h / 2 - 0.1 - 0.075 * title_fs / 6.6 * 4.1, lines, ha=align, va='top', fontsize=fs,
                color=INK, zorder=4, linespacing=1.3)


def region(ax, x0, y0, x1, y1, layer, label):
    _, line = LAYER_STYLE[layer]
    ax.add_patch(FancyBboxPatch((x0, y0), x1 - x0, y1 - y0, boxstyle='round,pad=0,rounding_size=0.18',
                                fc='none', ec=line, lw=0.8, ls=(0, (4, 2.5)), zorder=1))
    ax.text(x0 + 0.15, y1 - 0.12, label, ha='left', va='top', fontsize=7, color=line, fontweight='bold', zorder=5)


def reg(c, key, x, y, w, h):
    c.box[key] = (x, y, w, h)


# ---------------------------------------------------------------- 图 4
def fig_framework():
    fig, ax = plt.subplots(figsize=(7.2, 5.75))
    ax.set_xlim(0, 12)
    ax.set_ylim(-0.05, 9.55)
    ax.set_aspect('equal')
    ax.axis('off')
    c = Canvas(ax)
    TOP = 8.55
    region(ax, 0.1, 0.05, 3.15, TOP, 'agent', 'LLM agent')
    region(ax, 8.85, 0.05, 11.9, TOP, 'neutral', 'Executable bridge KG')
    ax.text(6.5, TOP - 0.12, 'Modeling stages', ha='center', va='top', fontsize=7, color=INK2, fontweight='bold')

    textbox(ax, 1.65, 9.1, 3.3, 0.68, 'neutral', 'Input description',
            'spans · sections · bearings · design standard', align='center', fs=5.1, title_fs=6.3)
    # 智能体泳道
    A, AW = 1.62, 2.85
    textbox(ax, A, 7.3, AW, 1.6, 'agent', 'Workflow prompt',
            '1  write the instance\n2  declare the required decisions\n3  propose decisions in order\n'
            '4  generate the model\n5  repair if a check fails\none context; ≤ 200 turns', fs=5.4, title_fs=6.3)
    reg(c, 'agent', A, 7.3, AW, 1.6)
    textbox(ax, A, 4.5, AW, 3.6, 'agent', '13 tools', '', title_fs=6.3)
    tools = [('Instance', 'get_input_schema · write_instance\nquery_component'),
             ('Knowledge', 'query_knowledge · retrieve_clause\nexecute_formula\ncompute_section_properties'),
             ('Decision', 'declare_decisions · propose_decision\ndecision_status'),
             ('Model', 'run_modal_analysis · generate_model\nfinish')]
    yy = 4.5 + 1.8 - 0.42
    for k, v in tools:
        ax.text(A - AW / 2 + 0.14, yy, k, ha='left', va='top', fontsize=5.6, color=INK, fontweight='bold', zorder=4)
        ax.text(A - AW / 2 + 0.14, yy - 0.2, v, ha='left', va='top', fontsize=5.2, color=INK, zorder=4,
                linespacing=1.25)
        yy -= 0.33 + 0.19 * (v.count('\n') + 1)
    textbox(ax, A, 1.37, AW, 2.4, 'agent', 'Feedback example',
            'C06, gpt-6-luna run\n'
            'propose_decision(support.1.S,\n   10.53, {JTG3362-8.7-S})\n'
            '→ rejected (value): formula gives\n   14.69 with a = 0.60 m,\n   b = 0.70 m, $t_1$ = 11 mm\n'
            '→ revised, then accepted', fs=5.3, title_fs=6.3)

    # 阶段
    X, W = 6.5, 3.0
    st = [('S1', 7.55, 0.95, 'instance', 'Instance writing (Sec. 4.3)',
           'C-01–C-08 completeness, plausibility;\nslots vs. templates; ≤ 5 rounds'),
          ('S2', 5.95, 1.5, 'decision', 'Decision validation (Sec. 4.4)',
           '(s, v, E) once prerequisites are accepted\n1 evidence · 2 applicability\n'
           '3 value, |v − v*| ≤ 0.1% of v*\n4 consistency, C-10–C-15'),
          ('S3', 4.45, 0.8, 'model', 'Modal analysis', 'model of accepted decisions → $f_1$'),
          ('S4', 3.25, 0.95, 'model', 'Model generation (Sec. 4.5)',
           'provenance IR → OpenSeesPy;\nself-weight, modal, lane-load analyses'),
          ('S5', 1.85, 0.95, 'constraint', 'Model checks (Sec. 4.6)',
           'L1 topology · L2 code · L3 mechanics;\nfailures traced to decisions; ≤ 5 rounds')]
    for key, y, h, layer, t, body in st:
        textbox(ax, X, y, W, h, layer, t, body, fs=5.4, title_fs=6.3, align='center')
        reg(c, key, X, y, W, h)
    textbox(ax, X, 0.55, W, 0.5, 'neutral', 'FE model and responses', '', title_fs=6.3)

    ga, gb, gm = A + AW / 2, X - W / 2, (A + AW / 2 + X - W / 2) / 2
    calls = [('S1', 'write_instance,\ndeclare_decisions', 'issues, missing slots'),
             ('S2', 'propose_decision\n(53 calls in C06)', 'accepted, or failed\ncheck with v*, inputs'),
             ('S3', 'run_modal_analysis', '$f_1$'),
             ('S4', 'generate_model', None),
             ('S5', None, 'violated constraint,\nsuspect decisions')]
    rc = LAYER_STYLE['code'][1]
    for key, call, ret in calls:
        y = c.box[key][1]
        if call:
            c.edge('agent', key, None, pa=(ga, y + 0.14), pb=(gb, y + 0.14))
            ax.text(gm, y + 0.2, call, ha='center', va='bottom', fontsize=5.2, color=INK2, linespacing=1.15)
        if ret:
            c.edge(key, 'agent', None, pa=(gb, y - 0.14), pb=(ga, y - 0.14), color=rc)
            ax.text(gm, y - 0.2, ret, ha='center', va='top', fontsize=5.2, color=rc, linespacing=1.15)
    c.edge('in', 'agent', None, pa=(A, 8.72), pb=(A, 8.15))
    c.edge('S4', 'S5', None, pa=(X, 3.25 - 0.475), pb=(X, 1.85 + 0.475))
    c.edge('S5', 'out', None, pa=(X, 1.85 - 0.475), pb=(X, 0.8))
    ax.text(X + 0.1, 1.08, 'pass', ha='left', va='center', fontsize=5.2, color=INK2)

    # 知识图谱
    K, KW = 10.38, 2.8
    kg = [('IL', 7.55, 'instance', 'Instance layer', 'Bridge, Deck, GirderSystem, Span,\nSupportLine, BearingGroup, Pier'),
          ('RL', 6.4, 'rule', 'Modeling-rule layer', '11 rules (MR-00–MR-08, LL-01/02);\n24 slots; 4 templates'),
          ('CL', 5.25, 'code', 'Design-code layer', '12 clauses: JTG D60-2015,\nJTG 3362-2018, JT/T 854-2013'),
          ('DL', 3.55, 'decision', 'Decision layer', 'accepted (s, v, E);\nBASED_ON, CONCERNS edges'),
          ('KC', 1.85, 'constraint', 'Constraint layer', 'C-01–C-08 instance; C-10–C-15\ndecision; L1-1–L3-3 model')]
    for key, y, layer, t, body in kg:
        textbox(ax, K, y, KW, 0.9, layer, t, body, fs=5.4, title_fs=6.3, align='center')
        reg(c, key, K, y, KW, 0.9)
    L, R = K - KW / 2, X + W / 2
    kc = lambda k: LAYER_STYLE[k][1]
    lab = lambda x, y, t, col: ax.text(x, y, t, ha='center', va='center', fontsize=5.2, color=col, linespacing=1.1,
                                       bbox=dict(fc='white', ec='none', pad=0.4), zorder=5)
    c.edge('S1', 'IL', None, pa=(R, 7.55), pb=(L, 7.55), color=kc('instance'))
    lab((R + L) / 2, 7.55, 'write', kc('instance'))
    c.edge('IL', 'S2', None, pa=(L, 7.3), pb=(R, 6.45), color=kc('instance'), ls=(0, (3, 2)))
    lab(8.4, 6.98, 'c(s)', kc('instance'))
    c.edge('RL', 'S2', None, pa=(L, 6.4), pb=(R, 6.05), color=kc('rule'), ls=(0, (3, 2)))
    c.edge('CL', 'S2', None, pa=(L, 5.25), pb=(R, 5.75), color=kc('code'), ls=(0, (3, 2)))
    lab(8.47, 5.88, 'GOVERNS,\nformulas', INK2)
    c.edge('S2', 'DL', None, pa=(R, 5.35), pb=(L, 3.75), color=kc('decision'))
    lab(8.42, 4.45, 'accept', kc('decision'))
    c.edge('DL', 'S4', None, pa=(L, 3.35), pb=(R, 3.25), color=kc('decision'), ls=(0, (3, 2)))
    lab(8.42, 3.3, 'provenance', kc('decision'))
    c.edge('KC', 'S5', None, pa=(L, 1.85), pb=(R, 1.85), color=kc('constraint'), ls=(0, (3, 2)))
    lab(8.42, 1.85, 'L1–L3', INK2)
    reg(c, 'out', X, 0.55, W, 0.5)
    return fig


# ---------------------------------------------------------------- 图 7
def fig_coupling():
    s = json.load(open(RUN, encoding='utf-8'))
    f1 = s['facts']['f1']
    mu = next(e['result']['value'] for e in s['log'] if e['tool'] == 'execute_formula'
              and e['args'].get('slot') == 'lane.mu')
    pk = {e['args']['slot']: e['args']['value'] for e in s['log'] if e['tool'] == 'propose_decision'}

    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 7.0)
    ax.set_aspect('equal')
    ax.axis('off')
    c = Canvas(ax)
    lanes = [(4.55, 6.95, 'model', 'FE model (OpenSeesPy)'), (2.3, 4.4, 'agent', 'LLM agent'),
             (0.05, 2.15, 'neutral', 'Executable bridge KG')]
    for y0, y1, layer, lab in lanes:
        region(ax, 0.1, y0, 11.9, y1, layer, lab)

    def box(key, x, y, w, h, layer, title, body):
        textbox(ax, x, y, w, h, layer, title, body, fs=5.4, title_fs=6.3, align='center')
        reg(c, key, x, y, w, h)

    c1, c2, c3, c4 = 1.65, 4.5, 7.4, 10.3
    ym, ya, yk = 5.55, 3.2, 1.0
    box('a1', c1, ya, 2.6, 1.05, 'agent', '1  Slot lane.mu pending',
        'structural decisions accepted;\nprerequisite fact $f_1$ missing')
    box('m2', c2, ym, 2.85, 1.3, 'model', '2  run_modal_analysis',
        'model of the accepted decisions:\ngirder A, I, Ec, m; bearings Kv, Kh;\npier columns  →  '
        f'$f_1$ = {f1:.2f} Hz')
    box('k3', c2, yk, 2.85, 1.55, 'code', '3  Clause JTGD60-4.3.2',
        'applicable when $f_1$ is available\nμ = 0.05 if $f_1$ < 1.5 Hz\nμ = 0.1767 ln $f_1$ − 0.0157\n'
        'μ = 0.45 if $f_1$ > 14 Hz')
    box('a4', c3, ya, 2.75, 1.05, 'agent', '4  execute_formula, propose',
        f'μ = {mu:.3f}; propose (lane.mu, {mu:.3f},\n{{JTGD60-4.3.2, $f_1$}})')
    box('k5', c4, yk, 2.85, 1.55, 'decision', '5  Validation and record',
        f'evidence · applicability ·\nvalue (v* = {mu:.3f}) · consistency\n→ dec:lane.mu, BASED_ON\n'
        'JTGD60-4.3.2, CONCERNS Deck')
    box('m6', c4, ym, 2.85, 1.3, 'model', '6  generate_model',
        f"lane loads × (1 + μ); $q_k$ = {pk['lane.qk']:g} kN/m,\n"
        f"$P_k$ = {pk['lane.Pk.1']:g}–{pk['lane.Pk.2']:g} kN, ξ = {pk['lane.xi']:g}\n"
        'check L2-2: μ consistent with $f_1$')

    lab = lambda x, y, t, col=INK2: ax.text(x, y, t, ha='center', va='center', fontsize=5.2, color=col,
                                            bbox=dict(fc='white', ec='none', pad=0.4), zorder=5)
    c.edge('a1', 'm2', None, pa=(c1, ya + 0.525), pb=(c2 - 1.425, ym - 0.2))
    lab(2.75, 4.55, 'needs $f_1$')
    c.edge('m2', 'k3', None, pa=(c2, ym - 0.65), pb=(c2, yk + 0.775))
    lab(c2, 3.2, f'$f_1$ = {f1:.2f} Hz')
    c.edge('k3', 'a4', None, pa=(c2 + 1.425, yk + 0.35), pb=(c3 - 1.375, ya - 0.2))
    lab(5.95, 2.2, 'retrieve, execute')
    c.edge('a4', 'k5', None, pa=(c3 + 1.375, ya - 0.2), pb=(c4 - 1.425, yk + 0.35))
    lab(8.85, 2.2, 'propose_decision')
    rc = LAYER_STYLE['code'][1]
    c.edge('k5', 'a4', None, pa=(c4 - 1.425, yk - 0.3), pb=(c3, ya - 0.525), color=rc, rad=-0.3)
    lab(7.6, 1.05, 'reject: v*, $f_1$', rc)
    c.edge('k5', 'm6', None, pa=(c4, yk + 0.775), pb=(c4, ym - 0.65))
    lab(c4, 3.2, 'accepted')
    c.edge('m6', 'm2', None, pa=(c4 - 1.425, ym + 0.2), pb=(c2 + 1.425, ym + 0.2), color=INK2, ls=(0, (3, 2)))
    ax.text((c2 + c4) / 2, ym + 0.32, 'a revised structural decision voids $f_1$\nand withdraws μ: repeat',
            ha='center', va='bottom', fontsize=5.2, color=INK2, linespacing=1.15)
    return fig


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join(ROOT, 'paper_figures'))
    a = ap.parse_args()
    plt.rcParams['font.sans-serif'] = ['Arial', 'Helvetica', 'DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False
    for name, fn in (('fig4_framework_en', fig_framework), ('fig7_coupling_en', fig_coupling)):
        fig = fn()
        p = os.path.join(a.out, name)
        fig.savefig(p + '.png', dpi=300, facecolor='white', bbox_inches='tight', pad_inches=0.04)
        fig.savefig(p + '.pdf', facecolor='white', bbox_inches='tight', pad_inches=0.04)
        plt.close(fig)
        print(p)


if __name__ == '__main__':
    main()

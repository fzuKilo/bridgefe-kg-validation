"""论文流程图（图 3–5）：python -m kgfem.plot_diagrams [--lang en|zh] [--out 目录]

图 3 BridgeFE-Bench 的构建；图 4 图谱约束的大模型驱动建模；图 5 冲击系数中规范知识与有限元模型的耦合。
"""
import argparse
import os

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

from .plot_ablation import INK, INK2

FILL, LINE = '#f0efec', '#8a8984'                 # 一般步骤
AFILL, ALINE = '#dbe9fb', '#2a78d6'               # 大模型智能体
KFILL, KLINE = '#fbe8d6', '#d9822b'               # 知识图谱及其校验

T = {
    'en': {
        'P': 'Parameter space||spans, girders, bearings,\npiers, load class',
        'S': 'Tiered sampling||A / B / C, 10 problems each;\nlong units S01–S03',
        'D': 'Decision-level answers||from the governing clauses;\nreviewed by engineers',
        'R': 'Analytical solutions /\nindependent parametric\nreference model||',
        'R2': 'Response-level\nanswers||',
        'I': 'Input descriptions||structured (EN / ZH), free text,\nboundary inputs',
        'U': 'Input description',
        'A': 'LLM agent||one context\none workflow prompt\n13 tools',
        'IL': 'Instance layer||completeness, plausibility',
        'V': 'Decision validation||evidence · applicability ·\nvalue · consistency',
        'M': 'Modal analysis||fundamental frequency f1',
        'G': 'Model generation||provenance IR → OpenSeesPy\n→ L1 / L2 / L3 checks',
        'O': 'Model and results',
        'KG': 'Executable\nbridge KG||modeling-rule\ndesign-code\ninstance\nconstraint\nlayers',
        'c1': 'write_instance,\ndeclare_decisions', 'r1': 'issues,\nmissing decisions',
        'c2': 'propose_decision', 'r2': 'structured feedback',
        'c3': 'run_modal_analysis', 'r3': 'f1',
        'c4': 'generate_model', 'r4': 'fail: violated constraints,\nsuspect decisions',
        'pass': 'pass',
        'F1': 'Agent: dynamic\namplification factor\nrequired||',
        'F2': 'Modal analysis||fundamental\nfrequency f1',
        'F3': 'Retrieve clause;\nexecute formula||μ = f(f1)',
        'F4': 'KG validation||citation and value',
        'F5': 'Lane-load\nparameters fixed||',
        'ffail': 'fail: formula result and inputs returned', 'fpass': 'pass',
    },
    'zh': {
        'P': '参数空间||跨径、主梁、支座、\n桥墩、荷载等级',
        'S': '分档抽样||A / B / C 各 10 题；\n长联 S01–S03',
        'D': '决策层答案||由所依据的条文计算；\n工程师复核',
        'R': '解析解 /\n独立编写的参数化\n参考模型||',
        'R2': '响应层答案||',
        'I': '输入描述||结构化（中 / 英）、自由文本、\n边界输入',
        'U': '输入描述',
        'A': '大模型智能体||一段上下文\n一份流程提示词\n13 个工具',
        'IL': '实例层||完整性、合理性',
        'V': '决策校验||依据 · 适用性 ·\n数值 · 一致性',
        'M': '模态分析||基频 f1',
        'G': '模型生成||溯源中间表示 → OpenSeesPy\n→ L1 / L2 / L3 校核',
        'O': '模型与结果',
        'KG': '可执行\n桥梁知识图谱||建模规则层\n规范层\n实例层\n约束层',
        'c1': 'write_instance,\ndeclare_decisions', 'r1': '问题、\n缺少的决策',
        'c2': 'propose_decision', 'r2': '结构化反馈',
        'c3': 'run_modal_analysis', 'r3': 'f1',
        'c4': 'generate_model', 'r4': '失败：违反的约束、\n可疑决策',
        'pass': '通过',
        'F1': '智能体：\n需要冲击系数||',
        'F2': '模态分析||基频 f1',
        'F3': '检索条文；\n执行公式||μ = f(f1)',
        'F4': '知识图谱校验||引用与数值',
        'F5': '车道荷载\n参数确定||',
        'ffail': '失败：返回公式结果及其输入', 'fpass': '通过',
    },
}


def box(ax, x, y, w, h, text, fill=FILL, line=LINE, fs=7.5, bold_first=True, title_h=None):
    """text 为“标题||正文”：标题加粗置于框顶，正文居中于其下；无“||”时整段居中（bold_first 控制是否加粗）。"""
    ax.add_patch(FancyBboxPatch((x - w / 2, y - h / 2), w, h, boxstyle='round,pad=0,rounding_size=0.12',
                                fc=fill, ec=line, lw=1.0))
    if '||' not in text:
        ax.text(x, y, text, ha='center', va='center', fontsize=fs, color=INK,
                fontweight='bold' if bold_first else None, linespacing=1.3)
        return
    head, body = text.split('||')
    if not body:
        ax.text(x, y, head, ha='center', va='center', fontsize=fs, color=INK, fontweight='bold', linespacing=1.25)
        return
    nh = head.count('\n') + 1
    th = title_h if title_h is not None else 0.14 + 0.2 * nh
    ax.text(x, y + h / 2 - 0.12, head, ha='center', va='top', fontsize=fs, color=INK, fontweight='bold',
            linespacing=1.25)
    top = y + h / 2 - 0.12 - th
    ax.text(x, (top + y - h / 2) / 2, body, ha='center', va='center', fontsize=fs - 0.5, color=INK, linespacing=1.3)


def arrow(ax, p, q, label=None, dy=0.13, dashed=False, rad=0.0, color=INK2, fs=6.5, lpos=None, ha='center'):
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle='-|>', mutation_scale=9, lw=1.0, color=color,
                                 linestyle=(0, (3, 2)) if dashed else '-', connectionstyle=f'arc3,rad={rad}',
                                 shrinkA=0, shrinkB=0))
    if label:
        x, y = lpos or ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2 + dy)
        ax.text(x, y, label, ha=ha, va='bottom' if dy >= 0 else 'top', fontsize=fs, color=INK2, linespacing=1.2)


def canvas(w, h, inch=7.2):
    fig = plt.figure(figsize=(inch, inch * h / w))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, w)
    ax.set_ylim(0, h)
    ax.axis('off')
    return fig, ax


def fig3(L):
    fig, ax = canvas(10.4, 3.6)
    box(ax, 1.05, 1.8, 1.9, 1.2, L['P'])
    box(ax, 3.4, 1.8, 2.1, 1.2, L['S'])
    box(ax, 6.2, 3.0, 2.4, 1.0, L['D'])
    box(ax, 6.2, 1.8, 2.4, 1.0, L['R'])
    box(ax, 9.25, 1.8, 1.9, 0.8, L['R2'], bold_first=True)
    box(ax, 6.2, 0.6, 2.4, 1.0, L['I'])
    arrow(ax, (2.0, 1.8), (2.35, 1.8))
    arrow(ax, (4.45, 2.1), (5.0, 3.0))
    arrow(ax, (4.45, 1.8), (5.0, 1.8))
    arrow(ax, (4.45, 1.5), (5.0, 0.6))
    arrow(ax, (7.4, 1.8), (8.3, 1.8))
    return fig


def fig4(L):
    fig, ax = canvas(10.6, 7.4)
    ys = [5.4, 4.05, 2.7, 1.35]
    box(ax, 1.6, 6.85, 2.2, 0.55, L['U'], bold_first=False)
    box(ax, 1.6, 3.4, 2.2, 5.0, L['A'], fill=AFILL, line=ALINE, fs=8.5)
    arrow(ax, (1.6, 6.57), (1.6, 5.9))
    mid = 6.3
    for y, key, fill, line in zip(ys, ['IL', 'V', 'M', 'G'], [KFILL, KFILL, FILL, KFILL], [KLINE, KLINE, LINE, KLINE]):
        box(ax, mid, y, 2.9, 1.0, L[key], fill=fill, line=line)
    for k, y in enumerate(ys, 1):
        arrow(ax, (2.7, y + 0.2), (4.85, y + 0.2), L[f'c{k}'], dy=0.06)
        arrow(ax, (4.85, y - 0.2), (2.7, y - 0.2), L[f'r{k}'], dy=-0.06)
    box(ax, mid, 0.25, 2.9, 0.42, L['O'], bold_first=False)
    arrow(ax, (mid, ys[3] - 0.5), (mid, 0.46), L['pass'], dy=0, lpos=(mid + 0.12, 0.62), ha='left')
    box(ax, 9.5, 3.4, 1.8, 5.0, L['KG'], fill=KFILL, line=KLINE, fs=8)
    for y in (ys[0], ys[1], ys[3]):
        arrow(ax, (8.6, y), (7.75, y), dashed=True, color=KLINE)
    return fig


def fig5(L):
    fig, ax = canvas(10.4, 2.5)
    xs = [1.0, 3.1, 5.2, 7.3, 9.4]
    y = 1.65
    for x, k, fill, line in zip(xs, ['F1', 'F2', 'F3', 'F4', 'F5'], [AFILL, FILL, FILL, KFILL, FILL],
                                [ALINE, LINE, LINE, KLINE, LINE]):
        box(ax, x, y, 1.8, 1.25, L[k], fill=fill, line=line, fs=7.5)
    for a, b in zip(xs, xs[1:]):
        arrow(ax, (a + 0.9, y), (b - 0.9, y))
    ax.add_patch(FancyArrowPatch((xs[3], y - 0.63), (xs[0], y - 0.63), arrowstyle='-|>', mutation_scale=9, lw=1.0,
                                 color=KLINE, connectionstyle='arc3,rad=-0.12', shrinkA=0, shrinkB=0))
    ax.text((xs[0] + xs[3]) / 2, 0.42, L['ffail'], ha='center', va='center', fontsize=6.5, color=INK2)
    return fig


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--lang', default='en')
    ap.add_argument('--out', default='paper_figures')
    a = ap.parse_args()
    if a.lang == 'zh':
        plt.rcParams['font.sans-serif'] = ['PingFang SC', 'Heiti SC', 'Arial Unicode MS']
    plt.rcParams['axes.unicode_minus'] = False
    os.makedirs(a.out, exist_ok=True)
    for n, f in (('fig3', fig3), ('fig4', fig4), ('fig5', fig5)):
        fig = f(T[a.lang])
        p = os.path.join(a.out, f'{n}_{a.lang}')
        fig.savefig(p + '.png', dpi=300, facecolor='white')
        fig.savefig(p + '.pdf', facecolor='white')
        plt.close(fig)
        print(p + '.png')


if __name__ == '__main__':
    main()

"""图 9（注入错误的修复）与图 10（规模与成本）：python -m kgfem.plot_h3 [--lang en|zh] [--out paper_figures]

图 9：runs_faults；图 10：runs_main 的 C4、C5 按档汇总，加 runs_scale 的长联 S01–S03。
"""
import argparse
import json
import os
import statistics as st
from collections import defaultdict

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from .plot_ablation import ACCENT, GRID, INK, INK2, NEUTRAL
from .cli import ROOT

SIG_COLORS = {'C5': '#2a78d6', 'A5': '#d9822b', 'F0': '#8b5cc4'}   # 已用 validate_palette.js 校验
CATS = ['modeling_rule', 'code_parameter', 'topology', 'input_interpretation']
T = {'en': dict(sig={'C5': 'C5 structured feedback + localization', 'A5': 'A5 feedback without localization',
                     'F0': 'F0 failure signal only'},
                cat={'modeling_rule': 'Modeling\nrule', 'code_parameter': 'Code\nparameter', 'topology': 'Topology',
                     'input_interpretation': 'Input\ninterpretation'},
                a9='(a) Faults repaired (%)', b9='(b) Model generations',
                c9='(c) Input tokens (thousand)',
                a10='(a) Accuracy', b10='(b) Wall-clock time per run (s)', c10='(c) Input tokens per run (thousand)',
                x10='Number of decisions', cfg={'C4': 'C4 KG as tools', 'C5': 'C5 KG constraint'}),
     'zh': dict(sig={'C5': 'C5 结构化反馈 + 定位', 'A5': 'A5 反馈不带定位', 'F0': 'F0 仅告知失败'},
                cat={'modeling_rule': '建模规则', 'code_parameter': '规范参数', 'topology': '构件拓扑',
                     'input_interpretation': '输入理解'},
                a9='(a) 修复成功率（%）', b9='(b) 生成模型的次数', c9='(c) 输入 token（千）',
                a10='(a) 准确率', b10='(b) 每次运行耗时（秒）', c10='(c) 每次运行输入 token（千）',
                x10='决策数', cfg={'C4': 'C4 图谱工具（不校验）', 'C5': 'C5 图谱约束（本文）'})}


def _style(ax, title):
    for s in ('top', 'right'):
        ax.spines[s].set_visible(False)
    ax.set_axisbelow(True)
    ax.grid(axis='y', color=GRID, lw=0.6)
    ax.set_title(title, loc='left', fontsize=9, color=INK)


def _load(path):
    last = {}
    for line in open(path, encoding='utf-8'):
        r = json.loads(line)
        if not r.get('error'):
            key = (r.get('config') or r.get('signal'), r.get('problem') if 'config' in r else r['fault'], r['rep'])
            last[key] = r
    return list(last.values())


def _usage(r):
    u = r.get('usage') or {}
    if 'roles' in u:
        return {k: sum(x['usage'].get(k, 0) for x in u['roles']) for k in ('turns', 'prompt_tokens')}
    return u


def fig9(L):
    rows = _load(os.path.join(ROOT, 'runs_faults', 'results.jsonl'))
    g = defaultdict(list)
    for r in rows:
        g[(r['signal'], r['category'])].append(r)
    fig, axes = plt.subplots(1, 3, figsize=(7.2, 2.9))
    x = np.arange(len(CATS))
    w = 0.26
    metrics = [(lambda rs: 100 * st.mean(bool(r['correct']) for r in rs), L['a9'], '{:.0f}'),
               (lambda rs: st.mean(r['repair_rounds'] for r in rs), L['b9'], '{:.2f}'),
               (lambda rs: st.mean(_usage(r).get('prompt_tokens', 0) for r in rs) / 1e3, L['c9'], '{:.0f}')]
    for ax, (fn, title, fmt) in zip(axes, metrics):
        for k, sig in enumerate(['C5', 'A5', 'F0']):
            vals = [fn(g[(sig, c)]) for c in CATS]
            xs = x + (k - 1) * w
            ax.bar(xs, vals, width=w - 0.03, color=SIG_COLORS[sig], label=L['sig'][sig])
            for xi, v in zip(xs, vals):
                ax.text(xi, v, fmt.format(v), ha='center', va='bottom', fontsize=5.3, color=INK, rotation=90)
        ax.set_xticks(x, [L['cat'][c] for c in CATS], fontsize=6.5)
        ax.margins(y=0.22)
        _style(ax, title)
    axes[0].set_ylim(0, 115)
    axes[1].set_ylim(1, None)
    h, lb = axes[0].get_legend_handles_labels()
    fig.legend(h, lb, loc='lower center', ncol=3, frameon=False, fontsize=7, bbox_to_anchor=(0.5, -0.02))
    fig.tight_layout(rect=(0, 0.08, 1, 1), w_pad=1.2)
    return fig


def fig10(L):
    rows = [r for r in _load(os.path.join(ROOT, 'runs_main', 'results.jsonl')) if r['config'] in ('C4', 'C5')]
    rows += _load(os.path.join(ROOT, 'runs_scale', 'results.jsonl'))
    g = defaultdict(list)
    for r in rows:
        key = r['problem'][0] if r['problem'][0] in 'ABC' else r['problem']
        g[(r['config'], key)].append(r)
    groups = ['A', 'B', 'C', 'S01', 'S02', 'S03']
    fig, axes = plt.subplots(1, 3, figsize=(7.2, 2.6))
    for cfg, col, mk in (('C4', NEUTRAL, 's'), ('C5', ACCENT, 'o')):
        xs = [st.mean(r['decisions_total'] for r in g[(cfg, k)]) for k in groups]
        ys = [[st.mean(bool(r['correct']) for r in g[(cfg, k)]) for k in groups],
              [st.mean(r['wall_s'] for r in g[(cfg, k)]) for k in groups],
              [st.mean(_usage(r).get('prompt_tokens', 0) for r in g[(cfg, k)]) / 1e3 for k in groups]]
        for ax, y in zip(axes, ys):
            ax.plot(xs, y, color=col, lw=1.6, marker=mk, ms=5, mec='white', mew=1, label=L['cfg'][cfg])
        if cfg == 'C5':
            for xi, k, y in zip(xs, groups, ys[1]):
                axes[1].annotate(k, (xi, y), textcoords='offset points', xytext=(0, 6), ha='center', fontsize=6,
                                 color=INK2)
    for ax, title in zip(axes, [L['a10'], L['b10'], L['c10']]):
        ax.set_xlabel(L['x10'], fontsize=7.5)
        _style(ax, title)
    axes[0].set_ylim(0.5, 1.05)
    axes[0].yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    axes[1].set_ylim(0, None)
    axes[2].set_ylim(0, None)
    h, lb = axes[0].get_legend_handles_labels()
    fig.legend(h, lb, loc='lower center', ncol=2, frameon=False, fontsize=7, bbox_to_anchor=(0.5, -0.03))
    fig.tight_layout(rect=(0, 0.09, 1, 1), w_pad=1.2)
    return fig


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--lang', default='en')
    ap.add_argument('--out', default=os.path.join(ROOT, 'paper_figures'))
    a = ap.parse_args()
    if a.lang == 'zh':
        plt.rcParams['font.sans-serif'] = ['PingFang SC', 'Heiti SC', 'Arial Unicode MS']
    plt.rcParams.update({'font.size': 8, 'axes.edgecolor': INK2, 'axes.labelcolor': INK, 'xtick.color': INK2,
                         'ytick.color': INK2, 'axes.linewidth': 0.6, 'axes.unicode_minus': False})
    os.makedirs(a.out, exist_ok=True)
    for n, f in (('fig9', fig9), ('fig10', fig10)):
        fig = f(T[a.lang])
        p = os.path.join(a.out, f'{n}_{a.lang}')
        fig.savefig(p + '.png', dpi=300, bbox_inches='tight', facecolor='white')
        fig.savefig(p + '.pdf', bbox_inches='tight', facecolor='white')
        plt.close(fig)
        print(p + '.png')


if __name__ == '__main__':
    main()

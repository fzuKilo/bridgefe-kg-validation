"""基座模型对比图（图 8）：python -m kgfem.plot_backbone runs_main runs_luna [--lang en|zh] [--out 前缀]

(a) 两个基座在 C0–C5 下的准确率与 95% bootstrap 置信区间；(b) C4、C5 下每题 3 次运行中的正确次数；
(c) C1–C5 的决策正确率；(d) 每次运行的输入 token。
"""
import argparse
import os
from collections import defaultdict

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import BoundaryNorm, ListedColormap

from .plot_ablation import GRID, INK, INK2, SEQ
from .summarize import boot_ci, load, per_problem, tokens

ORDER = ['C0', 'C1', 'C2', 'C3', 'C4', 'C5']
COLORS = ['#2a78d6', '#d9822b']                              # 已用 validate_palette.js 校验
MARKERS = ['o', 's']
LABEL = {'en': {'C0': 'C0 direct script', 'C1': 'C1 direct decisions', 'C2': 'C2 prompt knowledge',
                'C3': 'C3 retrieval', 'C4': 'C4 KG as tools', 'C5': 'C5 KG constraint'},
         'zh': {'C0': 'C0 直接生成脚本', 'C1': 'C1 直接生成决策', 'C2': 'C2 提示词知识', 'C3': 'C3 检索增强',
                'C4': 'C4 图谱工具（不校验）', 'C5': 'C5 图谱约束（本文）'}}
TXT = {'en': dict(a='(a) Accuracy (mean over problems, 95% CI)', b='(b) Correct runs out of 3, per problem',
                  c='(c) Decision accuracy', d='(d) Input tokens per run', tok='thousand tokens',
                  cb='correct runs', dec='Decision accuracy'),
       'zh': dict(a='(a) 准确率（按题平均，95% 置信区间）', b='(b) 各题 3 次运行中的正确次数', c='(c) 决策正确率',
                  d='(d) 每次运行输入 token', tok='千 token', cb='正确次数', dec='决策正确率')}


def _style(ax):
    for s in ('top', 'right'):
        ax.spines[s].set_visible(False)
    ax.set_axisbelow(True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('paths', nargs='+', help='每个基座一个结果目录')
    ap.add_argument('--names', nargs='+', default=['DeepSeek-V4-Flash', 'gpt-6-luna'])
    ap.add_argument('--lang', default='en')
    ap.add_argument('--out', default=None)
    a = ap.parse_args()
    L, T = LABEL[a.lang], TXT[a.lang]
    if a.lang == 'zh':
        plt.rcParams['font.sans-serif'] = ['PingFang SC', 'Heiti SC', 'Arial Unicode MS']
    plt.rcParams.update({'font.size': 8.5, 'axes.edgecolor': INK2, 'axes.labelcolor': INK, 'xtick.color': INK2,
                         'ytick.color': INK2, 'axes.linewidth': 0.6, 'axes.unicode_minus': False})
    data = []
    for p in a.paths:
        by = defaultdict(list)
        for r in load(p):
            by[r['config']].append(r)
        data.append(by)
    probs = sorted({r['problem'] for r in data[0]['C5']})

    fig = plt.figure(figsize=(7.2, 7.4))
    gs = fig.add_gridspec(3, 2, height_ratios=[1.45, 0.95, 0.95], hspace=0.62, wspace=0.28)

    # (a) 准确率与置信区间：同一方案下两个基座上下错开
    ax = fig.add_subplot(gs[0, :])
    y0 = np.arange(len(ORDER))[::-1]
    for k, (by, name) in enumerate(zip(data, a.names)):
        off = 0.17 if k == 0 else -0.17
        for yi, c in zip(y0, ORDER):
            pp = list(per_problem(by[c])[0].values())
            m, (lo, hi) = float(np.mean(pp)), boot_ci(pp)
            ax.plot([lo, hi], [yi + off] * 2, color=COLORS[k], lw=2, solid_capstyle='round', clip_on=False)
            ax.plot(m, yi + off, MARKERS[k], ms=6.5, color=COLORS[k], mec='white', mew=1.3, zorder=3,
                    clip_on=False, label=name if c == 'C0' else None)
            ax.text(1.02, yi + off, f'{m:.1%}', va='center', ha='left', color=INK, fontsize=7.5)
    ax.set_yticks(y0, [L[c] for c in ORDER])
    ax.set_xlim(0, 1)
    ax.set_ylim(-0.6, len(ORDER) - 0.4)
    ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    ax.grid(axis='x', color=GRID, lw=0.6)
    _style(ax)
    ax.legend(loc='upper center', bbox_to_anchor=(0.5, 1.0), frameon=False, fontsize=8)
    ax.set_title(T['a'], loc='left', fontsize=9, color=INK)

    # (b) C4、C5 下每题正确次数
    ax = fig.add_subplot(gs[1, :])
    rows, labels = [], []
    for c in ('C4', 'C5'):
        for by, name in zip(data, a.names):
            cnt = defaultdict(int)
            for r in by[c]:
                cnt[r['problem']] += bool(r['correct'])
            rows.append([cnt[p] for p in probs])
            labels.append(f'{c} · {name}')
    M = np.array(rows, dtype=float)
    im = ax.imshow(M, cmap=ListedColormap(SEQ), norm=BoundaryNorm([-0.5, 0.5, 1.5, 2.5, 3.5], 4), aspect='auto')
    ax.set_xticks(np.arange(len(probs)), probs, rotation=90, fontsize=7)
    ax.set_yticks(np.arange(len(labels)), labels, fontsize=7.5)
    ax.set_xticks(np.arange(-0.5, len(probs)), minor=True)
    ax.set_yticks(np.arange(-0.5, len(labels)), minor=True)
    ax.grid(which='minor', color='white', lw=1.5)
    ax.tick_params(which='minor', length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    for i in range(M.shape[0]):
        for j in range(M.shape[1]):
            if M[i, j] < 3:
                ax.text(j, i, int(M[i, j]), ha='center', va='center', fontsize=7,
                        color='white' if M[i, j] >= 2 else INK)
    for x in (9.5, 19.5):
        ax.axvline(x, color=INK2, lw=0.8)
    ax.axhline(1.5, color=INK2, lw=0.8)
    cb = fig.colorbar(im, ax=ax, ticks=[0, 1, 2, 3], fraction=0.025, pad=0.01)
    cb.set_label(T['cb'], color=INK2)
    cb.outline.set_visible(False)
    ax.set_title(T['b'], loc='left', fontsize=9, color=INK)

    # (c) 决策正确率、(d) 输入 token：分组柱，两个独立坐标轴
    def dec_acc(rs):
        v = [r['decisions_correct'] / r['decisions_total'] for r in rs if r.get('decisions_correct') is not None]
        return np.mean(v) if v else np.nan

    panels = [(['C1', 'C2', 'C3', 'C4', 'C5'], dec_acc, T['c'], None, lambda v: f'{v:.0%}'),
              (ORDER, lambda rs: np.mean([tokens(r.get('usage'))[0] for r in rs]) / 1e3, T['d'], T['tok'],
               lambda v: f'{v:.0f}')]
    for k, (cfgs, fn, title, unit, fmt) in enumerate(panels):
        ax = fig.add_subplot(gs[2, k])
        x = np.arange(len(cfgs))
        w = 0.38
        for j, (by, name) in enumerate(zip(data, a.names)):
            vals = [fn(by[c]) for c in cfgs]
            xs = x + (j - 0.5) * w
            ax.bar(xs, vals, width=w - 0.04, color=COLORS[j], label=name)
            if k == 1:
                for xi, v in zip(xs, vals):
                    ax.text(xi, v, fmt(v), ha='center', va='bottom', fontsize=6, color=INK, rotation=90)
        ax.set_xticks(x, cfgs)
        if k == 0:
            ax.set_ylim(0, 1)
            ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
        else:
            ax.set_ylabel(unit)
            ax.margins(y=0.3)
        ax.grid(axis='y', color=GRID, lw=0.6)
        _style(ax)
        ax.set_title(title, loc='left', fontsize=9, color=INK)

    out = a.out or os.path.join(a.paths[-1], f'fig_backbone_{a.lang}')
    fig.savefig(out + '.png', dpi=300, bbox_inches='tight', facecolor='white')
    fig.savefig(out + '.pdf', bbox_inches='tight', facecolor='white')
    print(out + '.png')


if __name__ == '__main__':
    main()

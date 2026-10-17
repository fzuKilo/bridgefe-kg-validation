"""结果图：python -m kgfem.plot_ablation runs_ablation_single [--lang en|zh]；主对比加 --preset main（runs_main）

(a) 各方案准确率与 95% bootstrap 置信区间；(b) 每题 3 次运行中的正确次数；(c) 每次运行的耗时与输入 token。
"""
import argparse
import json
import os
from collections import defaultdict

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import ListedColormap, BoundaryNorm

from .summarize import boot_ci, load, per_problem, tokens

ORDER = ['C5', 'A1', 'A1P', 'A2', 'A3', 'A4']
MAIN_ORDER = ['C0', 'C1', 'C2', 'C3', 'C4', 'C5']
MAIN_LABEL = {'en': {'C0': 'C0 direct script', 'C1': 'C1 direct decisions', 'C2': 'C2 prompt knowledge',
                     'C3': 'C3 retrieval', 'C4': 'C4 KG as tools', 'C5': 'C5 KG constraint'},
              'zh': {'C0': 'C0 直接生成脚本', 'C1': 'C1 直接生成决策', 'C2': 'C2 提示词知识', 'C3': 'C3 检索增强',
                     'C4': 'C4 图谱工具（不校验）', 'C5': 'C5 图谱约束（本文）'}}
LABEL = {'en': {'C5': 'C5 full method', 'A1': 'A1 −value check', 'A1P': 'A1+ −value check (all levels)',
                'A2': 'A2 −evidence/applicability', 'A3': 'A3 −consistency/instance', 'A4': 'A4 −feedback content'},
         'zh': {'C5': 'C5 完整方法', 'A1': 'A1 去掉决策级数值校验', 'A1P': 'A1+ 去掉全部数值校验',
                'A2': 'A2 去掉依据与适用性校验', 'A3': 'A3 去掉一致性与实例约束', 'A4': 'A4 反馈只保留“拒绝”'}}
TXT = {'en': dict(a='(a) Accuracy (mean over problems, 95% CI)', b='(b) Correct runs out of 3, per problem',
                  c='(c) Wall-clock time per run', d='(d) Input tokens per run', acc='Accuracy', t='s',
                  tok='thousand tokens', cb='correct runs'),
       'zh': dict(a='(a) 准确率（按题平均，95% 置信区间）', b='(b) 各题 3 次运行中的正确次数', c='(c) 每次运行耗时',
                  d='(d) 每次运行输入 token', acc='准确率', t='秒', tok='千 token', cb='正确次数')}

INK, INK2, GRID = '#0b0b0b', '#52514e', '#e4e3df'
ACCENT, NEUTRAL = '#2a78d6', '#8a8984'
SEQ = ['#f0efec', '#9ec5f4', '#3987e5', '#184f95']          # 0,1,2,3 次正确（单色相由浅到深）


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('path')
    ap.add_argument('--lang', default='en')
    ap.add_argument('--out', default=None)
    ap.add_argument('--preset', default='ablation', choices=['ablation', 'main'])
    a = ap.parse_args()
    L, T = LABEL[a.lang], TXT[a.lang]
    order = ORDER
    if a.preset == 'main':
        L, order = MAIN_LABEL[a.lang], MAIN_ORDER
    if a.lang == 'zh':
        plt.rcParams['font.sans-serif'] = ['PingFang SC', 'Heiti SC', 'Arial Unicode MS']
    plt.rcParams.update({'font.size': 8.5, 'axes.edgecolor': INK2, 'axes.labelcolor': INK, 'xtick.color': INK2,
                         'ytick.color': INK2, 'axes.linewidth': 0.6, 'axes.unicode_minus': False})
    rows = load(a.path)
    by = defaultdict(list)
    for r in rows:
        by[r['config']].append(r)
    cfgs = [c for c in order if c in by]
    probs = sorted({r['problem'] for r in rows})

    fig = plt.figure(figsize=(7.2, 6.6))
    gs = fig.add_gridspec(3, 2, height_ratios=[1.15, 1.25, 0.95], hspace=0.62, wspace=0.28)

    # (a) 准确率与置信区间
    ax = fig.add_subplot(gs[0, :])
    y = np.arange(len(cfgs))[::-1]
    for yi, c in zip(y, cfgs):
        pp = list(per_problem(by[c])[0].values())
        m, (lo, hi) = float(np.mean(pp)), boot_ci(pp)
        col = ACCENT if c == 'C5' else NEUTRAL
        ax.plot([lo, hi], [yi, yi], color=col, lw=2, solid_capstyle='round', clip_on=False)
        ax.plot(m, yi, 'o', ms=7, color=col, mec='white', mew=1.5, zorder=3, clip_on=False)
        ax.text(1.018, yi, f'{m:.1%}', va='center', ha='left', color=INK, fontsize=8)
    ax.set_yticks(y, [L[c] for c in cfgs])
    lows = [boot_ci(list(per_problem(by[c])[0].values()))[0] for c in cfgs]
    ax.set_xlim(max(0.0, np.floor(min(lows) * 10 - 0.5) / 10), 1.0)
    ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    ax.grid(axis='x', color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    for s in ('top', 'right'):
        ax.spines[s].set_visible(False)
    ax.set_title(T['a'], loc='left', fontsize=9, color=INK)

    # (b) 每题正确次数热图
    ax = fig.add_subplot(gs[1, :])
    M = np.full((len(cfgs), len(probs)), np.nan)
    for i, c in enumerate(cfgs):
        cnt = defaultdict(int)
        for r in by[c]:
            cnt[r['problem']] += bool(r['correct'])
        for j, p in enumerate(probs):
            M[i, j] = cnt[p]
    cmap = ListedColormap(SEQ)
    im = ax.imshow(M, cmap=cmap, norm=BoundaryNorm([-0.5, 0.5, 1.5, 2.5, 3.5], 4), aspect='auto')
    ax.set_xticks(np.arange(len(probs)), probs, rotation=90, fontsize=7)
    ax.set_yticks(np.arange(len(cfgs)), [c.replace('A1P', 'A1+') for c in cfgs])
    ax.set_xticks(np.arange(-0.5, len(probs)), minor=True)
    ax.set_yticks(np.arange(-0.5, len(cfgs)), minor=True)
    ax.grid(which='minor', color='white', lw=1.5)
    ax.tick_params(which='minor', length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    for i in range(len(cfgs)):
        for j in range(len(probs)):
            if M[i, j] < 3:
                ax.text(j, i, int(M[i, j]), ha='center', va='center', fontsize=7,
                        color='white' if M[i, j] >= 2 else INK)
    for x in (9.5, 19.5):                                    # 档位分隔
        ax.axvline(x, color=INK2, lw=0.8)
    cb = fig.colorbar(im, ax=ax, ticks=[0, 1, 2, 3], fraction=0.025, pad=0.01)
    cb.set_label(T['cb'], color=INK2)
    cb.outline.set_visible(False)
    ax.set_title(T['b'], loc='left', fontsize=9, color=INK)

    # (c)(d) 耗时与输入 token（两个独立坐标轴，不共用双纵轴）
    for k, (key, title, unit) in enumerate([('wall_s', T['c'], T['t']), ('tok', T['d'], T['tok'])]):
        ax = fig.add_subplot(gs[2, k])
        vals = []
        for c in cfgs:
            if key == 'wall_s':
                vals.append(np.mean([r['wall_s'] for r in by[c]]))
            else:
                vals.append(np.mean([tokens(r.get('usage'))[0] for r in by[c]]) / 1e3)
        x = np.arange(len(cfgs))
        ax.bar(x, vals, width=0.62, color=[ACCENT if c == 'C5' else NEUTRAL for c in cfgs])
        for xi, v in zip(x, vals):
            ax.text(xi, v, f'{v:.0f}', ha='center', va='bottom', fontsize=7.5, color=INK)
        ax.set_xticks(x, [c.replace('A1P', 'A1+') for c in cfgs])
        ax.set_ylabel(unit)
        ax.grid(axis='y', color=GRID, lw=0.6)
        ax.set_axisbelow(True)
        for s in ('top', 'right'):
            ax.spines[s].set_visible(False)
        ax.set_title(title, loc='left', fontsize=9, color=INK)
        ax.margins(y=0.15)

    out = a.out or os.path.join(a.path, f'fig_{a.preset}_{a.lang}')
    fig.savefig(out + '.png', dpi=300, bbox_inches='tight', facecolor='white')
    fig.savefig(out + '.pdf', bbox_inches='tight', facecolor='white')
    print(out + '.png')


if __name__ == '__main__':
    main()

"""汇总批量实验结果（论文表 3 指标）：python -m kgfem.summarize runs_ablation [--base C5]

每个方案：按题准确率的平均值与 95% bootstrap 置信区间（按题目重抽样 10,000 次）、全部运行均正确的题目数、
分类决策正确率、首次提案违反率、修复轮次、耗时与 token；与基准方案按各题准确率作 Wilcoxon 符号秩检验（Holm 校正）。
"""
import argparse
import json
import os
from collections import defaultdict

import numpy as np
from scipy.stats import wilcoxon

ORDER = ['C0', 'C1', 'C2', 'C3', 'C4', 'C5', 'A1', 'A1P', 'A2', 'A3', 'A4', 'A5', 'A6']


def load(path):
    rows = [json.loads(line) for line in open(os.path.join(path, 'results.jsonl'), encoding='utf-8')]
    keep = {}
    for r in rows:                                     # 同一作业以最后一次无程序错误的结果为准
        if not r.get('error'):
            keep[(r['config'], r['problem'], r['rep'])] = r
    return list(keep.values())


def per_problem(rows):
    acc = defaultdict(list)
    for r in rows:
        acc[r['problem']].append(bool(r['correct']))
    return {p: float(np.mean(v)) for p, v in acc.items()}, {p: all(v) for p, v in acc.items()}


def boot_ci(vals, n=10000, seed=20261016):
    v = np.array(vals)
    rng = np.random.default_rng(seed)
    m = rng.choice(v, size=(n, len(v)), replace=True).mean(axis=1)
    return float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))


def tokens(u):
    if not u:
        return 0, 0
    if isinstance(u, dict) and 'roles' in u:
        us = [r.get('usage') or {} for r in u['roles'] if isinstance(r, dict)]
    else:
        us = [u]
    return sum(x.get('prompt_tokens', 0) for x in us), sum(x.get('output_tokens', 0) for x in us)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('path')
    ap.add_argument('--base', default='C5')
    a = ap.parse_args()
    rows = load(a.path)
    by_cfg = defaultdict(list)
    for r in rows:
        by_cfg[r['config']].append(r)
    cfgs = sorted(by_cfg, key=lambda c: ORDER.index(c) if c in ORDER else 99)
    base_pp = per_problem(by_cfg[a.base])[0] if a.base in by_cfg else None
    tests = []
    print(f"{'config':6} {'runs':>5} {'acc':>6} {'95% CI':>15} {'all-ok':>7} {'dec-acc':>8} {'rule':>6} {'code':>6} "
          f"{'topo':>6} {'viol1':>6} {'repair':>6} {'time s':>7} {'in-tok':>8} {'out-tok':>8}")
    summary = {}
    for c in cfgs:
        rs = by_cfg[c]
        pp, allok = per_problem(rs)
        vals = list(pp.values())
        lo, hi = boot_ci(vals)
        dec = [r['decisions_correct'] / r['decisions_total'] for r in rs
               if r.get('decisions_correct') is not None and r.get('decisions_total')]
        cats = defaultdict(list)
        for r in rs:
            for k, v in (r.get('decision_accuracy_by_category') or {}).items():
                cats[k].append(v)
        vio = [(r.get('metrics') or {}).get('first_proposal_violation_rate') for r in rs]
        vio = [v for v in vio if v is not None]
        rep = [(r.get('metrics') or {}).get('repair_rounds') or 0 for r in rs]
        tok = [tokens(r.get('usage')) for r in rs]
        s = {'runs': len(rs), 'accuracy': float(np.mean(vals)), 'ci95': [lo, hi], 'problems_all_correct': sum(allok.values()),
             'problems': len(pp), 'decision_accuracy': float(np.mean(dec)) if dec else None,
             'first_violation_rate': float(np.mean(vio)) if vio else None, 'repair_rounds': float(np.mean(rep)),
             'wall_s': float(np.mean([r['wall_s'] for r in rs])),
             'prompt_tokens': float(np.mean([t[0] for t in tok])), 'output_tokens': float(np.mean([t[1] for t in tok]))}
        summary[c] = s
        f = lambda x: '   -  ' if x is None else f'{x:6.3f}'
        print(f"{c:6} {s['runs']:5d} {s['accuracy']:6.3f} [{lo:5.3f},{hi:5.3f}] {s['problems_all_correct']:3d}/{s['problems']:<3d} "
              f"{f(s['decision_accuracy']):>8} {f(np.mean(cats['modeling_rule']) if cats['modeling_rule'] else None)} "
              f"{f(np.mean(cats['code_parameter']) if cats['code_parameter'] else None)} "
              f"{f(np.mean(cats['topology']) if cats['topology'] else None)} {f(s['first_violation_rate'])} "
              f"{s['repair_rounds']:6.2f} {s['wall_s']:7.1f} {s['prompt_tokens']:8.0f} {s['output_tokens']:8.0f}")
        if base_pp and c != a.base:
            common = sorted(set(pp) & set(base_pp))
            d = [base_pp[p] - pp[p] for p in common]
            p = float(wilcoxon(d).pvalue) if any(d) else 1.0
            tests.append((c, p))
    if tests:
        tests.sort(key=lambda t: t[1])
        m = len(tests)
        print(f'\nWilcoxon signed-rank vs {a.base} (per-problem accuracy), Holm-adjusted:')
        adj_prev = 0
        for i, (c, p) in enumerate(tests):
            adj = max(adj_prev, min(1.0, (m - i) * p))
            adj_prev = adj
            summary[c]['p_vs_base_holm'] = adj
            print(f'  {c:6} p = {p:.4g}  p_holm = {adj:.4g}  {"*" if adj < 0.05 else ""}')
    with open(os.path.join(a.path, 'summary_stats.json'), 'w', encoding='utf-8') as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()

"""并行批量实验（论文 3.7 节实验矩阵）。每个作业 = (方案, 题目, 第几次运行)，结果逐条追加到 results.jsonl，
中断后重跑同一命令会跳过已完成的作业。

  python -m kgfem.batch --configs C5 A1 A1P A2 A3 A4 --runs 3 --workers 8 --out runs_ablation_single
  python -m kgfem.batch --configs C0 C1 --runs 5 --out runs_ablation                # DeepSeek-V4-Flash 思考模式直接生成
"""
import argparse
import glob
import json
import os
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed

from .cli import BENCH, ROOT, read_input

PROVIDER = 'deepseek'          # 由 --provider 设置：deepseek | openai

CONFIGS = {                    # 方案 → (消融开关, 智能体组织)。本文方法为单智能体（单一角色、全部工具）
    'C5': ([], 'single'),
    'A1': (['A1'], 'single'), 'A1P': (['A1', 'A1P'], 'single'), 'A2': (['A2'], 'single'),
    'A3': (['A3'], 'single'), 'A4': (['A4'], 'single'), 'A5': (['A5'], 'single'), 'F0': (['F0'], 'single'),
    'M4': ([], 'multi'),       # 按图谱四层分工的多智能体版本（已不写入论文，仅保留代码与早期结果）
    'C0': ([], 'direct_script'), 'C1': ([], 'direct_decisions'),      # 直接生成基线（默认用 --direct-model）
    'C2': ([], 'baseline'), 'C3': ([], 'baseline'), 'C4': ([], 'baseline'),   # 智能体基线（agent/baselines.py）
    'C4B': (['DEFECT'], 'baseline'), 'C5B': (['DEFECT'], 'single'),      # 边界输入实验：可报告输入缺陷
}


def _baseline(cfg, pid, rep, out, model, think):
    from .agent.backends import make_backend
    from .agent.baselines import run_baseline
    from .agent.session import ModelingSession
    from .evaluate import evaluate_run
    base, text = read_input(pid)
    s = ModelingSession(os.path.join(out, cfg, f'{pid}_r{rep}'), base)
    usage = run_baseline(cfg.rstrip('B'), s, make_backend(PROVIDER, model, think), text)
    path = s.save()
    ev = evaluate_run(os.path.join(BENCH, 'problems', f'{base}.json'), path)
    ev['usage'] = usage
    ev['defect'] = s.defect
    return ev


def _direct(cfg, pid, rep, out, model, think):
    from .agent.backends import make_backend
    from .agent.direct import evaluate_c0, run_c0, run_c1
    from .agent.session import ModelingSession
    from .evaluate import evaluate_run
    base, text = read_input(pid)
    s = ModelingSession(os.path.join(out, cfg, f'{pid}_r{rep}'), base)
    usage = (run_c0 if cfg == 'C0' else run_c1)(s, make_backend(PROVIDER, model, think, timeout=3600), text)
    path = s.save()
    prob = os.path.join(BENCH, 'problems', f'{base}.json')
    ev = evaluate_c0(prob, path) if cfg == 'C0' else evaluate_run(prob, path)
    ev['usage'] = usage
    return ev


def _job(cfg, pid, rep, out, model, think, direct, provider='deepseek'):
    global PROVIDER
    PROVIDER = provider
    from . import ablation
    from .cli import run_one
    flags, agents = CONFIGS[cfg]
    ablation.set_active(flags)
    args = argparse.Namespace(backend=provider, agents=agents, model=model, think=think, lang='en', repeat=2,
                              out=os.path.join(out, cfg), faults=[], model_faults=[], mock_instance_fault=False)
    t0 = time.time()
    try:
        if agents.startswith('direct'):
            ev = _direct(cfg, pid, rep, out, *direct)
        elif agents == 'baseline':
            ev = _baseline(cfg, pid, rep, out, model, think)
        else:
            ev = run_one(pid, args, rep)
        err = None
    except Exception:                                   # 程序错误：记录并上报，由调度方暂停修复
        ev, err = {}, traceback.format_exc()
    return {'config': cfg, 'problem': pid, 'rep': rep, 'error': err, 'wall_s': round(time.time() - t0, 1),
            'correct': ev.get('correct'), 'decisions_correct': ev.get('decisions_correct'),
            'decisions_total': ev.get('decisions_total'), 'executed': ev.get('executed'),
            'decision_accuracy_by_category': ev.get('decision_accuracy_by_category'),
            'wrong_decisions': ev.get('wrong_decisions'),
            'responses': ev.get('responses'), 'metrics': ev.get('metrics'), 'usage': ev.get('usage'),
            'defect': ev.get('defect')}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--configs', nargs='+', default=['C5'])
    ap.add_argument('--runs', type=int, default=5)
    ap.add_argument('--problems', nargs='*', default=[])
    ap.add_argument('--tiers', default='ABC')
    ap.add_argument('--boundary', action='store_true', help='边界输入 BD1–BD6，外加其原题（误报对照）')
    ap.add_argument('--free-text', action='store_true',
                    help='输入鲁棒性：--problems 中各题的 3 种自由文本 × 中英文，外加中文结构化输入')
    ap.add_argument('--workers', type=int, default=8)
    ap.add_argument('--provider', default='deepseek', choices=['deepseek', 'openai'],
                    help='openai：GPT 官方或第三方中转，需环境变量 OPENAI_API_KEY 与 OPENAI_BASE_URL')
    ap.add_argument('--model', default='deepseek-flash')
    ap.add_argument('--think', action='store_true')
    ap.add_argument('--direct-model', default='deepseek-flash', help='C0/C1 直接生成所用模型（与主实验相同的 DeepSeek-V4-Flash，默认开启思考）')
    ap.add_argument('--direct-no-think', action='store_true')
    ap.add_argument('--out', default=os.path.join(ROOT, 'runs_ablation'))
    ap.add_argument('--stop-on-error', type=int, default=1, help='出现几次程序错误后停止派发新作业')
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    res_path = os.path.join(a.out, 'results.jsonl')
    done = set()
    if os.path.exists(res_path):
        for line in open(res_path, encoding='utf-8'):
            r = json.loads(line)
            if not r.get('error'):
                done.add((r['config'], r['problem'], r['rep']))
    pids = a.problems or sorted(os.path.basename(p)[:-5] for p in glob.glob(os.path.join(BENCH, 'problems', '*.json'))
                                if os.path.basename(p)[0] in a.tiers)
    if a.boundary:
        idx = json.load(open(os.path.join(BENCH, 'boundary', 'index.json'), encoding='utf-8'))
        pids = sorted(idx) + sorted({v['base'] for v in idx.values()})
    if a.free_text:
        pids = [f'{p}_{v}' for p in pids for v in ['zh'] + [f's{k}_{lg}' for k in (1, 2, 3) for lg in ('en', 'zh')]]
    jobs = [(c, p, r) for r in range(1, a.runs + 1) for c in a.configs for p in pids if (c, p, r) not in done]
    print(f'{len(jobs)} jobs ({len(done)} already done)', flush=True)
    errors = 0
    with ProcessPoolExecutor(max_workers=a.workers) as ex, open(res_path, 'a', encoding='utf-8') as fh:
        futs = {ex.submit(_job, c, p, r, a.out, a.model, a.think, (a.direct_model, not a.direct_no_think), a.provider): (c, p, r) for c, p, r in jobs}
        for f in as_completed(futs):
            r = f.result()
            fh.write(json.dumps(r, ensure_ascii=False, default=str) + '\n')
            fh.flush()
            tag = 'ERROR' if r['error'] else ('ok' if r['correct'] else 'wrong')
            print(f"{r['config']} {r['problem']} r{r['rep']}: {tag} "
                  f"{r['decisions_correct']}/{r['decisions_total']} {r['wall_s']}s", flush=True)
            if r['error']:
                errors += 1
                print(r['error'][-1500:], flush=True)
                if errors >= a.stop_on_error:
                    print('程序错误，停止派发新作业；修复后重跑同一命令续跑', flush=True)
                    for g in futs:
                        g.cancel()
                    break


if __name__ == '__main__':
    main()

"""命令行入口。

  python -m kgfem.cli run --backend scripted --problems A01 B03 C06
  python -m kgfem.cli run --backend claude --model claude-opus-5 --problems A01 --repeat 10
  python -m kgfem.cli run --backend ollama --model qwen3.5:9b --problems A01            # 多智能体（默认）
  python -m kgfem.cli run --backend ollama --agents single --problems A01               # 单智能体（消融）
  python -m kgfem.cli run --backend deepseek --problems A01                              # 需先设置 DEEPSEEK_API_KEY
  python -m kgfem.cli run --backend openai --model gpt-4.1 --agents single --problems A01  # 需 OPENAI_API_KEY、OPENAI_BASE_URL
  python -m kgfem.cli run --backend mock --all                                           # 模拟后端自检
  python -m kgfem.cli run --backend scripted --all --faults lane.Pk.{j}=scale support.{k}.Kv=wrong_clause
  python -m kgfem.cli run --backend scripted --all --model-faults girder.w=1.1
"""
import argparse
import glob
import json
import os
import re

from .agent.session import ModelingSession
from .evaluate import evaluate_run

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BENCH = os.path.join(ROOT, 'bridgefe_bench')


def read_input(pid, lang='en'):
    """题目编号 → (原题编号, 输入文字)。A03 读结构化输入（按 lang）；A03_zh 读中文结构化输入；
    A03_s1_en 读自由文本改写（free_text/）。"""
    if re.fullmatch(r'BD\d', pid):                    # 边界输入（boundary/），按原题评估
        idx = json.load(open(os.path.join(BENCH, 'boundary', 'index.json'), encoding='utf-8'))
        return idx[pid]['base'], open(os.path.join(BENCH, 'boundary', f'{pid}_en.txt'), encoding='utf-8').read()
    m = re.fullmatch(r'([A-Z]\d\d)(?:_(s\d))?(?:_(en|zh))?', pid)
    if not m:
        raise ValueError(f'无法识别的题目编号：{pid}')
    base, style, lg = m.group(1), m.group(2), m.group(3) or lang
    path = (os.path.join(BENCH, 'free_text', f'{base}_{style}_{lg}.txt') if style
            else os.path.join(BENCH, 'inputs', f'{base}_{lg}.txt'))
    return base, open(path, encoding='utf-8').read()


def run_one(pid, args, rep):
    base, text = read_input(pid, args.lang)
    out_dir = os.path.join(args.out, pid if args.repeat == 1 else f'{pid}_r{rep}')
    session = ModelingSession(out_dir, base)
    if args.backend == 'scripted':
        from .agent.scripted import ScriptedAgent
        faults = dict(f.split('=') for f in args.faults)
        mfaults = {k: float(v) for k, v in (f.split('=') for f in args.model_faults)}
        ScriptedAgent(session, faults, mfaults).run(text)
        usage = None
    elif args.agents == 'multi':
        from .agent.backends import ClaudeBackend, OllamaBackend
        from .agent.multi import BridgeModelingFlow
        if args.backend == 'ollama':
            backend = OllamaBackend(model=args.model or 'qwen3.5:9b', host=args.host, num_ctx=args.num_ctx,
                                    think=not args.no_think)
        elif args.backend in ('deepseek', 'openai'):
            from .agent.backends import make_backend
            backend = make_backend(args.backend, args.model, args.think)
        elif args.backend == 'mock':
            from .tests.mock_backend import MockBackend
            backend = MockBackend(session, text, instance_fault=args.mock_instance_fault)
        else:
            backend = ClaudeBackend(model=args.model or 'claude-opus-5', effort=args.effort)
        usage = BridgeModelingFlow(session, backend).run(text)
    elif args.backend in ('deepseek', 'openai'):              # 单智能体：同一套提示词与全部工具
        from .agent.backends import make_backend, session_dispatch
        from .agent.claude import SYSTEM_PROMPT
        from .agent.tools import SESSION_TOOLS
        from . import ablation
        from .agent.tools import DEFECT_RULE
        names = [t['name'] for t in SESSION_TOOLS]
        prompt = SYSTEM_PROMPT
        if ablation.on('DEFECT'):                      # 边界输入实验：可报告输入缺陷
            names.append('report_input_defect')
            prompt += DEFECT_RULE
        usage = make_backend(args.backend, args.model, args.think).run(
            prompt, names, f'Bridge description:\n\n{text}', session_dispatch(session, set(names)),
            is_done=lambda: session.done, max_turns=200)
    elif args.backend == 'ollama':
        from .agent.local import OllamaDriver
        usage = OllamaDriver(session, model=args.model or 'qwen3.5:9b', host=args.host, num_ctx=args.num_ctx,
                             think=not args.no_think).run(text)
    else:
        from .agent.claude import ClaudeDriver
        usage = ClaudeDriver(session, model=args.model or 'claude-opus-5', effort=args.effort).run(text)
    path = session.save()
    ev = evaluate_run(os.path.join(BENCH, 'problems', f'{base}.json'), path)
    ev['usage'] = usage
    ev['defect'] = session.defect
    return ev


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    r = sub.add_parser('run')
    r.add_argument('--backend', choices=['scripted', 'claude', 'ollama', 'deepseek', 'openai', 'mock'], default='scripted')
    r.add_argument('--agents', choices=['multi', 'single'], default='multi',
                   help='multi：按图谱四层分工的多智能体（默认）；single：单智能体（消融对照）')
    r.add_argument('--mock-instance-fault', action='store_true')
    r.add_argument('--model', default=None, help='claude 默认 claude-opus-5；ollama 默认 qwen3.5:9b；deepseek 默认 deepseek-flash（不思考）')
    r.add_argument('--host', default='http://localhost:11434')
    r.add_argument('--num-ctx', type=int, default=32768)
    r.add_argument('--no-think', action='store_true', help='ollama：关闭思考模式')
    r.add_argument('--think', action='store_true', help='deepseek：开启思考模式（默认关闭）')
    r.add_argument('--effort', default='high')
    r.add_argument('--problems', nargs='*', default=[])
    r.add_argument('--all', action='store_true')
    r.add_argument('--repeat', type=int, default=1)
    r.add_argument('--lang', default='en')
    r.add_argument('--faults', nargs='*', default=[])
    r.add_argument('--model-faults', nargs='*', default=[])
    r.add_argument('--out', default=os.path.join(ROOT, 'runs'))
    r.add_argument('--ablation', nargs='*', default=[], choices=['A1', 'A1P', 'A2', 'A3', 'A4', 'A5', 'F0'],
                   help='消融开关（见 kgfem/ablation.py）；A6 用 --agents single')
    a = ap.parse_args()
    from . import ablation
    ablation.set_active(a.ablation)
    ids = a.problems or sorted(os.path.basename(p)[:-5] for p in glob.glob(os.path.join(BENCH, 'problems', '*.json')))
    rows = []
    for pid in ids:
        for rep in range(1, a.repeat + 1):
            ev = run_one(pid, a, rep)
            rows.append(ev)
            m = ev['metrics'] or {}
            print(f"{pid} r{rep}: correct={ev['correct']} decisions={ev['decisions_correct']}/{ev['decisions_total']} "
                  f"responses={all(ev['responses'].values()) if ev['responses'] else False} "
                  f"first_violation_rate={m.get('first_proposal_violation_rate')} repair_rounds={m.get('repair_rounds')} "
                  f"elapsed={m.get('elapsed_s')}s", flush=True)
            for w in ev['wrong_decisions'][:5]:
                print('   wrong:', w, flush=True)
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, 'summary.json'), 'w', encoding='utf-8') as fh:
        json.dump(rows, fh, ensure_ascii=False, indent=1, default=str)
    acc = sum(r['correct'] for r in rows) / len(rows)
    print(f'accuracy = {acc:.3f} over {len(rows)} runs')


if __name__ == '__main__':
    main()

"""注入错误实验（论文 3.7 节、5.3 节，检验 H3）。

每个错误：脚本化智能体按真实实例作出全部决策并通过校验后，绕过决策级校验直接改写一项已接受决策或实例字段，
生成模型；模型校核的结果交给大模型智能体修复。三种信号：带定位的结构化反馈（C5）、不带定位（A5）、仅告知失败（F0）。

  python -m kgfem.faults --check                                   # 脚本化预检：每个错误能否被检出、定位是否命中
  python -m kgfem.faults --signals C5 A5 F0 --runs 10 --workers 8 --out runs_faults
"""
import argparse
import copy
import json
import os
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed

from .cli import BENCH, ROOT, read_input

# (编号, 类别, 题目, 注入方式, 目标, 新值, 说明)。decision：改写已接受决策的取值；instance：改写实例字段（路径）
FAULTS = [
    ('R1', 'modeling_rule', 'B03', 'decision', 'structure.system', 'simply_supported', '连续体系按简支建模'),
    ('R2', 'modeling_rule', 'B03', 'decision', 'support.1.dofs',
     {'vertical': 'spring', 'longitudinal': 'free', 'rotation': 'free'}, '固定支座纵向放松'),
    ('R3', 'modeling_rule', 'C02', 'decision', 'support.0.dofs',
     {'vertical': 'spring', 'longitudinal': 'spring', 'rotation': 'free'}, '滑动支座纵向约束'),
    ('R4', 'modeling_rule', 'A08', 'decision', 'girder.A', '@girder.single.A', '多片梁未合并（面积取单片）'),
    ('R5', 'modeling_rule', 'C05', 'decision', 'structure.system', 'continuous', '未模拟桥墩'),
    ('K1', 'code_parameter', 'A03', 'decision', 'lane.qk', 10.5, '公路-II 级取了 I 级 qk'),
    ('K2', 'code_parameter', 'A08', 'decision', 'lane.xi', 0.78, '横向折减系数取错'),
    ('K3', 'code_parameter', 'B03', 'decision', 'girder.Ec', 32500.0, '弹性模量按 C40 取值'),
    ('K4', 'code_parameter', 'B06', 'decision', 'lane.Pk.2', 360.0, 'Pk 按 50 m 跨径取值'),
    ('K5', 'code_parameter', 'C05', 'decision', 'lane.mu', 0.25, '冲击系数与基频不符'),
    ('T1', 'topology', 'C02', 'decision', ['support.1.bearing', 'support.2.bearing'],
     [{'type': 'ptfe_sliding', 'count': 2}, {'type': 'plain_elastomeric', 'count': 2}], '固定支座设在错误的墩上'),
    ('T2', 'topology', 'C02', 'decision', ['pier.1.length', 'pier.2.length'], [27.0, 20.0], '两墩高度对调'),
    ('T3', 'topology', 'C05', 'decision', 'support.2.Kv', '@support.1.Kv', '支承线 2 取了支承线 1 的竖向刚度'),
    ('T4', 'topology', 'B03', 'decision', 'support.3.dofs',
     {'vertical': 'spring', 'longitudinal': 'spring', 'rotation': 'free'}, '桥台按固定支座约束，形成两条固定支承线'),
    ('T5', 'topology', 'B06', 'decision', 'support.0.bearing', {'type': 'plain_elastomeric', 'count': 6},
     '桥台滑动支座定为固定支座'),
    ('I1', 'input_interpretation', 'B06', 'instance', 'supports[*].bearing.per_girder_end', 2, '每梁端支座数读成 2'),
    ('I2', 'input_interpretation', 'A03', 'instance', 'girder.section.t_top', 0.20, '顶板厚 0.18 m 读成 0.20 m'),
    ('I3', 'input_interpretation', 'C05', 'instance', 'spans_m[1]', 45.0, '主跨 50 m 读成 45 m'),
    ('I4', 'input_interpretation', 'A08', 'instance', 'girder.count_per_span', 4, '主梁片数 3 读成 4'),
    ('I5', 'input_interpretation', 'C02', 'instance', 'supports[1].bearing.t1_mm', 8.0, '橡胶层厚 11 mm 读成 8 mm'),
]
SIGNALS = {'C5': [], 'A5': ['A5'], 'F0': ['F0']}
REPAIR_PROMPT = (
    'Bridge description:\n\n{text}\n\n'
    'State of the session: the instance has been written and every decision has been accepted. The model was then '
    'generated and FAILED its checks. The result of generate_model is:\n\n{result}\n\n'
    'Diagnose the root cause. It may lie in an accepted decision or in the instance (compare the instance with the '
    'description). Repair it with the tools—revise the responsible decisions with propose_decision, or correct the '
    'instance with write_instance and then re-decide what is withdrawn—regenerate the model, and call finish once the '
    'model passes its checks.')


def prepare(pid):
    """脚本化智能体作出全部正确决策（不生成模型），返回会话。"""
    from .agent.scripted import ScriptedAgent, parse_structured_en
    from .agent.session import ModelingSession
    return ScriptedAgent, parse_structured_en, ModelingSession


def _set_path(data, path, value):
    """path 形如 girder.section.t_top、spans_m[1]、supports[*].bearing.per_girder_end、supports[1].bearing.t1_mm。"""
    import re
    parts = re.findall(r'[^.\[\]]+|\[\*\]|\[\d+\]', path)
    nodes = [data]
    for i, p in enumerate(parts):
        last = i == len(parts) - 1
        nxt = []
        for n in nodes:
            if p == '[*]':
                nxt.extend(n)
            elif p.startswith('['):
                k = int(p[1:-1])
                if last:
                    n[k] = value
                else:
                    nxt.append(n[k])
            elif last:
                if n is not None:
                    n[p] = value
            else:
                nxt.append(n.get(p) if isinstance(n, dict) else None)
        nodes = [n for n in nxt if n is not None]


def build_faulted_session(fault, workdir):
    """按真实实例作出全部决策，再注入错误。返回 (会话, 输入文字, 注入前的已接受决策)。"""
    from .agent.scripted import ScriptedAgent, parse_structured_en
    from .agent.session import ModelingSession
    fid, cat, pid, how, target, value, _ = fault
    _, text = read_input(pid)
    s = ModelingSession(workdir, pid)
    agent = ScriptedAgent(s)
    s.write_instance(parse_structured_en(text))
    slots = s.inst.required_slots()
    s.declare_decisions(slots)
    for slot in [x for x in slots if x != 'lane.mu']:
        agent._decide(slot)
    s.run_modal_analysis()
    agent._decide('lane.mu')
    assert all(x in s.val.accepted for x in slots), 'scripted preparation incomplete'
    if how == 'decision':
        targets, values = (target, value) if isinstance(target, list) else ([target], [value])
        for t, v in zip(targets, values):
            if isinstance(v, str) and v.startswith('@'):
                v = s.val.accepted[v[1:]]['value']
            s.val.accepted[t]['value'] = copy.deepcopy(v)
    else:
        _set_path(s.inst.data, target, value)
    s.log.clear()
    return s, text


def responsible(fault):
    """该错误的责任对象：决策错误为被改写的槽位；实例错误为实例（以 'instance' 表示）。"""
    how, target = fault[3], fault[4]
    if how == 'instance':
        return {'instance'}
    return set(target) if isinstance(target, list) else {target}


def check_only(out):
    """脚本化预检：注入后首次生成模型的检出层级与定位。"""
    from . import ablation
    rows = []
    for f in FAULTS:
        ablation.set_active([])
        s, _ = build_faulted_session(f, os.path.join(out, 'check', f[0]))
        res = s.generate_model()
        fails = res.get('failed_checks') or []
        suspects = {d['slot'] for x in fails for d in x['suspect_decisions']}
        resp = responsible(f)
        rows.append({'fault': f[0], 'category': f[1], 'problem': f[2], 'desc': f[6], 'detected': not res['ok'],
                     'stage': res.get('stage'), 'checks': sorted({x['constraint'] for x in fails}),
                     'n_suspects': len(suspects), 'suspects': sorted(suspects),
                     'localized': bool(resp & suspects) if 'instance' not in resp else None})
        print(json.dumps(rows[-1], ensure_ascii=False), flush=True)
    return rows


def _job(fid, signal, rep, out, provider, model):
    from . import ablation
    from .agent.backends import make_backend, session_dispatch
    from .agent.claude import SYSTEM_PROMPT
    from .agent.tools import SESSION_TOOLS
    from .evaluate import evaluate_run
    fault = next(f for f in FAULTS if f[0] == fid)
    t0 = time.time()
    try:
        ablation.set_active(SIGNALS[signal])
        s, text = build_faulted_session(fault, os.path.join(out, signal, f'{fid}_r{rep}'))
        first = s.generate_model()
        usage, detected = None, not first['ok']
        if detected:
            names = [t['name'] for t in SESSION_TOOLS]
            prompt = REPAIR_PROMPT.format(text=text, result=json.dumps(
                {k: v for k, v in first.items() if k != 'script'}, ensure_ascii=False, default=str))
            usage = make_backend(provider, model).run(SYSTEM_PROMPT, names, prompt, session_dispatch(s, set(names)),
                                                      is_done=lambda: s.done, max_turns=120)
        path = s.save()
        ev = evaluate_run(os.path.join(BENCH, 'problems', f'{fault[2]}.json'), path)
        gens = [e for e in s.log if e.get('tool') == 'generate_model']
        err = None
    except Exception:
        ev, err, detected, gens, usage = {}, traceback.format_exc(), None, [], None
    return {'fault': fid, 'category': fault[1], 'problem': fault[2], 'signal': signal, 'rep': rep, 'error': err,
            'wall_s': round(time.time() - t0, 1), 'detected': detected, 'correct': ev.get('correct'),
            'repair_rounds': len(gens), 'wrong_decisions': ev.get('wrong_decisions'), 'usage': usage,
            'model_passed': (ev.get('metrics') or {}).get('model_passed')}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--signals', nargs='+', default=['C5', 'A5', 'F0'])
    ap.add_argument('--faults', nargs='*', default=[])
    ap.add_argument('--runs', type=int, default=10)
    ap.add_argument('--workers', type=int, default=8)
    ap.add_argument('--provider', default='deepseek')
    ap.add_argument('--model', default='deepseek-flash')
    ap.add_argument('--out', default=os.path.join(ROOT, 'runs_faults'))
    ap.add_argument('--stop-on-error', type=int, default=1)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    if a.check:
        rows = check_only(a.out)
        json.dump(rows, open(os.path.join(a.out, 'check.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        return
    res_path = os.path.join(a.out, 'results.jsonl')
    done = set()
    if os.path.exists(res_path):
        for line in open(res_path, encoding='utf-8'):
            r = json.loads(line)
            if not r.get('error'):
                done.add((r['fault'], r['signal'], r['rep']))
    fids = a.faults or [f[0] for f in FAULTS]
    jobs = [(f, sg, r) for r in range(1, a.runs + 1) for sg in a.signals for f in fids if (f, sg, r) not in done]
    print(f'{len(jobs)} jobs ({len(done)} already done)', flush=True)
    errors = 0
    with ProcessPoolExecutor(max_workers=a.workers) as ex, open(res_path, 'a', encoding='utf-8') as fh:
        futs = {ex.submit(_job, f, sg, r, a.out, a.provider, a.model): (f, sg, r) for f, sg, r in jobs}
        for fu in as_completed(futs):
            r = fu.result()
            fh.write(json.dumps(r, ensure_ascii=False, default=str) + '\n')
            fh.flush()
            tag = 'ERROR' if r['error'] else ('ok' if r['correct'] else 'wrong')
            print(f"{r['signal']} {r['fault']} r{r['rep']}: {tag} rounds={r['repair_rounds']} {r['wall_s']}s", flush=True)
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

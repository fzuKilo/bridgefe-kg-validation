"""Non-LLM baseline R: frozen rule-based parser + the same KG, validator, modal analysis and generator.

Pipeline per input: parse (analysis/rule_parser.py, frozen) -> write_instance -> deterministic
completion of all decisions from the governing KG nodes (same selector as the deterministic
replay, analysis/run_control.py) -> generate_model -> evaluate. No LLM calls. The parser and the
selector read no reference answers; evaluation reads them only after the session is saved.
R is deterministic, so each input is run once.
"""
from pathlib import Path
import json, sys, copy, time, hashlib, importlib.util, shutil
P = Path(__file__).resolve().parent; R = P.parent; sys.path.insert(0, str(R)); sys.path.insert(0, str(P))
_archived = R / 'supplementary/replay_20261017/validator_evaluated.py'
_spec = importlib.util.spec_from_file_location('kgfem.kg.validator', _archived)
_mod = importlib.util.module_from_spec(_spec); sys.modules['kgfem.kg.validator'] = _mod; _spec.loader.exec_module(_mod)
from kgfem.agent.session import ModelingSession
from kgfem.kg.knowledge import SLOTS
from kgfem.kg.validator import slot_pattern, same_value
from kgfem import ablation
from kgfem.cli import read_input
from rule_parser import parse, ParseError

PARSER_SHA256 = '5fd985645702b5bbda00106957aa5a12d4acdfc3a1216a457726253362bfc865'
OUT = P / 'rule_baseline'


def complete(s):
    slots = s.inst.required_slots(); s.declare_decisions(slots)
    for _ in range(len(slots) + 2):
        pending = [x for x in slots if x not in s.val.accepted]
        if not pending:
            break
        progress = False
        for slot in pending:
            if slot == 'lane.mu' and 'f1' not in s.val.facts:
                if not s.run_modal_analysis().get('ok'):
                    continue
            pat = slot_pattern(slot); pre = SLOTS[pat][2]
            idx = slot.split('.')[1] if slot.startswith(('support.', 'pier.')) else None
            pre = [x.replace('{k}', idx) if idx else x for x in pre]
            if any(x not in s.val.accepted for x in pre):
                continue
            nodes, env = s.val.applicable_nodes(slot)
            if not nodes:
                raise RuntimeError('no_applicable_rule:' + slot)
            priority = lambda n: (n['id'] != 'MR-00', n['layer'] != 'code')
            best = min(map(priority, nodes)); tied = [n for n in nodes if priority(n) == best]
            vals = [s.val.execute(n, slot, env) for n in tied]
            if not all(same_value(x, vals[0]) for x in vals):
                raise RuntimeError('conflicting_priority_tie:' + slot)
            value, node, ctx = s.val.expected(slot); ev = [node['id']]
            if node['id'] == 'MR-00':
                ev.append('INPUT:girder.' + ('E_override_MPa' if slot == 'girder.Ec' else 'gamma_override_kNm3'))
            if ctx.get('has_Ge_override') and slot.endswith(('.Kv', '.Kh')):
                ev.append(f'INPUT:supports[{idx}].bearing.Ge_MPa')
            r = s.propose_decision(slot, value, SLOTS[pat][1], ev, rationale='rule baseline')
            if not r['accepted']:
                raise RuntimeError('proposal_rejected:' + json.dumps(r, ensure_ascii=False))
            progress = True
        if not progress:
            raise RuntimeError('dependency_deadlock:' + str(pending))
    if any(x not in s.val.accepted for x in slots):
        raise RuntimeError('incomplete')


def run(pid, group):
    base, text = read_input(pid, 'en')
    wd = OUT / group / pid; shutil.rmtree(wd, ignore_errors=True); wd.mkdir(parents=True)
    ablation.set_active([]); s = ModelingSession(str(wd), base); t0 = time.perf_counter()
    status, failure = None, None
    try:
        inst = parse(text)
    except ParseError as e:
        status, failure = 'parse_rejected', str(e)
    if status is None:
        try:
            res = s.write_instance(copy.deepcopy(inst))
            if not res['ok']:
                status, failure = 'instance_rejected', res
            else:
                complete(s); g = s.generate_model()
                status = 'model_passed' if g['ok'] else 'model_failed'; failure = None if g['ok'] else g
        except Exception as ex:
            status, failure = 'controller_error', {'type': type(ex).__name__, 'message': str(ex)}
    elapsed = time.perf_counter() - t0
    path = s.save()
    from kgfem.evaluate import evaluate_run
    ev = evaluate_run(str(R / 'bridgefe_bench/problems' / f'{base}.json'), path) if status not in (
        'parse_rejected',) else {'correct': False}
    out = {'input': pid, 'base': base, 'group': group, 'status': status, 'correct': bool(ev.get('correct')),
           'evaluation': ev, 'failure': failure, 'seconds': elapsed, 'llm_calls': 0}
    json.dump(out, open(wd / 'result.json', 'w'), ensure_ascii=False, indent=2, default=str)
    return out


def main():
    assert hashlib.sha256((P / 'rule_parser.py').read_bytes()).hexdigest() == PARSER_SHA256, 'parser changed'
    ids = [f'{t}{i:02d}' for t in 'ABC' for i in range(1, 11)]
    groups = {
        'structured_en': ids,
        'structured_zh': [f'{x}_zh' for x in ['A03', 'B04', 'C02']],
        'long_units_en': ['S01', 'S02', 'S03'],
        'free_text': [f'{b}_s{k}_{l}' for b in ('A03', 'B04', 'C02') for k in (1, 2, 3) for l in ('en', 'zh')],
        'boundary': [f'BD{k}' for k in range(1, 7)],
        'unmodified_for_boundary': ['A05', 'B02', 'C03', 'A09', 'B07', 'C04'],
    }
    results = []
    for g, items in groups.items():
        for pid in items:
            r = run(pid, g); results.append(r)
            print(g, pid, r['status'], r['correct'], (r['failure'] if isinstance(r['failure'], str) else ''), flush=True)
    json.dump(results, open(P / 'rule_baseline_results.json', 'w'), ensure_ascii=False, indent=2, default=str)
    for g in groups:
        rs = [r for r in results if r['group'] == g]
        print('SUMMARY', g, sum(r['correct'] for r in rs), '/', len(rs),
              {k: sum(r['status'] == k for r in rs) for k in sorted({r['status'] for r in rs})})


if __name__ == '__main__':
    main()

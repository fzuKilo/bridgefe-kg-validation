"""Offline re-validation of the decisions accepted in the 90 C5 runs.

For each C5 run, the final instance and the final accepted decisions (value, unit, cited
evidence) are taken from the archived session record and re-submitted, in dependency order,
to a validator. No LLM is called. Run once with the evaluated validator (control: every
decision should be accepted again) and once with the stricter variant in kgfem/.

usage: python analysis/strict_revalidation.py {evaluated|strict} OUTDIR
"""
from pathlib import Path
import json, sys, copy, importlib.util, tempfile
P = Path(__file__).resolve().parent; R = P.parent; sys.path.insert(0, str(R))
MODE, OUT = sys.argv[1], Path(sys.argv[2]); OUT.mkdir(parents=True, exist_ok=True)
if MODE == 'evaluated':
    spec = importlib.util.spec_from_file_location('kgfem.kg.validator', R/'supplementary/replay_20261017/validator_evaluated.py')
    mod = importlib.util.module_from_spec(spec); sys.modules['kgfem.kg.validator'] = mod; spec.loader.exec_module(mod)
from kgfem.agent.session import ModelingSession
from kgfem.kg.knowledge import SLOTS
from kgfem.kg.validator import slot_pattern
from kgfem import ablation

rows = [json.loads(l) for l in (R/'runs_main/results.jsonl').read_text().splitlines()]
rows = sorted([r for r in rows if r['config'] == 'C5'], key=lambda r: (r['problem'], r['rep']))
assert len(rows) == 90
results = []
for row in rows:
    pid, rep = row['problem'], row['rep']
    src = R/row['source']/f'{pid}_r{rep}'/f'{pid}_session.json'
    arch = json.load(open(src))
    acc = arch['decisions']
    rec = {'problem': pid, 'rep': rep, 'historical_correct': bool(row['correct']), 'n_decisions': len(acc),
           'rejected': [], 'not_replayed': [], 'status': 'ok'}
    try:
        ablation.set_active([])
        wd = Path(tempfile.mkdtemp(dir=OUT))
        s = ModelingSession(str(wd), pid)
        w = s.write_instance(copy.deepcopy(arch['instance']))
        if not w['ok']:
            rec['status'] = 'instance_rejected'; rec['instance_issues'] = w.get('issues'); results.append(rec); continue
        s.declare_decisions(list(acc))
        pending = list(acc)
        for _ in range(len(pending) + 3):
            if not pending: break
            progress = False
            for slot in list(pending):
                pat = slot_pattern(slot)
                idx = slot.split('.')[1] if slot.startswith(('support.', 'pier.')) else None
                pre = [x.replace('{k}', idx) if idx else x for x in SLOTS[pat][2]]
                if any(x not in s.val.accepted for x in pre):
                    continue
                if slot == 'lane.mu' and 'f1' not in s.val.facts:
                    others = [x for x in pending if x != 'lane.mu']
                    if others: continue          # modal analysis after all structural decisions
                    m = s.run_modal_analysis()
                    if not m.get('ok'):
                        rec['status'] = 'modal_failed'; break
                d = acc[slot]
                res = s.propose_decision(slot, d['value'], d.get('unit'), d.get('evidence') or [], rationale='offline re-validation')
                pending.remove(slot); progress = True
                if not res['accepted']:
                    viol = [v for v in s.val.history[-1]['violations']]
                    rec['rejected'].append({'slot': slot, 'value': d['value'], 'evidence': d.get('evidence'), 'violations': viol})
                    # keep the archived value so that downstream decisions can still be checked
                    s.val._accept(slot, d['value'], d.get('unit'), d.get('evidence') or [])
            if not progress: break
        rec['not_replayed'] = pending
    except Exception as ex:
        rec['status'] = 'error'; rec['error'] = f'{type(ex).__name__}: {ex}'
    results.append(rec)
    print(pid, rep, rec['status'], len(rec['rejected']), len(rec['not_replayed']), flush=True)
json.dump(results, open(OUT/f'revalidation_{MODE}.json', 'w'), ensure_ascii=False, indent=2)
print('SUMMARY', MODE, 'runs', len(results), 'decisions', sum(r['n_decisions'] for r in results),
      'rejected', sum(len(r['rejected']) for r in results), 'runs_with_rejection', sum(bool(r['rejected']) for r in results),
      'errors', sum(r['status'] != 'ok' for r in results), 'not_replayed', sum(len(r['not_replayed']) for r in results))

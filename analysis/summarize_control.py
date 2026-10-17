from pathlib import Path
import json,collections,hashlib,sys
import numpy as np
P=Path(__file__).resolve().parent
r=json.load(open(P/'full_results.json'));assert len(r)==90;assert len({(x['problem'],x['rep']) for x in r})==90;assert all(x['initial_sha256']==x['stored_initial_sha256'] for x in r)
assert hashlib.sha256((P/'run_control.py').read_bytes()).hexdigest()==(P/'frozen_controller.sha256').read_text().strip()
unchanged=[x for x in r if not x['historical_final_differs_from_first_args']];assert len(unchanged)==85;assert all(x['D_correct']==x['historical_correct'] for x in unchanged)
pp={p:{k:sum(x[k] for x in r if x['problem']==p)/3 for k in ('D_correct','historical_correct')} for p in sorted({x['problem'] for x in r})};d=np.array([v['historical_correct']-v['D_correct'] for v in pp.values()]);rng=np.random.default_rng(20261016);boot=d[rng.integers(0,30,(20000,30))].mean(axis=1)
# One prespecified paired accuracy contrast, exact sign-rank p checked independently by sign enumeration.
from scipy.stats import rankdata
import itertools
z=d[d!=0];rk=rankdata(abs(z));obs=abs(sum(rk*np.sign(z)));p=sum(abs(sum(rk*np.array(s)))>=obs-1e-12 for s in itertools.product((-1,1),repeat=len(z)))/2**len(z)
summary={'n':90,'D_correct':sum(x['D_correct'] for x in r),'historical_L_correct':sum(x['historical_correct'] for x in r),'D_status_counts':dict(collections.Counter(x['D_status'] for x in r)),'same_outcomes_on_unchanged_initial_instances':{'n':85,'D_correct':sum(x['D_correct'] for x in unchanged),'L_correct':sum(x['historical_correct'] for x in unchanged)},'problem_level_L_minus_D':{'difference':float(d.mean()),'bootstrap_ci95':np.quantile(boot,[.025,.975]).tolist(),'n_pairs':30,'nonzero_pairs':len(z),'exact_signed_rank_p':p,'interpretation':'Exploratory historical comparison; asymmetric input-repair permissions, not a causal test of per-decision LLM advantage.'},'D_wall_seconds_mean':float(np.mean([x['D_seconds'] for x in r])),'D_wall_seconds_median':float(np.median([x['D_seconds'] for x in r])),'D_decision_LLM_calls':0,'resource_limit':'Archived usage aggregates whole LLM calls; cannot allocate extraction vs decision tokens exactly. Do not claim a precise token saving or latency ratio.','per_problem':pp}
json.dump(summary,open(P/'summary.json','w'),ensure_ascii=False,indent=2)
manifest=[]
root=P.parent
for path in sorted((root/'kgfem').rglob('*.py')):manifest.append({'path':str(path.relative_to(root)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
manifest.append({'path':'run_control.py','sha256':hashlib.sha256((P/'run_control.py').read_bytes()).hexdigest()});json.dump(manifest,open(P/'code_manifest.json','w'),indent=2)
print(json.dumps({k:v for k,v in summary.items() if k!='per_problem'},ensure_ascii=False,indent=2))

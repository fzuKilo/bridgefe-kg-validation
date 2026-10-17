from pathlib import Path
import json,sys,collections,itertools,hashlib
import numpy as np
from scipy.stats import wilcoxon
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
OUT=ROOT/'review_evidence'/'cluster';OUT.mkdir(parents=True,exist_ok=True)
rows=[json.loads(l) for l in (ROOT/'runs_faults/results.jsonl').read_text().splitlines() if l.strip()]
assert len(rows)==600 and len({(r['fault'],r['signal'],r['rep']) for r in rows})==600
assert not any(r['error'] for r in rows)
metrics={'success':lambda r:float(r['correct']),'generations':lambda r:r['repair_rounds'],'time_s':lambda r:r['wall_s'],'input_k':lambda r:r['usage']['prompt_tokens']/1000}
summary={s:{m:float(np.mean([fn(r) for r in rows if r['signal']==s])) for m,fn in metrics.items()} for s in ('C5','A5','F0')}
comparisons=[]
for subset in ('all','decision','input'):
 rr=[r for r in rows if subset=='all' or (r['category']=='input_interpretation')==(subset=='input')]
 bridges=sorted({r['problem'] for r in rr})
 for other in ('A5','F0'):
  for metric,fn in metrics.items():
   delta=[]
   for b in bridges:
    means={s:np.mean([fn(r) for r in rr if r['problem']==b and r['signal']==s]) for s in ('C5',other)}
    delta.append(means['C5']-means[other])
   delta=np.array(delta)
   null=np.array([np.mean(delta*np.array(signs)) for signs in itertools.product((-1,1),repeat=len(delta))])
   p=float(np.mean(np.abs(null)>=abs(delta.mean())-1e-12))
   rng=np.random.default_rng(20261016)
   boot=delta[rng.integers(0,len(delta),(20000,len(delta)))].mean(axis=1)
   comparisons.append(dict(subset=subset,other=other,metric=metric,n_bridges=len(bridges),bridges=bridges,bridge_equal_mean_difference=float(delta.mean()),bootstrap_percentile_95=np.quantile(boot,[.025,.975]).tolist(),exact_signflip_p=p,bridge_differences=delta.tolist()))
# Holm family: 8 all-error comparisons (two signals x four outcomes); subsets descriptive exploratory.
fam=[r for r in comparisons if r['subset']=='all']
prev=0
for i,r in enumerate(sorted(fam,key=lambda x:x['exact_signflip_p'])):
 prev=max(prev,min(1,(len(fam)-i)*r['exact_signflip_p']))
 r['holm_p_8']=prev
json.dump({'n_rows':len(rows),'summary_run_weighted':summary,'comparisons':comparisons,'note':'Bridge-equal weighting; repeated runs averaged within error then bridge (balanced here). Signals are paired by bridge, not by random run number. Bootstrap is exploratory with only 6 bridges (5 for input errors); sign-flip inference assumes exchangeable paired differences. Generations include the initial failed generation.'},open(OUT/'statistics.json','w'),ensure_ascii=False,indent=2)
from kgfem.faults import FAULTS
lines=['# 20 项注错清单','', '|ID|类型|桥梁|改写对象|目标|新值|说明|','|---|---|---|---|---|---|---|']
for fid,cat,pid,how,target,value,desc in FAULTS:
 lines.append('|'+ '|'.join(str(x).replace('|','/') for x in (fid,cat,pid,how,target,value,desc))+'|')
(OUT/'注错清单.md').write_text('\n'.join(lines)+'\n')
manifest=[]
for folder in ('kgfem','bridgefe_bench'):
 for p in sorted((ROOT/folder).rglob('*')):
  if p.is_file() and '__pycache__' not in p.parts:
   manifest.append({'path':str(p.relative_to(ROOT)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
for name in ('runs_faults/results.jsonl','runs_faults/check.json','runs_main/results.jsonl','runs_ablation_single/results.jsonl'):
 p=ROOT/name
 if p.exists():manifest.append({'path':name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
json.dump(manifest,open(OUT/'evidence_manifest.json','w'),ensure_ascii=False,indent=2)
print(json.dumps(summary,indent=2))
print('Cluster audit complete')

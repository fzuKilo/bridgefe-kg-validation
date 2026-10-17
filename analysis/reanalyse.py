from pathlib import Path
import json,sys,collections,hashlib
import numpy as np
from scipy.stats import wilcoxon,rankdata,binomtest
P=Path(__file__).resolve().parent;R=P.parent;sys.path.insert(0,str(R))
from kgfem.summarize import tokens

def holm(items,key,out):
 prev=0
 for i,x in enumerate(sorted(items,key=lambda x:x[key])):
  prev=max(prev,min(1,(len(items)-i)*x[key]));x[out]=prev

def exact_signed_rank(d):
 z=[int(x) for x in d if x]; ranks=np.rint(2*rankdata(np.abs(z),method='average')).astype(int)
 if not z:return 1.,0.,0
 obs=sum(r for r,v in zip(ranks,z) if v>0);total=sum(ranks);counts={0:1}
 for r in ranks:
  nxt=collections.defaultdict(int)
  for k,v in counts.items():nxt[k]+=v;nxt[k+int(r)]+=v
  counts=nxt
 tail=sum(v for k,v in counts.items() if min(k,total-k)<=min(obs,total-obs))
 return min(1,tail/2**len(z)),min(obs,total-obs)/2,len(z)

report={};manifest=[];dataset_rows={}
for dataset,folder in [('main','runs_main'),('ablation','runs_ablation_single'),('backbone','runs_luna')]:
 f=R/folder/'results.jsonl'; raw=[json.loads(l) for l in f.read_text().splitlines() if l.strip()];keep={};duplicates=[];err=[]
 for i,r in enumerate(raw,1):
  if r.get('error'):err.append(i);continue
  k=(r['config'],r['problem'],r['rep'])
  if k in keep:duplicates.append(k)
  keep[k]=r
 rows=list(keep.values());dataset_rows[dataset]=rows
 cfgs=sorted({r['config'] for r in rows});pp={};summary={}
 expected={(p,r) for p in [f'{t}{i:02d}' for t in 'ABC' for i in range(1,11)] for r in (1,2,3)}
 for c in cfgs:
  rr=[r for r in rows if r['config']==c];assert {(r['problem'],r['rep']) for r in rr}==expected,(dataset,c)
  assert all(isinstance(r['correct'],bool) for r in rr)
  counts={p:sum(r['correct'] for r in rr if r['problem']==p) for p in sorted({r['problem'] for r in rr})};pp[c]=counts
  vals=np.array(list(counts.values()))/3;rng=np.random.default_rng(20261016);boot=vals[rng.integers(0,30,(10000,30))].mean(axis=1)
  summary[c]={'runs':len(rr),'correct':sum(r['correct'] for r in rr),'accuracy':float(vals.mean()),'ci95':np.quantile(boot,[.025,.975]).tolist(),'problems_all_correct':sum(v==3 for v in counts.values()),'wall_s':float(np.mean([r['wall_s'] for r in rr])),'input_tokens':float(np.mean([tokens(r.get('usage'))[0] for r in rr])),'problem_success_counts':counts}
 tests=[]
 for c in cfgs:
  if c=='C5':continue
  d=np.array([pp['C5'][p]-pp[c][p] for p in sorted(pp[c])]);p,w,n=exact_signed_rank(d)
  legacy=float(wilcoxon(d/3).pvalue) if any(d) else 1.
  rng=np.random.default_rng(20261016);boot=d[rng.integers(0,30,(20000,30))].mean(axis=1)/3
  tests.append({'contrast':'C5-'+c,'n_pairs':30,'nonzero':n,'zero':int(sum(d==0)),'positive':int(sum(d>0)),'negative':int(sum(d<0)),'abs_difference_tie_counts':dict(collections.Counter(map(str,abs(d[d!=0])))),'mean_accuracy_difference':float(d.mean()/3),'difference_ci95':np.quantile(boot,[.025,.975]).tolist(),'rank_biserial':float((sum(rankdata(abs(d[d!=0]))[d[d!=0]>0])-sum(rankdata(abs(d[d!=0]))[d[d!=0]<0]))/sum(rankdata(abs(d[d!=0])))) if n else 0.,'W':w,'p_exact_tie_aware':p,'p_legacy_auto':legacy})
 holm(tests,'p_exact_tie_aware','p_exact_holm');holm(tests,'p_legacy_auto','p_legacy_holm')
 report[dataset]={'path':folder,'raw_lines':len(raw),'error_lines':err,'duplicate_success_keys':duplicates,'selected_runs':len(rows),'summary':summary,'tests':tests}
 manifest.append({'path':str(f.relative_to(R)),'sha256':hashlib.sha256(f.read_bytes()).hexdigest()})
# Identify subgroup from benchmark field, independently of outcome.
sub=[]
for p in sorted((R/'bridgefe_bench/problems').glob('[ABC]*.json')):
 d=json.load(open(p));text=json.dumps(d,ensure_ascii=False)
 # Use original structured description; look for explicit rubber shear-modulus override.
 s=(R/'bridgefe_bench/inputs'/f'{p.stem}_en.txt').read_text()
 import re
 nums=re.findall(r'shear modulus of the rubber ([\d.]+) MPa',s)
 if nums and any(float(x)!=1 for x in nums):sub.append(p.stem)
rr=dataset_rows['ablation'];groups={c:{p:sum(r['correct'] for r in rr if r['config']==c and r['problem']==p) for p in sub} for c in ('C5','A4')}
d=[groups['C5'][p]-groups['A4'][p] for p in sub];p,w,n=exact_signed_rank(d)
report['A4_subgroup']={'selection':'Explicit rubber shear modulus != 1 MPa in original English input','problems':sub,'success_out_of_3':groups,'n_pairs':len(sub),'p_exact_signed_rank':p,'p_exact_sign':binomtest(sum(x>0 for x in d),n,.5).pvalue if n else 1,'interpretation':'Exploratory subgroup; do not pool 12 repetitions as independent cases; no additional multiplicity adjustment claimed.'}
# Check shared C5 records and source-row provenance, without double-counting.
a={(r['problem'],r['rep']):r for r in dataset_rows['main'] if r['config']=='C5'};b={(r['problem'],r['rep']):r for r in rr if r['config']=='C5'}
report['shared_C5']={'n':len(a),'identical_correctness':all(a[k]['correct']==b[k]['correct'] for k in a),'identical_usage':all(a[k].get('usage')==b[k].get('usage') for k in a),'sources':dict(collections.Counter(r.get('source','unrecorded') for r in a.values())),'note':'Same C5 data reused across main and ablation; not independent replication.'}
json.dump(report,open(P/'statistics_verified.json','w'),ensure_ascii=False,indent=2)
json.dump(manifest,open(P/'input_hashes.json','w'),indent=2)
for dataset in ('main','ablation','backbone'):
 print(dataset,report[dataset]['raw_lines'],report[dataset]['selected_runs'],'errors',len(report[dataset]['error_lines']),'duplicates',len(report[dataset]['duplicate_success_keys']))
 for t in report[dataset]['tests']:print(t['contrast'],t['p_legacy_holm'],t['p_exact_holm'],t['positive'],t['negative'],t['zero'])
print('A4',report['A4_subgroup']);print('shared',report['shared_C5'])

from pathlib import Path
import json,sys,collections
import numpy as np
D=Path(__file__).resolve().parent;R=D.parents[4];sys.path.insert(0,str(R))
from kgfem.plot_c06 import analyse,C5,C4
from kgfem.summarize import tokens
r5,r4=analyse(C5),analyse(C4)
report={'midspan_x_m':[float(r5['x'][n-1]) for n in r5['IR']['mid_nodes']], 'midspan_M_MNm':[float(r5['M_sw'][n-1]/1000) for n in r5['IR']['mid_nodes']], 'deflection_min':{'x_m':float(r5['x'][np.argmin(r5['defl_mm'])]),'value_mm':float(min(r5['defl_mm']))}}
report['lane_plot']={}
for name,r in [('C5',r5),('C4',r4)]:
 i=int(np.argmax(r['env_pos']));report['lane_plot'][name]={'max_positive_kNm':float(r['env_pos'][i]),'x_m':float(r['x'][i]),'evaluated_sections':len(r['x'])}
report['peak_increase_percent']=100*(max(r4['env_pos'])/max(r5['env_pos'])-1)
(D/'c06_verified_plot_data.json').write_text(json.dumps(report,indent=2))
# Recompute aggregate points and resource contrasts directly from archived completed rows.
rows=[]
for folder in ['runs_main','runs_scale']:
 rows += [json.loads(l) for l in (R/folder/'results.jsonl').read_text().splitlines() if l.strip()]
g=collections.defaultdict(list)
for r in rows:
 if r.get('error') or r['config'] not in ['C4','C5']:continue
 key=r['problem'][0] if r['problem'][0] in 'ABC' else r['problem'];g[(key,r['config'])].append(r)
scale=[]
for key in ['A','B','C','S01','S02','S03']:
 item={'group':key}
 for cfg in ['C4','C5']:
  rr=g[key,cfg];item[cfg]={'n':len(rr),'correct':sum(r['correct'] for r in rr),'wall_s':float(np.mean([r['wall_s'] for r in rr])),'input_tokens':float(np.mean([tokens(r.get('usage'))[0] for r in rr]))}
 for field in ['wall_s','input_tokens']:item[field+'_increase_percent']=100*(item['C5'][field]/item['C4'][field]-1)
 scale.append(item)
(D/'scale_verified.json').write_text(json.dumps(scale,indent=2))
# Main paired interval already verified; cluster bootstrap across six paired bridges.
stats=json.loads((D.parent/'证据与统计_20261016/statistics_verified.json').read_text())
main=next(x for x in stats['main']['tests'] if x['contrast']=='C5-C4')
old=json.loads((D.parent/'本机核验_20261016/statistics.json').read_text());effects=[]
for item in old['comparisons']:
 if item['subset']!='all':continue
 d=np.array(item['bridge_differences']);rng=np.random.default_rng(20261016);b=d[rng.integers(0,len(d),(20000,len(d)))].mean(1)
 effects.append({'other':item['other'],'metric':item['metric'],'n_bridges':len(d),'difference':float(d.mean()),'ci95':np.quantile(b,[.025,.975]).tolist(),'bridge_differences':d.tolist()})
(D/'effect_intervals.json').write_text(json.dumps({'main':main,'repair':effects,'bootstrap':'paired bridges, percentile, 20000 resamples, seed 20261016; exploratory non-simultaneous intervals; only six clusters'},indent=2))
# Compact table of the existing convergence data; no new numerical experiment.
conv=json.loads((D.parent/'本机核验_20261016/convergence.json').read_text());lines=[]
for r in conv:
 x=r['results'];neg=x['lane_max_negative_moment_kNm'];lines.append(f"{r['problem']} & {r['girder_elements_per_span']} & {x['vertical_frequencies_Hz'][0]:.8f} & {x['lane_max_positive_moment_kNm']/1000:.6f} & "+(f"{neg/1000:.6f}" if neg is not None else '---')+r' \\')
(D/'convergence_rows.tex').write_text('\n'.join(lines))
print('C06',report);print('main interval',main['difference_ci95']);print('repair',effects)

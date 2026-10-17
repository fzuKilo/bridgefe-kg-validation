from pathlib import Path
import json,sys,copy,time,hashlib,argparse
P=Path(__file__).resolve().parent;R=P.parent;sys.path.insert(0,str(R))
import importlib.util
_archived=R/'supplementary/replay_20261017/validator_evaluated.py'
_spec=importlib.util.spec_from_file_location('kgfem.kg.validator',_archived)
_mod=importlib.util.module_from_spec(_spec);sys.modules['kgfem.kg.validator']=_mod;_spec.loader.exec_module(_mod)
from kgfem.agent.session import ModelingSession
from kgfem.kg.knowledge import SLOTS
from kgfem.kg.validator import slot_pattern,same_value
from kgfem import ablation

def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
def run(row,folder):
 pid,rep=row['problem'],row['rep'];src=R/row['source']/f'{pid}_r{rep}'/f'{pid}_session.json';archive=json.load(open(src));writes=[x for x in archive['log'] if x['tool']=='write_instance'];assert writes
 frozen=copy.deepcopy(writes[0]['args']);wd=folder/f'{pid}_r{rep}';wd.mkdir(parents=True,exist_ok=True);json.dump(frozen,open(wd/'frozen_initial_instance.json','w'),ensure_ascii=False,indent=2)
 ablation.set_active([]);s=ModelingSession(str(wd),pid);start=time.perf_counter();trace=[];status='unknown';failure=None
 try:
  res=s.write_instance(copy.deepcopy(frozen));assert digest(s.log[0]['args'])==digest(frozen)
  if not res['ok']:status='invalid_initial_instance';failure=res
  else:
   slots=s.inst.required_slots();s.declare_decisions(slots)
   for _ in range(len(slots)+2):
    pending=[x for x in slots if x not in s.val.accepted]
    if not pending:break
    progress=False
    for slot in pending:
     if slot=='lane.mu' and 'f1' not in s.val.facts:
      modal=s.run_modal_analysis()
      if not modal.get('ok'):continue
     pat=slot_pattern(slot);pre=SLOTS[pat][2];idx=slot.split('.')[1] if slot.startswith(('support.','pier.')) else None
     pre=[x.replace('{k}',idx) if idx else x for x in pre]
     if any(x not in s.val.accepted for x in pre):continue
     nodes,env=s.val.applicable_nodes(slot)
     if not nodes:raise RuntimeError('no_applicable_rule:'+slot)
     priority=lambda n:(n['id']!='MR-00',n['layer']!='code')
     best=min(map(priority,nodes));tied=[n for n in nodes if priority(n)==best];vals=[s.val.execute(n,slot,env) for n in tied]
     if not all(same_value(x,vals[0]) for x in vals):raise RuntimeError('conflicting_priority_tie:'+slot)
     value,node,ctx=s.val.expected(slot);ev=[node['id']]
     if node['id']=='MR-00':ev.append('INPUT:girder.'+('E_override_MPa' if slot=='girder.Ec' else 'gamma_override_kNm3'))
     if ctx.get('has_Ge_override') and slot.endswith(('.Kv','.Kh')):ev.append(f'INPUT:supports[{idx}].bearing.Ge_MPa')
     result=s.propose_decision(slot,value,SLOTS[pat][1],ev,rationale='deterministic completion of frozen initial instance')
     trace.append({'slot':slot,'rule':node['id'],'tied_candidates':[n['id'] for n in tied],'accepted':result['accepted']})
     if not result['accepted']:raise RuntimeError('proposal_rejected:'+json.dumps(result,ensure_ascii=False))
     progress=True
    if not progress:raise RuntimeError('dependency_deadlock:'+str(pending))
   if any(x not in s.val.accepted for x in slots):raise RuntimeError('incomplete')
   generation=s.generate_model();status='model_passed' if generation['ok'] else 'model_failed';failure=None if generation['ok'] else generation
 except Exception as ex:status='controller_error';failure={'type':type(ex).__name__,'message':str(ex)}
 elapsed=time.perf_counter()-start;path=s.save();assert digest(frozen)==digest(json.load(open(wd/'frozen_initial_instance.json')))
 assert sum(x['tool']=='write_instance' for x in s.log)==1
 # Only now may evaluation read the reference; no reference is accessed by the selector above.
 from kgfem.evaluate import evaluate_run
 ev=evaluate_run(str(R/'bridgefe_bench/problems'/f'{pid}.json'),path)
 out={'problem':pid,'rep':rep,'source':str(src.relative_to(R)),'source_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'initial_sha256':digest(frozen),'stored_initial_sha256':digest(s.log[0]['args']),'first_write_ok_historical':writes[0]['result'].get('ok'),'historical_write_calls':len(writes),'historical_final_differs_from_first_args':frozen!=archive['instance'],'historical_correct':bool(row['correct']),'D_status':status,'D_correct':bool(ev['correct']),'D_evaluation':ev,'failure':failure,'D_seconds':elapsed,'D_model_calls':0,'D_input_tokens':0,'D_output_tokens':0,'D_tool_calls':len(s.log),'rule_trace':trace,'historical_usage':row.get('usage'),'historical_wall_s':row['wall_s'],'comparison_note':'Historical L allows input correction; D locks first instance. Not a symmetric newly randomized decision-stage contrast.'}
 json.dump(out,open(wd/'control_result.json','w'),ensure_ascii=False,indent=2);return out

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--phase',choices=['pilot','full'],required=True);a=ap.parse_args();rows=[json.loads(l) for l in (R/'runs_main/results.jsonl').read_text().splitlines()];rows=sorted([r for r in rows if r['config']=='C5'],key=lambda r:(r['problem'],r['rep']));assert len(rows)==90
 if a.phase=='pilot':rows=[next(r for r in rows if (r['problem'],r['rep'])==(p,1)) for p in ('C01','A01')]
 else:
  pilot=json.load(open(P/'pilot_results.json'));assert len(pilot)==2 and all(r['initial_sha256']==r['stored_initial_sha256'] for r in pilot);assert {r['D_status'] for r in pilot}=={'model_passed','invalid_initial_instance'}
  assert (P/'frozen_controller.sha256').read_text().strip()==hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'controller changed after pilot'
 results=[]
 for r in rows:
  out=run(r,P/a.phase);results.append(out);print(r['problem'],r['rep'],out['D_status'],out['D_correct'],flush=True)
 json.dump(results,open(P/f'{a.phase}_results.json','w'),ensure_ascii=False,indent=2)
 if a.phase=='pilot':(P/'frozen_controller.sha256').write_text(hashlib.sha256(Path(__file__).read_bytes()).hexdigest()+'\n')
 print('SUMMARY',len(results),sum(r['D_correct'] for r in results),sum(r['historical_correct'] for r in results),flush=True)
if __name__=='__main__':main()

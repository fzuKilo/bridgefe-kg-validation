from pathlib import Path
import sys,json,copy
D=Path(__file__).resolve().parent;R=D.parents[4];sys.path.insert(0,str(R))
from kgfem.agent.session import ModelingSession
from kgfem.agent.scripted import ScriptedAgent,parse_structured_en
from kgfem.kg.expr import ExprError
from kgfem import ablation
ablation.set_active([])
s=ModelingSession(str(D/'C01_check'),'C01');inst=parse_structured_en((R/'bridgefe_bench/inputs/C01_en.txt').read_text());assert s.write_instance(inst)['ok'];s.declare_decisions(s.inst.required_slots());a=ScriptedAgent(s)
for slot in s.inst.required_slots():
 if slot!='lane.mu':assert a._decide(slot)['accepted'],slot
assert s.run_modal_analysis()['ok'];assert a._decide('lane.mu')['accepted'];assert s.generate_model()['ok']
slot='support.2.Kh';exp,node,ctx=s.val.expected(slot);records={}
for name,ev in [('correct',[node['id'],'INPUT:supports[2].bearing.Ge_MPa']),('wrong_support',[node['id'],'INPUT:supports[1].bearing.Ge_MPa']),('missing_override',[node['id']]),('missing_formula',['MR-04','INPUT:supports[2].bearing.Ge_MPa'])]:
 v=copy.deepcopy(s.val);res=v.validate(slot,exp,'kN/m',ev);records[name]=res;assert res['accepted']==(name=='correct'),(name,res)
rec=s.val.accepted[slot];assert rec['formula_source']==node['id'] and rec['active'] and rec['input_citations']==['INPUT:supports[2].bearing.Ge_MPa']
v=copy.deepcopy(s.val);n=copy.deepcopy(node);nid=n.pop('id');layer=n.pop('layer');typ=n.pop('type');v.kg.add_node(nid+'-conflict',layer,typ,**n);v.kg.add_edge(nid+'-conflict','GOVERNS','slot:support.{k}.Kh')
try:v.expected(slot);raise AssertionError('conflict not rejected')
except ExprError as e:records['conflict']=str(e)
patch=copy.deepcopy(s.inst.data);patch['supports'][2]['bearing']['Ge_MPa']=1.4;write=s.write_instance(patch)
for x in ['support.2.Kh','support.2.Kv','lane.mu']:
 assert x not in s.val.accepted and s.kg.get('dec:'+x)['active'] is False,x
assert not s.val.facts and not s.generate_model()['ok'];records['withdrawn']=write
for x in s.inst.required_slots():
 if x!='lane.mu' and x not in s.val.accepted:assert a._decide(x)['accepted']
assert s.run_modal_analysis()['ok'];assert a._decide('lane.mu')['accepted'];assert s.generate_model()['ok'];assert abs(s.val.accepted[slot]['value']-15272.7272727)<1e-4
# IDs stored in fact provenance must invalidate modal facts on structural revisions.
assert a._decide('girder.Ec')['accepted'];assert not s.val.facts and 'lane.mu' not in s.val.accepted
records['formula_record']=rec;records['checks_passed']=True
# End-to-end reference checks over all 33 authored benchmark problems, no API calls.
checks=[]
for p in sorted((R/'bridgefe_bench/inputs').glob('*_en.txt')):
 if p.stem[:-3][0] not in 'ABCS' or p.stem.startswith('BD'):continue
 pid=p.stem[:-3];ss=ModelingSession(str(D/'benchmark_checks'/pid),pid);out=ScriptedAgent(ss).run(p.read_text());assert out['ok'],(pid,out)
 ss.save();checks.append({'problem':pid,'generated':True,'metrics':ss.metrics()})
records['benchmark_checks']=checks
(D/'provenance_checks.json').write_text(json.dumps(records,ensure_ascii=False,indent=2,default=str));print('PASSED provenance probes and',len(checks),'benchmark generations')

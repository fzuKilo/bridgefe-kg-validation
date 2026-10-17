from pathlib import Path
import sys,json,copy
ROOT=Path(__file__).resolve().parents[1];P=ROOT/'review_evidence'/'convergence';P.mkdir(parents=True,exist_ok=True);sys.path.insert(0,str(ROOT))
from kgfem.kg.knowledge import build_knowledge_graph
from kgfem.kg.instance import Instance
from kgfem.model import ir,generator
out=[]
for pid in ('A03','B03','C06'):
 source=ROOT/'runs_main/C5'/f'{pid}_r1'/f'{pid}_session.json'
 if not source.exists():source=ROOT/'runs_ablation_multi/A6'/f'{pid}_r1'/f'{pid}_session.json'
 d=json.loads(source.read_text()); inst=Instance(build_knowledge_graph());inst.write(d['instance'])
 for n in (10,20,40):
  ir.N_PER_PIER=n//2
  model=ir.build_ir(inst,d['decisions'],mesh=n)
  path=P/f'{pid}_mesh{n}.py';generator.emit_script(model,str(path))
  res=generator.run_script(str(path));assert res['ok'],res
  out.append(dict(problem=pid,girder_elements_per_span=n,pier_elements=n//2,results=res))
  print(pid,n,res['vertical_frequencies_Hz'][0],res['lane_max_positive_moment_kNm'],flush=True)
json.dump(out,open(P/'convergence.json','w'),indent=2)

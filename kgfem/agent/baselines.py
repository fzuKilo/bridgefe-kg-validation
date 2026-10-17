"""智能体基线（论文表 4 的 C2–C4）：与本文方法（C5）使用同一个单智能体、同一流程与同样的计算工具，
只改变领域知识作用于大模型的方式。

  C2 提示词知识：全部建模规则与规范条文写入系统提示词；智能体结束后由同一模型做一次自检（检查点），自检给出的更正被采纳
  C3 检索增强：以 BM25 从同一批规则、条文文本与两个算例中检索，供智能体阅读
  C4 图谱工具：与 C5 相同的图谱工具（规则与条文查询、公式执行）
C2–C4 的提案一律照单接受（不做依据、适用性、数值、一致性校验），实例层不做完整性与合理性检查，
模型只反馈脚本执行错误（不做 L1–L3 校核与定位）。决策清单的完整性提示属于工具接口，各方案相同。
"""
import json
import math
import os
import re
from collections import Counter

from .. import ablation
from ..kg.knowledge import CLAUSES, RULES, SLOTS
from .backends import session_dispatch
from .session import MAX_REPAIR_ROUNDS
from .tools import SESSION_TOOLS

BENCH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'bridgefe_bench')
KG_TOOLS = {'query_knowledge', 'retrieve_clause', 'execute_formula'}
FLAGS = ['NOVAL', 'NOCHECK', 'A3']          # 不校验提案、不做模型校核、不做实例约束


# ---------------- 知识文本（与图谱同源） ----------------
EN_TITLE = {      # 英文标题与关键词，使英文检索也能命中中文条文（检索增强基线的公平性）
    'MR-01': 'structural idealization: girder bridge as a two-dimensional spine beam',
    'MR-05': 'structural system: simply supported, continuous, continuous on piers',
    'MR-02': 'girder section properties: area A and moment of inertia I, precast girders combined',
    'MR-00': 'input priority: values given in the description override code defaults (elastic modulus, unit weight)',
    'MR-07': 'dead load and mass: girder self-weight per metre w and mass per metre m',
    'MR-04': 'number of bearings on a support line; bearings in parallel',
    'MR-03': 'modeling of laminated elastomeric bearings: restrained degrees of freedom, horizontal stiffness',
    'MR-08': 'modeling of spherical bearings: rigid vertical support, fixed or sliding',
    'MR-06': 'modeling of piers: column length, section area and moment of inertia',
    'LL-01': 'lane load arrangement: uniform load and concentrated load on the influence line',
    'LL-02': 'fundamental frequency used for the impact factor',
    'JTG3362-3.1.5': 'elastic modulus of concrete by grade',
    'JTGD60-4.2.1': 'unit weight of materials, prestressed concrete',
    'JTG3362-8.7-S': 'shape factor of laminated elastomeric bearings',
    'JTG3362-8.7-Kv': 'vertical (compressive) stiffness of laminated elastomeric bearings',
    'JTG3362-8.7-Kh': 'shear (horizontal) stiffness of laminated elastomeric bearings',
    'JTG3362-8.7-Ge': 'shear modulus of rubber, standard value',
    'JTT854': 'spherical bearings for highway bridges',
    'JTGD60-4.3.1-lanes': 'number of design lanes from carriageway width',
    'JTGD60-4.3.1-xi': 'transverse (multi-lane) reduction factor',
    'JTGD60-4.3.1-qk': 'lane load: uniform load qk',
    'JTGD60-4.3.1-Pk': 'lane load: concentrated load Pk from span length',
    'JTGD60-4.3.2': 'impact factor (dynamic amplification) of vehicle load from fundamental frequency',
}


def _node_text(n):
    keep = {k: v for k, v in n.items() if k not in ('concept', 'supports')}
    if n['id'] in EN_TITLE:
        keep['title_en'] = EN_TITLE[n['id']]
    return json.dumps(keep, ensure_ascii=False)


def knowledge_docs():
    docs = [(n['id'], _node_text(n)) for n in RULES + CLAUSES]
    for pid in ('S01', 'S02'):                   # 算例取自不参加主对比的长联题
        d = json.load(open(os.path.join(BENCH, 'problems', f'{pid}.json'), encoding='utf-8'))
        lines = [f"Worked example {pid}.", d['input']['structured_en'], 'Decisions:']
        for r in d['reference_decisions']:
            lines.append(f"  {r['slot']} = {json.dumps(r['canonical'], ensure_ascii=False)} "
                         f"[{r.get('unit') or '-'}] (basis: {r.get('evidence')})")
        docs.append((f'example:{pid}', '\n'.join(lines)))
    return docs


def knowledge_text():
    return '\n'.join(f'- {t}' for i, t in knowledge_docs() if not i.startswith('example:'))


def _tokens(s):
    s = s.lower()
    words = re.findall(r'[a-z0-9_.{}]+', s)
    words += [p for w in list(words) for p in re.split(r'[._{}]+', w) if p and p != w]
    cjk = re.findall(r'[一-鿿]', s)
    return words + [a + b for a, b in zip(cjk, cjk[1:])]


class BM25:
    def __init__(self, docs, k1=1.5, b=0.75):
        self.docs = docs
        self.toks = [_tokens(t) for _, t in docs]
        self.avg = sum(map(len, self.toks)) / len(self.toks)
        df = Counter(w for t in self.toks for w in set(t))
        n = len(docs)
        self.idf = {w: math.log(1 + (n - c + 0.5) / (c + 0.5)) for w, c in df.items()}
        self.k1, self.b = k1, b

    def search(self, query, k=4):
        q = _tokens(query)
        scores = []
        for i, t in enumerate(self.toks):
            tf = Counter(t)
            s = sum(self.idf.get(w, 0) * tf[w] * (self.k1 + 1) /
                    (tf[w] + self.k1 * (1 - self.b + self.b * len(t) / self.avg)) for w in q if w in tf)
            scores.append((s, i))
        return [{'id': self.docs[i][0], 'text': self.docs[i][1]} for s, i in sorted(scores, reverse=True)[:k] if s > 0]


# ---------------- 提示词：流程与 C5 相同，只换知识相关部分 ----------------
WORKFLOW = f"""You are the driver of a finite element modeling workflow for girder bridges. You interpret the bridge \
description, propose every modeling decision, invoke tools to build and analyse an OpenSeesPy model, and repair \
errors.

Workflow
1. Call get_input_schema, then write_instance with everything the description states about spans, deck and \
design standard, girders and section geometry, supports, bearings and piers. Convert units exactly. The \
description is the only source of bridge data - never invent values it does not state.
2. Call declare_decisions with the decision slots the model needs (declarations accumulate; the tool lists the \
slots still missing). Slot names: structure.idealization, structure.system, girder.single.A/I (precast girders \
only), girder.A, girder.I, girder.Ec, girder.gamma, girder.w, girder.m, support.<k>.bearing, support.<k>.dofs, \
support.<k>.S / .Kv / .Kh (laminated elastomeric bearings only), pier.<k>.length / .A / .I / .Ec (supports on \
modelled pier columns), lane.n_lanes, lane.xi, lane.qk, lane.Pk.<span>, lane.mu. Units: {', '.join(f'{p} [{u}]' for p, (_, u, _) in SLOTS.items())}.
3. Decide every slot and record it with propose_decision (value, unit, evidence = the clause or rule you relied \
on). __KNOWLEDGE__ compute_section_properties integrates a section.
4. The impact factor needs the fundamental frequency: once the structural decisions are recorded, call \
run_modal_analysis, then decide lane.mu.
5. Call generate_model. If the script fails to execute, revise the responsible decisions and call generate_model \
again (at most {MAX_REPAIR_ROUNDS} rounds).
6. When generate_model succeeds, call finish with a short summary.

Value formats: numbers for numeric slots; structure.idealization "spine_beam_2d"; structure.system \
"simply_supported" | "continuous" | "continuous_on_piers"; support.<k>.bearing {{"type": "plain_elastomeric" | \
"ptfe_sliding" | "spherical_fixed" | "spherical_sliding", "count": <bearings on the line>}}; support.<k>.dofs \
{{"vertical": "spring" | "rigid", "longitudinal": "spring" | "free" | "fixed", "rotation": "free"}}. Supports are \
numbered from 0 at the first abutment; spans from 1. Decisions are recorded as proposed; no checks are applied. \
You may call several independent tools in one turn."""

KNOW = {
    'C2': ('Apply the modeling rules and code clauses listed below.',
           '\n\nModeling rules and design-code clauses (JTG D60-2015, JTG 3362-2018, JT/T 854-2013), each with its '
           'applicability condition, formulas and tables:\n' + '__KTEXT__'),
    'C3': ('Use search_knowledge to find the governing clause or rule and read it.', ''),
    'C4': ('Use query_knowledge(slot=...) to find the governing rule or clause and whether it applies to this bridge, '
           'retrieve_clause to read it, and execute_formula to evaluate its formula on this bridge.', ''),
}

SELF_CHECK = """You are checking a finite element model of a girder bridge prepared by another engineer. Compare \
every decision with the bridge description and with the modeling rules and code clauses below. Answer with one \
JSON object {"corrections": {"<slot>": <corrected value>, ...}} in a ```json block, listing only decisions that are \
wrong (an empty object if all are right). Keep the value formats and units of the decisions.

Modeling rules and design-code clauses:
"""


def system_prompt(cfg):
    step, extra = KNOW[cfg]
    p = WORKFLOW.replace('__KNOWLEDGE__', step) + extra
    return p.replace('__KTEXT__', knowledge_text())


def tool_names(cfg):
    names = [t['name'] for t in SESSION_TOOLS]
    if cfg in ('C2', 'C3'):
        names = [n for n in names if n not in KG_TOOLS]
    if cfg == 'C3':
        names.append('search_knowledge')
    if ablation.on('DEFECT'):
        names.append('report_input_defect')
    return names


def run_baseline(cfg, session, backend, description):
    ablation.set_active(FLAGS + (['DEFECT'] if ablation.on('DEFECT') else []))
    names = tool_names(cfg)
    base = session_dispatch(session, set(names))
    bm = BM25(knowledge_docs()) if cfg == 'C3' else None

    def dispatch(name, args):
        if name == 'search_knowledge' and bm is not None:
            q = args.get('query', '')
            return session._log('search_knowledge', {'query': q}, {'passages': bm.search(q)}), False
        return base(name, args)

    from .tools import DEFECT_RULE
    usage = backend.run(system_prompt(cfg) + (DEFECT_RULE if ablation.on('DEFECT') else ''), names, f'Bridge description:\n\n{description}', dispatch,
                        is_done=lambda: session.done, max_turns=200)
    out = {'agent': usage}
    if cfg == 'C2' and session.val.accepted:             # 自检检查点
        dec = {s: d['value'] for s, d in session.val.accepted.items()}
        msg, u2 = backend.complete(SELF_CHECK + knowledge_text(),
                                   f'Bridge description:\n\n{description}\n\nInstance:\n'
                                   f'{json.dumps(session.inst.data, ensure_ascii=False)}\n\nDecisions:\n'
                                   f'{json.dumps(dec, ensure_ascii=False)}', max_tokens=32768)
        out['self_check'] = u2
        m = re.findall(r'```json\s*\n(.*?)```', msg, re.S)
        try:
            corr = json.loads(m[-1] if m else msg).get('corrections') or {}
        except (json.JSONDecodeError, AttributeError):
            corr = {}
        applied = {}
        for slot, v in corr.items():
            if slot in session.val.accepted:
                r = session.val.validate(slot, v, session.val.accepted[slot]['unit'], [], is_revision=True)
                if r.get('accepted'):
                    applied[slot] = v
        out['self_check_corrections'] = applied
        if applied:
            res = session.generate_model()
            if not res.get('ok'):
                session.results = None
        session.role_log.append({'role': 'self_check', 'usage': u2, 'corrections': applied})
    return {'roles': [{'role': cfg, 'usage': usage}] + ([{'role': 'self_check', 'usage': out.get('self_check')}]
                                                        if 'self_check' in out else [])}

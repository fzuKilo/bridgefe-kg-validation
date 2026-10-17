"""直接生成基线（论文表 4 的 C0、C1）：一次调用、不给工具、不给领域知识，只给输出格式。

  C0 直接生成脚本：大模型写出完整的 OpenSeesPy 脚本，本地运行后按响应比对（容差 1%）
  C1 直接生成决策：大模型输出实例与决策集，由共用的确定性生成器建模，决策逐项比对（容差 0.1%）
二者对应 Geng 等人的通用大模型基线；C1 使直接生成的错误也能按决策归因。
"""
import json
import os
import re
import subprocess
import sys
import time

from ..kg.instance import SCHEMA_DOC
from ..kg.knowledge import SLOTS
from ..model import generator
from ..model.ir import N_PER_SPAN, build_ir
from .session import normalize_value

TOL_C0 = 1e-2
MAX_OUTPUT = 262144          # 含思考过程

RESPONSES = f"""Print, as the last line of standard output, the text RESULT followed by one JSON object with these keys:
  "vertical_frequencies_Hz": frequencies of the vertical bending modes of the girder in ascending order (at least \
the first);
  "self_weight_support_reactions_kN": vertical reaction of each support line under the girder self-weight, from \
the first abutment to the last, upward positive;
  "self_weight_midspan_moments_kNm": girder bending moment at the midspan of each span under the self-weight, \
sagging positive;
  "lane_max_positive_moment_kNm": the largest sagging moment at any span midspan under the design lane load, \
including the number of design lanes, the transverse reduction factor and the impact factor (1 + mu); the uniform \
load qk is placed on the parts of the bridge where the influence line has the unfavourable sign and the \
concentrated load Pk at the most unfavourable point;
  "lane_max_negative_moment_kNm": the most negative (hogging) moment at any interior support under the design \
lane load, defined the same way, as a negative number; null for a single span.
Model the bridge as a two-dimensional spine beam with {N_PER_SPAN} elastic beam-column elements per span and \
consistent mass. Units: kN, m, s."""

C0_SYSTEM = f"""You are a bridge engineer. Write one complete, self-contained Python script that uses OpenSeesPy \
(import openseespy.opensees as ops) and numpy to build and analyse a finite element model of the bridge described \
by the user, following the Chinese design codes JTG D60-2015 and JTG 3362-2018 where the description requires \
code values. Derive every value you need from the description and the codes; no tools are available.
{RESPONSES}
Return only the script in a single ```python code block."""


def _slot_table():
    rows = []
    for pat, (cat, unit, _) in SLOTS.items():
        rows.append(f'  {pat}  [{unit}]')
    return '\n'.join(rows)


C1_SYSTEM = f"""You are a bridge engineer preparing a finite element model of a girder bridge (two-dimensional \
spine beam, OpenSeesPy) according to the Chinese design codes JTG D60-2015, JTG 3362-2018 and JT/T 854-2013. A \
program will build and analyse the model from your answer; no tools are available, so derive every value yourself \
from the description and the codes.

Answer with one JSON object {{"instance": ..., "decisions": ...}} in a single ```json code block.

"instance" records the bridge as stated in the description, in this schema:
{SCHEMA_DOC}

"decisions" maps every decision slot this bridge needs to its value, in the unit shown. Slot patterns:
{_slot_table()}
Supports are numbered from 0 at the first abutment; spans from 1 (lane.Pk.<span>). girder.single.A/I are the \
middle-girder section of precast girders (omit for cast-in-place boxes); support.<k>.S/.Kv/.Kh apply to laminated \
elastomeric bearings only; pier.<k>.* apply only where pier columns are modelled.
Value formats: structure.idealization "spine_beam_2d"; structure.system "simply_supported" | "continuous" | \
"continuous_on_piers"; support.<k>.bearing {{"type": "plain_elastomeric" | "ptfe_sliding" | "spherical_fixed" | \
"spherical_sliding", "count": <bearings on the line>}}; support.<k>.dofs {{"vertical": "spring" | "rigid", \
"longitudinal": "spring" | "free" | "fixed", "rotation": "free"}}; all other slots are numbers."""


def _block(text, lang):
    m = re.findall(rf'```{lang}\s*\n(.*?)```', text, re.S)
    if m:
        return max(m, key=len)
    m = re.findall(r'```\w*\s*\n(.*?)```', text, re.S)
    return max(m, key=len) if m else text


def run_c0(session, backend, description):
    t0 = time.time()
    msg, usage = backend.complete(C0_SYSTEM, f'Bridge description:\n\n{description}', max_tokens=MAX_OUTPUT)
    code = _block(msg, 'python')
    path = os.path.join(session.workdir, f'{session.problem_id}_direct.py')
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(code)
    try:
        p = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=900,
                           cwd=session.workdir)
        out, err, rc = p.stdout, p.stderr, p.returncode
    except subprocess.TimeoutExpired:
        out, err, rc = '', 'timeout', -1
    res = None
    for line in reversed(out.splitlines()):
        if line.startswith('RESULT'):
            try:
                res = json.loads(line[len('RESULT'):].strip())
            except json.JSONDecodeError:
                pass
            break
    session.results = res
    session.role_log.append({'role': 'direct_script', 'usage': usage, 'returncode': rc,
                             'stderr': (err or '')[-2000:], 'elapsed_s': round(time.time() - t0, 1)})
    return usage


def run_c1(session, backend, description):
    t0 = time.time()
    msg, usage = backend.complete(C1_SYSTEM, f'Bridge description:\n\n{description}', max_tokens=MAX_OUTPUT)
    note = None
    try:
        ans = json.loads(_block(msg, 'json'))
        inst, dec = ans.get('instance') or {}, ans.get('decisions') or {}
        try:
            session.inst.write(inst)                   # 不做约束检查，直接写入
        except (ValueError, KeyError, TypeError) as e:
            note = f'instance: {e}'
        for slot, v in dec.items():                    # 不经校验直接接受
            if isinstance(v, dict) and 'value' in v and slot_is_scalar(slot):
                v = v['value']
            session.val.accepted[slot] = {'id': f'dec:{slot}', 'slot': slot, 'value': normalize_value(slot, v),
                                          'unit': None, 'evidence': []}
        ir = build_ir(session.inst, session.val.accepted)
        path = generator.emit_script(ir, os.path.join(session.workdir, f'{session.problem_id}_model.py'))
        res = generator.run_script(path, mode='full')
        session.results = res if res.get('ok') else None
        if not res.get('ok'):
            note = (note or '') + ' execution: ' + (res.get('stderr') or '')[-1500:]
    except Exception as e:                             # 缺决策、格式错误等：视为不可执行
        note = (note or '') + f' {type(e).__name__}: {e}'
    session.role_log.append({'role': 'direct_decisions', 'usage': usage, 'note': note,
                             'elapsed_s': round(time.time() - t0, 1)})
    return usage


def slot_is_scalar(slot):
    return not (slot.endswith('.bearing') or slot.endswith('.dofs'))


def evaluate_c0(problem_json, session_json):
    """C0 只能按响应比对（容差 1%）。"""
    ref = json.load(open(problem_json, encoding='utf-8'))
    run = json.load(open(session_json, encoding='utf-8'))
    rr, res = ref['reference_responses'], run.get('results') or {}

    def same(a, b):
        try:
            a, b = float(a), float(b)
        except (TypeError, ValueError):
            return False
        return abs(a) < 1e-6 if b == 0 else abs(a - b) <= TOL_C0 * abs(b)
    resp = {}
    if res:
        for key, is_list in [('self_weight_support_reactions_kN', True), ('self_weight_midspan_moments_kNm', True),
                             ('lane_max_positive_moment_kNm', False), ('lane_max_negative_moment_kNm', False)]:
            a, b = res.get(key), rr.get(key)
            if b is None:
                resp[key] = a is None
            elif is_list:
                resp[key] = isinstance(a, list) and len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
            else:
                resp[key] = same(a, b)
        resp['first_vertical_frequency_Hz'] = same((res.get('vertical_frequencies_Hz') or [None])[0],
                                                   rr['first_vertical_frequency_Hz'])
    return {'id': ref['id'], 'executed': bool(res), 'decisions_correct': None,
            'decisions_total': len(ref['reference_decisions']), 'responses': resp,
            'correct': bool(res) and bool(resp) and all(resp.values()), 'wrong_decisions': [],
            'metrics': run.get('metrics')}

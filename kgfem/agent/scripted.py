"""脚本化代理：不调用大模型、按固定策略使用同一套工具的测试替身。

用途：
  - 无需 API 即可端到端检验图谱、校验器、模型生成与校核的闭环；
  - 注入决策错误（faults），检验“提出—校验—反馈—修订”回路；
  - 注入模型级错误（model_faults），检验三级校核与定位修复（论文 5.3 节注入错误实验）。
它只能解析 BridgeFE-Bench 的英文结构化描述；真正的输入理解由大模型后端完成。
"""
import re

NUM = {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10}


def _num(s):
    s = s.strip().lower()
    return NUM[s] if s in NUM else float(s)


def parse_structured_en(text):
    part = {m.group(1): m.group(2) for m in re.finditer(r'\[(.+?)\]\s*(.*)', text)}
    span, secm, brg, std = (part['Span arrangement'], part['Section and material'],
                            part['Bearings and boundary'], part['Design standard'])
    inst = {'dead_load': 'girder_self_weight_only'}
    if 'Single simply supported span' in span:
        inst['structure_type'] = 'simply_supported'
        inst['spans_m'] = [float(re.search(r'span of ([\d.]+) m', span).group(1))]
    else:
        inst['structure_type'] = 'cast_in_place_continuous' if 'cast-in-place' in span else 'precast_continuous'
        inst['spans_m'] = [float(x) for x in re.search(r'spans?, ([\d.+ ]+) m', span).group(1).split('+')]
    deck_w = float(re.search(r'deck width ([\d.]+) m', span).group(1))

    g = {'material': 'prestressed_concrete', 'E_override_MPa': None, 'gamma_override_kNm3': None,
         'concrete': re.search(r'girder concrete (C\d+)', secm).group(1)}
    f = lambda pat: float(re.search(pat, secm).group(1))
    if 'small box' in secm:
        g['type'] = 'small_box'
        g['section'] = {'h': f(r'depth ([\d.]+) m'), 'b_top': f(r'top width ([\d.]+) m'),
                        't_tip': f(r'flange ([\d.]+) m thick at the tip'),
                        'haunch_rise': f(r'thickening by ([\d.]+) cm') / 100,
                        'haunch_len': f(r'over a ([\d.]+) cm long haunch') / 100,
                        'b_bottom': f(r'bottom slab ([\d.]+) m wide'), 't_bottom': f(r'bottom slab [\d.]+ m wide and ([\d.]+) m'),
                        't_top': f(r'top slab ([\d.]+) m thick'), 't_web': f(r'webs ([\d.]+) m thick'),
                        'web_slope': f(r'inclined at 1:([\d.]+)'), 'chamfer_w': 0.15, 'chamfer_h': 0.07}
    elif 'T girders' in secm:
        g['type'] = 't_girder'
        g['section'] = {'h': f(r'depth ([\d.]+) m'), 'b_flange': f(r'flange ([\d.]+) m wide'),
                        't_tip': f(r'wide, ([\d.]+) m thick over'), 'flat_len': f(r'over the outer ([\d.]+) m'),
                        't_root': f(r'linearly to ([\d.]+) m at the web'), 't_web': f(r'web ([\d.]+) m thick'),
                        'b_bulb': f(r'bulb ([\d.]+) m wide'), 'bulb_h': f(r'with a ([\d.]+) m vertical'),
                        'bulb_trans': f(r'and a ([\d.]+) m high linear')}
    else:
        g['type'] = 'cast_box'
        g['section'] = {'h': f(r'constant depth ([\d.]+) m'), 'B_top': f(r'top slab ([\d.]+) m wide'),
                        't_top': f(r'top slab [\d.]+ m wide and ([\d.]+) m'), 'B_bot': f(r'bottom slab ([\d.]+) m wide'),
                        't_bot': f(r'bottom slab [\d.]+ m wide and ([\d.]+) m'), 't_web': f(r'webs ([\d.]+) m thick'),
                        't_cant_root': f(r'flanges ([\d.]+) m thick at the root'), 't_cant_tip': f(r'to ([\d.]+) m at the tip')}
    m = re.search(r'(\w+) per span', secm)
    g['count_per_span'] = int(_num(m.group(1))) if m else 1
    m = re.search(r'elastic modulus of the girder concrete as ([\d.e+]+) MPa', secm)
    if m:
        g['E_override_MPa'] = float(m.group(1))
    m = re.search(r'unit weight of ([\d.]+) kN/m3', secm)
    if m:
        g['gamma_override_kNm3'] = float(m.group(1))
    inst['girder'] = g

    n_sup = len(inst['spans_m']) + 1
    sups = {k: {'index': k, 'kind': 'abutment' if k in (0, n_sup - 1) else 'pier', 'pier': None}
            for k in range(n_sup)}
    for grp in re.split(r'(?<=\.)\s+(?=(?:Abutment|Pier) \d)', brg):
        m = re.match(r'((?:(?:Abutment|Pier) \d+(?:, | and )?)+):\s*(.*)', grp)
        if not m:
            continue
        ks = [int(x) for x in re.findall(r'(?:Abutment|Pier) (\d+)', m.group(1))]
        body = m.group(2)
        if 'spherical' in body:
            b = {'family': 'spherical', 'fixed': 'longitudinally fixed' in body,
                 'sliding': 'longitudinally movable' in body,
                 'per_girder_end': 1, 'per_line': None, 'model': re.search(r'bearings (\w+)', body).group(1)}
        else:
            b = {'family': 'laminated_elastomeric', 'sliding': 'PTFE sliding' in body,
                 'fixed': 'PTFE sliding' not in body,
                 'per_girder_end': None, 'per_line': None,
                 'a_mm': float(re.search(r'size (\d+) mm', body).group(1)),
                 'b_mm': float(re.search(r'x (\d+) mm', body).group(1)),
                 'n_layers': int(_num(re.search(r'(\w+) internal rubber layers', body).group(1))),
                 't1_mm': float(re.search(r'layers (\d+) mm thick', body).group(1)),
                 'Ge_MPa': float(re.search(r'shear modulus of the rubber ([\d.]+) MPa', body).group(1))
                 if 'shear modulus' in body else None}
            mm = re.search(r'(\w+) under each girder end', body)
            if mm:
                b['per_girder_end'] = int(_num(mm.group(1)))
            mm = re.search(r'(\w+) per support line', body)
            if mm:
                b['per_line'] = int(_num(mm.group(1)))
        for k in ks:
            sups[k]['bearing'] = dict(b)
    m = re.search(r'Piers: twin circular columns of ([\d.]+) m diameter, concrete (C\d+).*?bearings: (.*?)\.', brg)
    if m:
        for k, h in re.findall(r'Pier (\d+) ([\d.]+) m', m.group(3)):
            sups[int(k)]['pier'] = {'height_m': float(h), 'diameter_m': float(m.group(1)), 'n_columns': 2,
                                    'concrete': m.group(2)}
    inst['supports'] = [sups[k] for k in range(n_sup)]
    inst['deck'] = {'deck_width_m': deck_w,
                    'carriageway_width_m': float(re.search(r'carriageway width ([\d.]+) m', std).group(1)),
                    'traffic': 'two_way' if 'two-way' in std else 'one_way',
                    'design_lanes': int(_num(re.search(r'(\w+) design lanes?', std).group(1))),
                    'load_class': re.search(r'Class (I+)', std).group(1)}
    return inst


UNITS = None


class ScriptedAgent:
    """faults: {槽位模式: 'scale' | 'wrong_clause' | 'wrong_unit'}，只作用于首次提案。
    model_faults: {槽位: 系数}，在生成模型前直接篡改已接受决策（绕过校验），检验模型级校核与定位。"""

    def __init__(self, session, faults=None, model_faults=None):
        self.s = session
        self.faults = faults or {}
        self.model_faults = model_faults or {}

    def run(self, text):
        s = self.s
        inst = parse_structured_en(text)
        res = s.write_instance(inst)
        if not res['ok']:
            return {'ok': False, 'stage': 'instance', 'issues': res['issues']}
        slots = s.inst.required_slots()
        s.declare_decisions(slots)
        for slot in [x for x in slots if x != 'lane.mu']:
            self._decide(slot)
        s.run_modal_analysis()
        self._decide('lane.mu')
        for slot, factor in self.model_faults.items():          # 模型级错误注入
            s.val.accepted[slot]['value'] = s.val.accepted[slot]['value'] * factor
        for _ in range(6):
            for slot in s.decision_status()['pending']:          # 修订引起的依赖决策撤回，重新提出
                if slot != 'lane.mu':
                    self._decide(slot, repair=True)
            if 'lane.mu' not in s.val.accepted:                   # 结构决策修订后基频失效，重做模态与冲击系数
                s.run_modal_analysis()
                self._decide('lane.mu', repair=True)
            out = s.generate_model()
            if out['ok']:
                break
            if out.get('stage') != 'model_checks':
                return out
            suspects = {d['slot'] for f in out['failed_checks'] for d in f['suspect_decisions']}
            for slot in sorted(suspects):                         # 按定位结果逐项复核并修订
                self._decide(slot, repair=True)
            if 'lane.mu' in suspects or 'fact.f1' in suspects:
                s.run_modal_analysis()
                self._decide('lane.mu', repair=True)
        s.finish('scripted agent run')
        return {'ok': s.results is not None, 'results': s.results}

    def _decide(self, slot, repair=False):
        s = self.s
        info = s.query_knowledge(slot=slot)
        app = info.get('applicable_to_this_bridge') or []
        node = sorted(app, key=lambda n: (n != 'MR-00', not n.startswith('JT')))[0] if app else None
        ex = s.execute_formula(node, slot) if node else {'error': 'no node'}
        value = ex.get('value')
        evidence = [node] if node else []
        ctx = s.inst.context(slot, s.val.accepted_values(), s.val.facts)
        if node == 'MR-00':
            path = {'girder.Ec': 'girder.E_override_MPa', 'girder.gamma': 'girder.gamma_override_kNm3'}[slot]
            evidence = ['MR-00', f'INPUT:{path}']
        if ctx.get('has_Ge_override') and slot.endswith(('.Kv', '.Kh')):
            k = slot.split('.')[1]
            evidence.append(f'INPUT:supports[{k}].bearing.Ge_MPa')
        unit = info.get('unit', '-')
        from ..kg.validator import slot_pattern
        fault = None if repair else self.faults.get(slot_pattern(slot))
        v, ev, un = value, evidence, unit
        if fault == 'scale' and isinstance(value, (int, float)):
            v = value * 1.15
        elif fault == 'wrong_clause':
            ev = ['JTGD60-4.3.1-qk'] if not slot.startswith('lane.qk') else ['JTGD60-4.3.1-Pk']
        elif fault == 'wrong_unit':
            un = 'N/m' if unit != 'N/m' else 'kN/m'
        res = s.propose_decision(slot, v, un, ev, rationale='scripted')
        tries = 0
        while not res['accepted'] and tries < 3:                 # 读取反馈并修订
            tries += 1
            v = res.get('formula_result', v)
            un = res.get('expected_unit', un)
            if 'applicability' in res.get('failed_checks', []) or 'evidence' in res.get('failed_checks', []):
                ev = evidence
            res = s.propose_decision(slot, v, un, ev, rationale='revised from KG feedback')
        return res

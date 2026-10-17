"""建模会话：把知识图谱与模型工具封装为大模型可调用的工具，并执行流程关卡与记录。

流程（论文图 4）：
  4.3 write_instance → 约束层完整性检查（≤ MAX_INSTANCE_ROUNDS 轮）→ declare_decisions
  4.4 propose_decision → 图谱四项校验 → 结构化反馈 → 修订
      （冲击系数前须 run_modal_analysis 取得基频）
  4.5 generate_model → 带溯源中间表示 → OpenSeesPy 脚本 → 运行
  4.6 三级校核失败 → 图谱定位可疑决策 → 修订 → 重新生成（≤ MAX_REPAIR_ROUNDS 轮）
"""
import json
import os
import time

from ..kg.instance import SCHEMA_DOC, Instance
from ..kg.knowledge import SLOTS, build_knowledge_graph
from ..kg.validator import DecisionValidator, slot_pattern
from ..kg.expr import ExprError
from ..model import checks, generator, sections
from ..model.ir import build_ir

MAX_INSTANCE_ROUNDS = 5
MAX_REPAIR_ROUNDS = 5
MAX_PROPOSALS_PER_SLOT = 8


def normalize_value(slot, value):
    """工具入口的类型规整：小模型常把数值或对象写成字符串。"""
    if isinstance(value, str):
        txt = value.strip()
        try:
            parsed = json.loads(txt)
            if isinstance(parsed, (int, float, dict, list, str)) and not isinstance(parsed, bool):
                value = parsed
        except json.JSONDecodeError:
            pass
    if isinstance(value, dict):
        value = {k: normalize_value(slot, v) if isinstance(v, str) and k == 'count' else v for k, v in value.items()}
        if isinstance(value.get('count'), float) and value['count'].is_integer():
            value['count'] = int(value['count'])
    if slot_pattern(slot) in SLOTS and SLOTS[slot_pattern(slot)][1] != '-' or slot in ('lane.n_lanes', 'lane.xi', 'lane.mu') \
            or slot.endswith('.S'):
        try:
            value = float(value)
            if slot == 'lane.n_lanes' and value.is_integer():
                value = int(value)
        except (TypeError, ValueError):
            pass
    return value


def normalize_evidence(evidence):
    if isinstance(evidence, str):
        try:
            parsed = json.loads(evidence)
            evidence = parsed if isinstance(parsed, list) else [str(parsed)]
        except json.JSONDecodeError:
            evidence = [e.strip(' "\'[]') for e in evidence.replace(';', ',').split(',')]
    return [str(e).strip() for e in (evidence or []) if str(e).strip()]


class ModelingSession:
    def __init__(self, workdir, problem_id='problem'):
        self.kg = build_knowledge_graph()
        self.inst = Instance(self.kg)
        self.val = DecisionValidator(self.kg, self.inst)
        self.workdir = os.path.abspath(workdir)       # 子进程在该目录运行脚本，须用绝对路径
        os.makedirs(self.workdir, exist_ok=True)
        self.problem_id = problem_id
        self.defect = None
        self.instance_rounds = 0
        self.repair_rounds = 0
        self.declared = None
        self.proposals = {}          # slot -> 提案次数
        self.last_check = None
        self.results = None
        self.done = False
        self.summary = None
        self.log = []
        self.role_log = []           # 多智能体模式：每次角色调用的记录
        self.t0 = time.time()

    # ---------------- 记录 ----------------
    def _log(self, tool, args, result):
        self.log.append({'t': round(time.time() - self.t0, 3), 'tool': tool, 'args': args, 'result': result})
        return result

    # ---------------- 工具：输入与实例层 ----------------
    def get_input_schema(self):
        return {'instance_schema': SCHEMA_DOC,
                'section_schemas': {k: {'fields': v, 'meaning': sections.DESCRIPTIONS[k]}
                                    for k, v in sections.SCHEMAS.items()}}

    def write_instance(self, instance):
        if isinstance(instance, str):
            try:
                instance = json.loads(instance)
            except json.JSONDecodeError:
                return {'ok': False, 'error': 'instance 必须是 JSON 对象'}
        self.instance_rounds += 1
        try:
            issues = self.inst.write(instance)
        except (ValueError, KeyError, TypeError) as e:
            return self._log('write_instance', instance, {'ok': False, 'error': str(e)})
        res = {'ok': not issues, 'issues': issues, 'round': self.instance_rounds}
        if self.val.accepted:                          # 实例修正后复核全部已接受决策，不再成立者撤回
            dropped = self.val.revalidate_all('实例层修正')
            if dropped:
                res['invalidated_decisions'] = dropped
        if issues and self.instance_rounds >= MAX_INSTANCE_ROUNDS:
            res['note'] = f'已达 {MAX_INSTANCE_ROUNDS} 轮补全上限，请按现有信息继续或说明无法建模'
        return self._log('write_instance', instance, res)

    def query_component(self, component):
        nid = component if component.startswith('inst:') else f'inst:{component}'
        node = self.kg.get(nid)
        if not node:
            return {'error': f'实例层中没有 {nid}',
                    'available': [n['id'] for n in self.kg.find(layer='instance')]}
        return {'node': node, 'relations': self.kg.relations(nid)}

    # ---------------- 工具：知识查询与公式执行 ----------------
    def query_knowledge(self, slot=None, keyword=None):
        if slot:
            pat = slot_pattern(slot)
            if pat not in SLOTS:
                return {'error': f'未知槽位 {slot}', 'known_slot_patterns': list(SLOTS)}
            cat, unit, pre = SLOTS[pat]
            out = {'slot': slot, 'category': cat, 'unit': unit, 'prerequisites': pre,
                   'governing_nodes': [self.val._describe(n) for n in self.val.governing_nodes(slot)]}
            try:
                app, _ = self.val.applicable_nodes(slot)
                out['applicable_to_this_bridge'] = [n['id'] for n in app]
            except (ExprError, KeyError, TypeError):
                pass
            return out
        kw = (keyword or '').lower()
        hits = [self.val._describe(n) for n in self.kg.nodes.values()
                if n['layer'] in ('rule', 'code', 'constraint') and n['type'] != 'DecisionSlot'
                and kw in json.dumps(n, ensure_ascii=False).lower()]
        return {'matches': hits[:20]}

    def retrieve_clause(self, node_id):
        n = self.kg.get(node_id)
        if not n or n['layer'] not in ('rule', 'code', 'constraint'):
            return {'error': f'图谱中没有 {node_id}'}
        return {k: v for k, v in n.items()}

    def execute_formula(self, node_id, slot):
        n = self.kg.get(node_id)
        if not n or slot_pattern(slot) not in n.get('formulas', {}):
            return {'error': f'{node_id} 没有 {slot_pattern(slot)} 的公式'}
        env = self.inst.context(slot, self.val.accepted_values(), self.val.facts)
        try:
            val = self.val.execute(n, slot, env)
        except (ExprError, ZeroDivisionError, KeyError, TypeError) as e:
            return {'error': f'执行失败：{e}'}
        applies = self.val._applies(n, slot_pattern(slot), env)
        used = {k: env[k] for k in n.get('inputs', []) if k in env and not isinstance(env[k], dict)}
        return self._log('execute_formula', {'node_id': node_id, 'slot': slot},
                         {'value': val, 'inputs': used, 'applicable_to_this_bridge': applies,
                          'applicability': n.get('applicability')})

    def compute_section_properties(self, section_type, geometry):
        try:
            return sections.properties(section_type, geometry)
        except (ValueError, KeyError) as e:
            return {'error': str(e), 'fields': sections.SCHEMAS.get(section_type)}

    # ---------------- 工具：决策 ----------------
    def declare_decisions(self, slots, replace=False):
        """声明决策清单。多次调用逐次累加（replace=True 时重写）；不需要的槽位不记入并在回复中列出。"""
        import re
        norm = []
        for x in slots if isinstance(slots, list) else [slots]:
            x = str(x).strip()
            m = re.match(r'^(support|pier)\.(\w+)\[(\d+)\]$', x) or re.match(r'^(lane)\.(Pk)\[(\d+)\]$', x)
            if m:                                         # support.dofs[0] → support.0.dofs；lane.Pk[1] → lane.Pk.1
                x = f'lane.Pk.{m.group(3)}' if m.group(1) == 'lane' else f'{m.group(1)}.{m.group(3)}.{m.group(2)}'
            norm.append(x)
        req = self.inst.required_slots()
        base = [] if replace or self.declared is None else self.declared
        self.declared = [x for x in req if x in set(base) | set(norm)]
        missing = [x for x in req if x not in self.declared]
        extra = [x for x in norm if x not in req]
        return self._log('declare_decisions', {'slots': slots, 'replace': replace},
                         {'complete': not missing, 'declared_so_far': len(self.declared), 'missing': missing,
                          'not_required_ignored': extra,
                          'note': 'declarations accumulate across calls; declare the missing slots next',
                          'constraint': 'C-13/T-templates'})

    def propose_decision(self, slot, value, unit, evidence, rationale=''):
        value, evidence = normalize_value(slot, value), normalize_evidence(evidence)
        n = self.proposals.get(slot, 0) + 1
        self.proposals[slot] = n
        if n > MAX_PROPOSALS_PER_SLOT:
            hint = {}
            try:
                exp, node, _ = self.val.expected(slot)
                hint = {'formula_result': exp, 'formula_source': node['id']}
            except (ExprError, KeyError, TypeError, ZeroDivisionError):
                pass
            from .. import ablation
            if ablation.on('A4'):
                return self._log('propose_decision', {'slot': slot}, {'accepted': False, 'slot': slot})
            if ablation.on('A1') or ablation.on('A2'):
                hint = {}
            return self._log('propose_decision', {'slot': slot}, {
                'accepted': False, 'error': f'{slot} 提案已达 {MAX_PROPOSALS_PER_SLOT} 次上限；请对照下列依据与数值检查后，'
                'report_instance_issue 或在交回时说明', **({} if ablation.on('A2') else {'valid_evidence': self.val.valid_evidence(slot)}), **hint})
        res = self.val.validate(slot, value, unit, evidence, is_revision=slot in self.val.accepted)
        return self._log('propose_decision', {'slot': slot, 'value': value, 'unit': unit, 'evidence': evidence,
                                              'rationale': rationale, 'attempt': n}, res)

    def pending_by_category(self):
        """待决策槽位按类别分组，并标出前置决策已就绪者。"""
        from ..kg.validator import slot_pattern as sp
        import re
        req = self.inst.required_slots()
        acc = self.val.accepted
        structural = [x for x in req if not x.startswith('lane.')]
        out = {}
        for slot in req:
            if slot in acc:
                continue
            cat, _, pre = SLOTS[sp(slot)]
            m = re.match(r'^(?:support|pier)\.(\d+)\.', slot)
            pre = [p.replace('{k}', m.group(1)) if m else p for p in pre]
            ready = all(p in acc for p in pre)
            if slot == 'lane.mu':
                ready = all(x in acc for x in structural)
            out.setdefault(cat, []).append((slot, ready))
        return out

    def decision_status(self):
        req = self.inst.required_slots()
        return {'accepted': {s: self.val.accepted[s]['value'] for s in req if s in self.val.accepted},
                'pending': [s for s in req if s not in self.val.accepted],
                'facts': self.val.facts}

    # ---------------- 工具：分析 ----------------
    def run_modal_analysis(self):
        struct = [s for s in self.inst.required_slots() if not s.startswith('lane.')]
        pend = [s for s in struct if s not in self.val.accepted]
        if pend:
            return self._log('run_modal_analysis', {}, {'ok': False, 'error': f'结构决策未全部通过：{pend}'})
        try:
            ir = build_ir(self.inst, self.val.accepted)
            path = generator.emit_script(ir, os.path.join(self.workdir, f'{self.problem_id}_modal.py'))
            res = generator.run_script(path, mode='modal')
        except Exception as e:                        # 未经校验的实例或决策无法组装模型：反馈给智能体
            return self._log('run_modal_analysis', {}, {'ok': False, 'stage': 'assembly',
                                                        'error': f'{type(e).__name__}: {e}'})
        if not res['ok'] or not res.get('vertical_frequencies_Hz'):
            return self._log('run_modal_analysis', {}, {'ok': False, 'error': res.get('stderr', '无竖向振型')})
        f = res['vertical_frequencies_Hz']
        self.val.set_fact('f1', f[0], [self.val.accepted[s]['id'] for s in struct])
        return self._log('run_modal_analysis', {}, {'ok': True, 'vertical_frequencies_Hz': f, 'fact': {'f1': f[0]}})

    def generate_model(self):
        pend = [s for s in self.inst.required_slots() if s not in self.val.accepted]
        if pend:
            return self._log('generate_model', {}, {'ok': False, 'error': f'仍有决策未通过：{pend}'})
        try:
            ir = build_ir(self.inst, self.val.accepted)
            with open(os.path.join(self.workdir, f'{self.problem_id}_ir.json'), 'w', encoding='utf-8') as fh:
                json.dump(ir, fh, ensure_ascii=False, indent=1)
            path = generator.emit_script(ir, os.path.join(self.workdir, f'{self.problem_id}_model.py'))
            res = generator.run_script(path, mode='full')
        except Exception as e:                        # 未经校验的实例或决策无法组装模型：作为执行错误反馈
            self.repair_rounds += 1
            return self._log('generate_model', {}, {'ok': False, 'stage': 'assembly',
                                                    'error': f'{type(e).__name__}: {e}',
                                                    'repair_round': self.repair_rounds})
        from .. import ablation
        if not res['ok']:
            self.repair_rounds += 1
            out = {'ok': False, 'stage': 'execution', 'error': res.get('stderr'), 'repair_round': self.repair_rounds}
            if not ablation.on('NOCHECK'):                # 分析失败时仍对组装的模型做拓扑与规范校核，以便定位
                fails = self._signal(checks.run_checks(ir, {}, self.val, self.kg))
                if fails:
                    out['failed_checks'] = fails
                self.last_check = fails
            return self._log('generate_model', {}, out)
        fails = [] if ablation.on('NOCHECK') else checks.run_checks(ir, res, self.val, self.kg)
        fails = self._signal(fails)
        self.last_check = fails
        if fails:
            self.repair_rounds += 1
            out = {'ok': False, 'stage': 'model_checks', 'failed_checks': fails, 'repair_round': self.repair_rounds}
            if self.repair_rounds >= MAX_REPAIR_ROUNDS:
                out['note'] = f'已达 {MAX_REPAIR_ROUNDS} 轮修复上限'
            return self._log('generate_model', {}, out)
        self.results = res
        return self._log('generate_model', {}, {'ok': True, 'script': path, 'results': res})

    def report_input_defect(self, defect_type='', message=''):
        """边界输入：报告描述有缺陷并结束会话，不生成模型。"""
        self.defect = {'defect_type': defect_type, 'message': message}
        self.done = True
        return self._log('report_input_defect', {'defect_type': defect_type, 'message': message}, {'ok': True})

    @staticmethod
    def _signal(fails):
        """按消融开关裁剪模型校核的反馈：F0 仅告知失败；A5 不给溯源定位。"""
        from .. import ablation
        if ablation.on('F0') and fails:
            return [{'constraint': 'model_checks', 'text': '', 'message': 'the model failed its checks',
                     'suspect_decisions': []}]
        if ablation.on('A5'):
            return [{'constraint': f['constraint'], 'text': f['text'], 'message': 'model check failed',
                     'suspect_decisions': []} for f in fails]
        return fails

    def finish(self, summary=''):
        if self.results is None and self.repair_rounds < MAX_REPAIR_ROUNDS:
            return {'ok': False, 'error': '模型尚未通过校核，不能结束'}
        self.done = True
        self.summary = summary
        return self._log('finish', {'summary': summary}, {'ok': True})

    # ---------------- 统计（论文 3.5 节指标） ----------------
    def metrics(self):
        hist = self.val.history
        first = {}
        for h in hist:
            first.setdefault(h['slot'], h)
        n_first = len(first)
        viol_first = sum(1 for h in first.values() if not h['accepted'])
        by_check = {}
        for h in hist:
            for v in h['violations']:
                by_check[v['check']] = by_check.get(v['check'], 0) + 1
        return {'proposals': len(hist), 'slots_proposed': n_first,
                'first_proposal_violation_rate': viol_first / n_first if n_first else None,
                'violations_by_check': by_check, 'instance_rounds': self.instance_rounds,
                'repair_rounds': self.repair_rounds, 'model_passed': self.results is not None,
                'elapsed_s': round(time.time() - self.t0, 2)}

    def save(self):
        out = os.path.join(self.workdir, f'{self.problem_id}_session.json')
        with open(out, 'w', encoding='utf-8') as fh:
            json.dump({'metrics': self.metrics(), 'decisions': self.val.accepted, 'facts': self.val.facts,
                       'instance': self.inst.data, 'results': self.results, 'defect': self.defect, 'last_check': self.last_check,
                       'role_log': self.role_log, 'log': self.log}, fh, ensure_ascii=False, indent=1, default=str)
        self.kg.to_json(os.path.join(self.workdir, f'{self.problem_id}_kg.json'))
        return out

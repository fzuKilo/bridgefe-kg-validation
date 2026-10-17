"""图谱约束的建模决策（I2，论文 4.4 节）。

大模型以 (槽位, 取值, 单位, 依据节点) 的形式提出决策，图谱逐项校验：
  1 evidence      依据存在性：所引规则 / 条文在图谱中存在（或 INPUT:路径 在实例层中有值）
  2 applicability 条件适用性：所引依据约束该决策，且其适用条件对本桥成立
  3 value         数值一致性：重新执行对应公式，复现所提数值（容差 0.1%）
  4 consistency   约束相容性：与已接受决策、构件拓扑不矛盾（约束层 C-10~C-15）
任一项不通过即返回结构化反馈：违反了哪条规则或约束、适用条件是什么、公式算得多少。
通过全部校验的决策写入决策层，并保留指向依据与实例构件的溯源边。
"""
import re

from .expr import ExprError, evaluate
from .knowledge import FACT_PREREQS, SLOTS

REL_TOL = 1e-3
UNIT_ALIASES = {'kN/m3': 'kN/m^3', 'kN/m³': 'kN/m^3', 'm2': 'm^2', 'm²': 'm^2', 'm4': 'm^4', 'm⁴': 'm^4',
                'N/mm^2': 'MPa', 'N/mm2': 'MPa', 'N/mm²': 'MPa', 't/m': 't/m', '': '-', None: '-',
                'none': '-', 'None': '-', 'dimensionless': '-', 'unitless': '-', '1': '-',
                'string': '-', 'object': '-', 'text': '-', 'n/a': '-', 'N/A': '-'}


def slot_pattern(slot):
    """'support.3.Kv' -> 'support.{k}.Kv'；'lane.Pk.2' -> 'lane.Pk.{j}'。"""
    p = re.sub(r'^(support|pier)\.\d+\.', r'\1.{k}.', slot)
    return re.sub(r'^lane\.Pk\.\d+$', 'lane.Pk.{j}', p)


def slot_component(slot):
    m = re.match(r'^(support|pier)\.(\d+)\.', slot)
    if m:
        return f'inst:{"bearing" if m.group(1) == "support" else "pier"}:{m.group(2)}'
    m = re.match(r'^lane\.Pk\.(\d+)$', slot)
    if m:
        return f'inst:span:{m.group(1)}'
    return 'inst:deck' if slot.startswith('lane.') else 'inst:girder'


def norm_unit(u):
    u = (u or '').strip()
    return UNIT_ALIASES.get(u, u)


def same_value(a, b):
    if isinstance(b, dict):
        return isinstance(a, dict) and set(a) == set(b) and all(same_value(a[k], b[k]) for k in b)
    if isinstance(b, str):
        return isinstance(a, str) and a.strip().lower() == b.strip().lower()
    if isinstance(b, bool) or isinstance(a, bool):
        return a == b
    try:
        a, b = float(a), float(b)
    except (TypeError, ValueError):
        return False
    if b == 0:
        return abs(a) <= 1e-9
    return abs(a - b) <= REL_TOL * abs(b)


from .. import ablation


class DecisionValidator:
    def __init__(self, kg, instance):
        self.kg = kg
        self.inst = instance
        self.accepted = {}       # slot -> 决策记录
        self.facts = {}          # 分析事实，如 {'f1': 3.2}
        self.fact_prov = {}      # 事实 -> 产生它的决策集合
        self.history = []        # 全部提案及校验结果（供约束违反率统计）

    # ---------------- 依据查询工具 ----------------
    def governing_nodes(self, slot):
        pat = slot_pattern(slot)
        return [n for n in self.kg.into(f'slot:{pat}', 'GOVERNS')]

    def applicable_nodes(self, slot):
        env = self.inst.context(slot, self.accepted_values(), self.facts)
        pat = slot_pattern(slot)
        out = []
        for n in self.governing_nodes(slot):
            if self._applies(n, pat, env):
                out.append(n)
        return out, env

    def _applies(self, node, pat, env):
        try:
            ok = bool(evaluate(node.get('applicability', 'True'), env))
            fa = node.get('formula_applicability', {}).get(pat)
            if ok and fa:
                ok = bool(evaluate(fa, env))
            return ok
        except ExprError:
            return False

    def accepted_values(self):
        return {s: d['value'] for s, d in self.accepted.items()}

    def execute(self, node, slot, env):
        """执行节点上该槽位的公式（含中间量）。"""
        env = dict(env)
        for k, v in node.get('tables', {}).items():
            env.setdefault(k, v)
        for name, expr in node.get('intermediates', []):
            env[name] = evaluate(expr, env)
        return evaluate(node['formulas'][slot_pattern(slot)], env)

    def expected(self, slot):
        """图谱对该槽位的期望：(期望值, 依据节点, 上下文) 或抛出 ExprError。"""
        nodes, env = self.applicable_nodes(slot)
        if not nodes:
            raise ExprError('图谱中没有对本桥适用的规则或条文约束该决策')
        # 输入优先（MR-00）> 规范条文 > 建模规则
        nodes.sort(key=lambda n: (n['id'] != 'MR-00', n['layer'] != 'code'))
        return self.execute(nodes[0], slot, env), nodes[0], env

    # ---------------- 四项校验 ----------------
    def validate(self, slot, value, unit, evidence, is_revision=False):
        evidence = evidence or []
        violations = []
        feedback = {'slot': slot}

        def fail(check, constraint, msg):
            if ablation.on('A1') and check == 'value':
                return
            if ablation.on('A2') and check in ('evidence', 'applicability'):
                return
            if ablation.on('A3') and check == 'consistency' and constraint != 'C-14':
                return
            violations.append({'check': check, 'constraint': constraint, 'message': msg})

        pat = slot_pattern(slot)
        if pat not in SLOTS:
            fail('consistency', 'C-13', f'未知决策槽位 {slot}；可用槽位见 list_required_decisions')
            return self._record(slot, value, unit, evidence, violations, feedback, is_revision)
        category, canon_unit, prereqs = SLOTS[pat]
        feedback.update(category=category, expected_unit=canon_unit)
        if ablation.on('NOVAL'):                    # 基线 C2–C4：提案照单接受
            return self._record(slot, value, unit, evidence, [], feedback, is_revision)

        # 4a 拓扑：构件存在；前置决策与分析事实已就绪
        if not self.inst.component_exists(slot):
            fail('consistency', 'C-13', f'{slot} 所指构件在实例层中不存在')
        idx = re.match(r'^(?:support|pier)\.(\d+)\.', slot)
        missing = [p.replace('{k}', idx.group(1)) if idx else p for p in prereqs]
        missing = [p for p in missing if p not in self.accepted]
        missing += [f for f in FACT_PREREQS.get(pat, []) if f.split('.', 1)[1] not in self.facts]
        if missing:
            fail('consistency', 'C-14', f'前置决策或分析事实尚未就绪：{missing}')

        # 1 依据存在性（规范化各种写法后判断；辅助依据须真实存在且与本决策相关）
        kinds = {}
        unknown = []
        for e in evidence:
            kind, eid = self.normalize_evidence(e, slot)
            if kind == 'unknown':
                unknown.append(e)
            else:
                kinds.setdefault(kind, []).append(eid)
        gov = self.governing_nodes(slot)
        sup = self.supporting_nodes(slot)
        if not ablation.on('A2'):
            feedback['candidate_evidence'] = [self._describe(n) for n in gov]
        if not evidence:
            fail('evidence', 'I2', '未给出依据节点')
        if unknown:
            fail('evidence', 'I2', f'依据在图谱中不存在或写法无法识别：{unknown}')
        if (not evidence or unknown) and not ablation.on('A2'):
            feedback['valid_evidence'] = self.valid_evidence(slot)

        # 2 条件适用性
        try:
            applicable, env = self.applicable_nodes(slot)
        except ExprError as e:
            applicable, env = [], {}
            fail('applicability', 'I2', str(e))
        pat_env = env
        app_ids = {n['id'] for n in applicable}
        gov_ids = {n['id'] for n in gov}
        sup_ids = {n['id'] for n in sup}
        cited_rules = kinds.get('rule', [])
        inputs = kinds.get('input', [])
        for e in cited_rules:
            n = self.kg.get(e)
            if e in gov_ids:
                if e not in app_ids:
                    fail('applicability', e, f"{e} 的适用条件对本桥不成立：{n.get('applicability')}")
            elif e in sup_ids:
                if not self._applies(n, pat, pat_env):
                    fail('applicability', e, f"{e} 的适用条件对本桥不成立：{n.get('applicability')}")
            else:
                fail('applicability', e, f'{e} 既不给出也不支撑 {pat} 这一决策')
        override = env.get('has_override')
        if override:
            if not ('MR-00' in cited_rules or inputs):
                fail('applicability', 'MR-00', '题目给定了该参数，应以输入值为准，引用 MR-00 及对应的 INPUT:路径')
        elif applicable and not (app_ids & set(cited_rules)):
            fail('applicability', 'I2', f'未引用对本桥适用的主依据，应引用：{sorted(app_ids)}')
        if env.get('has_Ge_override') and pat in ('support.{k}.Kv', 'support.{k}.Kh') and \
                not ('MR-00' in cited_rules or any('Ge' in i for i in inputs)):
            fail('applicability', 'MR-00', '题目给定了支座剪变模量 Ge，应按该值计算并引用 MR-00 或 INPUT:路径')
        if any(v['check'] in ('evidence', 'applicability') for v in violations):
            feedback['valid_evidence'] = self.valid_evidence(slot)

        # 3 数值一致性
        if norm_unit(unit) != norm_unit(canon_unit):
            fail('value', 'I2', f'单位应为 {canon_unit}，所给为 {unit}')
        try:
            if ablation.on('A1'):
                raise KeyError('value check ablated')
            exp, node, ctx = self.expected(slot)
            feedback['formula_result'] = exp
            feedback['formula_source'] = node['id']
            feedback['formula_inputs'] = {k: ctx[k] for k in node.get('inputs', [])
                                          if k in ctx and not isinstance(ctx[k], dict)}
            feedback['hint'] = ('若公式结果与你对描述的理解不符，先核对 formula_inputs 中取自实例层的数据；'
                                '实例层写错时用 write_instance 修正，不要照搬公式结果')
            if not same_value(value, exp):
                fail('value', node['id'], f'按 {node["id"]} 计算得 {exp!r}，所提为 {value!r}')
        except (ExprError, ZeroDivisionError, KeyError, TypeError) as e:
            if not missing:
                fail('value', 'I2', f'无法复算：{e}')

        # 4b 与已接受决策相容
        self._consistency(slot, pat, value, fail)

        return self._record(slot, value, unit, evidence, violations, feedback, is_revision)

    def _consistency(self, slot, pat, value, fail):
        acc = self.accepted_values()
        if pat == 'support.{k}.Kh':
            k = slot.split('.')[1]
            dofs = acc.get(f'support.{k}.dofs', {})
            lon = dofs.get('longitudinal') if isinstance(dofs, dict) else None
            if lon == 'free' and not same_value(value, 0.0):
                fail('consistency', 'C-11', f'支承线 {k} 已接受纵向自由，Kh 应为 0')
            if lon == 'spring' and same_value(value, 0.0):
                fail('consistency', 'C-11', f'支承线 {k} 已接受纵向弹簧，Kh 应为正值')
        if pat == 'girder.w' and 'girder.gamma' in acc and 'girder.A' in acc:
            if not same_value(value, acc['girder.gamma'] * acc['girder.A']):
                fail('consistency', 'C-12', '自重应等于已接受的重度与截面面积之积')
        if pat == 'support.{k}.dofs' and isinstance(value, dict):
            dofs = {s: v for s, v in acc.items() if s.endswith('.dofs') and s != slot}
            dofs[slot] = value
            n_sup = len(self.inst.data.get('supports') or [])
            if len(dofs) == n_sup and not any(
                    isinstance(v, dict) and v.get('longitudinal') in ('spring', 'fixed') for v in dofs.values()):
                fail('consistency', 'C-15', '全部支承线纵向自由，结构纵向可变')

    def supporting_nodes(self, slot):
        return [n for n in self.kg.into(f'slot:{slot_pattern(slot)}', 'SUPPORTS')]

    # ---------------- 依据写法规范化 ----------------
    @staticmethod
    def canonical_path(path):
        """把各种输入路径写法换算为 supports[0].bearing.per_girder_end 这样的规范形式。"""
        toks = [t for t in re.split(r'[.:\[\]/]+', path.strip()) if t]
        if not toks:
            return path
        head = toks[0].lower()
        idx = toks[1] if len(toks) > 1 and toks[1].isdigit() else None
        rest = toks[2:] if idx is not None else toks[1:]
        if head in ('bearing', 'bearings') and idx is not None:
            return '.'.join([f'supports[{idx}].bearing'] + rest)
        if head in ('support', 'supports') and idx is not None:
            return '.'.join([f'supports[{idx}]'] + rest)
        if head in ('pier', 'piers') and idx is not None:
            return '.'.join([f'supports[{idx}].pier'] + rest)
        if head in ('span', 'spans') and idx is not None:
            return f'spans_m[{int(idx) - 1}]'
        if head == 'spans_m' and idx is not None:
            return f'spans_m[{idx}]'
        return '.'.join(toks)

    def normalize_evidence(self, e, slot):
        """返回 (类别, 规范编号)。类别：rule / input / instance / fact / decision / unknown。"""
        e = str(e).strip().strip('"\'')
        if not e:
            return 'unknown', e
        if self.kg.has(e) and self.kg.get(e)['layer'] in ('rule', 'code') and self.kg.get(e)['type'] != 'DecisionSlot':
            return 'rule', e
        low = e.lower()
        if low in ('f1', 'fact:f1', 'fact.f1', 'fact_f1') and 'f1' in self.facts:
            return 'fact', 'fact:f1'
        body = e[4:] if low.startswith('dec:') else e
        name = re.split(r'\s*[=:]\s*(?=[-\d.])', body)[0].strip()
        if name in self.accepted:
            return 'decision', f'dec:{name}'
        if low.startswith('inst:'):
            nid = e if self.kg.has(e) else 'inst:' + re.sub(r'^inst:', '', e).replace('.', ':')
            return ('instance', nid) if self.kg.has(nid) else ('unknown', e)
        path = e[6:] if low.startswith('input:') else e
        canon = self.canonical_path(path)
        if self._input_exists(canon):
            return 'input', f'INPUT:{canon}'
        dname = re.split(r'\s*[=:]\s*(?=[-\d.])', path)[0].strip()      # 把已接受决策写成 INPUT 路径的情况
        if dname in self.accepted:
            return 'decision', f'dec:{dname}'
        nid = 'inst:' + re.sub(r'[.\[\]]+', ':', path).strip(':')
        if self.kg.has(nid):
            return 'instance', nid
        return 'unknown', e

    def input_paths(self, slot):
        """与该决策相关、在实例层中有值的 INPUT 路径。"""
        d = self.inst.data
        out = []
        m = re.match(r'^(support|pier)\.(\d+)\.', slot)
        if m:
            k = int(m.group(2))
            sup = next((s for s in d.get('supports') or [] if s['index'] == k), {})
            part = 'bearing' if m.group(1) == 'support' else 'pier'
            for f, v in (sup.get(part) or {}).items():
                if v is not None:
                    out.append(f'INPUT:supports[{k}].{part}.{f}')
            if part == 'bearing':
                out.append('INPUT:girder.count_per_span')
        elif slot.startswith('girder.') or slot.startswith('structure.'):
            for f, v in (d.get('girder') or {}).items():
                if v is not None:
                    out.append(f'INPUT:girder.{f}')
            if slot.startswith('structure.'):
                out.append('INPUT:spans_m')
        elif slot.startswith('lane.'):
            m = re.match(r'^lane\.Pk\.(\d+)$', slot)
            if m:
                out.append(f'INPUT:spans_m[{int(m.group(1)) - 1}]')
            for f, v in (d.get('deck') or {}).items():
                if v is not None:
                    out.append(f'INPUT:deck.{f}')
        return out

    def valid_evidence(self, slot):
        try:
            app, env = self.applicable_nodes(slot)
        except (ExprError, KeyError, TypeError):
            app, env = [], {}
        comp = slot_component(slot)
        return {'primary_applicable': [n['id'] for n in app],
                'supporting': [n['id'] for n in self.supporting_nodes(slot) if self._applies(n, slot_pattern(slot), env)],
                'input_paths': self.input_paths(slot),
                'instance_nodes': [comp] if self.kg.has(comp) else [],
                'rule': '至少引用一条主依据（题目给定覆盖值时引用 MR-00 与对应 INPUT 路径）；'
                        '其余为可选辅助依据，须写成此处列出的形式'}

    def _input_exists(self, path):
        cur = self.inst.data
        for part in re.findall(r'[^.\[\]]+', path):
            if isinstance(cur, list):
                try:
                    cur = cur[int(part)]
                except (ValueError, IndexError):
                    return False
            elif isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                return False
        return cur is not None

    def _describe(self, n):
        return {k: n.get(k) for k in ('id', 'title', 'clause', 'applicability', 'text', 'note') if n.get(k)} | \
               {'formula': n.get('formulas', {})}

    # ---------------- 记录与溯源 ----------------
    def _record(self, slot, value, unit, evidence, violations, feedback, is_revision):
        ok = not violations
        rec = {'slot': slot, 'value': value, 'unit': unit, 'evidence': evidence,
               'accepted': ok, 'revision': is_revision, 'violations': violations}
        self.history.append(rec)
        if ok:
            self._accept(slot, value, unit, evidence)
            return {'accepted': True, 'slot': slot, 'decision_id': self.accepted[slot]['id']}
        if ablation.on('A4'):
            return {'accepted': False, 'slot': slot}
        feedback['violations'] = violations
        feedback['failed_checks'] = sorted({v['check'] for v in violations})
        return {'accepted': False, **feedback}

    def _accept(self, slot, value, unit, evidence):
        did = f'dec:{slot}'
        if self.kg.has(did):                      # 修订：旧决策作废，边重建
            self.kg.edges = [e for e in self.kg.edges if e[0] != did]
        self.kg.add_node(did, 'decision', 'Decision', slot=slot, value=value, unit=unit, evidence=evidence)
        for e in evidence:
            if self.kg.has(e):
                self.kg.add_edge(did, 'BASED_ON', e)
        comp = slot_component(slot)
        if self.kg.has(comp):
            self.kg.add_edge(did, 'CONCERNS', comp)
        self.accepted[slot] = {'id': did, 'slot': slot, 'value': value, 'unit': unit, 'evidence': evidence}
        # 依赖该决策的已接受决策复核：不再成立者撤回，须重新提出
        self._propagate(slot)
        # 依赖该决策的分析事实失效（如修订刚度后须重新做模态分析）
        for fact, prov in list(self.fact_prov.items()):
            if slot in prov:
                self.facts.pop(fact, None)
                self.fact_prov.pop(fact, None)
                if 'lane.mu' in self.accepted:
                    self.accepted.pop('lane.mu')

    def _propagate(self, slot):
        if ablation.on('A1'):
            return
        for other in list(self.accepted):
            pat = slot_pattern(other)
            idx = re.match(r'^(?:support|pier)\.(\d+)\.', other)
            pre = [p.replace('{k}', idx.group(1)) if idx else p for p in SLOTS.get(pat, ('', '', []))[2]]
            if slot not in pre:
                continue
            try:
                exp, node, _ = self.expected(other)
            except (ExprError, ZeroDivisionError, KeyError, TypeError):
                continue
            if not same_value(self.accepted[other]['value'], exp):
                self.accepted.pop(other)
                self.history.append({'slot': other, 'value': None, 'unit': None, 'evidence': [],
                                     'accepted': False, 'revision': True, 'invalidated_by': slot,
                                     'violations': [{'check': 'consistency', 'constraint': 'C-14',
                                                     'message': f'{slot} 修订后 {other} 不再成立，须重新提出'}]})
                self._propagate(other)

    def revalidate_all(self, reason):
        """实例层修正后复核全部已接受决策：不再成立者撤回；分析事实与冲击系数失效。"""
        dropped = []
        for slot in list(self.accepted if not ablation.on('A1') else []):
            try:
                exp, node, _ = self.expected(slot)
            except (ExprError, ZeroDivisionError, KeyError, TypeError):
                exp = None
            if exp is None or not same_value(self.accepted[slot]['value'], exp):
                self.accepted.pop(slot)
                dropped.append(slot)
                self.history.append({'slot': slot, 'value': None, 'unit': None, 'evidence': [], 'accepted': False,
                                     'revision': True, 'invalidated_by': reason,
                                     'violations': [{'check': 'consistency', 'constraint': 'C-14',
                                                     'message': f'{reason} 后 {slot} 不再成立，须重新提出'}]})
        if dropped:
            self.facts.clear()
            self.fact_prov.clear()
            self.accepted.pop('lane.mu', None)
        return dropped

    def set_fact(self, name, value, provenance):
        self.facts[name] = value
        self.fact_prov[name] = set(provenance)

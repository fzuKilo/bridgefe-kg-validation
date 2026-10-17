"""模拟后端：按角色扮演各智能体，全部动作经由编排器的工具分发执行（检验工具权限、分轮调度与回路）。

instance_fault=True 时，实例智能体首次把每梁端支座数写成 2；决策智能体发现公式输入与描述矛盾后
上报实例问题，检验“上报 → 实例修正 → 图谱复核 → 重新决策”的回路。
"""
import ast
import re

from kgfem.agent.scripted import parse_structured_en


class MockBackend:
    def __init__(self, session, description, instance_fault=False):
        self.s = session
        self.truth = parse_structured_en(description)
        self.fault = instance_fault
        self.calls = []

    def run(self, system, tool_names, user_text, dispatch, is_done=lambda: False, max_turns=80):
        role = ('diagnosis' if 'at model level' in system else 'instance' if 'INSTANCE layer' in system else
                'rule' if 'MODELING-RULE' in system else 'code' if 'DESIGN-CODE' in system else 'constraint')
        self.calls.append(role)
        turns = 0

        def call(name, **args):
            nonlocal turns
            turns += 1
            return dispatch(name, args)

        if role == 'instance':
            inst = parse_structured_en(user_text.split('Bridge description:\n\n')[1].split('\n\n')[0])
            if self.fault and 'reported this problem' not in user_text:
                for sp in inst['supports']:
                    if sp['bearing'].get('per_girder_end'):
                        sp['bearing']['per_girder_end'] = 2
            call('write_instance', instance=inst)
            call('declare_decisions', slots=self.s.inst.required_slots())
        elif role == 'diagnosis':
            import json as _json
            report = _json.loads(user_text.split('Model generation result:\n')[1].split('\n\nAccepted decisions')[0])
            for _ in range(3):
                suspects = sorted({d['slot'] for f in report.get('failed_checks', []) for d in f['suspect_decisions']})
                for slot in suspects:
                    q, _ = call('query_knowledge', slot=slot)
                    node = sorted(q['applicable_to_this_bridge'], key=lambda n: (n != 'MR-00', not n.startswith('JT')))[0]
                    ex, _ = call('execute_formula', node_id=node, slot=slot)
                    call('propose_decision', slot=slot, value=ex['value'], unit=q['unit'], evidence=[node])
                if 'lane.mu' not in self.s.val.accepted:
                    call('run_modal_analysis')
                    ex, _ = call('execute_formula', node_id='JTGD60-4.3.2', slot='lane.mu')
                    call('propose_decision', slot='lane.mu', value=ex['value'], unit='-', evidence=['JTGD60-4.3.2'])
                report, _ = call('generate_model')
                if report.get('ok'):
                    call('finish', summary='repaired')
                    return {'turns': turns, 'ended': 'handoff'}
        else:
            slots = ast.literal_eval(re.search(r'Your assigned decision slots: (\[.*?\])', user_text).group(1))
            if 'lane.mu' in slots:
                call('run_modal_analysis')
            for slot in slots:
                q, _ = call('query_knowledge', slot=slot)
                node = sorted(q['applicable_to_this_bridge'], key=lambda n: (n != 'MR-00', not n.startswith('JT')))[0]
                ex, _ = call('execute_formula', node_id=node, slot=slot)
                if self._contradicts(slot, ex.get('inputs', {})):
                    call('report_instance_issue', message=f'{slot}: per_girder_end in the instance contradicts '
                         'the description ("one under each girder end")')
                    return {'turns': turns, 'ended': 'handoff'}
                ev = [node] + (['INPUT:girder.gamma_override_kNm3' if slot == 'girder.gamma' else
                                'INPUT:girder.E_override_MPa'] if node == 'MR-00' else [])
                ctx = self.s.inst.context(slot, self.s.val.accepted_values(), self.s.val.facts)
                if ctx.get('has_Ge_override') and slot.endswith(('.Kv', '.Kh')):
                    ev.append(f"INPUT:supports[{slot.split('.')[1]}].bearing.Ge_MPa")
                call('propose_decision', slot=slot, value=ex['value'], unit=q['unit'], evidence=ev)
        call('handoff', summary='done')
        return {'turns': turns, 'ended': 'handoff'}

    def _contradicts(self, slot, inputs):
        m = re.match(r'support\.(\d+)\.bearing', slot)
        if not m:
            return False
        truth = self.truth['supports'][int(m.group(1))]['bearing'].get('per_girder_end')
        cur = self.s.inst.data['supports'][int(m.group(1))]['bearing'].get('per_girder_end')
        return truth is not None and cur != truth

"""多智能体编排：按知识图谱四层划分角色，由确定性状态机 BridgeModelingFlow 调度（论文图 4）。

状态：INSTANCE → DECISION → MODEL → (REPAIR) → DONE | FAILED
阶段之间以 JSON 数据契约传递并存档：InstanceSpec、DecisionPlan、DecisionSet、ModelIR、CheckReport。

  1 实例智能体写入实例层并声明决策清单（约束层检查完整性）
  2 决策分轮推进：每轮依次调用约束 → 建模规则 → 规范智能体，各自只处理本类中前置决策已就绪的槽位；
    任一角色上报实例问题 → 实例智能体修正 → 图谱复核全部已接受决策
  3 编排器调用模型生成工具；L1~L3 校核失败 → 约束智能体（诊断模式）按定位结果修复
每次角色调用都使用全新上下文，只携带描述、本角色任务与所需的已接受决策，控制上下文长度。
"""
import json
import os
import time

from .backends import session_dispatch
from .roles import DECISION_ORDER, ROLES, system_prompt

MAX_INSTANCE_CALLS = 3
MAX_ISSUE_LOOPS = 2
MAX_DECISION_PASSES = 4
ROLE_MAX_TURNS = 60


class BridgeModelingFlow:
    def __init__(self, session, backend):
        self.s = session
        self.backend = backend
        self.issues = []
        self.status = 'running'
        self.state = 'INSTANCE'
        self.transitions = []

    # ---------------- 状态机与数据契约 ----------------
    def _to(self, state, note=''):
        self.transitions.append({'from': self.state, 'to': state, 'note': note,
                                 't': round(time.time() - self.s.t0, 2)})
        self.state = state
        self._save_contracts()

    def _save_contracts(self):
        s = self.s
        req = s.inst.required_slots() if s.inst.data else []
        from ..kg.knowledge import SLOTS
        from ..kg.validator import slot_pattern
        contracts = {
            'InstanceSpec': s.inst.data,
            'DecisionPlan': [{'slot': x, 'category': SLOTS[slot_pattern(x)][0],
                              'agent': next((ROLES[r]['agent'] for r in DECISION_ORDER
                                             if SLOTS[slot_pattern(x)][0] in ROLES[r]['categories']), None)}
                             for x in req],
            'DecisionSet': s.val.accepted,
            'ModelIR': os.path.join(s.workdir, f'{s.problem_id}_ir.json'),
            'CheckReport': {'failed_checks': s.last_check, 'results': s.results},
            'state': self.state, 'transitions': self.transitions,
        }
        with open(os.path.join(s.workdir, f'{s.problem_id}_contracts.json'), 'w', encoding='utf-8') as fh:
            json.dump(contracts, fh, ensure_ascii=False, indent=1, default=str)

    # ---------------- 角色调用 ----------------
    def _call_role(self, role, user_text, is_done=lambda: False):
        spec = ROLES[role]
        reported = {}

        base = session_dispatch(self.s, set(spec['tools']))

        def dispatch(name, args):
            if name == 'handoff':
                return {'ok': True}, True
            if name == 'report_instance_issue':
                reported['message'] = args.get('message', '')
                return {'ok': True, 'note': 'the instance agent will correct the instance'}, True
            return base(name, args)

        n_log = len(self.s.log)
        usage = self.backend.run(system_prompt(role), spec['tools'], user_text, dispatch, is_done=is_done,
                                 max_turns=ROLE_MAX_TURNS)
        self.s.role_log.append({'role': role, 'agent': spec['agent'], 'layer': spec['layer'], 'usage': usage,
                                'tool_events': len(self.s.log) - n_log, 'reported_issue': reported.get('message')})
        return reported.get('message')

    def _accepted_brief(self, slots=None):
        acc = self.s.val.accepted
        return {k: v['value'] for k, v in acc.items() if slots is None or k in slots}

    # ---------------- 1 实例层 ----------------
    def _instance_ok(self):
        d = self.s.declared
        return bool(self.s.inst.data) and not self.s.inst.check() and d is not None and \
            set(self.s.inst.required_slots()) <= set(d)

    def run_instance(self, description, issue=None):
        if issue:
            text = (f'Bridge description:\n\n{description}\n\nAnother agent reported this problem with the instance '
                    f'layer:\n{issue}\n\nCurrent instance:\n{json.dumps(self.s.inst.data, ensure_ascii=False)}\n\n'
                    'Correct the instance where it contradicts the description, then call handoff.')
            self._call_role('instance', text)
            return
        text = f'Bridge description:\n\n{description}'
        for _ in range(MAX_INSTANCE_CALLS):
            self._call_role('instance', text)
            if self._instance_ok():
                return True
            text = (f'Bridge description:\n\n{description}\n\nThe instance layer or the declared decision list is '
                    f'not complete yet.\nConstraint-layer issues: {json.dumps(self.s.inst.check(), ensure_ascii=False)}'
                    f'\nDeclared: {self.s.declared}\nContinue: fix the instance, declare the full decision list and '
                    'call handoff.')
        return self._instance_ok()

    # ---------------- 2 决策 ----------------
    def run_decisions(self, description):
        for _ in range(MAX_DECISION_PASSES):
            progressed = False
            for role in DECISION_ORDER:
                pend = self.s.pending_by_category()
                slots = [s for cat in ROLES[role]['categories'] for s, ready in pend.get(cat, []) if ready]
                if not slots:
                    continue
                before = len(self.s.val.accepted)
                text = (f'Bridge description:\n\n{description}\n\nYour assigned decision slots: {slots}\n'
                        f'Already accepted decisions (for reference): '
                        f'{json.dumps(self._accepted_brief(), ensure_ascii=False)}\n'
                        'Decide every assigned slot, then call handoff.')
                issue = self._call_role(role, text, is_done=lambda sl=slots: all(x in self.s.val.accepted for x in sl))
                if issue:
                    self._handle_issue(description, issue, role)
                progressed = progressed or len(self.s.val.accepted) > before or bool(issue)
            if not any(self.s.pending_by_category().values()):
                return True
            if not progressed:
                break
        return not any(self.s.pending_by_category().values())

    def _handle_issue(self, description, issue, role):
        self.issues.append({'from': role, 'message': issue})
        if len(self.issues) > MAX_ISSUE_LOOPS:
            return
        prev = self.state
        self._to('INSTANCE', f'issue reported by {role}')
        self.run_instance(description, issue=issue)
        dropped = self.s.val.revalidate_all(f'实例层修正（{role} 上报）')
        self.s.role_log.append({'role': 'orchestrator', 'event': 'revalidate', 'dropped': dropped})
        self._to(prev, f'instance corrected; {len(dropped)} decisions invalidated')

    # ---------------- 3 模型生成与诊断 ----------------
    def run_model(self, description):
        out = self.s.generate_model()
        if out['ok']:
            self.s.finish('model generated and all L1-L3 checks passed')
            return True
        self._to('REPAIR', 'L1-L3 checks failed')
        report = {'ok': out.get('ok'), 'stage': out.get('stage'), 'error': (out.get('error') or '')[-1500:] or None,
                  'repair_round': out.get('repair_round'),
                  'failed_checks': [{'constraint': f['constraint'], 'message': f['message'],
                                     'suspect_decisions': [{'slot': d['slot'], 'value': d['value']}
                                                           for d in f['suspect_decisions']]}
                                    for f in out.get('failed_checks') or []]}
        text = (f'Bridge description:\n\n{description}\n\nModel generation result:\n'
                f'{json.dumps(report, ensure_ascii=False, default=str)}\n\nAccepted decisions:\n'
                f'{json.dumps(self._accepted_brief(), ensure_ascii=False)}')
        issue = self._call_role('diagnosis', text, is_done=lambda: self.s.done)
        if issue and not self.s.done:
            self._handle_issue(description, issue, 'diagnosis')
            self.run_decisions(description)
            out = self.s.generate_model()
            if out['ok']:
                self.s.finish('model regenerated after instance correction')
        return self.s.results is not None

    def run(self, description):
        if not self.run_instance(description):
            self.status = 'instance_incomplete'
        else:
            self._to('DECISION')
            if not self.run_decisions(description):
                self.status = 'decisions_incomplete'
            else:
                self._to('MODEL')
                self.status = 'passed' if self.run_model(description) else 'model_failed'
        self._to('DONE' if self.status == 'passed' else 'FAILED', self.status)
        self.s.role_log.append({'role': 'orchestrator', 'event': 'end', 'status': self.status,
                                'issues': self.issues, 'transitions': self.transitions})
        return {'status': self.status, 'roles': self.s.role_log}

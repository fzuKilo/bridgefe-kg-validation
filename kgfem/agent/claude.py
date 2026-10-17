"""Claude 驱动层：大模型通过工具驱动整个建模过程，知识图谱在每一步约束它。

采用人工控制的工具调用循环（而非 SDK 的 tool runner），以便由 ModelingSession 执行流程关卡、
记录每轮约束违反与修订，并在达到上限时终止。基座模型可替换（论文 H2 的跨基座比较）。
"""
import json

import anthropic

from .session import MAX_INSTANCE_ROUNDS, MAX_REPAIR_ROUNDS
from .tools import SESSION_TOOLS

DEFAULT_MODEL = 'claude-opus-5'
FALLBACK_MODELS = {'claude-opus-5', 'claude-fable-5', 'claude-fable-5-1'}   # 支持服务端 fallbacks 的模型
MAX_TURNS = 200
MAX_NUDGES = 3

SYSTEM_PROMPT = f"""You are the driver of a finite element modeling workflow for girder bridges. You interpret the \
bridge description, plan the work, propose every modeling decision, invoke tools to build and analyse an OpenSeesPy \
model, and diagnose and repair errors. An executable bridge knowledge graph (KG) constrains you: it supplies the \
modeling rules and design-code clauses (JTG D60-2015, JTG 3362-2018, JT/T 854-2013), validates every decision you \
propose, and localizes suspect decisions when the finished model fails its checks.

Workflow
1. Call get_input_schema, then write_instance with everything the description states about spans, deck and \
design standard, girders and section geometry, supports, bearings and piers. Convert units exactly (mm -> m where \
the schema asks for m). Leave a field null only if the description does not give it. The KG checks completeness \
and plausibility; fix the reported issues (at most {MAX_INSTANCE_ROUNDS} rounds). The description is the only \
source of bridge data - never invent values it does not state.
2. Call declare_decisions with the full list of decision slots the model needs, then fix what the KG reports as \
missing or not required. Slot names follow the KG patterns: structure.idealization, structure.system, \
girder.single.A/I (precast girders only), girder.A, girder.I, girder.Ec, girder.gamma, girder.w, girder.m, \
support.<k>.bearing, support.<k>.dofs, support.<k>.S / .Kv / .Kh (laminated elastomeric bearings only), \
pier.<k>.length / .A / .I / .Ec (supports that sit on piers), lane.n_lanes, lane.xi, lane.qk, lane.Pk.<span>, lane.mu.
3. For each decision, use query_knowledge(slot=...) to find the governing rule or clause and its applicability, \
compute the value (execute_formula runs the clause formula on this bridge; compute_section_properties integrates a \
section), and call propose_decision with the value, the unit the KG expects and the evidence node ids. When the \
description gives a value that overrides a code default, cite MR-00 and the instance path as "INPUT:<path>" \
(for example "INPUT:girder.E_override_MPa" or "INPUT:supports[2].bearing.Ge_MPa"). If a proposal is rejected, \
read the structured feedback - the violated check, the applicable conditions, the formula result and the \
formula inputs taken from the instance - and revise. If the formula result contradicts the description, the \
instance is probably wrong: check formula_inputs against the description and correct the instance with \
write_instance rather than copying the formula result. Evidence: cite at least one PRIMARY node - an applicable rule or clause that gives the formula for the slot (query_knowledge lists them as applicable_to_this_bridge); when the description overrides a code default, cite MR-00 and the INPUT path instead. You may add SUPPORTING evidence: supporting clauses, instance nodes such as \"inst:bearing:0\", instance data as \"INPUT:<path>\" in the form \"INPUT:supports[0].bearing.per_girder_end\", \"INPUT:girder.count_per_span\", \"INPUT:spans_m[0]\", \"INPUT:deck.carriageway_width_m\", the fact \"fact:f1\", or an accepted decision \"dec:<slot>\". If evidence is rejected, the feedback field valid_evidence lists exactly what may be cited.
4. The impact factor needs the fundamental frequency: once all structural decisions are accepted, call \
run_modal_analysis, then decide lane.mu from JTGD60-4.3.2.
5. Call generate_model. If the model fails its L1/L2/L3 checks, the KG returns the violated constraints and the \
suspect decisions traced through provenance; diagnose the root cause, revise the responsible decisions with \
propose_decision (redo run_modal_analysis and lane.mu if structural decisions changed) and call generate_model \
again (at most {MAX_REPAIR_ROUNDS} rounds).
6. When generate_model succeeds, call finish with a short summary of the model and the key results.

Value formats: numbers for numeric slots in the KG unit; structure.idealization "spine_beam_2d"; structure.system \
"simply_supported" | "continuous" | "continuous_on_piers"; support.<k>.bearing \
{{"type": "plain_elastomeric" | "ptfe_sliding" | "spherical_fixed" | "spherical_sliding", "count": <bearings on \
the line>}}; support.<k>.dofs {{"vertical": "spring" | "rigid", "longitudinal": "spring" | "free" | "fixed", \
"rotation": "free"}}. Supports are numbered from 0 at the first abutment; spans from 1.

Work through the decisions steadily; you may call several independent tools in one turn. Report problems you \
cannot resolve in the finish summary instead of guessing."""

TOOLS = [dict(t) for t in SESSION_TOOLS]
TOOLS[-1]['cache_control'] = {'type': 'ephemeral'}          # 工具定义与系统提示词构成稳定前缀，缓存复用


class ClaudeDriver:
    def __init__(self, session, model=DEFAULT_MODEL, effort='high', client=None):
        self.s = session
        self.model = model
        self.effort = effort
        self.client = client or anthropic.Anthropic()
        self.usage = {'input_tokens': 0, 'output_tokens': 0, 'cache_read_input_tokens': 0,
                      'cache_creation_input_tokens': 0, 'turns': 0}

    def _call(self, messages):
        kw = dict(model=self.model, max_tokens=16000, tools=TOOLS, messages=messages,
                  system=[{'type': 'text', 'text': SYSTEM_PROMPT}],
                  output_config={'effort': self.effort})
        if self.model in FALLBACK_MODELS:
            return self.client.beta.messages.create(betas=['server-side-fallback-2026-07-01'],
                                                    fallbacks='default', **kw)
        return self.client.messages.create(**kw)

    def _dispatch(self, name, args):
        fn = getattr(self.s, name, None)
        if fn is None or name.startswith('_') or name not in {t['name'] for t in TOOLS}:
            return {'error': f'unknown tool {name}'}
        try:
            return fn(**args)
        except TypeError as e:
            return {'error': f'invalid arguments for {name}: {e}'}

    def run(self, description):
        messages = [{'role': 'user', 'content': f'Bridge description:\n\n{description}'}]
        nudges = 0
        for _ in range(MAX_TURNS):
            resp = self._call(messages)
            self.usage['turns'] += 1
            for k in ('input_tokens', 'output_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens'):
                self.usage[k] += getattr(resp.usage, k, 0) or 0
            if resp.stop_reason == 'refusal':
                self.usage['stopped'] = 'refusal'
                break
            messages.append({'role': 'assistant', 'content': resp.content})
            if resp.stop_reason == 'max_tokens':
                messages.append({'role': 'user', 'content': 'Your last turn hit the output limit. Continue with '
                                 'smaller steps.'})
                continue
            calls = [b for b in resp.content if b.type == 'tool_use']
            if not calls:
                if self.s.done or nudges >= MAX_NUDGES:
                    break
                nudges += 1
                messages.append({'role': 'user', 'content': 'The session is not finished. Continue the workflow; '
                                 'call finish once generate_model has succeeded.'})
                continue
            results = []
            for b in calls:
                args = b.input if isinstance(b.input, dict) else {}
                out = self._dispatch(b.name, args)
                results.append({'type': 'tool_result', 'tool_use_id': b.id,
                                'content': json.dumps(out, ensure_ascii=False, default=str),
                                'is_error': isinstance(out, dict) and 'error' in out})
            messages.append({'role': 'user', 'content': results})
            if self.s.done:
                break
        self.usage['finished'] = self.s.done
        return self.usage

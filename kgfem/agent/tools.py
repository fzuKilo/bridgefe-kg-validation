"""大模型可调用的工具定义（Anthropic 格式；Ollama 后端转换为 function 格式）。

单智能体模式使用 SESSION_TOOLS；多智能体模式下各角色只取与其图谱层对应的子集，
另加 handoff（完成本角色任务、交回编排器）与 report_instance_issue（上报实例层问题）。
"""
ANY_VALUE = {'description': 'number, string or object, in the format required by the slot'}
SESSION_TOOLS = [
    {'name': 'get_input_schema', 'description': 'Return the JSON schema of the instance layer and the section geometry fields.',
     'input_schema': {'type': 'object', 'properties': {}}},
    {'name': 'write_instance', 'description': 'Write (merge) the bridge described in the input into the KG instance '
     'layer. Supports are merged by index. Returns completeness and plausibility issues from the constraint layer.',
     'input_schema': {'type': 'object', 'properties': {'instance': {'type': 'object'}}, 'required': ['instance']}},
    {'name': 'query_component', 'description': 'Return an instance-layer component (e.g. "support:2", "pier:1", '
     '"span:3", "girder", "deck") and its relations.',
     'input_schema': {'type': 'object', 'properties': {'component': {'type': 'string'}}, 'required': ['component']}},
    {'name': 'query_knowledge', 'description': 'Query the rule and code layers. With slot: the rules/clauses that '
     'govern that decision, their applicability conditions and formulas, and which apply to this bridge. With '
     'keyword: matching rules, clauses and constraints.',
     'input_schema': {'type': 'object', 'properties': {'slot': {'type': 'string'}, 'keyword': {'type': 'string'}}}},
    {'name': 'retrieve_clause', 'description': 'Return the full content of a rule, clause or constraint node.',
     'input_schema': {'type': 'object', 'properties': {'node_id': {'type': 'string'}}, 'required': ['node_id']}},
    {'name': 'execute_formula', 'description': 'Execute the formula of a rule or clause for a decision slot, using '
     'this bridge\'s instance data, accepted decisions and analysis facts. Returns the value and the inputs used.',
     'input_schema': {'type': 'object', 'properties': {'node_id': {'type': 'string'}, 'slot': {'type': 'string'}},
                      'required': ['node_id', 'slot']}},
    {'name': 'compute_section_properties', 'description': 'Integrate a cross-section (m): returns A, yc, I.',
     'input_schema': {'type': 'object', 'properties': {
         'section_type': {'type': 'string', 'enum': ['small_box', 't_girder', 'cast_box']},
         'geometry': {'type': 'object'}}, 'required': ['section_type', 'geometry']}},
    {'name': 'declare_decisions', 'description': 'Declare the decision slots needed to complete the model. '
     'Declarations accumulate across calls (replace=true starts over); the constraint layer reports the slots still '
     'missing and ignores slots that are not required.',
     'input_schema': {'type': 'object', 'properties': {'slots': {'type': 'array', 'items': {'type': 'string'}},
                                                       'replace': {'type': 'boolean'}},
                      'required': ['slots']}},
    {'name': 'propose_decision', 'description': 'Propose one modeling decision with its evidence. The KG checks '
     'evidence existence, applicability, value (re-executing the formula) and consistency with accepted decisions, '
     'and either accepts it or returns structured feedback. Re-proposing an accepted slot revises it.',
     'input_schema': {'type': 'object', 'properties': {
         'slot': {'type': 'string'}, 'value': ANY_VALUE, 'unit': {'type': 'string'},
         'evidence': {'type': 'array', 'items': {'type': 'string'}}, 'rationale': {'type': 'string'}},
         'required': ['slot', 'value', 'unit', 'evidence']}},
    {'name': 'decision_status', 'description': 'List accepted and pending decisions and analysis facts.',
     'input_schema': {'type': 'object', 'properties': {}}},
    {'name': 'run_modal_analysis', 'description': 'Build the model from the accepted structural decisions and run a '
     'modal analysis; records the first vertical bending frequency as fact f1.',
     'input_schema': {'type': 'object', 'properties': {}}},
    {'name': 'generate_model', 'description': 'Assemble the accepted decisions into a provenance-tracked '
     'representation, emit and run the OpenSeesPy script, and run the L1 topology, L2 code and L3 mechanics checks.',
     'input_schema': {'type': 'object', 'properties': {}}},
    {'name': 'finish', 'description': 'End the session with a short summary, after generate_model has succeeded.',
     'input_schema': {'type': 'object', 'properties': {'summary': {'type': 'string'}}, 'required': ['summary']}},
]

ROLE_TOOLS = [
    {'name': 'handoff', 'description': 'Finish your role and hand control back to the orchestrator, with a short '
     'summary of what you did and anything left unresolved.',
     'input_schema': {'type': 'object', 'properties': {'summary': {'type': 'string'}}, 'required': ['summary']}},
    {'name': 'report_instance_issue', 'description': 'Report that the instance layer contradicts the bridge '
     'description (for example a formula input that disagrees with what the description states). The instance agent '
     'will correct the instance; your role ends here.',
     'input_schema': {'type': 'object', 'properties': {'message': {'type': 'string'}}, 'required': ['message']}},
]
DEFECT_TOOL = {
    'name': 'report_input_defect',
    'description': 'Report that the bridge description cannot be modeled as given and end the session without '
                   'building a model. Use it only when a quantity the model needs is missing, statements contradict '
                   'each other, a statement is ambiguous, or a component lies outside the scope of the knowledge graph.',
    'input_schema': {'type': 'object', 'properties': {
        'defect_type': {'type': 'string', 'enum': ['missing', 'contradictory', 'ambiguous', 'out_of_scope']},
        'message': {'type': 'string', 'description': 'What is defective, quoting the statement concerned.'}},
        'required': ['defect_type', 'message']}}
DEFECT_RULE = ('\n\nDefective input: if the description omits a quantity the model needs, contains statements that '
               'contradict each other, contains a statement that can be read in more than one way, or describes a '
               'component outside the scope of the knowledge graph (a girder, bearing or structural type that its '
               'rules and clauses do not cover), do not guess and do not build a model: call report_input_defect with '
               'the defect and stop. Do not call it for a description that can be modeled as given.')
TOOL_DEFS = {t['name']: t for t in SESSION_TOOLS + ROLE_TOOLS + [DEFECT_TOOL]}


SEARCH_TOOL = {'name': 'search_knowledge', 'description': 'Search the design-code clauses, modeling rules and two '
               'worked examples (BM25 full-text search). Returns the best-matching passages to read.',
               'input_schema': {'type': 'object', 'properties': {'query': {'type': 'string'}},
                                'required': ['query']}}      # 仅检索增强基线 C3 使用


def tool_defs(names):
    return [TOOL_DEFS.get(n) or SEARCH_TOOL for n in names]

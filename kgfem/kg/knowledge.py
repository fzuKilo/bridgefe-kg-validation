"""可执行桥梁知识图谱的知识内容（建模规则层、规范层、约束层与决策模板）。

每个规则 / 条文节点包含论文 4.2 节所述五项属性：
  applicability  适用条件（表达式，对本桥上下文求值）
  inputs         输入参数（由公式自动列出）
  formulas       输出 → 公式（可执行表达式），键为决策槽位模式
  outputs        输出参数
  clause / text  条文编号与原文摘要
另有 intermediates：按顺序先求值的中间量（如形状系数 S、抗压弹性模量 Ee）。

决策槽位（slot）是一项建模决策的规范化名称，形如 'support.{k}.Kv'。
单位统一为 m、kN、MPa。条文号按 JTG D60-2015、JTG 3362-2018、JT/T 854-2013 整理，
使用前须由专家核对。
"""
from .expr import names
from .graph import KnowledgeGraph

EC_TABLE = {'C25': 2.80e4, 'C30': 3.00e4, 'C35': 3.15e4, 'C40': 3.25e4, 'C45': 3.35e4,
            'C50': 3.45e4, 'C55': 3.55e4, 'C60': 3.60e4, 'C65': 3.65e4, 'C70': 3.70e4,
            'C75': 3.75e4, 'C80': 3.80e4}
XI_TABLE = {1: 1.20, 2: 1.00, 3: 0.78, 4: 0.67, 5: 0.60, 6: 0.55, 7: 0.52, 8: 0.50}
G_ACC = 9.81

# 槽位的类别、单位与前置决策（{k}、{j} 为支承线号、跨号占位符）
SLOTS = {
    'structure.idealization': ('modeling_rule', '-', []),
    'structure.system': ('modeling_rule', '-', []),
    'girder.single.A': ('modeling_rule', 'm^2', []),
    'girder.single.I': ('modeling_rule', 'm^4', []),
    'girder.A': ('modeling_rule', 'm^2', []),
    'girder.I': ('modeling_rule', 'm^4', []),
    'girder.Ec': ('code_parameter', 'MPa', []),
    'girder.gamma': ('code_parameter', 'kN/m^3', []),
    'girder.w': ('code_parameter', 'kN/m', ['girder.gamma', 'girder.A']),
    'girder.m': ('modeling_rule', 't/m', ['girder.w']),
    'support.{k}.bearing': ('topology', '-', []),
    'support.{k}.dofs': ('modeling_rule', '-', ['support.{k}.bearing']),
    'support.{k}.S': ('code_parameter', '-', ['support.{k}.bearing']),
    'support.{k}.Kv': ('code_parameter', 'kN/m', ['support.{k}.bearing']),
    'support.{k}.Kh': ('code_parameter', 'kN/m', ['support.{k}.bearing', 'support.{k}.dofs']),
    'pier.{k}.length': ('topology', 'm', []),
    'pier.{k}.A': ('modeling_rule', 'm^2', []),
    'pier.{k}.I': ('modeling_rule', 'm^4', []),
    'pier.{k}.Ec': ('code_parameter', 'MPa', []),
    'lane.n_lanes': ('code_parameter', '-', []),
    'lane.xi': ('code_parameter', '-', ['lane.n_lanes']),
    'lane.qk': ('code_parameter', 'kN/m', []),
    'lane.Pk.{j}': ('code_parameter', 'kN', []),
    'lane.mu': ('code_parameter', '-', []),
}

# 冲击系数依赖模态分析得到的基频（论文图 3 的规范—模型双向耦合）
FACT_PREREQS = {'lane.mu': ['fact.f1']}

RULES = [
    dict(id='MR-01', title='梁桥单梁（脊梁）理想化',
         text='直线梁桥的整体计算采用二维单梁模型、线弹性分析，主梁采用弹性梁柱单元。',
         applicability='True',
         formulas={'structure.idealization': "'spine_beam_2d'"}),
    dict(id='MR-05', title='结构体系',
         text='单跨为简支体系；先简支后连续结构按成桥连续体系计算，不模拟施工阶段体系转换；'
              '含桥墩的现浇连续梁按支承于桥墩的连续梁计算。models_pier_columns 指实例中给出了墩柱几何、需模拟墩柱；'
              '(models_pier_columns is true only when pier column geometry is given; support lines merely named "Pier" '
              'without column data are bearings on rigid supports, so the system is "continuous") '
              '中间支承线仅称为“桥墩”而描述未给墩柱数据时不模拟墩柱（墩顶按支座支承），体系为 continuous。',
         applicability='True',
         formulas={'structure.system': "'simply_supported' if n_spans == 1 else "
                                       "('continuous_on_piers' if models_pier_columns else 'continuous')"}),
    dict(id='MR-02', title='主梁截面特性',
         text='截面特性由截面几何（外轮廓减内孔）精确积分计算；多片预制梁合并为单梁时，'
              'A、I 取单片中梁跨中截面乘以片数，湿接缝与横隔板不计。',
         applicability='True',
         formulas={'girder.single.A': 'sec_A', 'girder.single.I': 'sec_I',
                   'girder.A': 'A_single * n_girders if precast else sec_A',
                   'girder.I': 'I_single * n_girders if precast else sec_I'}, supports=['girder.w']),
    dict(id='MR-00', title='输入优先',
         text='题目明确给定的参数（实测弹性模量、业主指定重度、厂家剪变模量等）优先于规范默认值。',
         applicability='has_override',
         formulas={'girder.Ec': 'override', 'girder.gamma': 'override'}),
    dict(id='MR-07', title='恒载与质量',
         text='恒载只计主梁自重 w = γA；质量取 m = w/g，采用一致质量矩阵。',
         applicability='True',
         formulas={'girder.w': 'gamma * A', 'girder.m': 'w / 9.81'}),
    dict(id='MR-04', title='支座数量与并联',
         text='同一支承线上的支座并联、刚度相加；预制梁支座数 = 每梁端支座数 × 主梁片数，'
              '现浇箱梁取每条支承线支座数。',
         applicability='True',
         formulas={'support.{k}.bearing': "{'type': bearing_type, 'count': count}"},
         supports=['support.{k}.Kv', 'support.{k}.Kh']),
    dict(id='MR-03', title='板式橡胶支座的模拟',
         text='板式橡胶支座以零长度弹簧模拟：竖向刚度 Kv；普通板式支座纵向取剪切刚度 Kh，'
              '四氟滑板支座纵向自由（Kh = 0）；转动自由。支座置于主梁轴线标高。',
         applicability="family == 'laminated_elastomeric'",
         formulas={'support.{k}.dofs': "{'vertical': 'spring', 'longitudinal': 'free' if sliding else 'spring', "
                                       "'rotation': 'free'}",
                   'support.{k}.Kh': '0.0'},
         formula_applicability={'support.{k}.Kh': 'sliding'}),
    dict(id='MR-08', title='球形支座的模拟',
         text='球形支座按竖向刚性支承模拟，转动自由；固定型（GD）及横桥向单向活动型（DX）纵向约束，'
              '纵向活动型纵向自由。',
         applicability="family == 'spherical'",
         formulas={'support.{k}.dofs': "{'vertical': 'rigid', 'longitudinal': 'fixed' if fixed else 'free', "
                                       "'rotation': 'free'}"}),
    dict(id='MR-06', title='桥墩的模拟',
         text='桥墩按弹性梁柱单元模拟，墩底固结；双柱墩合并为单柱，A、I 取各柱之和；墩身质量计入。',
         applicability='has_pier',
         formulas={'pier.{k}.length': 'H', 'pier.{k}.A': 'n_col * pi * D**2 / 4',
                   'pier.{k}.I': 'n_col * pi * D**4 / 64'}),
    dict(id='LL-01', title='车道荷载布置',
         text='qk 满布于同号影响线区段；Pk 置于影响线最不利纵坐标处，按其所在跨计算跨径取值；'
              '效应乘以 (1+μ)、设计车道数与横向车道布载系数。',
         applicability='True', formulas={}, supports=['lane.qk', 'lane.Pk.{j}', 'lane.n_lanes', 'lane.xi']),
    dict(id='LL-02', title='冲击系数所用基频',
         text='冲击系数按 JTG D60-2015 第 4.3.2 条由结构基频计算，基频取有限元模态分析的一阶竖向弯曲频率。',
         applicability='has_f1', formulas={}, supports=['lane.mu']),
]

CLAUSES = [
    dict(id='JTG3362-3.1.5', clause='JTG 3362-2018 3.1.5 表 3.1.5', title='混凝土弹性模量',
         concept='concrete', applicability='grade in EC_TABLE and not has_override',
         formulas={'girder.Ec': 'EC_TABLE[grade]', 'pier.{k}.Ec': 'EC_TABLE[grade]'},
         tables={'EC_TABLE': EC_TABLE}),
    dict(id='JTGD60-4.2.1', clause='JTG D60-2015 4.2.1 表 4.2.1', title='材料重度',
         concept='concrete', applicability="material == 'prestressed_concrete' and not has_override",
         formulas={'girder.gamma': '26.0'}, supports=['girder.w'],
         note='钢筋混凝土、预应力混凝土 25.0~26.0 kN/m3，预应力混凝土取上限 26.0'),
    dict(id='JTG3362-8.7-S', clause='JTG 3362-2018 8.7', title='板式橡胶支座形状系数',
         concept='bearing', applicability="family == 'laminated_elastomeric'",
         formulas={'support.{k}.S': 'a * b / (2 * t1 * (a + b))'}, supports=['support.{k}.Kv']),
    dict(id='JTG3362-8.7-Kv', clause='JTG 3362-2018 8.7', title='板式橡胶支座竖向刚度',
         concept='bearing', applicability="family == 'laminated_elastomeric'",
         intermediates=[('S', 'a * b / (2 * t1 * (a + b))'), ('Ee', '5.4 * Ge * S**2')],
         formulas={'support.{k}.Kv': 'count * a * b / (te * (1 / Ee + 1 / Eb)) * 1000'},
         note='Ee = 5.4 Ge S^2，Eb = 2000 MPa；Kv 单位 kN/m（a、b、te 以 m 计，模量以 MPa 计）'),
    dict(id='JTG3362-8.7-Kh', clause='JTG 3362-2018 8.7', title='板式橡胶支座剪切刚度',
         concept='bearing', applicability="family == 'laminated_elastomeric' and not sliding",
         formulas={'support.{k}.Kh': 'count * Ge * a * b / te * 1000'}),
    dict(id='JTG3362-8.7-Ge', clause='JTG 3362-2018 8.7', title='橡胶剪变模量标准值',
         concept='bearing', applicability="family == 'laminated_elastomeric' and not has_Ge_override",
         formulas={}, value={'Ge': 1.0}, supports=['support.{k}.Kv', 'support.{k}.Kh']),
    dict(id='JTT854', clause='JT/T 854-2013', title='公路桥梁球形支座',
         concept='bearing', applicability="family == 'spherical'", formulas={},
         note='GD 固定、DX 单向活动、SX 双向活动；竖向压缩变形小，可按刚性支承',
         supports=['support.{k}.bearing', 'support.{k}.dofs']),
    dict(id='JTGD60-4.3.1-lanes', clause='JTG D60-2015 4.3.1 表 4.3.1-4', title='设计车道数',
         concept='lane', applicability='W >= 6.0 if two_way else True',
         formulas={'lane.n_lanes': '(2 if W < 14 else 4 if W < 21 else 6 if W < 28 else 8) if two_way else '
                                   '(1 if W < 7 else 2 if W < 10.5 else 3 if W < 14 else 4 if W < 17.5 else '
                                   '5 if W < 21 else 6 if W < 24.5 else 7 if W < 28 else 8)'}),
    dict(id='JTGD60-4.3.1-xi', clause='JTG D60-2015 4.3.1 表 4.3.1-5', title='横向车道布载系数',
         concept='lane', applicability='n_lanes in XI_TABLE',
         formulas={'lane.xi': 'XI_TABLE[n_lanes]'}, tables={'XI_TABLE': XI_TABLE}),
    dict(id='JTGD60-4.3.1-qk', clause='JTG D60-2015 4.3.1', title='车道荷载均布荷载标准值',
         concept='lane', applicability="load_class in ('I', 'II')",
         formulas={'lane.qk': "10.5 * (1.0 if load_class == 'I' else 0.75)"}),
    dict(id='JTGD60-4.3.1-Pk', clause='JTG D60-2015 4.3.1', title='车道荷载集中荷载标准值',
         concept='lane', applicability="load_class in ('I', 'II') and L0 > 0",
         formulas={'lane.Pk.{j}': "(270 if L0 <= 5 else 360 if L0 >= 50 else 2 * (L0 + 130)) * "
                                  "(1.0 if load_class == 'I' else 0.75)"}),
    dict(id='JTGD60-4.3.2', clause='JTG D60-2015 4.3.2', title='汽车荷载冲击系数',
         concept='lane', applicability='has_f1',
         formulas={'lane.mu': '0.05 if f1 < 1.5 else 0.45 if f1 > 14 else 0.1767 * log(f1) - 0.0157'}),
]

# 约束层：kind = instance（完整性、合理性）/ decision（决策相容性）/ model（模型级校核）
CONSTRAINTS = [
    dict(id='C-01', kind='instance', text='支承线数 = 跨数 + 1，跨径均为正值'),
    dict(id='C-02', kind='instance', text='每条支承线必须有支座，支座参数完整（板式橡胶支座需平面尺寸与橡胶层）'),
    dict(id='C-03', kind='instance', text='主梁类型、片数、混凝土与截面几何必须完整'),
    dict(id='C-04', kind='instance', text='含桥墩的结构，每个中间支承线必须有桥墩（墩高、柱径、柱数、混凝土）'),
    dict(id='C-05', kind='instance', text='设计标准必须给出荷载等级、行车道宽、行车方向与设计车道数，且车道数与行车道宽相符'),
    dict(id='C-06', kind='instance', text='至少一条支承线纵向约束（固定支座），否则结构纵向可变'),
    dict(id='C-07', kind='instance', text='支座数量合理：预制梁每个梁端 1~2 个，现浇箱梁每条支承线 1~6 个'),
    dict(id='C-08', kind='instance', text='截面几何自洽：各板件尺寸不超过所属轮廓，内孔与翼缘尺寸为正，板厚之和小于梁高'),
    dict(id='C-10', kind='decision', text='支座约束自由度须与该支承线已接受的支座类型一致'),
    dict(id='C-11', kind='decision', text='纵向自由的支承线 Kh 必须为 0；纵向为弹簧的支承线 Kh 必须为正'),
    dict(id='C-12', kind='decision', text='自重 w 须等于已接受的重度与截面面积之积'),
    dict(id='C-13', kind='decision', text='决策所指构件必须存在于实例层（支承线号、桥墩号、跨号）'),
    dict(id='C-14', kind='decision', text='前置决策须先被接受（如 Kv 依赖支座类型与数量）'),
    dict(id='C-15', kind='decision', text='全部支承线的约束自由度确定后，至少一条纵向约束'),
    dict(id='L1-1', kind='model', text='无孤立节点、无重复单元，主梁节点连通'),
    dict(id='L1-2', kind='model', text='主梁竖向支承不少于两处，纵向至少一处约束'),
    dict(id='L2-1', kind='model', text='模型中每个构件的参数与其溯源决策一致，且按规则层 / 规范层公式复算成立'),
    dict(id='L2-2', kind='model', text='每跨均有车道荷载 Pk，冲击系数与模型一阶竖向频率一致'),
    dict(id='L3-1', kind='model', text='自重下支座反力之和等于总自重'),
    dict(id='L3-2', kind='model', text='总自重等于重度 × 截面面积 × 桥长（工程量）'),
    dict(id='L3-3', kind='model', text='一阶竖向频率位于跨径对应的经验范围内'),
]

# 决策模板：每类构件需要做出的决策（槽位）及其适用条件
TEMPLATES = [
    dict(id='T-bridge', component='Bridge', slots=[
        ('structure.idealization', 'True'), ('structure.system', 'True'),
        ('girder.single.A', 'precast'), ('girder.single.I', 'precast'),
        ('girder.A', 'True'), ('girder.I', 'True'), ('girder.Ec', 'True'), ('girder.gamma', 'True'),
        ('girder.w', 'True'), ('girder.m', 'True'),
        ('lane.n_lanes', 'True'), ('lane.xi', 'True'), ('lane.qk', 'True'), ('lane.mu', 'True')]),
    dict(id='T-span', component='Span', slots=[('lane.Pk.{j}', 'True')]),
    dict(id='T-support', component='Support', slots=[
        ('support.{k}.bearing', 'True'), ('support.{k}.dofs', 'True'),
        ('support.{k}.S', "family == 'laminated_elastomeric'"),
        ('support.{k}.Kv', "family == 'laminated_elastomeric'"),
        ('support.{k}.Kh', "family == 'laminated_elastomeric'")]),
    dict(id='T-pier', component='Pier', slots=[
        ('pier.{k}.length', 'True'), ('pier.{k}.A', 'True'), ('pier.{k}.I', 'True'), ('pier.{k}.Ec', 'True')]),
]


def build_knowledge_graph():
    """构建规则层、规范层、约束层与决策模板（实例层与决策层在建模过程中写入）。"""
    kg = KnowledgeGraph()
    for r in RULES:
        r = dict(r)
        kg.add_node(r.pop('id'), 'rule', 'ModelingRule', inputs=_inputs(r), outputs=list(r['formulas']), **r)
    for c in CLAUSES:
        c = dict(c)
        cid = c.pop('id')
        kg.add_node(cid, 'code', 'CodeClause', inputs=_inputs(c), outputs=list(c['formulas']), **c)
        concept = f"concept:{c['concept']}"
        if not kg.has(concept):
            kg.add_node(concept, 'rule', 'ComponentConcept', name=c['concept'])
        kg.add_edge(cid, 'ACTS_ON', concept)
    for c in CONSTRAINTS:
        c = dict(c)
        kg.add_node(c.pop('id'), 'constraint', 'Constraint', **c)
    for t in TEMPLATES:
        t = dict(t)
        kg.add_node(t.pop('id'), 'rule', 'DecisionTemplate', **t)
    # 槽位 → 依据节点：GOVERNS（给出该决策的公式，主依据）与 SUPPORTS（提供输入或模拟依据，辅助依据）
    for slot, (cat, unit, pre) in SLOTS.items():
        kg.add_node(f'slot:{slot}', 'rule', 'DecisionSlot', pattern=slot, category=cat, unit=unit, prerequisites=pre)
    for n in list(kg.nodes.values()):
        for slot in n.get('formulas', {}):
            kg.add_edge(n['id'], 'GOVERNS', f'slot:{slot}')
        for slot in n.get('supports', []):
            kg.add_edge(n['id'], 'SUPPORTS', f'slot:{slot}')
    return kg


def _inputs(node):
    exprs = list(node.get('formulas', {}).values()) + [e for _, e in node.get('intermediates', [])]
    got = set()
    for e in exprs:
        got.update(names(e))
    got -= {n for n, _ in node.get('intermediates', [])}
    return sorted(got)

"""生成 BridgeFE-Bench 数据集。

运行：python build_dataset.py
输出（均在 bridgefe_bench/ 下）：
  problems/<id>.json         单题完整记录：输入描述、题目参数、决策层与响应层参考答案
  inputs/<id>_en.txt, _zh.txt 结构化输入描述（提供给被测方法的唯一输入）
  free_text/<id>_s<k>_<lang>.txt  自由文本改写（3 题 × 3 种写法 × 中英文）
  index.csv                   题目总表
  rules.json                  决策依据编号（建模规则、约定、规范条文）
  validation_report.md        参考答案自检报告
"""
import csv
import json
import os

import analytical
import code_provisions as cp
import descriptions as ds
import problems as P
import reference_model as R

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FREE_TEXT_IDS = ['A03', 'B04', 'C02']

RULES = {
    'MR-01': '梁桥上部结构按二维单梁（脊梁）模型、线弹性分析；主梁采用弹性梁柱单元（OpenSees elasticBeamColumn）。',
    'MR-02': '多片预制梁合并为单梁：A、I 取单片中梁截面特性乘以片数（湿接缝、横隔板不计）；现浇箱梁按给定尺寸计算全截面特性。截面特性由截面几何精确计算。',
    'MR-03': '板式橡胶支座以零长度弹簧单元模拟：竖向刚度 Kv；普通板式（固定）支座纵向刚度取剪切刚度 Kh，四氟滑板（滑动）支座纵向自由；转动自由。支座与墩顶均置于主梁轴线标高，偏心不计。',
    'MR-04': '同一支承线上的多个支座并联，刚度相加；支座数量 = 每梁端支座数 × 主梁片数（预制梁），或每条支承线支座数（现浇箱梁）。',
    'MR-05': '先简支后连续结构按成桥连续体系计算，不模拟施工阶段体系转换；现浇连续梁在中间支点连续。',
    'MR-06': '桥墩按弹性梁柱单元模拟，墩底固结；双柱墩合并为单柱，A、I 取两柱之和；墩身质量计入，墩身自重不计入支座反力。',
    'MR-07': '恒载仅计主梁自重 w = γA；质量取 m = w/g，采用一致质量矩阵。',
    'MR-08': '球形支座（JT/T 854）按竖向刚性支承模拟，转动自由；固定型（GD）及横桥向单向活动型（DX）纵向约束，纵向活动型（SX/DX）纵向自由。',
    'LL-01': '车道荷载：qk 满布于同号影响线区段；Pk 置于影响线最不利纵坐标处，Pk 按其所在跨的计算跨径取值；效应乘以 (1+μ)、设计车道数与横向车道布载系数。正弯矩控制截面取各跨跨中，负弯矩控制截面取各中间支点。',
    'LL-02': '冲击系数 μ 按 JTG D60-2015 第 4.3.2 条由结构基频计算，基频取有限元模态分析得到的一阶竖向弯曲频率，正负弯矩均用同一 μ。',
    'INPUT': '取值由题目输入直接给定（覆盖规范默认值时以输入为准）。',
    **cp.CLAUSES,
}


SIMPLE_SLOTS = [
    ('structural idealization', 'structure.idealization'), ('structural system', 'structure.system'),
    ('single girder section A', 'girder.single.A'), ('single girder section I', 'girder.single.I'),
    ('spine-beam section A', 'girder.A'), ('spine-beam section I', 'girder.I'),
    ('girder section A', 'girder.A'), ('girder section I', 'girder.I'),
    ('girder elastic modulus Ec', 'girder.Ec'), ('unit weight of girder concrete', 'girder.gamma'),
    ('girder self-weight w', 'girder.w'), ('girder mass per length', 'girder.m'),
    ('number of design lanes', 'lane.n_lanes'), ('transverse lane reduction factor', 'lane.xi'),
    ('lane load qk', 'lane.qk'), ('impact factor mu', 'lane.mu'),
]
COMPONENT_SLOTS = [
    ('bearing type and number', 'support.{k}.bearing'), ('restrained DOFs', 'support.{k}.dofs'),
    ('shape factor S', 'support.{k}.S'), ('vertical stiffness Kv', 'support.{k}.Kv'),
    ('longitudinal stiffness Kh', 'support.{k}.Kh'), ('pier column length', 'pier.{k}.length'),
    ('pier section A', 'pier.{k}.A'), ('pier section I', 'pier.{k}.I'), ('pier elastic modulus', 'pier.{k}.Ec'),
]
BEARING_TYPE = {'elastomeric': 'plain_elastomeric', 'sliding': 'ptfe_sliding',
                'spherical_fixed': 'spherical_fixed', 'spherical_sliding': 'spherical_sliding'}


def annotate_slots(p, decisions):
    """为参考决策补充方法所用的槽位名（slot）与规范化取值（canonical），供决策层评估。"""
    import re
    system = {'simply_supported': 'simply_supported', 'precast_continuous': 'continuous',
              'cast_continuous_with_piers': 'continuous_on_piers'}[p['structure']]
    for d in decisions:
        item, slot, canon = d['item'], None, d['value']
        m = re.match(r'(?:Abutment|Pier) (\d+): (.*)', item)
        if m:
            k, rest = int(m.group(1)), m.group(2)
            for key, pat in COMPONENT_SLOTS:
                if rest.startswith(key):
                    slot = pat.replace('{k}', str(k))
            b = p['bearings'][k]
            if slot and slot.endswith('.bearing'):
                count = int(re.search(r'(\d+) bearings', d['value']).group(1))
                canon = {'type': BEARING_TYPE[b['kind']], 'count': count}
            elif slot and slot.endswith('.dofs'):
                if b['kind'].startswith('spherical'):
                    canon = {'vertical': 'rigid', 'longitudinal': 'fixed' if b['kind'] == 'spherical_fixed'
                             else 'free', 'rotation': 'free'}
                else:
                    canon = {'vertical': 'spring', 'longitudinal': 'free' if b['kind'] == 'sliding' else 'spring',
                             'rotation': 'free'}
        else:
            m = re.match(r'lane load Pk \(span (\d+)', item)
            if m:
                slot = f'lane.Pk.{m.group(1)}'
            for key, sl in SIMPLE_SLOTS:
                if slot is None and item.startswith(key):
                    slot = sl
            if slot == 'structure.idealization':
                canon = 'spine_beam_2d'
            elif slot == 'structure.system':
                canon = system
        d['slot'] = slot
        d['canonical'] = canon
    return decisions


def rel(a, b):
    return abs(a - b) / abs(b) if b else abs(a - b)


def main():
    for sub in ['problems', 'inputs', 'free_text']:
        os.makedirs(os.path.join(ROOT, sub), exist_ok=True)
    problems = P.sample_all()
    index_rows, report = [], []
    report.append('# BridgeFE-Bench 参考答案自检报告\n')
    report.append('| 题号 | 反力之和/总自重 | A 档：解析解 vs OpenSees 最大相对差 | 网格加密（每跨 20→40 单元）最大相对变化 |')
    report.append('|---|---|---|---|')

    for p in problems:
        decisions, spec, props = P.resolve(p)
        resp_fe = R.solve_reference(spec)
        if p['tier'] == 'A':
            resp = analytical.solve_tier_a(spec)
            resp['vertical_frequencies_Hz_fe'] = resp_fe['vertical_frequencies_Hz']
            source = 'analytical (cross-checked with OpenSeesPy)'
            keys = ['first_vertical_frequency_Hz', 'lane_max_positive_moment_kNm']
            diff_a = max([rel(resp_fe[k], resp[k]) for k in keys]
                         + [rel(x, y) for x, y in zip(resp_fe['self_weight_support_reactions_kN'],
                                                     resp['self_weight_support_reactions_kN'])]
                         + [rel(resp_fe['self_weight_midspan_moments_kNm'][0],
                                resp['self_weight_midspan_moments_kNm'][0])])
            diff_a_s = f'{diff_a:.1e}'
        else:
            resp = resp_fe
            source = 'independent OpenSeesPy reference model'
            diff_a_s = '—'

        # 网格收敛性
        R.N_PER_SPAN = 40
        fine = R.solve_reference(spec)
        R.N_PER_SPAN = 20
        conv = max([rel(fine['first_vertical_frequency_Hz'], resp_fe['first_vertical_frequency_Hz']),
                    rel(fine['lane_max_positive_moment_kNm'], resp_fe['lane_max_positive_moment_kNm'])]
                   + ([rel(fine['lane_max_negative_moment_kNm'], resp_fe['lane_max_negative_moment_kNm'])]
                      if resp_fe['lane_max_negative_moment_kNm'] else []))
        total_w = spec['girder']['w'] * sum(spec['spans']) / 1e3
        eq = sum(resp['self_weight_support_reactions_kN']) / total_w
        report.append(f"| {p['id']} | {eq:.12f} | {diff_a_s} | {conv:.1e} |")

        annotate_slots(p, decisions)
        for d in decisions:
            if d['item'] == 'impact factor mu':
                d['value'] = resp['impact_factor_mu']
                d['note'] = f"f1 = {resp['first_vertical_frequency_Hz']:.6g} Hz; mu = 0.1767 ln f1 - 0.0157"
                d['canonical'] = resp['impact_factor_mu']

        text_en, text_zh = ds.structured_en(p), ds.structured_zh(p)
        record = {
            'id': p['id'], 'tier': p['tier'], 'structure': p['structure'],
            'review_status': 'decision-level answers reviewed by two bridge engineers',
            'input': {'structured_en': text_en, 'structured_zh': text_zh},
            'parameters': p,
            'reference_decisions': decisions,
            'reference_responses': {'source': source, 'tolerance': 0.001, **resp},
            'reference_model_spec': spec,
        }
        with open(os.path.join(ROOT, 'problems', f"{p['id']}.json"), 'w', encoding='utf-8') as fh:
            json.dump(record, fh, ensure_ascii=False, indent=2)
        for lang, txt in [('en', text_en), ('zh', text_zh)]:
            with open(os.path.join(ROOT, 'inputs', f"{p['id']}_{lang}.txt"), 'w', encoding='utf-8') as fh:
                fh.write(txt + '\n')
        if p['id'] in FREE_TEXT_IDS:
            for style in (1, 2, 3):
                for lang in ('en', 'zh'):
                    with open(os.path.join(ROOT, 'free_text', f"{p['id']}_s{style}_{lang}.txt"), 'w',
                              encoding='utf-8') as fh:
                        fh.write(ds.free_text(p, style, lang) + '\n')

        g = p['girder']
        index_rows.append({
            'id': p['id'], 'tier': p['tier'], 'structure': p['structure'],
            'spans_m': ds.spans_str(p['spans']), 'girder': g['type'],
            'n_girders': g['n'], 'concrete': g['concrete'],
            'load_class': p['deck']['load_class'], 'design_lanes': p['deck']['n_lanes'],
            'fixed_supports': ' '.join(str(k) for k, b in enumerate(p['bearings']) if b['kind'] in ('elastomeric', 'spherical_fixed')),
            'pier_heights_m': ' '.join(f"{q['H']:g}" for q in p['piers']) if p['piers'] else '',
            'nonstandard': ','.join(p['overrides']) or '',
            'n_decisions': len(decisions),
            'R_sum_kN': round(sum(resp['self_weight_support_reactions_kN']), 3),
            'f1_Hz': round(resp['first_vertical_frequency_Hz'], 5),
            'mu': round(resp['impact_factor_mu'], 5),
            'M_lane_pos_kNm': round(resp['lane_max_positive_moment_kNm'], 2),
            'M_lane_neg_kNm': (round(resp['lane_max_negative_moment_kNm'], 2)
                               if resp['lane_max_negative_moment_kNm'] is not None else ''),
        })
        print(f"{p['id']}  f1={resp['first_vertical_frequency_Hz']:.4f} Hz  "
              f"M+={resp['lane_max_positive_moment_kNm']:.1f}  decisions={len(decisions)}")

    with open(os.path.join(ROOT, 'index.csv'), 'w', newline='', encoding='utf-8-sig') as fh:
        w = csv.DictWriter(fh, fieldnames=list(index_rows[0]))
        w.writeheader()
        w.writerows(index_rows)
    with open(os.path.join(ROOT, 'rules.json'), 'w', encoding='utf-8') as fh:
        json.dump(RULES, fh, ensure_ascii=False, indent=2)
    with open(os.path.join(ROOT, 'validation_report.md'), 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(report) + '\n')


if __name__ == '__main__':
    main()

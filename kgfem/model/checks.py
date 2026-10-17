"""模型级三级校核与图谱引导的定位（I3，论文 4.6 节）。

L1 拓扑：孤立节点、重复单元、主梁连通、竖向与纵向支承
L2 规范：模型实体参数与其溯源决策一致；每跨有 Pk；冲击系数与模型一阶竖向频率一致
L3 力学：反力之和 = 总自重；总自重 = γ·A·桥长；一阶竖向频率在经验范围内
失败时沿 prov 字段从失败实体反查决策，返回可疑决策及其违反的约束。
"""
import math

from ..kg.expr import evaluate

TOL = 1e-3


def run_checks(ir, results, validator, kg):
    acc = {s: r for s, r in validator.accepted.items()}
    by_id = {r['id']: r for r in acc.values()}
    fails = []

    def fail(cid, msg, prov):
        suspects = sorted({p for p in prov if p})
        fails.append({'constraint': cid, 'text': kg.get(cid)['text'] if kg.has(cid) else '',
                      'message': msg,
                      'suspect_decisions': [{'decision_id': s, 'slot': by_id[s]['slot'], 'value': by_id[s]['value'],
                                             'evidence': by_id[s]['evidence']} for s in suspects if s in by_id]})

    # ---------------- L1 拓扑 ----------------
    used = set()
    seen = set()
    for e in ir['elements']:
        key = tuple(sorted(e['nodes']))
        if key in seen:
            fail('L1-1', f"单元 {e['id']} 与其他单元重复", e['prov'])
        seen.add(key)
        used.update(e['nodes'])
    for b in ir['bearings']:
        used.add(b['girder_node'])
        if b.get('base_node'):
            used.add(b['base_node'])
    for n in ir['nodes']:
        if n['id'] not in used:
            fail('L1-1', f"节点 {n['id']} 孤立", n['prov'])
    girder_ids = [e for e in ir['elements'] if e['role'] == 'girder']
    if len(girder_ids) != ir['n_girder_nodes'] - 1:
        fail('L1-1', '主梁单元数与节点数不连贯', [p for e in girder_ids for p in e['prov']])
    if len(ir['bearings']) < 2:
        fail('L1-2', '主梁竖向支承少于两处', [p for b in ir['bearings'] for p in b['prov']])
    if not any(b['long'] in ('spring', 'fixed') and (b['kind'] == 'rigid' or b.get('Kh', 0) > 0)
               for b in ir['bearings']):
        fail('L1-2', '没有纵向约束的支承线，结构纵向可变', [p for b in ir['bearings'] for p in b['prov']])

    # ---------------- L2 规范与溯源一致性 ----------------
    for b in ir['bearings']:
        k = b['support']
        if b['kind'] == 'zeroLength':
            for key, slot in (('Kv', f'support.{k}.Kv'), ('Kh', f'support.{k}.Kh')):
                if slot in acc and not _close(b[key], acc[slot]['value']):
                    fail('L2-1', f'支承线 {k} 模型 {key} 与决策不一致', b['prov'])
    # 模型所用的每个参数按规则层 / 规范层公式复算（决策被接受后若被改动或已失效，在此暴露）
    from ..kg.expr import ExprError
    from .. import ablation
    for slot, r in (acc.items() if not ablation.on('A1P') else []):     # A1+：连同模型级复算一起去掉
        try:
            exp, node, _ = validator.expected(slot)
        except (ExprError, ZeroDivisionError, KeyError, TypeError):
            continue
        if not _same(r['value'], exp):
            fail('L2-1', f'{slot} 在模型中取 {r["value"]!r}，按 {node["id"]} 复算为 {exp!r}', [r['id']])
    for j, P in ir['lane']['Pk'].items():
        if P is None:
            fail('L2-2', f'第 {j} 跨缺少 Pk', ir['lane']['prov'])
    f_model = (results.get('vertical_frequencies_Hz') or [None])[0]
    f_fact = validator.facts.get('f1')
    mu = ir['lane']['mu']
    if f_model and mu is not None:
        mu_model = evaluate(kg.get('JTGD60-4.3.2')['formulas']['lane.mu'], {'f1': f_model})
        if not _close(mu, mu_model):
            prov = ir['lane']['prov'] + sorted(validator.fact_prov.get('f1', []))
            fail('L2-2', f'冲击系数 {mu:.4f} 与模型一阶竖向频率 {f_model:.4f} Hz 对应的 {mu_model:.4f} 不一致'
                         f'（模态分析事实 f1 = {f_fact}）', [acc['lane.mu']['id']] + prov)

    # ---------------- L3 力学 ----------------
    Ltot = sum(ir['spans'])
    w = ir['self_weight']['w']
    R = results.get('self_weight_support_reactions_kN')
    if R is not None and not _close(sum(R), w * Ltot):
        fail('L3-1', f'反力之和 {sum(R):.3f} kN ≠ 总自重 {w * Ltot:.3f} kN',
             [p for b in ir['bearings'] for p in b['prov']] + ir['self_weight']['prov'])
    if 'girder.gamma' in acc and 'girder.A' in acc:
        qty = acc['girder.gamma']['value'] * acc['girder.A']['value'] * Ltot
        if not _close(w * Ltot, qty):
            fail('L3-2', f'模型自重 {w * Ltot:.2f} kN ≠ 工程量 γ·A·L = {qty:.2f} kN',
                 ir['self_weight']['prov'] + [acc['girder.gamma']['id'], acc['girder.A']['id']])
    if f_model and all(s in acc for s in ('girder.Ec', 'girder.I', 'girder.m')):
        Lmax = max(ir['spans'])
        EI = acc['girder.Ec']['value'] * 1e3 * acc['girder.I']['value']
        f_ss = math.pi / (2 * Lmax ** 2) * math.sqrt(EI / acc['girder.m']['value'])
        lo, hi = 0.6 * f_ss, 2.6 * f_ss
        if not lo <= f_model <= hi:
            prov = [acc[s]['id'] for s in ('girder.Ec', 'girder.I', 'girder.m')]
            prov += [p for b in ir['bearings'] for p in b['prov']]
            fail('L3-3', f'一阶竖向频率 {f_model:.3f} Hz 超出经验范围 [{lo:.3f}, {hi:.3f}] Hz', prov)
    return fails


def _same(a, b):
    if isinstance(b, dict):
        return isinstance(a, dict) and set(a) == set(b) and all(_same(a[k], b[k]) for k in b)
    if isinstance(b, str):
        return a == b
    return _close(float(a), float(b))


def _close(a, b):
    if b == 0:
        return abs(a) < 1e-9
    return abs(a - b) <= TOL * abs(b)

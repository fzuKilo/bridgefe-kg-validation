"""按 BridgeFE-Bench 评估一次建模运行（论文 3.5 节）。

一次运行判为正确，当且仅当：脚本可执行、全部决策与参考一致、全部响应与参考相差不超过 0.1%。
另按类别（建模规则 / 规范参数 / 构件拓扑）统计决策正确率。
"""
import json

TOL = 1e-3


def _same(a, b):
    if isinstance(b, dict):
        return isinstance(a, dict) and set(a) == set(b) and all(_same(a[k], b[k]) for k in b)
    if isinstance(b, str):
        return isinstance(a, str) and a.lower() == b.lower()
    try:
        a, b = float(a), float(b)
    except (TypeError, ValueError):
        return False
    return abs(a) < 1e-9 if b == 0 else abs(a - b) <= TOL * abs(b)


def evaluate_run(problem_json, session_json):
    ref = json.load(open(problem_json, encoding='utf-8'))
    run = json.load(open(session_json, encoding='utf-8'))
    dec = {s: d['value'] for s, d in (run.get('decisions') or {}).items()}
    by_cat, wrong = {}, []
    for d in ref['reference_decisions']:
        ok = d['slot'] in dec and _same(dec[d['slot']], d['canonical'])
        c = by_cat.setdefault(d['category'], [0, 0])
        c[0] += ok
        c[1] += 1
        if not ok:
            wrong.append({'slot': d['slot'], 'reference': d['canonical'], 'method': dec.get(d['slot'])})
    rr, res = ref['reference_responses'], run.get('results') or {}
    resp = {}
    if res:
        pairs = [('self_weight_support_reactions_kN', True), ('self_weight_midspan_moments_kNm', True),
                 ('lane_max_positive_moment_kNm', False), ('lane_max_negative_moment_kNm', False)]
        for key, is_list in pairs:
            a, b = res.get(key), rr.get(key)
            if b is None:
                resp[key] = a is None
            elif is_list:
                resp[key] = a is not None and len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b))
            else:
                resp[key] = a is not None and _same(a, b)
        resp['first_vertical_frequency_Hz'] = _same((res.get('vertical_frequencies_Hz') or [None])[0],
                                                    rr['first_vertical_frequency_Hz'])
    executed = bool(res)
    n_ok = sum(v[0] for v in by_cat.values())
    n = sum(v[1] for v in by_cat.values())
    return {'id': ref['id'], 'executed': executed, 'decisions_correct': n_ok, 'decisions_total': n,
            'decision_accuracy_by_category': {k: v[0] / v[1] for k, v in by_cat.items()},
            'responses': resp, 'correct': executed and n_ok == n and resp and all(resp.values()),
            'wrong_decisions': wrong, 'metrics': run.get('metrics')}

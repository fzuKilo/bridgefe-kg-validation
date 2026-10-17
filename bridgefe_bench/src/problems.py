"""BridgeFE-Bench 题目抽样与决策层参考答案。

sample_all() 用固定随机种子生成 30 道主题（A/B/C 各 10）与 3 道长联扩展题（S）。
resolve(p) 由题目参数推导全部建模决策（决策层参考答案）并组装参考模型规格 spec。
"""
import math

import numpy as np

import code_provisions as cp
import sections as sec

SEED = 20260925
T1_PRECAST = 0.008        # 预制梁支座单层橡胶厚 (m)
T1_CAST = 0.011           # 现浇箱梁支座单层橡胶厚 (m)

# 预制梁每个梁端支座尺寸（按跨径档位）：(a, b, 橡胶层数)
PRECAST_BEARING = {20: (0.25, 0.30, 4), 25: (0.30, 0.35, 4), 30: (0.30, 0.40, 5),
                   35: (0.35, 0.45, 5), 40: (0.40, 0.45, 6)}

# 桥面布置：(方向, 行车道宽 W, 桥面全宽)
DECKS = [('one_way', 8.0, 9.0), ('two_way', 9.0, 10.0),
         ('one_way', 11.5, 12.5), ('one_way', 15.0, 16.0)]


def girder_count(girder_type, deck_width):
    # 梁间距按浙江 2024 通用图：小箱梁 3.07–3.24 m，T 梁 2.525 m
    spacing = {'small_box': 3.15, 't_girder': 2.525}[girder_type]
    return max(3, round(deck_width / spacing))


def deck_dict(choice, load_class):
    d, W, B = choice
    two_way = d == 'two_way'
    return {'direction': d, 'carriageway_width': W, 'deck_width': B,
            'n_lanes': cp.design_lanes(W, two_way), 'load_class': load_class}


def spherical_pair():
    """40 m 简支 T 梁：浙江 2024 通用图 40JT-17，每梁端 1 个 GQZ2000 球形支座，
    0 号台纵向活动（SX/DX），1 号台纵向固定（中梁 GD、边梁横向单向活动 DX）。"""
    base = {'model': 'GQZ2000', 'capacity_kN': 2000, 'height': 0.091, 'per_girder': 1, 'Ge': None}
    return [{**base, 'kind': 'spherical_sliding'}, {**base, 'kind': 'spherical_fixed'}]


def precast_bearing(span_class, girder_type, kind):
    a, b, n = PRECAST_BEARING[span_class]
    return {'kind': kind, 'a': a, 'b': b, 't1': T1_PRECAST, 'n_layers': n,
            'per_girder': 2 if girder_type == 'small_box' else 1, 'Ge': None}


# ---------------- 抽样 ----------------
def sample_tier_a(rng):
    # 通用图覆盖的跨径档位：T 梁 20/25/30/40 m，小箱梁 25/30 m
    pairs = [(20, 't_girder'), (25, 't_girder'), (30, 't_girder'), (40, 't_girder'), (40, 't_girder'),
             (25, 'small_box'), (30, 'small_box'), (25, 'small_box'), (30, 'small_box'), (30, 'small_box')]
    rng.shuffle(pairs)
    out = []
    seen = set()
    for i, (L, t) in enumerate(pairs, 1):
        while True:                               # 跨径、梁型、片数、混凝土组合互不相同
            deck = deck_dict(DECKS[rng.integers(len(DECKS))], 'II' if i in (3, 8) else 'I')
            conc = str(rng.choice(['C40', 'C45', 'C50', 'C55']))
            key = (L, t, girder_count(t, deck['deck_width']), conc)
            if key not in seen:
                seen.add(key)
                break
        out.append({
            'id': f'A{i:02d}', 'tier': 'A', 'structure': 'simply_supported',
            'spans': [float(L)], 'girder': {'type': t, 'span_class': L,
                                            'n': girder_count(t, deck['deck_width']), 'concrete': conc},
            'deck': deck,
            'bearings': (spherical_pair() if (t, L) == ('t_girder', 40)
                         else [precast_bearing(L, t, 'elastomeric') for _ in range(2)]),
            'piers': None, 'overrides': {},
        })
    return out


def _precast_continuous(pid, tier, n_span, cls, unequal, t, deck, fixed_piers):
    spans = [float(cls)] * n_span
    if unequal:
        spans[0] = spans[-1] = float(cls - 5)
    bearings = []
    for k in range(n_span + 1):
        kind = 'elastomeric' if k in fixed_piers else 'sliding'
        bearings.append(precast_bearing(cls, t, kind))
    return {
        'id': pid, 'tier': tier, 'structure': 'precast_continuous',
        'spans': spans, 'girder': {'type': t, 'span_class': cls,
                                   'n': girder_count(t, deck['deck_width']), 'concrete': 'C50'},
        'deck': deck, 'bearings': bearings, 'piers': None, 'overrides': {},
    }


def sample_tier_b(rng):
    n_spans = [3, 3, 3, 4, 4, 4, 4, 5, 5, 5]
    unequal = [False, True] * 5
    rng.shuffle(unequal)
    out, seen = [], set()
    for i in range(10):
        n = n_spans[i]
        t = 'small_box' if i % 2 == 0 else 't_girder'
        while True:                               # 保证各题参数组合互不相同
            choices = {'small_box': [25, 30], 't_girder': [25, 30, 40] if unequal[i] else [20, 25, 30, 40]}[t]
            cls = int(rng.choice(choices))
            deck_choice = DECKS[rng.integers(len(DECKS))]
            d_try = deck_dict(deck_choice, 'I')
            key = (n, cls, unequal[i], t, girder_count(t, d_try['deck_width']), d_try['n_lanes'])
            if key not in seen:
                seen.add(key)
                break
        deck = deck_dict(deck_choice, 'II' if i == 6 else 'I')
        piers = list(range(1, n))
        if n == 5 and rng.random() < 0.5:
            fixed = [2, 3]                       # 两个中墩固定
        else:
            fixed = [int(rng.choice(piers))]
        out.append(_precast_continuous(f'B{i + 1:02d}', 'B', n, cls, unequal[i], t, deck, fixed))
    return out


C_SPANS = [[30, 40, 30], [35, 45, 35], [32, 40, 32], [30, 45, 30], [35, 50, 35],
           [30, 40, 40, 30], [35, 45, 45, 35], [30, 42, 42, 30], [36, 48, 36], [32, 45, 45, 32]]


def sample_tier_c(rng):
    out = []
    nonstandard = ['Ge', 'E_measured', 'gamma', 'Ge', 'E_measured',
                   'gamma', 'Ge', 'E_measured', 'Ge', 'gamma']
    for i, spans in enumerate(C_SPANS):
        n = len(spans)
        L_main = max(spans)
        h = round(L_main / 20 / 0.1) * 0.1
        wide = i % 3 == 2
        deck = deck_dict(('one_way', 15.0, 16.0) if wide else ('one_way', 11.5, 12.5),
                         'I')
        box = {'B_top': deck['deck_width'], 'B_bot': 9.0 if wide else 6.5, 'h': h,
               't_top': 0.25, 't_bot': float(rng.choice([0.22, 0.25])),
               't_web': float(rng.choice([0.45, 0.50])),
               't_cant_root': 0.50, 't_cant_tip': 0.20}
        # 桥墩高度：互不相等，相差不少于 3 m
        while True:
            H = sorted(rng.integers(6, 31, size=n - 1).tolist())
            if all(b - a >= 3 for a, b in zip(H, H[1:])):
                break
        rng.shuffle(H)
        D = float(rng.choice([1.4, 1.6, 1.8]))
        piers = [{'H': float(x), 'D': D, 'n_col': 2, 'concrete': 'C40'} for x in H]
        # 固定墩：最高墩以外、位于中部的一个墩
        mid = [k for k in range(1, n)]
        fixed = [min(mid, key=lambda k: (H[k - 1] == max(H), abs(k - n / 2)))]
        bearings = []
        for k in range(n + 1):
            if k in (0, n):
                a, b, nl = 0.40, 0.50, 5
            else:
                a, b, nl = (0.60, 0.70, 7) if k in fixed else (0.55, 0.65, 6)
            bearings.append({'kind': 'elastomeric' if k in fixed else 'sliding',
                             'a': a, 'b': b, 't1': T1_CAST, 'n_layers': nl,
                             'per_line': 2, 'Ge': None})
        ov = {}
        ns = nonstandard[i]
        if ns == 'Ge':
            for bb in bearings:
                bb['Ge'] = 1.2e6
            ov['Ge'] = 1.2e6
        elif ns == 'E_measured':
            ov['E_girder'] = 3.70e10
        elif ns == 'gamma':
            ov['gamma'] = 26.5e3
        out.append({
            'id': f'C{i + 1:02d}', 'tier': 'C', 'structure': 'cast_continuous_with_piers',
            'spans': [float(x) for x in spans],
            'girder': {'type': 'cast_box', 'box': box, 'n': 1,
                       'concrete': 'C55' if i % 4 == 3 else 'C50'},
            'deck': deck, 'bearings': bearings, 'piers': piers, 'overrides': ov,
        })
    return out


def sample_scalability(rng):
    specs = [(6, 30, 'small_box', [3]), (8, 30, 't_girder', [4, 5]), (10, 25, 'small_box', [5, 6])]
    out = []
    for i, (n, cls, t, fixed) in enumerate(specs, 1):
        deck = deck_dict(DECKS[2], 'I')
        out.append(_precast_continuous(f'S{i:02d}', 'S', n, cls, False, t, deck, fixed))
    return out


def sample_all():
    rng = np.random.default_rng(SEED)
    return sample_tier_a(rng) + sample_tier_b(rng) + sample_tier_c(rng) + sample_scalability(rng)


# ---------------- 决策层参考答案 ----------------
def support_name(k, n_span, lang='en'):
    if k in (0, n_span):
        return f'Abutment {k}' if lang == 'en' else f'{k} 号台'
    return f'Pier {k}' if lang == 'en' else f'{k} 号墩'


def resolve(p):
    """返回 (decisions, spec)。"""
    D = []

    def add(cat, item, value, unit, evidence, note=''):
        D.append({'id': f'D{len(D) + 1:02d}', 'category': cat, 'item': item,
                  'value': value, 'unit': unit, 'evidence': evidence, 'note': note})

    n_span = len(p['spans'])
    g = p['girder']
    ov = p['overrides']

    # 1 结构体系与单元
    add('modeling_rule', 'structural idealization',
        '2D spine beam, linear elastic; girder = elasticBeamColumn', '', 'MR-01')
    if p['structure'] == 'simply_supported':
        add('modeling_rule', 'structural system', 'single simply supported span', '', 'MR-01')
    elif p['structure'] == 'precast_continuous':
        add('modeling_rule', 'structural system',
            f'{n_span}-span continuous beam (completed system after continuity); '
            'construction-stage system change not modeled', '', 'MR-05')
    else:
        add('modeling_rule', 'structural system',
            f'{n_span}-span continuous girder on bearings, supported by piers fixed at base', '',
            'MR-05, MR-06')

    # 2 截面
    if g['type'] == 'cast_box':
        props = sec.section_props(*sec.cast_box_geometry(**g['box']))
        add('modeling_rule', 'girder section A', props['A'], 'm^2', 'MR-02',
            'single-cell box from given dimensions')
        add('modeling_rule', 'girder section I', props['I'], 'm^4', 'MR-02')
        A_tot, I_tot = props['A'], props['I']
    else:
        props = sec.girder_section(g['type'], g['span_class'])
        add('modeling_rule', 'single girder section A', props['A'], 'm^2', 'MR-02',
            'from given middle-girder dimensions')
        add('modeling_rule', 'single girder section I', props['I'], 'm^4', 'MR-02')
        A_tot, I_tot = g['n'] * props['A'], g['n'] * props['I']
        add('modeling_rule', 'spine-beam section A (n girders)', A_tot, 'm^2', 'MR-02',
            f"{g['n']} girders; wet joints and diaphragms neglected")
        add('modeling_rule', 'spine-beam section I (n girders)', I_tot, 'm^4', 'MR-02')

    # 3 材料
    if 'E_girder' in ov:
        E = ov['E_girder']
        add('code_parameter', 'girder elastic modulus Ec', E / 1e6, 'MPa', 'INPUT',
            f"given value overrides JTG 3362 Table 3.1.5 ({g['concrete']}: "
            f"{cp.EC_TABLE[g['concrete']]:.3g} MPa)")
    else:
        E = cp.concrete_E(g['concrete'])
        add('code_parameter', 'girder elastic modulus Ec', E / 1e6, 'MPa', 'JTG3362-3.1.5',
            g['concrete'])
    gamma = ov.get('gamma', cp.GAMMA_PC)
    add('code_parameter', 'unit weight of girder concrete', gamma / 1e3, 'kN/m^3',
        'INPUT' if 'gamma' in ov else 'JTGD60-4.2.1',
        'given value' if 'gamma' in ov else 'prestressed concrete, upper value of 25.0-26.0')
    w = gamma * A_tot
    m = w / cp.G_ACC
    add('code_parameter', 'girder self-weight w', w / 1e3, 'kN/m', 'MR-07')
    add('modeling_rule', 'girder mass per length', m / 1e3, 't/m', 'MR-07',
        'consistent mass; girder self-weight only')

    # 4 支座
    supports = []
    for k, b in enumerate(p['bearings']):
        name = support_name(k, n_span)
        if b['kind'].startswith('spherical'):
            count = b['per_girder'] * g['n']
            fixed = b['kind'] == 'spherical_fixed'
            add('topology', f'{name}: bearing type and number',
                f"spherical bearing {b['model']} ({'longitudinally fixed' if fixed else 'longitudinally movable'}), "
                f"{count} bearings", '', 'INPUT, MR-04')
            add('modeling_rule', f'{name}: restrained DOFs',
                'vertical rigid; longitudinal ' + ('fixed' if fixed else 'free') + '; rotation free', '', 'MR-08')
            supports.append({'rigid': True, 'fix_x': fixed, 'Kv': None, 'Kh': None, 'pier': None})
            continue
        Ge = b['Ge'] or cp.GE_STANDARD
        Kv1, Kh1, S, Ee = cp.bearing_stiffness(b['a'], b['b'], b['t1'], b['n_layers'], Ge)
        count = b.get('per_line') or b['per_girder'] * g['n']
        sliding = b['kind'] == 'sliding'
        add('topology', f'{name}: bearing type and number',
            f"{'PTFE sliding' if sliding else 'plain laminated'} elastomeric, {count} bearings", '',
            'INPUT, MR-04')
        add('modeling_rule', f'{name}: restrained DOFs',
            'vertical spring; longitudinal ' + ('free' if sliding else 'spring') + '; rotation free',
            '', 'MR-03')
        ev = 'JTG3362-8.7-Ee' + (', INPUT (Ge)' if b['Ge'] else ', JTG3362-8.7-Ge')
        add('code_parameter', f'{name}: shape factor S', S, '-', 'JTG3362-8.7-Ee')
        add('code_parameter', f'{name}: vertical stiffness Kv (all bearings)', count * Kv1 / 1e3,
            'kN/m', ev, f'single bearing {Kv1 / 1e3:.6g} kN/m, Ee = {Ee / 1e6:.4g} MPa')
        Kh = 0.0 if sliding else count * Kh1
        add('code_parameter', f'{name}: longitudinal stiffness Kh (all bearings)', Kh / 1e3,
            'kN/m', 'MR-03' if sliding else ev,
            'sliding surface, no longitudinal restraint' if sliding else f'single bearing {Kh1 / 1e3:.6g} kN/m')
        supports.append({'Kv': count * Kv1, 'Kh': Kh, 'pier': None})

    # 5 桥墩
    if p['piers']:
        for k, pr in enumerate(p['piers'], 1):
            Ep = cp.concrete_E(pr['concrete'])
            Ap = pr['n_col'] * math.pi * pr['D']**2 / 4
            Ip = pr['n_col'] * math.pi * pr['D']**4 / 64
            mp = cp.GAMMA_PC * Ap / cp.G_ACC
            name = support_name(k, n_span)
            add('topology', f'{name}: pier column length', pr['H'], 'm', 'INPUT, MR-06',
                'base fixed; top connected to girder through the bearings of this pier')
            add('modeling_rule', f'{name}: pier section A (twin columns)', Ap, 'm^2', 'MR-06')
            add('modeling_rule', f'{name}: pier section I (twin columns)', Ip, 'm^4', 'MR-06')
            add('code_parameter', f'{name}: pier elastic modulus', Ep / 1e6, 'MPa',
                'JTG3362-3.1.5', pr['concrete'])
            supports[k]['pier'] = {'H': pr['H'], 'E': Ep, 'A': Ap, 'I': Ip, 'm': mp}

    # 6 车道荷载
    d = p['deck']
    xi = cp.XI[d['n_lanes']]
    add('code_parameter', 'number of design lanes', d['n_lanes'], '-', 'JTGD60-4.3.1-lanes',
        f"{'two-way' if d['direction'] == 'two_way' else 'one-way'}, carriageway {d['carriageway_width']} m")
    add('code_parameter', 'transverse lane reduction factor', xi, '-', 'JTGD60-4.3.1-xi')
    qk, _ = cp.lane_load(d['load_class'], p['spans'][0])
    add('code_parameter', 'lane load qk', qk / 1e3, 'kN/m', 'JTGD60-4.3.1-lane',
        f"Highway Class {d['load_class']}")
    for k, L in enumerate(p['spans'], 1):
        add('code_parameter', f'lane load Pk (span {k}, L0 = {L:g} m)',
            cp.lane_load(d['load_class'], L)[1] / 1e3, 'kN', 'JTGD60-4.3.1-lane', 'LL-01')
    add('code_parameter', 'impact factor mu', None, '-', 'JTGD60-4.3.2, LL-02',
        'filled from the first vertical frequency (see responses)')

    spec = {'spans': p['spans'], 'girder': {'E': E, 'A': A_tot, 'I': I_tot, 'w': w, 'm': m},
            'supports': supports,
            'lane': {'load_class': d['load_class'], 'n_lanes': d['n_lanes'], 'xi': xi}}
    return D, spec, props

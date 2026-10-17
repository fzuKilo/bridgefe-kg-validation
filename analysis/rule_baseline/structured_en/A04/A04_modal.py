"""由 kgfem 模型生成工具自动生成的 OpenSeesPy 脚本（单位 kN、m、t、kPa）。"""
import json
import math
import sys

import numpy as np
import openseespy.opensees as ops

IR = json.loads(r"""{"units": "kN, m, t, kPa", "spans": [30], "n_girder_nodes": 21, "support_nodes": [1, 21], "mid_nodes": [11], "nodes": [{"id": 1, "x": 0.0, "y": 0.0, "role": "girder", "prov": ["dec:structure.idealization"]}, {"id": 2, "x": 1.5, "y": 0.0, "role": "girder", "prov": ["dec:structure.idealization"]}, {"id": 3, "x": 3.0, "y": 0.0, "role": "girder", "prov": ["dec:structure.idealization"]}, {"id": 4, "x": 4.5, "y": 0.0, "role": "girder", "prov": ["dec:structure.idealization"]}, {"id": 5, "x": 6.0, "y": 0.0, "role": "girder", "prov": ["dec:structure.idealization"]}, {"id": 6, "x": 7.5, "y": 0.0, "role": "girder", "prov": ["dec:structure.idealization"]}, {"id": 7, "x": 9.0, "y": 0.0, "role": "girder", "prov": ["dec:structure.idealization"]}, {"id": 8, "x": 10.5, "y": 0.0, "role": "girder", "prov": ["dec:structure.idealization"]}, {"id": 9, "x": 12.0, "y": 0.0, "role": "girder", "prov": ["dec:structure.idealization"]}, {"id": 10, "x": 13.5, "y": 0.0, "role": "girder", "prov": ["dec:structure.idealization"]}, {"id": 11, "x": 15.0, "y": 0.0, "role": "girder", "prov": ["dec:structure.idealization"]}, {"id": 12, "x": 16.5, "y": 0.0, "role": "girder", "prov": ["dec:structure.idealization"]}, {"id": 13, "x": 18.0, "y": 0.0, "role": "girder", "prov": ["dec:structure.idealization"]}, {"id": 14, "x": 19.5, "y": 0.0, "role": "girder", "prov": ["dec:structure.idealization"]}, {"id": 15, "x": 21.0, "y": 0.0, "role": "girder", "prov": ["dec:structure.idealization"]}, {"id": 16, "x": 22.5, "y": 0.0, "role": "girder", "prov": ["dec:structure.idealization"]}, {"id": 17, "x": 24.0, "y": 0.0, "role": "girder", "prov": ["dec:structure.idealization"]}, {"id": 18, "x": 25.5, "y": 0.0, "role": "girder", "prov": ["dec:structure.idealization"]}, {"id": 19, "x": 27.0, "y": 0.0, "role": "girder", "prov": ["dec:structure.idealization"]}, {"id": 20, "x": 28.5, "y": 0.0, "role": "girder", "prov": ["dec:structure.idealization"]}, {"id": 21, "x": 30.0, "y": 0.0, "role": "girder", "prov": ["dec:structure.idealization"]}, {"id": 22, "x": 0.0, "y": 0.0, "role": "bearing_base", "prov": ["dec:support.0.bearing", "dec:support.0.dofs", "dec:support.0.Kv", "dec:support.0.Kh"]}, {"id": 23, "x": 30.0, "y": 0.0, "role": "bearing_base", "prov": ["dec:support.1.bearing", "dec:support.1.dofs", "dec:support.1.Kv", "dec:support.1.Kh"]}], "elements": [{"id": 1, "type": "elasticBeamColumn", "nodes": [1, 2], "role": "girder", "span": 1, "A": 3.4167862499999995, "I": 1.0647505474265637, "E": 35500000.0, "mass": 9.055702599388377, "prov": ["dec:girder.A", "dec:girder.I", "dec:girder.Ec", "dec:girder.m"]}, {"id": 2, "type": "elasticBeamColumn", "nodes": [2, 3], "role": "girder", "span": 1, "A": 3.4167862499999995, "I": 1.0647505474265637, "E": 35500000.0, "mass": 9.055702599388377, "prov": ["dec:girder.A", "dec:girder.I", "dec:girder.Ec", "dec:girder.m"]}, {"id": 3, "type": "elasticBeamColumn", "nodes": [3, 4], "role": "girder", "span": 1, "A": 3.4167862499999995, "I": 1.0647505474265637, "E": 35500000.0, "mass": 9.055702599388377, "prov": ["dec:girder.A", "dec:girder.I", "dec:girder.Ec", "dec:girder.m"]}, {"id": 4, "type": "elasticBeamColumn", "nodes": [4, 5], "role": "girder", "span": 1, "A": 3.4167862499999995, "I": 1.0647505474265637, "E": 35500000.0, "mass": 9.055702599388377, "prov": ["dec:girder.A", "dec:girder.I", "dec:girder.Ec", "dec:girder.m"]}, {"id": 5, "type": "elasticBeamColumn", "nodes": [5, 6], "role": "girder", "span": 1, "A": 3.4167862499999995, "I": 1.0647505474265637, "E": 35500000.0, "mass": 9.055702599388377, "prov": ["dec:girder.A", "dec:girder.I", "dec:girder.Ec", "dec:girder.m"]}, {"id": 6, "type": "elasticBeamColumn", "nodes": [6, 7], "role": "girder", "span": 1, "A": 3.4167862499999995, "I": 1.0647505474265637, "E": 35500000.0, "mass": 9.055702599388377, "prov": ["dec:girder.A", "dec:girder.I", "dec:girder.Ec", "dec:girder.m"]}, {"id": 7, "type": "elasticBeamColumn", "nodes": [7, 8], "role": "girder", "span": 1, "A": 3.4167862499999995, "I": 1.0647505474265637, "E": 35500000.0, "mass": 9.055702599388377, "prov": ["dec:girder.A", "dec:girder.I", "dec:girder.Ec", "dec:girder.m"]}, {"id": 8, "type": "elasticBeamColumn", "nodes": [8, 9], "role": "girder", "span": 1, "A": 3.4167862499999995, "I": 1.0647505474265637, "E": 35500000.0, "mass": 9.055702599388377, "prov": ["dec:girder.A", "dec:girder.I", "dec:girder.Ec", "dec:girder.m"]}, {"id": 9, "type": "elasticBeamColumn", "nodes": [9, 10], "role": "girder", "span": 1, "A": 3.4167862499999995, "I": 1.0647505474265637, "E": 35500000.0, "mass": 9.055702599388377, "prov": ["dec:girder.A", "dec:girder.I", "dec:girder.Ec", "dec:girder.m"]}, {"id": 10, "type": "elasticBeamColumn", "nodes": [10, 11], "role": "girder", "span": 1, "A": 3.4167862499999995, "I": 1.0647505474265637, "E": 35500000.0, "mass": 9.055702599388377, "prov": ["dec:girder.A", "dec:girder.I", "dec:girder.Ec", "dec:girder.m"]}, {"id": 11, "type": "elasticBeamColumn", "nodes": [11, 12], "role": "girder", "span": 1, "A": 3.4167862499999995, "I": 1.0647505474265637, "E": 35500000.0, "mass": 9.055702599388377, "prov": ["dec:girder.A", "dec:girder.I", "dec:girder.Ec", "dec:girder.m"]}, {"id": 12, "type": "elasticBeamColumn", "nodes": [12, 13], "role": "girder", "span": 1, "A": 3.4167862499999995, "I": 1.0647505474265637, "E": 35500000.0, "mass": 9.055702599388377, "prov": ["dec:girder.A", "dec:girder.I", "dec:girder.Ec", "dec:girder.m"]}, {"id": 13, "type": "elasticBeamColumn", "nodes": [13, 14], "role": "girder", "span": 1, "A": 3.4167862499999995, "I": 1.0647505474265637, "E": 35500000.0, "mass": 9.055702599388377, "prov": ["dec:girder.A", "dec:girder.I", "dec:girder.Ec", "dec:girder.m"]}, {"id": 14, "type": "elasticBeamColumn", "nodes": [14, 15], "role": "girder", "span": 1, "A": 3.4167862499999995, "I": 1.0647505474265637, "E": 35500000.0, "mass": 9.055702599388377, "prov": ["dec:girder.A", "dec:girder.I", "dec:girder.Ec", "dec:girder.m"]}, {"id": 15, "type": "elasticBeamColumn", "nodes": [15, 16], "role": "girder", "span": 1, "A": 3.4167862499999995, "I": 1.0647505474265637, "E": 35500000.0, "mass": 9.055702599388377, "prov": ["dec:girder.A", "dec:girder.I", "dec:girder.Ec", "dec:girder.m"]}, {"id": 16, "type": "elasticBeamColumn", "nodes": [16, 17], "role": "girder", "span": 1, "A": 3.4167862499999995, "I": 1.0647505474265637, "E": 35500000.0, "mass": 9.055702599388377, "prov": ["dec:girder.A", "dec:girder.I", "dec:girder.Ec", "dec:girder.m"]}, {"id": 17, "type": "elasticBeamColumn", "nodes": [17, 18], "role": "girder", "span": 1, "A": 3.4167862499999995, "I": 1.0647505474265637, "E": 35500000.0, "mass": 9.055702599388377, "prov": ["dec:girder.A", "dec:girder.I", "dec:girder.Ec", "dec:girder.m"]}, {"id": 18, "type": "elasticBeamColumn", "nodes": [18, 19], "role": "girder", "span": 1, "A": 3.4167862499999995, "I": 1.0647505474265637, "E": 35500000.0, "mass": 9.055702599388377, "prov": ["dec:girder.A", "dec:girder.I", "dec:girder.Ec", "dec:girder.m"]}, {"id": 19, "type": "elasticBeamColumn", "nodes": [19, 20], "role": "girder", "span": 1, "A": 3.4167862499999995, "I": 1.0647505474265637, "E": 35500000.0, "mass": 9.055702599388377, "prov": ["dec:girder.A", "dec:girder.I", "dec:girder.Ec", "dec:girder.m"]}, {"id": 20, "type": "elasticBeamColumn", "nodes": [20, 21], "role": "girder", "span": 1, "A": 3.4167862499999995, "I": 1.0647505474265637, "E": 35500000.0, "mass": 9.055702599388377, "prov": ["dec:girder.A", "dec:girder.I", "dec:girder.Ec", "dec:girder.m"]}], "bearings": [{"id": "B0", "support": 0, "kind": "zeroLength", "girder_node": 1, "base_node": 22, "Kv": 8518013.631937683, "Kh": 18000.0, "long": "spring", "prov": ["dec:support.0.bearing", "dec:support.0.dofs", "dec:support.0.Kv", "dec:support.0.Kh"]}, {"id": "B1", "support": 1, "kind": "zeroLength", "girder_node": 21, "base_node": 23, "Kv": 8518013.631937683, "Kh": 18000.0, "long": "spring", "prov": ["dec:support.1.bearing", "dec:support.1.dofs", "dec:support.1.Kv", "dec:support.1.Kh"]}], "fixities": [{"node": 22, "dofs": [1, 1, 1], "prov": ["dec:support.0.bearing", "dec:support.0.dofs", "dec:support.0.Kv", "dec:support.0.Kh"]}, {"node": 23, "dofs": [1, 1, 1], "prov": ["dec:support.1.bearing", "dec:support.1.dofs", "dec:support.1.Kv", "dec:support.1.Kh"]}], "self_weight": {"w": 88.83644249999999, "prov": ["dec:girder.w"]}, "lane": {"qk": 10.5, "Pk": {"1": 320.0}, "mu": null, "n_lanes": 2, "xi": 1.0, "prov": ["dec:lane.n_lanes", "dec:lane.xi", "dec:lane.qk", "dec:lane.Pk.1"]}, "mesh": 20}""")
MODE = sys.argv[1] if len(sys.argv) > 1 else 'full'
N_MODES = 30


def build():
    ops.wipe()
    ops.model('basic', '-ndm', 2, '-ndf', 3)
    ops.geomTransf('Linear', 1)
    for n in IR['nodes']:
        ops.node(n['id'], n['x'], n['y'])
    for e in IR['elements']:
        ops.element('elasticBeamColumn', e['id'], *e['nodes'], e['A'], e['E'], e['I'], 1,
                    '-mass', e['mass'], '-cMass')
    for f in IR['fixities']:
        ops.fix(f['node'], *f['dofs'])
    mat, tag = 1, max(e['id'] for e in IR['elements'])
    for b in IR['bearings']:
        if b['kind'] == 'rigid':
            ops.fix(b['girder_node'], 1 if b['long'] == 'fixed' else 0, 1, 0)
            continue
        mats, dirs = [], []
        if b['long'] in ('spring', 'fixed') and b['Kh'] > 0:
            ops.uniaxialMaterial('Elastic', mat, b['Kh']); mats.append(mat); dirs.append(1); mat += 1
        ops.uniaxialMaterial('Elastic', mat, b['Kv']); mats.append(mat); dirs.append(2); mat += 1
        tag += 1
        b['ele'] = tag
        ops.element('zeroLength', tag, b['base_node'], b['girder_node'], '-mat', *mats, '-dir', *dirs)
    ops.timeSeries('Constant', 1)


GIRDER = [e for e in IR['elements'] if e['role'] == 'girder']
X = [n['x'] for n in IR['nodes'] if n['role'] == 'girder']
state = {'pat': 0}


def static(add_loads):
    if state['pat']:
        ops.remove('loadPattern', state['pat'])
    ops.reset()
    state['pat'] += 1
    ops.pattern('Plain', state['pat'], 1)
    add_loads()
    if ops.analyze(1) != 0:
        raise RuntimeError('static analysis failed')


def setup_static():
    ops.wipeAnalysis()
    ops.system('BandGeneral'); ops.numberer('RCM'); ops.constraints('Plain')
    ops.integrator('LoadControl', 1.0); ops.algorithm('Linear'); ops.analysis('Static')


def moment(node):
    """主梁节点弯矩，下缘受拉为正。"""
    if node == 1:
        return -ops.eleResponse(1, 'localForce')[2]
    return ops.eleResponse(node - 1, 'localForce')[5]


def reactions():
    ops.reactions()
    out = []
    for b in IR['bearings']:
        if b['kind'] == 'rigid':
            out.append(ops.nodeReaction(b['girder_node'], 2))
        else:
            out.append(b['Kv'] * (ops.nodeDisp(b['base_node'], 2) - ops.nodeDisp(b['girder_node'], 2)))
    return out


def modal():
    ops.wipeAnalysis()
    lam = ops.eigen(N_MODES)
    mass = {}
    for e in IR['elements']:
        (xi, yi), (xj, yj) = ops.nodeCoord(e['nodes'][0]), ops.nodeCoord(e['nodes'][1])
        share = e['mass'] * math.hypot(xj - xi, yj - yi) / 2
        for n in e['nodes']:
            mass[n] = mass.get(n, 0.0) + share
    ng = IR['n_girder_nodes']
    freqs = []
    for i, l in enumerate(lam, 1):
        tot = gv = 0.0
        for n, m in mass.items():
            ux, uy = ops.nodeEigenvector(n, i, 1), ops.nodeEigenvector(n, i, 2)
            tot += m * (ux * ux + uy * uy)
            if n <= ng:
                gv += m * uy * uy
        if gv > 0.5 * tot:
            freqs.append(math.sqrt(l) / (2 * math.pi))
    return freqs[:3]


def lane(mu):
    L = IR['lane']
    amp = (1 + mu) * L['n_lanes'] * L['xi']
    secs = [('span', j + 1, n) for j, n in enumerate(IR['mid_nodes'])]
    secs += [('support', k, n) for k, n in enumerate(IR['support_nodes']) if 0 < k < len(IR['support_nodes']) - 1]
    gn = [s[2] for s in secs]
    t = np.array([0.0, 1 / 3, 2 / 3, 1.0])
    Vinv = np.linalg.inv(np.vander(t, 4, increasing=True))
    cache = {}

    def unit_load(e, xi):
        key = (e, round(xi, 12))
        if key not in cache:
            static(lambda: ops.eleLoad('-ele', e, '-type', '-beamPoint', -1.0, xi))
            cache[key] = [moment(n) for n in gn]
        return cache[key]

    area = np.zeros(len(secs))
    peak = [[0.0] * len(IR['spans']) for _ in secs]
    for e in GIRDER:
        span = e['span'] - 1
        x0, x1 = X[e['nodes'][0] - 1], X[e['nodes'][1] - 1]
        Y = np.array([unit_load(e['id'], x) for x in t])
        C = Vinv @ Y
        for s, (kind, _, _) in enumerate(secs):
            c = C[:, s] * (1.0 if kind == 'span' else -1.0)
            p = np.polynomial.Polynomial(c)
            r = sorted(z.real for z in p.roots() if abs(z.imag) < 1e-12 and 0 < z.real < 1) if np.any(c[1:]) else []
            P = p.integ()
            knots = [0.0] + r + [1.0]
            area[s] += (x1 - x0) * sum(max(P(b) - P(a), 0.0) for a, b in zip(knots, knots[1:]))
            cand = [0.0, 1.0] + ([z.real for z in p.deriv().roots() if abs(z.imag) < 1e-12 and 0 < z.real < 1]
                                 if np.any(p.deriv().coef) else [])
            peak[s][span] = max(peak[s][span], max(p(z) for z in cand))
    out = []
    for s, (kind, idx, node) in enumerate(secs):
        sign = 1.0 if kind == 'span' else -1.0
        conc = max(float(L['Pk'][str(j + 1)]) * peak[s][j] for j in range(len(IR['spans'])))
        out.append({'section': kind, 'index': idx, 'M_kNm': sign * amp * (L['qk'] * area[s] + conc)})
    return out


build()
result = {}
freqs = modal()
result['vertical_frequencies_Hz'] = freqs
if MODE == 'full':
    setup_static()
    w = IR['self_weight']['w']
    static(lambda: ops.eleLoad('-ele', *[e['id'] for e in GIRDER], '-type', '-beamUniform', -w))
    result['self_weight_support_reactions_kN'] = reactions()
    result['self_weight_midspan_moments_kNm'] = [moment(n) for n in IR['mid_nodes']]
    result['self_weight_support_moments_kNm'] = [moment(n) for n in IR['support_nodes'][1:-1]]
    lm = lane(IR['lane']['mu'])
    result['lane_moments_by_section'] = lm
    pos = [r['M_kNm'] for r in lm if r['section'] == 'span']
    neg = [r['M_kNm'] for r in lm if r['section'] == 'support']
    result['lane_max_positive_moment_kNm'] = max(pos)
    result['lane_max_negative_moment_kNm'] = min(neg) if neg else None
print('KGFEM_RESULT ' + json.dumps(result))

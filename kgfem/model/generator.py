"""模型生成工具：中间表示 → 可独立运行的 OpenSeesPy 脚本，并在子进程中运行。

大模型负责组织与调用，具体代码由本工具从中间表示生成（论文 4.5 节），
避免长代码手写错误；脚本内嵌中间表示，任一实体均可按 prov 反查决策。
"""
import json
import os
import subprocess
import sys

TEMPLATE = r'''"""由 kgfem 模型生成工具自动生成的 OpenSeesPy 脚本（单位 kN、m、t、kPa）。"""
import json
import math
import sys

import numpy as np
import openseespy.opensees as ops

IR = json.loads(r"""__IR__""")
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
'''


def emit_script(ir, path):
    ir = json.loads(json.dumps(ir))                   # 键统一为字符串
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(TEMPLATE.replace('__IR__', json.dumps(ir, ensure_ascii=False)))
    return path


def run_script(path, mode='full', timeout=600):
    proc = subprocess.run([sys.executable, path, mode], capture_output=True, text=True, timeout=timeout,
                          cwd=os.path.dirname(path))
    for line in proc.stdout.splitlines():
        if line.startswith('KGFEM_RESULT '):
            return {'ok': True, **json.loads(line[len('KGFEM_RESULT '):])}
    return {'ok': False, 'stderr': proc.stderr[-2000:], 'stdout': proc.stdout[-500:]}

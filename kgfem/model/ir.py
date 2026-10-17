"""带溯源的中间表示（论文 4.5 节）。

由已接受的决策组装二维单梁模型；每个节点、单元、支座、约束与荷载都带 prov 字段，
列出产生它的决策编号（decision id），模型级校核失败时据此反向定位可疑决策。
单位：kN、m、t（质量），弹性模量 kPa。
"""
N_PER_SPAN = 20
N_PER_PIER = 10
PIER_GAMMA = 26.0      # 桥墩钢筋混凝土重度（JTGD60-4.2.1；题目的重度覆盖只针对主梁）


def build_ir(instance, accepted, mesh=N_PER_SPAN):
    d = instance.data
    dec = {s: r['id'] for s, r in accepted.items()}
    val = {s: r['value'] for s, r in accepted.items()}
    spans = d['spans_m']
    g_prov = [dec[s] for s in ('girder.A', 'girder.I', 'girder.Ec', 'girder.m') if s in dec]

    nodes, elems, bearings, fix = [], [], [], []
    x, nid = 0.0, 1
    nodes.append({'id': nid, 'x': 0.0, 'y': 0.0, 'role': 'girder', 'prov': [dec.get('structure.idealization')]})
    support_nodes, mid_nodes = [1], []
    for j, L in enumerate(spans, 1):
        for i in range(1, mesh + 1):
            nid += 1
            nodes.append({'id': nid, 'x': x + L * i / mesh, 'y': 0.0, 'role': 'girder',
                          'prov': [dec.get('structure.idealization')]})
            elems.append({'id': nid - 1, 'type': 'elasticBeamColumn', 'nodes': [nid - 1, nid], 'role': 'girder',
                          'span': j, 'A': val['girder.A'], 'I': val['girder.I'], 'E': val['girder.Ec'] * 1e3,
                          'mass': val['girder.m'], 'prov': g_prov})
            if i == mesh // 2:
                mid_nodes.append(nid)
        x += L
        support_nodes.append(nid)
    n_girder = nid

    eid = len(elems)
    for k, gnode in enumerate(support_nodes):
        dofs = val[f'support.{k}.dofs']
        prov = [dec[s] for s in (f'support.{k}.bearing', f'support.{k}.dofs', f'support.{k}.Kv',
                                  f'support.{k}.Kh') if s in dec]
        pier_key = f'pier.{k}.length'
        if dofs.get('vertical') == 'rigid':
            bearings.append({'id': f'B{k}', 'support': k, 'kind': 'rigid', 'girder_node': gnode,
                             'long': dofs.get('longitudinal'), 'prov': prov})
            continue
        nid += 1
        top = nid
        nodes.append({'id': top, 'x': nodes[gnode - 1]['x'], 'y': 0.0, 'role': 'bearing_base', 'prov': prov})
        if pier_key in val:
            p_prov = [dec[s] for s in (pier_key, f'pier.{k}.A', f'pier.{k}.I', f'pier.{k}.Ec') if s in dec]
            H = val[pier_key]
            prev = top
            for i in range(1, N_PER_PIER + 1):
                nid += 1
                nodes.append({'id': nid, 'x': nodes[gnode - 1]['x'], 'y': -H * i / N_PER_PIER,
                              'role': 'pier', 'prov': p_prov})
                eid += 1
                elems.append({'id': eid, 'type': 'elasticBeamColumn', 'nodes': [nid, prev], 'role': 'pier',
                              'support': k, 'A': val[f'pier.{k}.A'], 'I': val[f'pier.{k}.I'],
                              'E': val[f'pier.{k}.Ec'] * 1e3,
                              'mass': val[f'pier.{k}.A'] * PIER_GAMMA / 9.81, 'prov': p_prov})
                prev = nid
            fix.append({'node': nid, 'dofs': [1, 1, 1], 'prov': p_prov})
        else:
            fix.append({'node': top, 'dofs': [1, 1, 1], 'prov': prov})
        bearings.append({'id': f'B{k}', 'support': k, 'kind': 'zeroLength', 'girder_node': gnode,
                         'base_node': top, 'Kv': val[f'support.{k}.Kv'],
                         'Kh': val.get(f'support.{k}.Kh', 0.0), 'long': dofs.get('longitudinal'), 'prov': prov})

    lane_prov = [dec[s] for s in dec if s.startswith('lane.')]
    return {
        'units': 'kN, m, t, kPa',
        'spans': spans, 'n_girder_nodes': n_girder,
        'support_nodes': support_nodes, 'mid_nodes': mid_nodes,
        'nodes': nodes, 'elements': elems, 'bearings': bearings, 'fixities': fix,
        'self_weight': {'w': val['girder.w'], 'prov': [dec[s] for s in ('girder.w',) if s in dec]},
        'lane': {'qk': val.get('lane.qk'), 'Pk': {j: val.get(f'lane.Pk.{j}') for j in range(1, len(spans) + 1)},
                 'mu': val.get('lane.mu'), 'n_lanes': val.get('lane.n_lanes'), 'xi': val.get('lane.xi'),
                 'prov': lane_prov},
        'mesh': mesh,
    }

"""知识图谱存储：带分层属性的有向属性图。

四个层：rule（建模规则层）、code（规范层）、instance（实例层）、constraint（约束层）。
另有 decision 层记录大模型提出并通过校验的决策及其依据（溯源链的终点）。
采用内存存储并可序列化为 JSON；接口保持简单，便于替换为图数据库后端。
"""
import json

LAYERS = ('rule', 'code', 'instance', 'constraint', 'decision')


class KnowledgeGraph:
    def __init__(self):
        self.nodes = {}          # id -> {'id','layer','type', **attrs}
        self.edges = []          # (src, rel, dst)

    # ---------------- 写入 ----------------
    def add_node(self, nid, layer, ntype, **attrs):
        if layer not in LAYERS:
            raise ValueError(f'未知层: {layer}')
        self.nodes[nid] = {'id': nid, 'layer': layer, 'type': ntype, **attrs}
        return self.nodes[nid]

    def update_node(self, nid, **attrs):
        self.nodes[nid].update(attrs)

    def add_edge(self, src, rel, dst):
        e = (src, rel, dst)
        if e not in self.edges:
            self.edges.append(e)

    def remove_layer(self, layer):
        ids = {n for n, v in self.nodes.items() if v['layer'] == layer}
        self.nodes = {n: v for n, v in self.nodes.items() if n not in ids}
        self.edges = [e for e in self.edges if e[0] not in ids and e[2] not in ids]

    # ---------------- 查询 ----------------
    def get(self, nid):
        return self.nodes.get(nid)

    def has(self, nid):
        return nid in self.nodes

    def find(self, layer=None, ntype=None, **match):
        out = []
        for v in self.nodes.values():
            if layer and v['layer'] != layer:
                continue
            if ntype and v['type'] != ntype:
                continue
            if all(v.get(k) == val for k, val in match.items()):
                out.append(v)
        return out

    def out(self, nid, rel=None):
        return [self.nodes[d] for s, r, d in self.edges if s == nid and (rel is None or r == rel)]

    def into(self, nid, rel=None):
        return [self.nodes[s] for s, r, d in self.edges if d == nid and (rel is None or r == rel)]

    def relations(self, nid):
        return ([{'from': s, 'rel': r, 'to': d} for s, r, d in self.edges if nid in (s, d)])

    # ---------------- 序列化 ----------------
    def to_json(self, path=None, layers=LAYERS):
        data = {'nodes': [v for v in self.nodes.values() if v['layer'] in layers],
                'edges': [list(e) for e in self.edges
                          if self.nodes[e[0]]['layer'] in layers and self.nodes[e[2]]['layer'] in layers]}
        if path:
            with open(path, 'w', encoding='utf-8') as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2, default=str)
        return data

    @classmethod
    def from_json(cls, path):
        with open(path, encoding='utf-8') as fh:
            data = json.load(fh)
        kg = cls()
        for v in data['nodes']:
            v = dict(v)
            kg.add_node(v.pop('id'), v.pop('layer'), v.pop('type'), **v)
        for s, r, d in data['edges']:
            kg.add_edge(s, r, d)
        return kg

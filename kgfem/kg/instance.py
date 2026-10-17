"""实例层：本桥构件、连接关系与位置（论文 4.3 节）。

大模型通过 write_instance 工具写入本桥描述（JSON，见 SCHEMA_DOC），本模块：
  1. 合并写入并同步为图谱实例层节点与边（跨 BETWEEN 支承线、支座 AT 支承线、
     支座 SUPPORTS 主梁、桥墩 UNDER 支承线）；
  2. 按约束层 C-01~C-06 检查完整性与合理性；
  3. 为每个决策槽位构造公式求值上下文（本桥参数 + 已接受决策 + 分析事实）。
"""
import copy
import re

from ..model import sections
from .knowledge import EC_TABLE, TEMPLATES, XI_TABLE
from .expr import evaluate

SCHEMA_DOC = """{
  "structure_type": "simply_supported" | "precast_continuous" | "cast_in_place_continuous",
  "spans_m": [30, 40, 30],                        # bearing centre-line spans, in order
  "deck": {"deck_width_m": 12.5, "carriageway_width_m": 11.5, "traffic": "one_way" | "two_way",
           "design_lanes": 3, "load_class": "I" | "II"},
  "girder": {"type": "small_box" | "t_girder" | "cast_box", "count_per_span": 4,
             "concrete": "C50", "material": "prestressed_concrete",
             "E_override_MPa": null, "gamma_override_kNm3": null,
             "section": {geometry in metres, fields by type - see compute_section_properties}},
  "supports": [{"index": 0, "kind": "abutment" | "pier",
                "bearing": {"family": "laminated_elastomeric" | "spherical",
                            "sliding": false,          # PTFE sliding / longitudinally movable
                            "fixed": true,             # longitudinally fixed
                            "per_girder_end": 2,       # precast girders; or null
                            "per_line": null,          # cast-in-place box; or null
                            "a_mm": 300, "b_mm": 400, "t1_mm": 8, "n_layers": 5,   # laminated only
                            "Ge_MPa": null,            # only if a non-standard value is given
                            "model": null},            # e.g. "GQZ2000" for spherical
                "pier": null | {"height_m": 12, "diameter_m": 1.6, "n_columns": 2, "concrete": "C40"}}],
                # pier: only when the description gives pier column geometry; a support line merely
                # called "Pier k" (bearings on a pier cap, no column data) keeps "pier": null
  "dead_load": "girder_self_weight_only"
}"""

def longitudinally_restrained(b):
    """支座纵向是否受约束：普通板式橡胶支座（剪切刚度）或固定型球形支座。"""
    if b.get('family') == 'spherical':
        return bool(b.get('fixed'))
    return not b.get('sliding')


def section_geometry_issues(stype, g):
    """截面几何自洽性（约束层 C-08）：各板件尺寸不超过所属轮廓、内孔与翼缘尺寸为正。"""
    out = []
    try:
        if stype == 't_girder':
            if g['flat_len'] + g['t_web'] / 2 >= g['b_flange'] / 2:
                out.append(f"翼缘外侧等厚段 flat_len={g['flat_len']} m 与半腹板之和超过翼缘半宽 {g['b_flange'] / 2} m")
            if g['t_root'] < g['t_tip']:
                out.append('翼缘根部厚 t_root 小于端部厚 t_tip')
            if g['bulb_h'] + g['bulb_trans'] + g['t_root'] >= g['h']:
                out.append('马蹄高度、过渡段与翼缘根部厚之和不小于梁高')
            if g['b_bulb'] < g['t_web'] or g['b_flange'] < g['t_web']:
                out.append('马蹄宽或翼缘宽小于腹板厚')
        elif stype == 'small_box':
            yw = g['h'] - g['t_tip'] - g['haunch_rise']
            xw = g['b_bottom'] / 2 + yw / g['web_slope']
            if xw + g['haunch_len'] > g['b_top'] / 2:
                out.append(f"腹板外倾与加腋后的宽度 {2 * (xw + g['haunch_len']):.3f} m 超过顶宽 {g['b_top']} m")
            if g['t_bottom'] + g['t_top'] + g['chamfer_h'] >= g['h']:
                out.append('顶板、底板与倒角高度之和不小于梁高')
            if g['b_bottom'] / 2 - g['t_web'] <= 0:
                out.append('底宽不足以容纳两道腹板')
            if 2 * g['chamfer_w'] >= 2 * (g['b_bottom'] / 2 + (g['h'] - g['t_top']) / g['web_slope'] - g['t_web']):
                out.append('箱内倒角宽度超过箱室顶宽')
        elif stype == 'cast_box':
            if g['B_bot'] >= g['B_top']:
                out.append('底宽不小于顶宽')
            if g['t_top'] + g['t_bot'] >= g['h'] or g['t_cant_root'] >= g['h']:
                out.append('板厚之和不小于梁高')
            if 2 * g['t_web'] >= g['B_bot']:
                out.append('两道腹板厚度之和不小于底宽')
            if g['t_cant_root'] < g['t_cant_tip']:
                out.append('悬臂根部厚小于端部厚')
    except (TypeError, ZeroDivisionError, KeyError) as e:
        out.append(f'截面参数无法计算：{e}')
    return out


SLOT_RE = re.compile(r'^(support|pier)\.(\d+)\.(\w+)$|^lane\.Pk\.(\d+)$')


class Instance:
    def __init__(self, kg):
        self.kg = kg
        self.data = {}

    # ---------------- 写入 ----------------
    def write(self, patch):
        patch = copy.deepcopy(patch)
        if 'supports' in patch:
            cur = {s['index']: s for s in self.data.get('supports', [])}
            for s in patch.pop('supports'):
                if 'index' not in s:
                    raise ValueError('每条支承线需给出 index')
                cur[s['index']] = {**cur.get(s['index'], {}), **s}
            self.data['supports'] = [cur[k] for k in sorted(cur)]
            for s in self.data['supports']:          # 全空的桥墩对象不代表墩柱（描述未给墩柱数据）
                if isinstance(s.get('pier'), dict) and all(v is None for v in s['pier'].values()):
                    s['pier'] = None
        for key, val in patch.items():
            if isinstance(val, dict) and isinstance(self.data.get(key), dict):
                self.data[key] = {**self.data[key], **val}
            else:
                self.data[key] = val
        self._sync_graph()
        return self.check()

    def _sync_graph(self):
        kg, d = self.kg, self.data
        kg.remove_layer('instance')
        kg.add_node('inst:bridge', 'instance', 'Bridge', structure_type=d.get('structure_type'))
        if d.get('deck'):
            kg.add_node('inst:deck', 'instance', 'Deck', **d['deck'])
            kg.add_edge('inst:bridge', 'HAS', 'inst:deck')
        if d.get('girder'):
            g = {('girder_type' if k == 'type' else k): v for k, v in d['girder'].items() if k != 'section'}
            kg.add_node('inst:girder', 'instance', 'GirderSystem', section=d['girder'].get('section'), **g)
            kg.add_edge('inst:bridge', 'HAS', 'inst:girder')
        for k, s in enumerate(d.get('supports', [])):
            sid = f"inst:support:{s['index']}"
            kg.add_node(sid, 'instance', 'SupportLine', index=s['index'], kind=s.get('kind'))
            kg.add_edge('inst:bridge', 'HAS', sid)
            if s.get('bearing'):
                bid = f"inst:bearing:{s['index']}"
                kg.add_node(bid, 'instance', 'BearingGroup', support=s['index'], **s['bearing'])
                kg.add_edge(bid, 'AT', sid)
                if kg.has('inst:girder'):
                    kg.add_edge(bid, 'SUPPORTS', 'inst:girder')
            if s.get('pier'):
                pid = f"inst:pier:{s['index']}"
                kg.add_node(pid, 'instance', 'Pier', support=s['index'], **s['pier'])
                kg.add_edge(pid, 'UNDER', sid)
        for j, L in enumerate(d.get('spans_m', []), 1):
            nid = f'inst:span:{j}'
            kg.add_node(nid, 'instance', 'Span', index=j, length=L)
            kg.add_edge('inst:bridge', 'HAS', nid)
            for k in (j - 1, j):
                if kg.has(f'inst:support:{k}'):
                    kg.add_edge(nid, 'BETWEEN', f'inst:support:{k}')
            if kg.has('inst:girder'):
                kg.add_edge('inst:girder', 'SPANS', nid)

    # ---------------- 约束层：完整性与合理性 ----------------
    def check(self):
        from .. import ablation
        if ablation.on('A3'):
            return []
        d, issues = self.data, []

        def add(cid, msg):
            issues.append({'constraint': cid, 'message': msg})

        spans = d.get('spans_m') or []
        sups = d.get('supports') or []
        if not spans or any((L or 0) <= 0 for L in spans):
            add('C-01', '缺少跨径或跨径非正')
        if len(sups) != len(spans) + 1:
            add('C-01', f'跨数为 {len(spans)}，支承线应为 {len(spans) + 1} 条，实际 {len(sups)} 条')
        if [s['index'] for s in sups] != list(range(len(sups))):
            add('C-01', '支承线编号应从 0 起连续编号')
        for s in sups:
            b = s.get('bearing')
            if not b:
                add('C-02', f"支承线 {s['index']} 没有支座")
                continue
            if b.get('family') not in ('laminated_elastomeric', 'spherical'):
                add('C-02', f"支承线 {s['index']} 支座类型 family 未知")
            if not (b.get('per_girder_end') or b.get('per_line')):
                add('C-02', f"支承线 {s['index']} 缺少支座数量（per_girder_end 或 per_line）")
            if b.get('family') == 'laminated_elastomeric':
                miss = [k for k in ('a_mm', 'b_mm', 't1_mm', 'n_layers') if not b.get(k)]
                if miss:
                    add('C-02', f"支承线 {s['index']} 板式橡胶支座缺少 {miss}")
            if b.get('per_girder_end') and not 1 <= b['per_girder_end'] <= 2:
                add('C-07', f"支承线 {s['index']} 每个梁端 {b['per_girder_end']} 个支座不合理（预制梁每端通常 1~2 个），"
                            f"请核对描述：per_girder_end 是每片梁每端的支座数，不是主梁片数")
            if b.get('per_line') and not 1 <= b['per_line'] <= 6:
                add('C-07', f"支承线 {s['index']} 每条支承线 {b['per_line']} 个支座不合理，请核对描述")
            if b.get('sliding') and b.get('fixed'):
                add('C-02', f"支承线 {s['index']} 支座不能同时为滑动与固定")
        g = d.get('girder') or {}
        for k in ('type', 'concrete', 'section'):
            if not g.get(k):
                add('C-03', f'主梁缺少 {k}')
        if g.get('type') in ('small_box', 't_girder') and not g.get('count_per_span'):
            add('C-03', '预制梁缺少每跨片数 count_per_span')
        if g.get('type') in sections.SCHEMAS and g.get('section'):
            miss = [k for k in sections.SCHEMAS[g['type']] if g['section'].get(k) is None]
            if miss:
                add('C-03', f'截面几何缺少 {miss}')
        if g.get('type') in sections.SCHEMAS and g.get('section') and \
                all(g['section'].get(k) is not None for k in sections.SCHEMAS[g['type']]):
            for msg in section_geometry_issues(g['type'], g['section']):
                add('C-08', f'截面几何不自洽：{msg}，请核对描述中的截面尺寸')
        if d.get('structure_type') == 'cast_in_place_continuous':
            for s in sups[1:-1]:
                p = s.get('pier')
                if not p or any(p.get(k) is None for k in ('height_m', 'diameter_m', 'n_columns', 'concrete')):
                    add('C-04', f"中间支承线 {s['index']} 缺少完整的桥墩参数")
        dk = d.get('deck') or {}
        miss = [k for k in ('carriageway_width_m', 'traffic', 'design_lanes', 'load_class') if dk.get(k) is None]
        if miss:
            add('C-05', f'设计标准缺少 {miss}')
        elif dk['design_lanes'] != self._lanes_from_width(dk):
            add('C-05', f"行车道宽 {dk['carriageway_width_m']} m（{dk['traffic']}）按 JTG D60 表 4.3.1-4 对应 "
                        f"{self._lanes_from_width(dk)} 个设计车道，与所写 {dk['design_lanes']} 不符，请核对输入")
        if sups and all(s.get('bearing') for s in sups) and not any(
                longitudinally_restrained(s['bearing']) for s in sups):
            add('C-06', '所有支承线均为纵向活动支座，结构纵向可变，请核对固定支座位置')
        return issues

    def _lanes_from_width(self, dk):
        node = self.kg.get('JTGD60-4.3.1-lanes')
        return evaluate(node['formulas']['lane.n_lanes'],
                        {'W': dk['carriageway_width_m'], 'two_way': dk['traffic'] == 'two_way'})

    # ---------------- 决策清单 ----------------
    def required_slots(self):
        """由决策模板与实例层推导完成建模所需的全部决策槽位。"""
        d = self.data
        tpl = {t['component']: t['slots'] for t in TEMPLATES}
        env = {'precast': (d.get('girder') or {}).get('type') in ('small_box', 't_girder')}
        out = [s for s, cond in tpl['Bridge'] if evaluate(cond, env)]
        for j in range(1, len(d.get('spans_m') or []) + 1):
            out += [s.replace('{j}', str(j)) for s, _ in tpl['Span']]
        for s in d.get('supports') or []:
            benv = {'family': (s.get('bearing') or {}).get('family')}
            out += [p.replace('{k}', str(s['index'])) for p, cond in tpl['Support'] if evaluate(cond, benv)]
        for s in d.get('supports') or []:
            if s.get('pier'):
                out += [p.replace('{k}', str(s['index'])) for p, _ in tpl['Pier']]
        return out

    # ---------------- 公式上下文 ----------------
    def context(self, slot, accepted, facts):
        """槽位的求值环境。accepted: slot -> 已接受值；facts: 分析事实（如 f1）。"""
        d = self.data
        g = d.get('girder') or {}
        env = {'EC_TABLE': EC_TABLE, 'XI_TABLE': XI_TABLE, 'pi': 3.141592653589793,
               'n_spans': len(d.get('spans_m') or []),
               'models_pier_columns': any(s.get('pier') for s in d.get('supports') or []),
               'precast': g.get('type') in ('small_box', 't_girder'),
               'n_girders': g.get('count_per_span') or 1}
        m = SLOT_RE.match(slot)
        if slot.startswith('girder.'):
            if g.get('type') in sections.SCHEMAS and g.get('section'):
                try:
                    p = sections.properties(g['type'], g['section'])
                    env.update(sec_A=p['A'], sec_I=p['I'])
                except ValueError:
                    pass
            for key, var in (('girder.single.A', 'A_single'), ('girder.single.I', 'I_single'),
                             ('girder.gamma', 'gamma'), ('girder.A', 'A'), ('girder.w', 'w')):
                if key in accepted:
                    env[var] = accepted[key]
            env.update(grade=g.get('concrete'), material=g.get('material', 'prestressed_concrete'))
            if slot == 'girder.Ec':
                env.update(has_override=g.get('E_override_MPa') is not None, override=g.get('E_override_MPa'))
            elif slot == 'girder.gamma':
                env.update(has_override=g.get('gamma_override_kNm3') is not None,
                           override=g.get('gamma_override_kNm3'))
            else:
                env['has_override'] = False
        elif m and m.group(1) == 'support':
            k = int(m.group(2))
            s = self._support(k)
            b = (s or {}).get('bearing') or {}
            fam = b.get('family')
            if fam == 'laminated_elastomeric':
                btype = 'ptfe_sliding' if b.get('sliding') else 'plain_elastomeric'
            else:
                btype = 'spherical_fixed' if b.get('fixed') else 'spherical_sliding'
            count = (b.get('per_girder_end') or 0) * env['n_girders'] if b.get('per_girder_end') else b.get('per_line')
            if f'support.{k}.bearing' in accepted and slot != f'support.{k}.bearing':
                count = accepted[f'support.{k}.bearing'].get('count', count)
            env.update(family=fam, sliding=bool(b.get('sliding')), fixed=bool(b.get('fixed')),
                       bearing_type=btype, count=count, has_Ge_override=b.get('Ge_MPa') is not None,
                       Ge=b.get('Ge_MPa') or 1.0, Eb=2000.0, has_override=False)
            geo = [b.get(k) for k in ('a_mm', 'b_mm', 't1_mm', 'n_layers')]
            if fam == 'laminated_elastomeric' and all(isinstance(v, (int, float)) for v in geo):
                a, bb, t1, n = geo                      # 几何不全时不给出这些输入，公式执行返回“缺少输入”
                env.update(a=a / 1000, b=bb / 1000, t1=t1 / 1000, te=t1 * n / 1000, n_layers=n)
        elif m and m.group(1) == 'pier':
            k = int(m.group(2))
            p = (self._support(k) or {}).get('pier') or {}
            env.update(has_pier=bool(p), H=p.get('height_m'), D=p.get('diameter_m'), n_col=p.get('n_columns'),
                       grade=p.get('concrete'), has_override=False)
        elif slot.startswith('lane.'):
            dk = d.get('deck') or {}
            env.update(W=dk.get('carriageway_width_m'), two_way=dk.get('traffic') == 'two_way',
                       load_class=dk.get('load_class'), has_override=False)
            if 'lane.n_lanes' in accepted:
                env['n_lanes'] = accepted['lane.n_lanes']
            if m and m.group(4):
                j = int(m.group(4))
                spans = d.get('spans_m') or []
                env['L0'] = spans[j - 1] if 0 < j <= len(spans) else None
            if 'f1' in facts:
                env['f1'] = facts['f1']
            env['has_f1'] = 'f1' in facts
        return env

    def _support(self, k):
        for s in self.data.get('supports') or []:
            if s['index'] == k:
                return s
        return None

    def component_exists(self, slot):
        m = SLOT_RE.match(slot)
        if not m:
            return True
        if m.group(1) == 'support':
            return self._support(int(m.group(2))) is not None
        if m.group(1) == 'pier':
            s = self._support(int(m.group(2)))
            return bool(s and s.get('pier'))
        j = int(m.group(4))
        return 0 < j <= len(self.data.get('spans_m') or [])

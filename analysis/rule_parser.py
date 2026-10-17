"""Non-LLM baseline: deterministic rule-based parser for the BridgeFE-Bench input schema.

The parser targets the published four-part structured description (English and Chinese),
written from the input grammar of bridgefe_bench/src/descriptions.py and the instance schema
(kgfem/kg/instance.py). It reads no reference answers and no agent session. Text that does not
follow the schema raises ParseError, which is how a fixed-schema rule system behaves on
out-of-schema input.
"""
import re

NUM = {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7, 'eight': 8,
       'nine': 9, 'ten': 10}
ZHNUM = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9, '十': 10}
F = r'(\d+(?:\.\d+)?)'


class ParseError(ValueError):
    pass


def _num(s):
    s = s.strip()
    if s in NUM:
        return NUM[s]
    if s in ZHNUM:
        return ZHNUM[s]
    v = float(s)
    return int(v) if v.is_integer() else v


def _m(pat, text, what, flags=0):
    m = re.search(pat, text, flags)
    if not m:
        raise ParseError(f'cannot find {what}')
    return m


def _parts(text, lang):
    if lang == 'en':
        keys = ['Span arrangement', 'Section and material', 'Bearings and boundary', 'Design standard']
        pat = r'\[(%s)\]' % '|'.join(map(re.escape, keys))
    else:
        keys = ['跨径布置', '截面与材料', '支座与边界', '设计标准']
        pat = r'【(%s)】' % '|'.join(keys)
    pieces = re.split(pat, text)
    out = {pieces[i]: pieces[i + 1].strip() for i in range(1, len(pieces) - 1, 2)}
    missing = [k for k in keys if k not in out]
    if missing:
        raise ParseError('missing sections: ' + ', '.join(missing))
    return [out[k] for k in keys]


def detect_lang(text):
    if '[Span arrangement]' in text:
        return 'en'
    if '【跨径布置】' in text:
        return 'zh'
    raise ParseError('input does not follow the four-part structured schema')


# ---------------------------------------------------------------- span arrangement
def parse_span(s, lang):
    if lang == 'en':
        if s.startswith('Single simply supported span'):
            st = 'simply_supported'
            spans = [_num(_m(r'span of ' + F + ' m', s, 'span').group(1))]
        else:
            st = 'cast_in_place_continuous' if 'cast-in-place continuous unit' in s else 'precast_continuous'
            if st == 'precast_continuous' and 'made continuous afterwards' not in s:
                raise ParseError('unknown structure type')
            m = _m(r'unit of (\w+) spans, ([\d.+ ]+) m', s, 'span list')
            n = _num(m.group(1))
            spans = [_num(x) for x in m.group(2).split('+')]
            if len(spans) != n:
                raise ParseError('span count does not match span list')
        width = _num(_m(r'deck width ' + F + ' m', s, 'deck width').group(1))
    else:
        if s.startswith('单跨简支'):
            st = 'simply_supported'
            spans = [_num(_m(r'计算跨径 ' + F + ' m', s, 'span').group(1))]
        else:
            st = 'cast_in_place_continuous' if s.startswith('现浇连续梁') else 'precast_continuous'
            if st == 'precast_continuous' and '先简支后连续' not in s:
                raise ParseError('unknown structure type')
            m = _m(r'一联(.)跨，跨径 ([\d.+ ]+) m', s, 'span list')
            n = _num(m.group(1))
            spans = [_num(x) for x in m.group(2).split('+')]
            if len(spans) != n:
                raise ParseError('span count does not match span list')
        width = _num(_m(r'桥面全宽 ' + F + ' m', s, 'deck width').group(1))
    return st, spans, width


# ---------------------------------------------------------------- section and material
def parse_section(s, lang):
    g = {'material': 'prestressed_concrete', 'E_override_MPa': None, 'gamma_override_kNm3': None}
    if lang == 'en':
        g['concrete'] = _m(r'girder concrete (C\d+)', s, 'girder concrete').group(1)
        m = re.search(r'elastic modulus of the girder concrete as ' + F + ' MPa', s)
        if m:
            g['E_override_MPa'] = _num(m.group(1))
        m = re.search(r'unit weight of ' + F + ' kN/m3', s)
        if m:
            g['gamma_override_kNm3'] = _num(m.group(1))
        if s.startswith('Cast-in-place prestressed concrete box girder'):
            g['type'], g['count_per_span'] = 'cast_box', 1
            m = _m(r'constant depth {0} m: top slab {0} m wide and {0} m thick; bottom slab {0} m wide and {0} m '
                   r'thick; two vertical webs {0} m thick; cantilever flanges {0} m thick at the root tapering '
                   r'linearly to {0} m at the tip'.format(F), s, 'box section')
            v = [_num(x) for x in m.groups()]
            g['section'] = dict(zip(['h', 'B_top', 't_top', 'B_bot', 't_bot', 't_web', 't_cant_root',
                                     't_cant_tip'], v))
        elif s.startswith('Precast prestressed small box girders'):
            g['type'] = 'small_box'
            g['count_per_span'] = _num(_m(r'girders, (\d+) per span', s, 'girder count').group(1))
            m = _m(r'depth {0} m; top width {0} m; flange {0} m thick at the tip, thickening by {0} cm over a {0} cm '
                   r'long haunch next to the web; bottom slab {0} m wide and {0} m thick; top slab {0} m thick; '
                   r'webs {0} m thick \(measured horizontally\) with outer faces inclined at 1:{0}; {0} cm x {0} cm '
                   r'chamfers'.format(F), s, 'small box section')
            v = [_num(x) for x in m.groups()]
            g['section'] = {'h': v[0], 'b_top': v[1], 't_tip': v[2], 'haunch_rise': v[3] / 100,
                            'haunch_len': v[4] / 100, 'b_bottom': v[5], 't_bottom': v[6], 't_top': v[7],
                            't_web': v[8], 'web_slope': v[9], 'chamfer_w': v[10] / 100, 'chamfer_h': v[11] / 100}
        elif s.startswith('Precast prestressed T girders'):
            g['type'] = 't_girder'
            g['count_per_span'] = _num(_m(r'girders, (\d+) per span', s, 'girder count').group(1))
            m = _m(r'depth {0} m; precast flange {0} m wide, {0} m thick over the outer {0} m and thickening linearly '
                   r'to {0} m at the web; web {0} m thick; bottom bulb {0} m wide with a {0} m vertical part and a '
                   r'{0} m high linear transition'.format(F), s, 'T section')
            v = [_num(x) for x in m.groups()]
            g['section'] = dict(zip(['h', 'b_flange', 't_tip', 'flat_len', 't_root', 't_web', 'b_bulb', 'bulb_h',
                                     'bulb_trans'], v))
        else:
            raise ParseError('unknown girder type')
    else:
        g['concrete'] = _m(r'主梁混凝土 (C\d+)', s, 'girder concrete').group(1)
        m = re.search(r'弹性模量取 ' + F + ' MPa', s)
        if m:
            g['E_override_MPa'] = _num(m.group(1))
        m = re.search(r'重度取 ' + F + ' kN/m', s)
        if m:
            g['gamma_override_kNm3'] = _num(m.group(1))
        if s.startswith('现浇预应力混凝土箱梁'):
            g['type'], g['count_per_span'] = 'cast_box', 1
            m = _m(r'梁高 {0} m：顶板宽 {0} m、厚 {0} m；底板宽 {0} m、厚 {0} m；两道竖直腹板厚 {0} m；翼缘悬臂根部厚 {0} m，'
                   r'线性变化至端部 {0} m'.format(F), s, 'box section')
            v = [_num(x) for x in m.groups()]
            g['section'] = dict(zip(['h', 'B_top', 't_top', 'B_bot', 't_bot', 't_web', 't_cant_root',
                                     't_cant_tip'], v))
        elif s.startswith('预制预应力混凝土小箱梁'):
            g['type'] = 'small_box'
            g['count_per_span'] = _num(_m(r'每跨 (\d+) 片', s, 'girder count').group(1))
            m = _m(r'梁高 {0} m；顶宽 {0} m；翼缘端部厚 {0} m，近腹板处经 {0} cm 长加腋增厚 {0} cm；底板宽 {0} m、厚 {0} m；'
                   r'顶板厚 {0} m；腹板水平厚 {0} m，外侧坡度 1:{0}；箱内顶角设 {0} cm × {0} cm 倒角'.format(F), s,
                   'small box section')
            v = [_num(x) for x in m.groups()]
            g['section'] = {'h': v[0], 'b_top': v[1], 't_tip': v[2], 'haunch_len': v[3] / 100,
                            'haunch_rise': v[4] / 100, 'b_bottom': v[5], 't_bottom': v[6], 't_top': v[7],
                            't_web': v[8], 'web_slope': v[9], 'chamfer_w': v[10] / 100, 'chamfer_h': v[11] / 100}
        elif s.startswith('预制预应力混凝土 T 梁'):
            g['type'] = 't_girder'
            g['count_per_span'] = _num(_m(r'每跨 (\d+) 片', s, 'girder count').group(1))
            m = _m(r'梁高 {0} m；预制翼缘宽 {0} m，外侧 {0} m 范围厚 {0} m，向腹板线性增厚至 {0} m；腹板厚 {0} m；'
                   r'马蹄宽 {0} m，竖直段高 {0} m，经 {0} m 高线性过渡段'.format(F), s, 'T section')
            v = [_num(x) for x in m.groups()]
            g['section'] = dict(zip(['h', 'b_flange', 'flat_len', 't_tip', 't_root', 't_web', 'b_bulb', 'bulb_h',
                                     'bulb_trans'], v))
        else:
            raise ParseError('unknown girder type')
    return g


# ---------------------------------------------------------------- bearings and boundary
def _support_index(name, lang):
    m = re.fullmatch(r'(Abutment|Pier) (\d+)', name.strip()) if lang == 'en' else \
        re.fullmatch(r'(\d+) 号(台|墩)', name.strip())
    if not m:
        raise ParseError(f'unknown support name: {name}')
    return int(m.group(2) if lang == 'en' else m.group(1))


def _bearing(desc, lang, precast):
    b = {'family': None, 'sliding': None, 'fixed': None, 'per_girder_end': None, 'per_line': None,
         'a_mm': None, 'b_mm': None, 't1_mm': None, 'n_layers': None, 'Ge_MPa': None, 'model': None}
    if lang == 'en':
        if desc.startswith('spherical bearings'):
            b['family'] = 'spherical'
            b['model'] = _m(r'spherical bearings (GQZ\d+)', desc, 'bearing model').group(1)
            mov = 'longitudinally movable' in desc
            if not mov and 'longitudinally fixed' not in desc:
                raise ParseError('spherical bearing restraint not stated')
            b['sliding'], b['fixed'] = mov, not mov
            if 'one under each girder end' not in desc:
                raise ParseError('spherical bearing count')
            b['per_girder_end'] = 1
            return b
        if desc.startswith('PTFE sliding laminated elastomeric bearings'):
            b['sliding'] = True
        elif desc.startswith('plain laminated elastomeric bearings'):
            b['sliding'] = False
        else:
            raise ParseError('unknown bearing type')
        b['family'], b['fixed'] = 'laminated_elastomeric', not b['sliding']
        m = re.search(r'(\w+) under each girder end', desc)
        if m:
            b['per_girder_end'] = _num(m.group(1))
        else:
            b['per_line'] = _num(_m(r'(\w+) per support line', desc, 'bearing count').group(1))
        m = _m(r'effective plan size (\d+) mm x (\d+) mm, (\w+) internal rubber layers (\d+) mm thick', desc,
               'bearing dimensions')
        b['a_mm'], b['b_mm'], b['n_layers'], b['t1_mm'] = (_num(m.group(1)), _num(m.group(2)), _num(m.group(3)),
                                                            _num(m.group(4)))
        m = re.search(r'shear modulus of the rubber ' + F + ' MPa', desc)
    else:
        if desc.startswith('球形支座'):
            b['family'] = 'spherical'
            b['model'] = _m(r'球形支座 (GQZ\d+)', desc, 'bearing model').group(1)
            mov = '纵桥向活动' in desc
            if not mov and '纵桥向固定' not in desc:
                raise ParseError('spherical bearing restraint not stated')
            b['sliding'], b['fixed'] = mov, not mov
            if '每个梁端 1 个' not in desc:
                raise ParseError('spherical bearing count')
            b['per_girder_end'] = 1
            return b
        if desc.startswith('四氟滑板式板式橡胶支座'):
            b['sliding'] = True
        elif desc.startswith('普通板式橡胶支座'):
            b['sliding'] = False
        else:
            raise ParseError('unknown bearing type')
        b['family'], b['fixed'] = 'laminated_elastomeric', not b['sliding']
        m = re.search(r'每个梁端 (\d+) 个', desc)
        if m:
            b['per_girder_end'] = _num(m.group(1))
        else:
            b['per_line'] = _num(_m(r'每条支承线 (\d+) 个', desc, 'bearing count').group(1))
        m = _m(r'有效平面尺寸 (\d+) mm × (\d+) mm，中间橡胶层 (\d+) 层、每层厚 (\d+) mm', desc, 'bearing dimensions')
        b['a_mm'], b['b_mm'], b['n_layers'], b['t1_mm'] = (_num(m.group(1)), _num(m.group(2)), _num(m.group(3)),
                                                            _num(m.group(4)))
        m = re.search(r'橡胶剪变模量 ' + F + ' MPa', desc)
    if m:
        b['Ge_MPa'] = _num(m.group(1))
    if precast and b['per_girder_end'] is None:
        raise ParseError('precast girder bearings must be counted per girder end')
    return b


def parse_bearings(s, lang, n_span, precast):
    supports = {}
    piers = None
    if lang == 'en':
        s = s.replace('Abutments at both ends.', '').strip()
        sentences = [x.strip() for x in re.split(r'(?<=\.)\s+(?=(?:Abutment|Pier|Piers)\b)', s) if x.strip()]
    else:
        s = s.replace('两端为桥台。', '').strip()
        sentences = [x.strip() for x in re.split(r'(?<=。)', s) if x.strip()]
    for sent in sentences:
        head, sep, desc = sent.partition(':' if lang == 'en' else '：')
        if not sep:
            raise ParseError(f'cannot parse bearing statement: {sent[:40]}')
        desc = desc.strip().rstrip('.。')
        if head.strip() in ('Piers', '桥墩'):
            if lang == 'en':
                m = _m(r'twin circular columns of {0} m diameter, concrete (C\d+), fixed at the base; height from '
                       r'base to bearings: (.*)$'.format(F), desc, 'pier data')
                D, conc, hs = _num(m.group(1)), m.group(2), m.group(3)
                heights = {int(k): _num(h) for k, h in re.findall(r'Pier (\d+) ' + F + ' m', hs)}
            else:
                m = _m(r'双圆柱墩，柱径 {0} m，混凝土 (C\d+)，墩底固结；墩底至支座高度：(.*)$'.format(F), desc, 'pier data')
                D, conc, hs = _num(m.group(1)), m.group(2), m.group(3)
                heights = {int(k): _num(h) for k, h in re.findall(r'(\d+) 号墩 ' + F + ' m', hs)}
            piers = {k: {'height_m': h, 'diameter_m': D, 'n_columns': 2, 'concrete': conc} for k, h in heights.items()}
            continue
        names = re.split(r', | and ' if lang == 'en' else r'、', head)
        b = _bearing(desc, lang, precast)
        for nm in names:
            k = _support_index(nm, lang)
            if k in supports:
                raise ParseError(f'support {k} described twice')
            supports[k] = dict(b)
    if sorted(supports) != list(range(n_span + 1)):
        raise ParseError('bearings not given for every support line')
    out = []
    for k in range(n_span + 1):
        kind = 'abutment' if k in (0, n_span) else 'pier'
        pier = piers.get(k) if (piers and kind == 'pier') else None
        if piers and kind == 'pier' and pier is None:
            raise ParseError(f'pier {k} height missing')
        out.append({'index': k, 'kind': kind, 'bearing': supports[k], 'pier': pier})
    return out


# ---------------------------------------------------------------- design standard
def parse_standard(s, lang):
    if lang == 'en':
        cls = _m(r'Highway Class (II|I) loading', s, 'load class').group(1)
        traffic = 'two_way' if 'two-way traffic' in s else 'one_way' if 'one-way traffic' in s else None
        cw = _num(_m(r'carriageway width ' + F + ' m', s, 'carriageway width').group(1))
        lanes = _num(_m(r'(\w+) design lanes', s, 'design lanes').group(1))
    else:
        cls = _m(r'公路-(II|I) 级', s, 'load class').group(1)
        traffic = 'two_way' if '双向行驶' in s else 'one_way' if '单向行驶' in s else None
        cw = _num(_m(r'行车道宽 ' + F + ' m', s, 'carriageway width').group(1))
        lanes = _num(_m(r'设计车道数 (\d+)', s, 'design lanes').group(1))
    if traffic is None:
        raise ParseError('traffic direction')
    return {'carriageway_width_m': cw, 'traffic': traffic, 'design_lanes': lanes, 'load_class': cls}


def parse(text):
    lang = detect_lang(text)
    span, sec, brg, std = _parts(text, lang)
    st, spans, width = parse_span(span, lang)
    girder = parse_section(sec, lang)
    supports = parse_bearings(brg, lang, len(spans), girder['type'] != 'cast_box')
    deck = {'deck_width_m': width, **parse_standard(std, lang)}
    return {'structure_type': st, 'spans_m': spans, 'deck': deck, 'girder': girder, 'supports': supports,
            'dead_load': 'girder_self_weight_only'}

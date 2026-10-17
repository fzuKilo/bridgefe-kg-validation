"""BridgeFE-Bench 输入描述：四段式结构化描述（中英文）与自由文本改写。

描述只给出设计荷载等级与车道数，不给任何荷载数值；截面给出中梁（或箱梁）
主要尺寸，截面特性须由被测方法自行计算。
"""
from problems import support_name

NUM_EN = {1: 'one', 2: 'two', 3: 'three', 4: 'four', 5: 'five', 6: 'six', 7: 'seven',
          8: 'eight', 9: 'nine', 10: 'ten'}
NUM_ZH = {1: '一', 2: '二', 3: '三', 4: '四', 5: '五', 6: '六', 7: '七', 8: '八',
          9: '九', 10: '十'}
TYPE_EN = {'small_box': 'precast prestressed small box girders', 't_girder': 'precast prestressed T girders'}
SHORT_ZH = {'small_box': '小箱梁', 't_girder': 'T 梁'}
TYPE_ZH = {'small_box': '预制预应力混凝土小箱梁', 't_girder': '预制预应力混凝土 T 梁'}


def has_sliding(p):
    return any(b['kind'] == 'sliding' for b in p['bearings'])


def cap(text):
    return text[:1].upper() + text[1:]


def mm(x):
    return f'{x * 1000:.0f}'


def spans_str(spans):
    return ' + '.join(f'{L:g}' for L in spans)


def _precast(p):
    import sections as sec
    g = p['girder']
    if g['type'] == 'small_box':
        return {**sec.SMALL_BOX_COMMON, **sec.SMALL_BOX[g['span_class']]}
    return {**sec.T_GIRDER_COMMON, **sec.T_GIRDER[g['span_class']]}


def section_en(p):
    g = p['girder']
    if g['type'] == 'small_box':
        d = _precast(p)
        return (f"middle-girder section at midspan: depth {d['h']:g} m; top width {d['b_top']:.2f} m; "
                f"flange {d['t_tip']:.2f} m thick at the tip, thickening by {d['haunch_rise'] * 100:g} cm over a "
                f"{d['haunch_len'] * 100:g} cm long haunch next to the web; bottom slab {d['b_bot']:.2f} m wide and "
                f"{d['t_bot']:.2f} m thick; top slab {d['t_top']:.2f} m thick; webs {d['t_web']:.2f} m thick "
                f"(measured horizontally) with outer faces inclined at 1:{d['web_slope']:g}; "
                f"15 cm x 7 cm chamfers at the upper corners of the cell")
    if g['type'] == 't_girder':
        d = _precast(p)
        return (f"middle-girder section at midspan: depth {d['h']:g} m; precast flange {d['b_top']:.2f} m wide, "
                f"{d['t_tip']:.2f} m thick over the outer {d['flat_len']:.2f} m and thickening linearly to "
                f"{d['t_root']:.2f} m at the web; web {d['t_web']:.2f} m thick; bottom bulb {d['b_bulb']:.2f} m wide "
                f"with a {d['bulb_h']:.2f} m vertical part and a {d['bulb_trans']:.2f} m high linear transition to the web")
    b = g['box']
    return (f"single-cell box section of constant depth {b['h']:g} m: top slab {b['B_top']:g} m wide "
            f"and {b['t_top']:g} m thick; bottom slab {b['B_bot']:g} m wide and {b['t_bot']:g} m thick; "
            f"two vertical webs {b['t_web']:g} m thick; cantilever flanges {b['t_cant_root']:g} m thick "
            f"at the root tapering linearly to {b['t_cant_tip']:g} m at the tip")


def section_zh(p):
    g = p['girder']
    if g['type'] == 'small_box':
        d = _precast(p)
        return (f"中梁跨中截面：梁高 {d['h']:g} m；顶宽 {d['b_top']:.2f} m；翼缘端部厚 {d['t_tip']:.2f} m，"
                f"近腹板处经 {d['haunch_len'] * 100:g} cm 长加腋增厚 {d['haunch_rise'] * 100:g} cm；"
                f"底板宽 {d['b_bot']:.2f} m、厚 {d['t_bot']:.2f} m；顶板厚 {d['t_top']:.2f} m；"
                f"腹板水平厚 {d['t_web']:.2f} m，外侧坡度 1:{d['web_slope']:g}；箱内顶角设 15 cm × 7 cm 倒角")
    if g['type'] == 't_girder':
        d = _precast(p)
        return (f"中梁跨中截面：梁高 {d['h']:g} m；预制翼缘宽 {d['b_top']:.2f} m，外侧 {d['flat_len']:.2f} m 范围厚 "
                f"{d['t_tip']:.2f} m，向腹板线性增厚至 {d['t_root']:.2f} m；腹板厚 {d['t_web']:.2f} m；"
                f"马蹄宽 {d['b_bulb']:.2f} m，竖直段高 {d['bulb_h']:.2f} m，经 {d['bulb_trans']:.2f} m 高线性过渡段接腹板")
    b = g['box']
    return (f"单箱单室等高截面，梁高 {b['h']:g} m：顶板宽 {b['B_top']:g} m、厚 {b['t_top']:g} m；"
            f"底板宽 {b['B_bot']:g} m、厚 {b['t_bot']:g} m；两道竖直腹板厚 {b['t_web']:g} m；"
            f"翼缘悬臂根部厚 {b['t_cant_root']:g} m，线性变化至端部 {b['t_cant_tip']:g} m")


def bearing_groups(p):
    """按支座规格与类型归并支承线，返回 [(kind, bearing, [k...])]。"""
    groups = []
    for k, b in enumerate(p['bearings']):
        key = (b['kind'], b.get('model'), b.get('a'), b.get('b'), b.get('t1'), b.get('n_layers'), b['Ge'])
        for gkey, gb, ks in groups:
            if gkey == key:
                ks.append(k)
                break
        else:
            groups.append((key, b, [k]))
    return [(g[0][0], g[1], g[2]) for g in groups]


def names(ks, n, lang):
    parts = [support_name(k, n, lang) for k in ks]
    if lang == 'en':
        return parts[0] if len(parts) == 1 else ', '.join(parts[:-1]) + ' and ' + parts[-1]
    return '、'.join(parts)


def structured_en(p):
    n = len(p['spans'])
    g, d = p['girder'], p['deck']
    ov = p['overrides']
    if p['structure'] == 'simply_supported':
        span = f"Single simply supported span of {p['spans'][0]:g} m (centre-to-centre of bearings)"
    elif p['structure'] == 'precast_continuous':
        span = (f"One continuous unit of {NUM_EN[n]} spans, {spans_str(p['spans'])} m (centre-to-centre "
                f"of bearings), precast girders simply supported during erection and made continuous afterwards")
    else:
        span = (f"One cast-in-place continuous unit of {NUM_EN[n]} spans, {spans_str(p['spans'])} m "
                f"(centre-to-centre of bearings)")
    span += f"; deck width {d['deck_width']:g} m."

    if g['type'] == 'cast_box':
        sec = f"Cast-in-place prestressed concrete box girder, {section_en(p)}; girder concrete {g['concrete']}."
    else:
        sec = (f"{cap(TYPE_EN[g['type']])}, {g['n']} per span; {section_en(p)}; "
               f"girder concrete {g['concrete']}.")
    if 'E_girder' in ov:
        sec += f" Per material tests, take the elastic modulus of the girder concrete as {ov['E_girder'] / 1e6:.0f} MPa."
    if 'gamma' in ov:
        sec += f" The owner requires a unit weight of {ov['gamma'] / 1e3:g} kN/m3 for the girder concrete."
    sec += " Consider the self-weight of the main girders only (no wet joints, diaphragms, pavement or barriers)."

    bl = []
    for kind, b, ks in bearing_groups(p):
        if kind.startswith('spherical'):
            mv = ('longitudinally fixed (fixed type GD at middle girders, transversely movable type DX at edge girders)'
                  if kind == 'spherical_fixed' else 'longitudinally movable (types SX/DX)')
            bl.append(f"{names(ks, n, 'en')}: spherical bearings {b['model']} (JT/T 854-2013, vertical design "
                      f"capacity {b['capacity_kN']} kN), one under each girder end, {mv}.")
            continue
        count = (f"{'two' if b.get('per_girder') == 2 else 'one'} under each girder end"
                 if b.get('per_girder') else f"{NUM_EN[b['per_line']]} per support line")
        typ = ('PTFE sliding laminated elastomeric bearings' if kind == 'sliding' else
               'plain laminated elastomeric bearings' + (' (fixed)' if has_sliding(p) else ''))
        s = (f"{names(ks, n, 'en')}: {typ}, {count}; effective plan size {mm(b['a'])} mm x {mm(b['b'])} mm, "
             f"{NUM_EN[b['n_layers']]} internal rubber layers {mm(b['t1'])} mm thick")
        if b['Ge']:
            s += f"; shear modulus of the rubber {b['Ge'] / 1e6:g} MPa (manufacturer's test value)"
        bl.append(s + '.')
    if p['piers']:
        pr = p['piers'][0]
        hs = '; '.join(f"{support_name(k, n)} {q['H']:g} m" for k, q in enumerate(p['piers'], 1))
        bl.append(f"Piers: twin circular columns of {pr['D']:g} m diameter, concrete {pr['concrete']}, "
                  f"fixed at the base; height from base to bearings: {hs}.")
    if p['structure'] == 'simply_supported':
        bl.insert(0, 'Abutments at both ends.')

    direction = 'two-way' if d['direction'] == 'two_way' else 'one-way'
    std = (f"Highway Class {d['load_class']} loading (JTG D60-2015); {direction} traffic, carriageway "
           f"width {d['carriageway_width']:g} m, {NUM_EN[d['n_lanes']]} design lanes.")
    return '\n'.join([f'[Span arrangement] {span}', f'[Section and material] {sec}',
                      f"[Bearings and boundary] {' '.join(bl)}", f'[Design standard] {std}'])


def structured_zh(p):
    n = len(p['spans'])
    g, d = p['girder'], p['deck']
    ov = p['overrides']
    if p['structure'] == 'simply_supported':
        span = f"单跨简支，计算跨径 {p['spans'][0]:g} m（支座中心线间距）"
    elif p['structure'] == 'precast_continuous':
        span = f"一联{NUM_ZH[n]}跨，跨径 {spans_str(p['spans'])} m（支座中心线间距），先简支后连续"
    else:
        span = f"现浇连续梁一联{NUM_ZH[n]}跨，跨径 {spans_str(p['spans'])} m（支座中心线间距）"
    span += f"；桥面全宽 {d['deck_width']:g} m。"

    if g['type'] == 'cast_box':
        sec = f"现浇预应力混凝土箱梁，{section_zh(p)}；主梁混凝土 {g['concrete']}。"
    else:
        sec = f"{TYPE_ZH[g['type']]}，每跨 {g['n']} 片；{section_zh(p)}；主梁混凝土 {g['concrete']}。"
    if 'E_girder' in ov:
        sec += f"根据材料试验，主梁混凝土弹性模量取 {ov['E_girder'] / 1e6:.0f} MPa。"
    if 'gamma' in ov:
        sec += f"业主要求主梁混凝土重度取 {ov['gamma'] / 1e3:g} kN/m³。"
    sec += "只计主梁自重（不计湿接缝、横隔板、铺装与护栏）。"

    bl = []
    for kind, b, ks in bearing_groups(p):
        if kind.startswith('spherical'):
            mv = ('纵桥向固定（中梁为固定支座 GD，边梁为横桥向单向活动支座 DX）'
                  if kind == 'spherical_fixed' else '纵桥向活动（SX/DX 型）')
            bl.append(f"{names(ks, n, 'zh')}：球形支座 {b['model']}（JT/T 854-2013，竖向设计承载力 "
                      f"{b['capacity_kN']} kN），每个梁端 1 个，{mv}。")
            continue
        count = (f"每个梁端 {'2' if b.get('per_girder') == 2 else '1'} 个"
                 if b.get('per_girder') else f"每条支承线 {b['per_line']} 个")
        typ = ('四氟滑板式板式橡胶支座' if kind == 'sliding' else
               '普通板式橡胶支座' + ('（固定）' if has_sliding(p) else ''))
        s = (f"{names(ks, n, 'zh')}：{typ}，{count}；有效平面尺寸 {mm(b['a'])} mm × {mm(b['b'])} mm，"
             f"中间橡胶层 {b['n_layers']} 层、每层厚 {mm(b['t1'])} mm")
        if b['Ge']:
            s += f"；橡胶剪变模量 {b['Ge'] / 1e6:g} MPa（厂家试验值）"
        bl.append(s + '。')
    if p['piers']:
        pr = p['piers'][0]
        hs = '；'.join(f"{support_name(k, n, 'zh')} {q['H']:g} m" for k, q in enumerate(p['piers'], 1))
        bl.append(f"桥墩：双圆柱墩，柱径 {pr['D']:g} m，混凝土 {pr['concrete']}，墩底固结；"
                  f"墩底至支座高度：{hs}。")
    if p['structure'] == 'simply_supported':
        bl.insert(0, '两端为桥台。')

    direction = '双向行驶' if d['direction'] == 'two_way' else '单向行驶'
    std = (f"公路-{d['load_class']} 级（JTG D60-2015）；{direction}，行车道宽 "
           f"{d['carriageway_width']:g} m，设计车道数 {d['n_lanes']}。")
    return '\n'.join([f'【跨径布置】{span}', f'【截面与材料】{sec}',
                      f"【支座与边界】{''.join(bl)}", f'【设计标准】{std}'])


# ---------------- 自由文本改写 ----------------
def free_text(p, style, lang):
    """style 1：工程师口述笔记；2：邮件委托，信息顺序打乱、单位混用；3：简写参数清单。"""
    n = len(p['spans'])
    g, d = p['girder'], p['deck']
    ov = p['overrides']
    lanes = d['n_lanes']
    lc = d['load_class']
    sec_en, sec_zh = section_en(p), section_zh(p)
    groups = bearing_groups(p)

    def brg_en(short=False):
        out = []
        for kind, b, ks in groups:
            if kind.startswith('spherical'):
                out.append(f"{b['model']} spherical bearings at {names(ks, n, 'en')}, one per girder end, "
                           + ('fixed longitudinally' if kind == 'spherical_fixed' else 'free to slide longitudinally'))
                continue
            t = 'sliding (PTFE)' if kind == 'sliding' else ('fixed (plain elastomeric)' if has_sliding(p) else 'plain elastomeric')
            cnt = (f"{b['per_girder']}/girder end" if b.get('per_girder') else f"{b['per_line']}/line")
            ge = f", G={b['Ge'] / 1e6:g} MPa" if b['Ge'] else ''
            if short:
                out.append(f"{names(ks, n, 'en')}: {t}, {cnt}, {mm(b['a'])}x{mm(b['b'])}, {b['n_layers']}x{mm(b['t1'])} mm{ge}")
            else:
                out.append(f"{t} bearings at {names(ks, n, 'en')} ({cnt}, {b['a'] * 100:g} cm by {b['b'] * 100:g} cm, "
                           f"{b['n_layers']} rubber layers of {b['t1'] * 100:g} cm{ge})")
        return out

    def brg_zh(short=False):
        out = []
        for kind, b, ks in groups:
            if kind.startswith('spherical'):
                out.append(f"{names(ks, n, 'zh')}用 {b['model']} 球形支座，每梁端1个，"
                           + ('纵向固定' if kind == 'spherical_fixed' else '纵向活动'))
                continue
            t = '滑动（四氟板）' if kind == 'sliding' else ('固定（普通板式）' if has_sliding(p) else '普通板式')
            cnt = (f"每梁端{b['per_girder']}个" if b.get('per_girder') else f"每排{b['per_line']}个")
            ge = f"，G={b['Ge'] / 1e6:g}MPa" if b['Ge'] else ''
            if short:
                out.append(f"{names(ks, n, 'zh')}：{t}，{cnt}，{mm(b['a'])}×{mm(b['b'])}，{b['n_layers']}×{mm(b['t1'])}mm{ge}")
            else:
                out.append(f"{names(ks, n, 'zh')}用{t}支座，{cnt}，平面 {b['a'] * 100:g}×{b['b'] * 100:g} cm，"
                           f"橡胶 {b['n_layers']} 层、每层 {b['t1'] * 100:g} cm{ge}")
        return out

    extra_en, extra_zh = [], []
    if 'E_girder' in ov:
        extra_en.append(f"use Ec = {ov['E_girder'] / 1e6:.0f} MPa from the material tests")
        extra_zh.append(f"弹性模量按试验取 {ov['E_girder'] / 1e6:.0f} MPa")
    if 'gamma' in ov:
        extra_en.append(f"unit weight {ov['gamma'] / 1e3:g} kN/m3 as the owner asked")
        extra_zh.append(f"重度按业主要求取 {ov['gamma'] / 1e3:g} kN/m³")
    pier_en = pier_zh = ''
    if p['piers']:
        hs = ', '.join(f"{q['H']:g}" for q in p['piers'])
        pier_en = (f"Piers are twin {p['piers'][0]['D']:g} m round columns ({p['piers'][0]['concrete']}), "
                   f"fixed at the footing, heights {hs} m from Pier 1 onward.")
        pier_zh = (f"墩为双柱圆墩，柱径 {p['piers'][0]['D']:g} m（{p['piers'][0]['concrete']}），墩底固结，"
                   f"自 1 号墩起墩高依次为 {hs} m。")
    what_en = {'simply_supported': 'a single simply supported span',
               'precast_continuous': 'a precast unit made continuous after erection',
               'cast_continuous_with_piers': 'a cast-in-place continuous box girder'}[p['structure']]
    what_zh = {'simply_supported': '单跨简支梁', 'precast_continuous': '先简支后连续的一联',
               'cast_continuous_with_piers': '现浇连续箱梁'}[p['structure']]
    girders_en = (f"{g['n']} {TYPE_EN[g['type']].replace('precast prestressed ', '')} per span"
                  if g['type'] != 'cast_box' else 'one single-cell box')
    girders_zh = f"每跨 {g['n']} 片{SHORT_ZH[g['type']]}" if g['type'] != 'cast_box' else '单箱单室'

    if lang == 'en':
        if style == 1:
            return (f"Quick note from site. It's {what_en}, spans {spans_str(p['spans'])} m bearing to bearing, "
                    f"deck {d['deck_width']:g} m wide, {girders_en}, {g['concrete']} throughout. "
                    f"Section is the usual one: {sec_en}. "
                    + (f"Also {', and '.join(extra_en)}. " if extra_en else '')
                    + f"Bearings: {'; '.join(brg_en())}. {pier_en} "
                    f"Traffic is {'two-way' if d['direction'] == 'two_way' else 'one-way'} on a {d['carriageway_width']:g} m carriageway, "
                    f"{lanes} lanes, designed for Highway Class {lc}. Girder self-weight only, nothing else on it yet.")
        if style == 2:
            return (f"Dear colleague,\n\nCould you set up the global FE model for the bridge below? Design loading is "
                    f"Highway Class {lc}, {lanes} design lanes ({d['carriageway_width'] * 100:g} cm carriageway, "
                    f"{'two-way' if d['direction'] == 'two_way' else 'one-way'}). {cap('; '.join(brg_en()))}. {pier_en} "
                    f"The superstructure is {what_en} with spans of {spans_str([L * 1000 for L in p['spans']])} mm "
                    f"and an overall deck width of {d['deck_width']:g} m, {girders_en}, concrete {g['concrete']}"
                    + (f" ({'; '.join(extra_en)})" if extra_en else '')
                    + f". For the section, {sec_en}. Please include only the self-weight of the girders.\n\nThanks!")
        return ('\n'.join([f"TYPE: {what_en}", f"SPANS (m): {spans_str(p['spans'])}",
                           f"DECK: {d['deck_width']:g} m; {girders_en}; {g['concrete']}" + (f"; {'; '.join(extra_en)}" if extra_en else ''),
                           f"SECTION: {sec_en}"] + [f"BRG {x}" for x in brg_en(True)]
                          + ([f"PIERS: {pier_en}"] if pier_en else [])
                          + [f"LOADING: Hwy-{lc}, {lanes} lanes, CW {d['carriageway_width']:g} m, "
                             f"{'2-way' if d['direction'] == 'two_way' else '1-way'}", "DL: girder SW only"]))
    if style == 1:
        return (f"现场记一下：这是{what_zh}，跨径 {spans_str(p['spans'])} m（支座中心），桥宽 {d['deck_width']:g} m，"
                f"{girders_zh}，混凝土都是 {g['concrete']}。截面就是常规那套，{sec_zh}。"
                + (f"另外{'，'.join(extra_zh)}。" if extra_zh else '')
                + f"支座：{'；'.join(brg_zh())}。{pier_zh}"
                f"{'双向' if d['direction'] == 'two_way' else '单向'}行驶，行车道 {d['carriageway_width']:g} m，{lanes} 个车道，"
                f"按公路-{lc} 级设计。先只算主梁自重，其他恒载不管。")
    if style == 2:
        return (f"您好：\n\n麻烦帮忙建一下下面这座桥的整体有限元模型。设计荷载公路-{lc} 级，设计车道 {lanes} 个"
                f"（行车道宽 {d['carriageway_width'] * 100:g} cm，{'双向' if d['direction'] == 'two_way' else '单向'}行驶）。"
                f"{'；'.join(brg_zh())}。{pier_zh}上部结构为{what_zh}，跨径 {spans_str([L * 1000 for L in p['spans']])} mm，"
                f"桥面全宽 {d['deck_width']:g} m，{girders_zh}，混凝土 {g['concrete']}"
                + (f"（{'；'.join(extra_zh)}）" if extra_zh else '')
                + f"。截面：{sec_zh}。荷载只考虑主梁自重。\n\n谢谢！")
    return ('\n'.join([f"桥型：{what_zh}", f"跨径(m)：{spans_str(p['spans'])}",
                       f"桥宽：{d['deck_width']:g} m；{girders_zh}；{g['concrete']}" + (f"；{'；'.join(extra_zh)}" if extra_zh else ''),
                       f"截面：{sec_zh}"] + [f"支座 {x}" for x in brg_zh(True)]
                      + ([f"桥墩：{pier_zh}"] if pier_zh else [])
                      + [f"荷载：公路-{lc}，{lanes} 车道，行车道 {d['carriageway_width']:g} m，"
                         f"{'双向' if d['direction'] == 'two_way' else '单向'}", "恒载：仅主梁自重"]))

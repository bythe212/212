"""Sonify 빌드 검증 — TD 안에서 실행 (Textport 또는 TD MCP execute_python_script).

    SONIFY_DIR = r'.../212/touchdesigner'; exec(open(SONIFY_DIR + '/td/verify_sonify.py', encoding='utf-8').read())

이미지를 띄우기 전에 숫자로 확인한다: 확장 상태, 노드 에러, 각 TOP 해상도/밝기, CHOP 값, API/OSC 상태.
빌드 직후 같은 호출에서 돌리지 말고, 몇 프레임 뒤 따로 실행한다.
"""
import json

import numpy as np
import td


def _verify_sonify():
    parent = td.op(globals().get('SONIFY_PARENT', '/project1'))
    roots = [c for c in parent.children if 'sonify' in c.tags]
    if not roots:
        return {'fatal': 'sonify 태그 컨테이너가 없음 — build_sonify.py 먼저 실행'}
    root = roots[0]
    names = root.fetch('sonify_ops', {}, search=False)
    out = {'container': root.path}

    ext = getattr(root.ext, 'SonifyExt', None)
    out['ext'] = None if ext is None else {'error': ext.error, 'engine': ext.engine is not None,
                                           'fps': round(ext._fps, 1), 'img_res': ext._img_res}
    errs = []
    for c in root.findChildren(depth=1):
        try:
            e = c.errors() or c.warnings()
        except Exception:
            e = ''
        if e:
            errs.append((c.name, e[:160]))
    out['node_errors'] = errs

    def stat(key):
        o = root.op(names.get(key, ''))
        if o is None:
            return None
        try:
            a = o.numpyArray(delayed=False)
            rgb = a[:, :, :3]
            return {'res': (o.width, o.height), 'rgb_max': round(float(rgb.max()), 3),
                    'rgb_mean': round(float(rgb.mean()), 4), 'alpha_mean': round(float(a[:, :, 3].mean()), 3),
                    'nan': bool(np.isnan(a).any())}
        except Exception as e:
            return {'err': str(e)[:120]}

    out['tops'] = {k: stat(k) for k in ('source', 'analysis', 'overlay', 'glsl', 'out')}

    def chop(key, keep):
        o = root.op(names.get(key, ''))
        if o is None:
            return None
        try:
            return {'samples': o.numSamples,
                    'chans': {c.name: round(float(c[0]), 4) for c in o.chans() if not keep or c.name in keep}}
        except Exception as e:
            return {'err': str(e)[:120]}

    out['scan'] = chop('chop_scan', ('pos', 'lum', 'hue', 'centroid', 'edge', 'note', 'trig'))
    out['feeds'] = chop('chop_feeds', ('feed1_price', 'feed1_ok', 'feed2_price', 'feed2_ok', 'feed3_price',
                                       'feed3_ok', 'iss_lat', 'iss_ok'))
    out['bands'] = chop('chop_bands', ('lum',))

    st = root.op(names.get('status', ''))
    if st is not None:
        out['status'] = [[c.val for c in r][:10] for r in st.rows()[1:]]
    if ext is not None and ext.engine is not None:
        e = ext.engine
        out['engine'] = {'pos': round(e.pos, 4), 'playing': e.playing, 'image': e.analyzer.size,
                         'palette': [[round(float(v), 2) for v in c] for c in e.analyzer.palette],
                         'osc_sent': e.osc.sent, 'osc_error': e.osc.last_error, 'trigs': e.trig_count}
    return out


try:
    SONIFY_VERIFY = _verify_sonify()
except Exception as _e:
    import traceback
    SONIFY_VERIFY = {'fatal': '%s: %s' % (type(_e).__name__, _e), 'trace': traceback.format_exc()}
print(json.dumps(SONIFY_VERIFY, ensure_ascii=False, default=str))

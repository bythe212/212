"""Sonify 네트워크 빌드 스크립트 — TouchDesigner 안에서 실행한다.

Textport (Alt+T) 에 한 줄로:
    SONIFY_DIR = r'C:/경로/212/touchdesigner'; exec(open(SONIFY_DIR + '/build_sonify.py', encoding='utf-8').read())

또는 이 파일을 TD 네트워크로 드래그해서 생긴 Text DAT 을 우클릭 → Run Script.
TD MCP 의 execute_python_script 로 위 한 줄을 보내도 된다.

여러 번 실행해도 안전하다(멱등): 'sonify' 태그가 붙은 이전 컨테이너의 커스텀 파라미터 값과
OSC 매핑 표를 기억해 두었다가, 지우고 새로 만든 뒤 되살린다. 다른 노드는 건드리지 않는다.

선택 변수(실행 전에 정의하면 적용):
    SONIFY_PARENT = '/project1'   # 컨테이너를 만들 위치
    SONIFY_OPEN_WINDOW = True     # 빌드 후 UI 창 열기
"""
import json
import os
import sys
import traceback

import td


def _sonify_dir():
    g = globals()
    d = g.get('SONIFY_DIR')
    if d:
        return os.path.abspath(d)
    f = g.get('__file__')
    if f and os.path.basename(f) == 'build_sonify.py':
        return os.path.dirname(os.path.abspath(f))
    m = g.get('me')
    try:
        path = m.par.file.eval()
        if path and os.path.basename(path) == 'build_sonify.py':
            return os.path.dirname(os.path.abspath(path))
    except Exception:
        pass
    raise RuntimeError("SONIFY_DIR 를 지정하세요. 예: SONIFY_DIR = r'C:/.../212/touchdesigner'")


def build_sonify():
    rep = []    # 꼭 확인해야 하는 실패
    soft = []   # 있으면 좋은 설정의 실패(버전마다 파라미터 이름이 다를 수 있음)
    base = _sonify_dir()
    pydir = os.path.join(base, 'python')
    tddir = os.path.join(base, 'td')
    for d in (pydir, tddir):
        if not os.path.isdir(d):
            raise RuntimeError('폴더가 없습니다: %s' % d)
    if pydir not in sys.path:
        sys.path.insert(0, pydir)
    import sonify_td
    sonify_td = sonify_td.reload_all()
    R = sonify_td.render
    D = sonify_td.DEFAULTS

    def read(name):
        with open(os.path.join(tddir, name), encoding='utf-8') as fh:
            return fh.read()

    def T(name):
        return getattr(td, name)

    def st(o, critical=True, **kw):
        for k, v in kw.items():
            try:
                getattr(o.par, k).val = v
            except Exception as e:
                (rep if critical else soft).append('SET %s.%s: %s' % (o.name, k, e))

    def ex(o, critical=True, **kw):
        for k, v in kw.items():
            try:
                getattr(o.par, k).expr = v
            except Exception as e:
                (rep if critical else soft).append('EXPR %s.%s: %s' % (o.name, k, e))

    def pick(o, pn, prefs, critical=True):
        try:
            par = getattr(o.par, pn)
            names = list(par.menuNames)
            for c in prefs:
                if c in names:
                    par.val = c
                    return c
            (rep if critical else soft).append('MENU %s.%s 후보 %s' % (o.name, pn, names))
        except Exception as e:
            (rep if critical else soft).append('MENU %s.%s: %s' % (o.name, pn, e))

    def conn(s, d, i=0):
        try:
            d.inputConnectors[i].connect(s)
        except Exception as e:
            rep.append('CONN %s->%s[%d]: %s' % (s.name, d.name, i, e))

    def setres(o, w, h):
        pick(o, 'outputresolution', ['custom'])
        st(o, resolutionw=w, resolutionh=h)
        st(o, critical=False, resmult=False)

    # ------------------------------------------------------------------ 위치/이전 상태
    parent = td.op(globals().get('SONIFY_PARENT', '/project1'))
    if parent is None:
        raise RuntimeError('부모 COMP 가 없습니다: %s' % globals().get('SONIFY_PARENT', '/project1'))

    saved = {'pars': {}, 'oscmap': None, 'name': None, 'pos': None}
    for old in [c for c in parent.children if 'sonify' in c.tags]:
        saved['name'], saved['pos'] = old.name, (old.nodeX, old.nodeY)
        for p in old.customPars:
            try:
                if not p.isPulse and p.name not in ('Libpath', 'Version', 'Scanpos'):
                    saved['pars'][p.name] = p.eval()
            except Exception:
                pass
        try:
            names = old.fetch('sonify_ops', {}, search=False)
            t = old.op(names.get('oscmap', ''))
            if t is not None:
                saved['oscmap'] = [[c.val for c in r] for r in t.rows()]
        except Exception:
            pass
        old.destroy()

    root = parent.create(T('containerCOMP'), saved['name']) if saved['name'] else parent.create(T('containerCOMP'))
    root.tags.add('sonify')
    root.comment = 'Sonify: 사진 스캔 + 실시간 API → OSC (Ableton). 컨트롤은 이 컨테이너의 커스텀 파라미터.'
    root.nodeX, root.nodeY = saved['pos'] or (0, 0)
    root.color = (0.15, 0.35, 0.55)
    st(root, w=1600, h=720)
    st(root, critical=False, bgcolorr=0.04, bgcolorg=0.045, bgcolorb=0.06, bgalpha=1)

    # ------------------------------------------------------------------ 커스텀 파라미터 (컨트롤)
    def page(name):
        return root.appendCustomPage(name)

    def cpar(pg, kind, name, label, default=None, norm=None, lim=None, menu=None, help=None):
        try:
            res = getattr(pg, 'append' + kind)(name, label=label)
            try:
                pars = list(res)
            except TypeError:
                pars = [res[0]]
        except Exception as e:
            rep.append('PAR %s: %s' % (name, e))
            return None
        p = pars[0]
        try:
            if menu is not None:
                p.menuNames = [m[0] for m in menu]
                p.menuLabels = [m[1] for m in menu]
            if norm is not None:
                p.normMin, p.normMax = norm
            if lim is not None:
                if lim[0] is not None:
                    p.min, p.clampMin = lim[0], True
                if lim[1] is not None:
                    p.max, p.clampMax = lim[1], True
            if default is not None:
                vals = default if isinstance(default, (tuple, list)) else (default,)
                for q, v in zip(pars, vals):
                    q.default = v
                    q.val = v
        except Exception as e:
            rep.append('PARCFG %s: %s' % (name, e))
        if help:
            try:
                p.help = help
            except Exception:
                pass
        return p

    image_default = os.path.join(base, 'assets', 'deep_field.jpg').replace('\\', '/')

    pg = page('Scan')
    cpar(pg, 'File', 'Imagefile', 'Image File', image_default, help='스캔할 사진 (우주 사진 추천)')
    cpar(pg, 'Pulse', 'Reloadimage', 'Reload Image')
    cpar(pg, 'TOP', 'Sourcetop', 'Source TOP (optional)', help='사진 대신 카메라/영상 TOP 을 스캔. 비우면 Imagefile 사용')
    cpar(pg, 'Toggle', 'Livesource', 'Live Source (video)', False, help='영상이면 켜기: 매 프레임 다시 분석')
    cpar(pg, 'Toggle', 'Scanplay', 'Play', D['playing'])
    cpar(pg, 'Float', 'Scanpos', 'Position', 0.0, norm=(0, 1), lim=(0, 1), help='스캔선 위치. 드래그하면 이동')
    cpar(pg, 'Float', 'Sweepseconds', 'Sweep Seconds', D['sweep_seconds'], norm=(2, 120), lim=(0.5, None),
         help='왼쪽 끝→오른쪽 끝까지 걸리는 시간')
    cpar(pg, 'Menu', 'Scanmode', 'Mode', D['mode'],
         menu=[('loop', 'Loop'), ('pingpong', 'Ping-Pong'), ('once', 'Once')])
    cpar(pg, 'Pulse', 'Scanreset', 'Restart')
    cpar(pg, 'Int', 'Bands', 'Bands', D['bands'], norm=(4, 64), lim=(1, 128), help='세로 대역 수 = 음 개수')
    cpar(pg, 'Int', 'Scanwidth', 'Line Width (px)', D['scan_width'], norm=(1, 16), lim=(1, 64))
    cpar(pg, 'Float', 'Threshold', 'Trigger Threshold', D['threshold'], norm=(0, 1), lim=(0, 1),
         help='대역 밝기가 이 값을 넘으면 /scan/trig 노트 이벤트')
    cpar(pg, 'Int', 'Palettesize', 'Palette Colors', D['palette_size'], norm=(2, 8), lim=(1, 12))

    pg = page('Music')
    cpar(pg, 'Int', 'Notelow', 'Lowest Note (MIDI)', D['note_low'], norm=(0, 127), lim=(0, 127))
    cpar(pg, 'Int', 'Notehigh', 'Highest Note (MIDI)', D['note_high'], norm=(0, 127), lim=(0, 127))
    cpar(pg, 'Menu', 'Scale', 'Scale', D['scale'], menu=[(k, k) for k in sonify_td.SCALE_KEYS])
    cpar(pg, 'Menu', 'Rootnote', 'Root', str(D['root']),
         menu=[(str(i), n) for i, n in enumerate(sonify_td.NOTE_NAMES)])

    pg = page('Data')
    prov = [(k, k.capitalize() if k != 'sim' else 'Simulated') for k in sonify_td.PROVIDER_KEYS]
    for i in range(1, 4):
        cpar(pg, 'Toggle', 'Feed%dactive' % i, 'Feed %d On' % i, D['feed%d_enabled' % i])
        cpar(pg, 'Menu', 'Feed%dprovider' % i, 'Feed %d API' % i, D['feed%d_provider' % i], menu=prov)
        cpar(pg, 'Str', 'Feed%dsymbol' % i, 'Feed %d Symbol' % i, D['feed%d_symbol' % i],
             help='예: KRW-BTC (Upbit), ETHUSDT (Binance), SOL-USD (Coinbase), BTC_KRW (Bithumb). btc 처럼 짧게 써도 됨')
    cpar(pg, 'Toggle', 'Spaceactive', 'ISS Position (API 4)', D['space_enabled'])
    cpar(pg, 'Float', 'Pollinterval', 'Market Poll (s)', D['poll_interval'], norm=(0.2, 10), lim=(0.2, None))
    cpar(pg, 'Float', 'Spaceinterval', 'ISS Poll (s)', D['space_interval'], norm=(1, 30), lim=(1, None))
    cpar(pg, 'Int', 'Window', 'Stats Window (ticks)', D['window'], norm=(5, 600), lim=(5, 5000))
    cpar(pg, 'Float', 'Smoothing', 'Smoothing (s)', D['smoothing'], norm=(0.01, 5), lim=(0.01, None))
    cpar(pg, 'Float', 'Release', 'Activity Release (s)', D['release'], norm=(0.05, 5), lim=(0.01, None))
    cpar(pg, 'Menu', 'Sslmode', 'SSL', D['ssl_mode'],
         menu=[('auto', 'Auto (fallback)'), ('verify', 'Verify'), ('off', 'Off')])
    cpar(pg, 'Pulse', 'Reconnect', 'Reconnect')
    cpar(pg, 'Pulse', 'Resetfeeds', 'Reset Stats')

    pg = page('OSC')
    cpar(pg, 'Toggle', 'Oscactive', 'Send OSC', D['osc_enabled'])
    cpar(pg, 'Str', 'Oschost', 'Host', D['osc_host'])
    cpar(pg, 'Int', 'Oscport', 'Port (generic)', D['osc_port'], norm=(1024, 65535), lim=(1, 65535))
    cpar(pg, 'Float', 'Oscrate', 'Rate (Hz)', D['osc_rate'], norm=(1, 120), lim=(0.5, 1000))
    cpar(pg, 'Str', 'Oscprefix', 'Address Prefix', D['osc_prefix'])
    cpar(pg, 'Menu', 'Oscmode', 'Mode', D['osc_mode'],
         menu=[('generic', 'Generic /sonify/*'), ('mapped', 'Mapped (AbletonOSC)'), ('both', 'Both')])
    cpar(pg, 'Toggle', 'Oscbundle', 'Bundle per Tick', D['osc_bundle'])
    cpar(pg, 'Int', 'Abletonport', 'AbletonOSC Port', D['ableton_port'], norm=(1024, 65535), lim=(1, 65535))
    cpar(pg, 'Pulse', 'Testosc', 'Send Test')

    pg = page('View')
    cpar(pg, 'Pulse', 'Openwindow', 'Open Window')
    cpar(pg, 'Pulse', 'Closewindow', 'Close Window')
    cpar(pg, 'RGB', 'Linecolor', 'Line Color', (1.0, 0.77, 0.35))
    cpar(pg, 'Float', 'Lineglow', 'Line Glow', 0.35, norm=(0, 2), lim=(0, None))
    cpar(pg, 'Float', 'Dimahead', 'Unscanned Brightness', 0.6, norm=(0, 1), lim=(0, 1))
    cpar(pg, 'Float', 'Uirate', 'Panel FPS', 30.0, norm=(5, 60), lim=(1, 120))
    cpar(pg, 'Toggle', 'Overlayflip', 'Flip Overlay', True, help='글자가 위아래 뒤집혀 보이면 끄기')

    pg = page('Setup')
    cpar(pg, 'Folder', 'Libpath', 'Python Path', pydir.replace('\\', '/'))
    cpar(pg, 'Pulse', 'Reload', 'Reload Python')
    v = cpar(pg, 'Str', 'Version', 'Version', sonify_td.__version__)
    if v is not None:
        try:
            v.readOnly = True
        except Exception:
            pass

    for name, val in saved['pars'].items():           # 이전 빌드의 값 되살리기
        p = getattr(root.par, name, None)
        if p is None:
            continue
        if name == 'Imagefile' and val and not os.path.isfile(str(val)):
            continue
        try:
            p.val = val
        except Exception as e:
            soft.append('RESTORE %s: %s' % (name, e))

    # ------------------------------------------------------------------ 노드
    def mk(types, x, y, comment=None):
        types = types if isinstance(types, (list, tuple)) else [types]
        err = None
        for t in types:
            try:
                o = root.create(T(t))
                break
            except Exception as e:
                err = e
        else:
            raise RuntimeError('노드 생성 실패 %s: %s' % (types, err))
        o.nodeX, o.nodeY = x, y
        if comment:
            o.comment = comment
        return o

    def callbacks_dat(o, text, parname='callbacks'):
        d = None
        try:
            d = getattr(o.par, parname).eval()
        except Exception:
            pass
        if d is None:
            d = root.op(o.name + ('_callbacks' if parname == 'callbacks' else '_pixel'))
        if d is None:
            d = mk('textDAT', o.nodeX, o.nodeY - 150)
            st(o, **{parname: d.name})
        d.text = text
        return d

    # 사진 → 분석용 해상도
    movie = mk('moviefileinTOP', -1000, 300, '사진 (Imagefile)')
    ex(movie, file='parent().par.Imagefile')
    noise = mk('noiseTOP', -1000, 120, '사진이 없을 때 대체 이미지')
    setres(noise, 1024, 512)
    st(noise, critical=False, mono=False)
    select = mk('selectTOP', -1000, -60, 'Source TOP (선택 사항)')
    ex(select, top="parent().par.Sourcetop.eval() or op('%s')" % noise.name)
    source = mk('switchTOP', -800, 300, '사진 / 대체 / Source TOP 선택')
    conn(movie, source, 0)
    conn(noise, source, 1)
    conn(select, source, 2)
    ex(source, index="2 if parent().par.Sourcetop.eval() else "
                     "(1 if (not parent().par.Imagefile.eval() or op('%s').errors()) else 0)" % movie.name)
    analysis_res = mk(['resolutionTOP', 'fitTOP'], -600, 300, '분석 해상도 512x256')
    conn(source, analysis_res)
    setres(analysis_res, 512, 256)
    analysis = mk('nullTOP', -400, 300, '분석용 → numpyArray()')
    conn(analysis_res, analysis)

    # 대시보드: 오버레이(Script TOP) + GLSL 합성
    overlay = mk('scriptTOP', -600, 60, '대시보드 오버레이 (numpy 로 그림)')
    callbacks_dat(overlay, read('callbacks_script_top.py'))
    glsl = mk('glslTOP', -200, 200, '대시보드 합성: 사진 + 스캔선 + 오버레이')
    conn(source, glsl, 0)
    conn(overlay, glsl, 1)
    setres(glsl, R.WIDTH, R.HEIGHT)
    pick(glsl, 'format', ['rgba8fixed'], critical=False)
    callbacks_dat(glsl, read('glsl_dashboard.frag'), parname='pixeldat')
    gx, gy, gw, gh = R.image_rect_gl()
    uniforms = [
        ('uScan', ['parent().par.Scanpos', 0, 0, 0]),
        ('uImgArea', [gx, gy, gw, gh]),
        ('uLine', ['parent().par.Linecolorr', 'parent().par.Linecolorg', 'parent().par.Linecolorb',
                   'parent().par.Lineglow']),
        ('uDim', ['parent().par.Dimahead', 0, 0, 0]),
    ]
    try:
        if glsl.seq.vec.numBlocks < len(uniforms):
            glsl.seq.vec.numBlocks = len(uniforms)
    except Exception as e:
        soft.append('GLSL seq.vec: %s (구버전이면 무시)' % e)
    for i, (uname, vals) in enumerate(uniforms):
        st(glsl, **{'vec%dname' % i: uname})
        for comp, v in zip('xyzw', vals):
            if isinstance(v, str):
                ex(glsl, **{'vec%dvalue%s' % (i, comp): v})
            else:
                st(glsl, **{'vec%dvalue%s' % (i, comp): v})
    out = mk('nullTOP', 0, 200, '최종 대시보드')
    conn(glsl, out)

    # 데이터 → CHOP
    chops = {}
    for j, (key, group, note) in enumerate([
            ('chop_scan', 'scan', '스캔 값 (pos lum hue centroid edge note trig...)'),
            ('chop_feeds', 'feeds', 'API 값 (feed1_price feed1_zs ... iss_lat)'),
            ('chop_bands', 'bands', '대역별 lum r g b peak note (샘플 = 대역)'),
            ('chop_palette', 'palette', '팔레트 r g b weight mix (샘플 = 색)')]):
        s = mk('scriptCHOP', -1000 + j * 200, -300, note)
        callbacks_dat(s, read('callbacks_script_chop.py').replace('{group}', group))
        n = mk('nullCHOP', -1000 + j * 200, -480, group)
        conn(s, n)
        chops[key] = s
        chops[key + '_out'] = n

    # 제어용 DAT
    ext_dat = mk('textDAT', -1000, -700, 'SonifyExt 확장 (td/SonifyExt.py 와 동기화)')
    ext_path = os.path.join(tddir, 'SonifyExt.py').replace('\\', '/')
    ext_dat.text = read('SonifyExt.py')
    st(ext_dat, critical=False, file=ext_path)
    st(ext_dat, critical=False, syncfile=True)
    execute = mk('executeDAT', -800, -700, '매 프레임 Tick')
    execute.text = read('callbacks_execute.py')
    for k in ('start', 'create', 'exit', 'frameend', 'playstatechange', 'devicechange'):
        st(execute, critical=False, **{k: False})
    st(execute, framestart=True)
    st(execute, critical=False, active=True)
    parexec = mk('parameterexecuteDAT', -600, -700, '커스텀 파라미터 → 확장')
    parexec.text = read('callbacks_parexec.py')
    st(parexec, op='..', pars='*')
    st(parexec, critical=False, custom=True, builtin=False, valuechange=True, onpulse=True, active=True)
    oscmap = mk('tableDAT', -400, -700, 'OSC 매핑 표 (AbletonOSC 등) — active 를 1 로')
    oscmap.clear()
    for r in (saved['oscmap'] or [sonify_td.oscmap.HEADER] + sonify_td.oscmap.DEFAULT_ROWS):
        oscmap.appendRow(r)
    status = mk('tableDAT', -200, -700, 'API/OSC 상태 (0.5초마다 갱신)')
    status.clear()
    status.appendRow(['slot', 'status'])

    # UI 패널: 대시보드 뷰 + 파라미터 패널 + 창
    view = mk('containerCOMP', 300, 300, '대시보드 (클릭/드래그 = 스캔 위치 이동)')
    st(view, x=0, y=0, w=R.WIDTH, h=R.HEIGHT, top='../' + out.name)
    params = mk('parameterCOMP', 300, 100, '컨트롤 패널 = 이 컨테이너의 커스텀 파라미터')
    st(params, x=R.WIDTH, y=0, w=320, h=R.HEIGHT, op='..')
    st(params, critical=False, builtin=False, custom=True, pagenames=True)
    window = mk('windowCOMP', 300, -100, 'UI 창 (View 페이지의 Open Window)')
    st(window, winop='..')
    st(window, critical=False, winw=1600, winh=720, title='Sonify')

    root.store('sonify_ops', {
        'movie': movie.name, 'source': source.name, 'analysis': analysis.name, 'overlay': overlay.name,
        'glsl': glsl.name, 'out': out.name, 'view': view.name, 'params': params.name, 'window': window.name,
        'ext': ext_dat.name, 'execute': execute.name, 'parexec': parexec.name, 'oscmap': oscmap.name,
        'status': status.name,
        'chop_scan': chops['chop_scan'].name, 'chop_feeds': chops['chop_feeds'].name,
        'chop_bands': chops['chop_bands'].name, 'chop_palette': chops['chop_palette'].name,
        'out_scan': chops['chop_scan_out'].name, 'out_feeds': chops['chop_feeds_out'].name,
        'out_bands': chops['chop_bands_out'].name, 'out_palette': chops['chop_palette_out'].name,
    })

    # ------------------------------------------------------------------ 확장 연결 (마지막에: 노드가 다 있어야 함)
    ext_expr = "op('./%s').module.SonifyExt(me)" % ext_dat.name
    ext_mode = None
    if hasattr(root.par, 'extension1'):
        st(root, extension1=ext_expr)
        st(root, critical=False, promoteextension1=True, extname1='SonifyExt')
        ext_mode = 'extension1'
    else:
        try:
            root.seq.ext.numBlocks = max(1, root.seq.ext.numBlocks)
            st(root, ext0object=ext_expr)
            st(root, critical=False, ext0promote=True, ext0name='SonifyExt')
            ext_mode = 'seq.ext'
        except Exception as e:
            rep.append('EXT: 확장 파라미터를 찾지 못함 (%s)' % e)
    for pn in ('reinitextensions', 'reinitext'):
        if hasattr(root.par, pn):
            try:
                getattr(root.par, pn).pulse()
            except Exception as e:
                soft.append('REINIT %s' % e)
            break

    if globals().get('SONIFY_OPEN_WINDOW', True):
        try:
            window.par.winopen.pulse()
        except Exception as e:
            soft.append('WINOPEN %s' % e)

    errs = []
    try:
        errs = [(c.name, c.errors()[:160]) for c in root.findChildren(depth=1) if c.errors()]
    except Exception:
        pass

    return {
        'container': root.path,
        'ext': ext_mode,
        'ops': len(root.children),
        'restored_pars': len(saved['pars']),
        'rep': rep,
        'soft': soft,
        'node_errors': errs,
        'next': 'View 페이지 Open Window 로 UI 창. 다음 프레임에 확인: %s.ext.SonifyExt.error, op("%s/%s")' % (
            root.path, root.path, status.name),
    }


try:
    SONIFY_RESULT = build_sonify()
except Exception as _e:
    SONIFY_RESULT = {'fatal': '%s: %s' % (type(_e).__name__, _e), 'trace': traceback.format_exc()}
print(json.dumps(SONIFY_RESULT, ensure_ascii=False, indent=1, default=str))

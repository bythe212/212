"""build_sonify.py + td/*.py 를 TD 모의 환경에서 실제로 실행해 본다."""
import os
import time

import numpy as np
import pytest
from PIL import Image

import mock_td


@pytest.fixture
def td_env():
    td = mock_td.install()
    mock_td.reset()
    yield td
    mock_td.reset()


def run_build(td_dir, **extra):
    ns = {'SONIFY_DIR': td_dir}
    ns.update(extra)
    path = os.path.join(td_dir, 'build_sonify.py')
    with open(path, encoding='utf-8') as fh:
        exec(compile(fh.read(), path, 'exec'), ns)
    return ns['SONIFY_RESULT']


def load_analysis_array(td_dir):
    img = Image.open(os.path.join(td_dir, 'assets', 'deep_field.jpg')).convert('RGBA').resize((512, 256))
    arr = np.asarray(img, np.float32) / 255.0
    return np.ascontiguousarray(arr[::-1])           # TD 규약: 0행 = 아래


def frames(root, names, n, sleep=0.0):
    execute = root.op(names['execute'])
    for k in range(n):
        execute.module.onFrameStart(k)
        if sleep:
            time.sleep(sleep)


def setpar(root, name, value):
    getattr(root.par, name).val = value


def build_offline(td_env, td_dir, port):
    """빌드 후 네트워크 없이 돌도록 시뮬레이션 시세 + 테스트 OSC 포트로 바꾼다."""
    res = run_build(td_dir)
    assert 'fatal' not in res, res.get('trace')
    root = td_env.op(res['container'])
    names = root.fetch('sonify_ops')
    root._parexec = root.op(names['parexec'])        # 모의 parexec 연결 (파라미터 변경 → 확장)
    for i in (1, 2, 3):
        setpar(root, 'Feed%dprovider' % i, 'sim')
    setpar(root, 'Spaceactive', False)
    setpar(root, 'Pollinterval', 0.2)
    setpar(root, 'Oscport', port)
    root.op(names['analysis'])._array = load_analysis_array(td_dir)
    src = root.op(names['source'])
    src.width, src.height = 1024, 512
    return res, root, names


def test_build_structure(td_env, td_dir):
    res = run_build(td_dir)
    assert 'fatal' not in res, res.get('trace')
    assert res['rep'] == [], res['rep']
    assert res['ext'] == 'extension1'
    root = td_env.op(res['container'])
    assert root.path == '/project1/container1' and 'sonify' in root.tags
    assert (root.par.w.val, root.par.h.val) == (1600, 720)
    names = root.fetch('sonify_ops')
    for key, name in names.items():
        assert root.op(name) is not None, key

    # TD 기본 이름 그대로
    assert names['movie'] == 'moviefilein1' and names['parexec'] == 'parexec1' and names['view'] == 'container1'
    assert names['chop_scan'] == 'script2' and names['overlay'] == 'script1'
    # 연결
    glsl = root.op(names['glsl'])
    assert [i.name for i in glsl.inputs] == [names['source'], names['overlay']]
    assert [i.name for i in root.op(names['source']).inputs] == [names['movie'], 'noise1', 'select1']
    assert 'Sourcetop' in root.op(names['source']).par.index.expr
    assert 'uScan' in root.op(glsl.name + '_pixel').text
    assert glsl.par.vec0name.val == 'uScan' and glsl.par.vec0valuex.expr == 'parent().par.Scanpos'
    assert glsl.par.vec1valuey.val == 720 - 532 and glsl.par.vec1valuez.val == 848
    assert glsl.par.vec2valuew.expr == 'parent().par.Lineglow'
    assert (glsl.par.resolutionw.val, glsl.par.resolutionh.val) == (1280, 720)
    assert root.op(names['view']).par.top.val == '../' + names['out']
    assert root.op(names['params']).par.op.val == '..'
    assert root.op(names['parexec']).par.op.val == '..'
    assert root.op(names['window']).par.winopen.pulses == 1
    assert root.op(names['execute']).par.framestart.val is True
    assert root.op(names['ext']).par.file.val.endswith('td/SonifyExt.py')
    assert "GROUP = 'bands'" in root.op(names['chop_bands'] + '_callbacks').text
    # 커스텀 파라미터
    for p in ['Imagefile', 'Scanplay', 'Scanpos', 'Feed1provider', 'Feed3symbol', 'Oschost', 'Libpath',
              'Linecolorr', 'Linecolorb', 'Testosc', 'Openwindow', 'Rootnote', 'Abletonport']:
        assert hasattr(root.par, p), p
    assert 'sim' in root.par.Feed1provider.menuNames
    assert root.par.Imagefile.val.endswith('assets/deep_field.jpg')
    assert root.par.Rootnote.val == '0' and root.par.Rootnote.menuLabels[1] == 'C#'
    assert root.par.Scanpos.clampMin and root.par.Scanpos.max == 1
    # OSC 매핑 표 기본값
    rows = root.op(names['oscmap']).rows()
    assert rows[0][0].val == 'active' and len(rows) == 8
    # 확장이 reinit 펄스로 생성
    ext = root.ext.SonifyExt
    assert ext.error is None and ext.engine is not None and ext.engine.poller is not None


def test_runtime_loop(td_env, td_dir, udp_listener):
    port, recv_all = udp_listener
    res, root, names = build_offline(td_env, td_dir, port)
    ext = root.ext.SonifyExt
    eng = ext.engine
    assert eng.cfg['feed1_provider'] == 'sim' and eng.cfg['osc_port'] == port

    frames(root, names, 80, sleep=0.01)
    assert eng.analyzer.ready and len(eng.analyzer.palette) == 5
    assert eng.pos > 0 and root.par.Scanpos.val == pytest.approx(eng.pos)
    assert all(f.ticks >= 1 for f in eng.feeds)

    # CHOP 출력
    scan = root.op(names['chop_scan'])
    assert {'pos', 'lum', 'centroid', 'note', 'trig'} <= {c.name for c in scan.chans()}
    feeds = root.op(names['chop_feeds'])
    assert {'feed1_price', 'feed2_zs', 'iss_latn'} <= {c.name for c in feeds.chans()}
    bands = root.op(names['chop_bands'])
    assert bands.numSamples == 24 and {'lum', 'r', 'peak', 'note'} <= {c.name for c in bands.chans()}
    pal = root.op(names['chop_palette'])
    assert pal.numSamples == 5
    # 대시보드 오버레이
    ov = root.op(names['overlay'])
    assert ov._array.shape == (720, 1280, 4) and ov._array.dtype == np.uint8
    # 오버레이는 TD 규약(아래→위)으로 뒤집혀 들어간다: 헤더(맨 위)가 배열의 마지막 행 쪽
    assert ov._array[-30:, :400, :3].max() > 100 and ov._array[:10, 16:500, 3].max() == 255
    # 상태 표
    st = root.op(names['status']).rows()
    assert st[1][0].val == 'feed1' and st[1][9].val == 'ok'
    assert st[-2][0].val == 'osc'
    # OSC 가 실제로 나갔는지
    addrs = {a for a, _ in recv_all()}
    assert {'/sonify/scan/lum', '/sonify/scan/bands', '/sonify/feed1/zs', '/sonify/meta/bandnotes'} <= addrs


def test_controls(td_env, td_dir, udp_listener):
    port, recv_all = udp_listener
    res, root, names = build_offline(td_env, td_dir, port)
    ext = root.ext.SonifyExt
    eng = ext.engine
    frames(root, names, 5)

    # Position 슬라이더를 사용자가 움직이면 → seek
    setpar(root, 'Scanplay', False)
    assert not eng.playing
    setpar(root, 'Scanpos', 0.9)
    assert eng.pos == pytest.approx(0.9)
    frames(root, names, 3)
    assert eng.pos == pytest.approx(0.9)            # 정지 상태라 그대로

    # 펄스
    root.par.Scanreset.pulse()
    assert eng.pos == 0.0
    recv_all()
    root.par.Testosc.pulse()
    assert ('/sonify/test', [1, 'sonify']) in recv_all()

    # 설정 → 엔진
    setpar(root, 'Bands', 12)
    setpar(root, 'Scale', 'minor')
    setpar(root, 'Scanmode', 'pingpong')
    assert eng.cfg['bands'] == 12 and len(eng.notes) == 12 and eng.cfg['mode'] == 'pingpong'
    setpar(root, 'Oscprefix', '')
    assert eng._prefix() == ''

    # 이미지 클릭 → 그 위치로 스캔선
    view = root.op(names['view'])
    from sonify_td.render import fit_rect, WIDTH, HEIGHT
    fx, fy, fw, fh = fit_rect(1024, 512)
    target = 0.25
    view.panel.u.val = (fx + target * fw) / WIDTH
    view.panel.v.val = 1.0 - (fy + fh / 2) / HEIGHT
    view.panel.lselect.val = 1
    frames(root, names, 1)
    assert eng.pos == pytest.approx(target, abs=0.002)
    view.panel.lselect.val = 0

    # once 모드가 끝나면 Play 토글이 자동으로 꺼진다
    setpar(root, 'Scanmode', 'once')
    setpar(root, 'Sweepseconds', 0.5)
    setpar(root, 'Scanplay', True)
    frames(root, names, 60, sleep=0.012)
    assert eng.finished and root.par.Scanplay.val is False

    # Source TOP 을 지정하면 매 프레임 다시 분석 (영상 입력)
    setpar(root, 'Sourcetop', root.op(names['out']))
    a = root.op(names['analysis'])
    a._array = np.ascontiguousarray(a._array[:, ::-1])
    v0 = eng.analyzer.version
    frames(root, names, 1)
    assert eng.analyzer.version == v0 + 1
    setpar(root, 'Sourcetop', None)

    # 매핑 표 수정 → 0.5초 안에 반영
    t = root.op(names['oscmap'])
    t._rows[1][0] = '1'
    frames(root, names, 40, sleep=0.015)
    assert eng.mapping[0]['active']

    # Reload 펄스 → 엔진 교체, 이전 엔진의 폴러는 정지
    old = eng
    root.par.Reload.pulse()
    assert ext.engine is not old and old.poller is None and ext.engine.poller is not None


def test_rebuild_preserves_state(td_env, td_dir, udp_listener):
    port, recv_all = udp_listener
    res, root, names = build_offline(td_env, td_dir, port)
    old_engine = root.ext.SonifyExt.engine
    setpar(root, 'Bands', 16)
    setpar(root, 'Feed2symbol', 'XRPUSDT')
    root.op(names['oscmap'])._rows[2][0] = '1'
    root.nodeX, root.nodeY = 300, -150

    res2 = run_build(td_dir)
    assert res2['rep'] == [] and res2['restored_pars'] > 20
    root2 = td_env.op(res2['container'])
    assert root2 is not root and root2.path == root.path and (root2.nodeX, root2.nodeY) == (300, -150)
    assert root2.par.Bands.val == 16 and root2.par.Feed2symbol.val == 'XRPUSDT'
    assert root2.par.Feed1provider.val == 'sim'
    assert root2.op(names['oscmap']).rows()[2][0].val == '1'
    assert old_engine.poller is None                 # 이전 스레드 정리됨
    assert len([c for c in td_env.PROJECT.children if 'sonify' in c.tags]) == 1


def test_user_nodes_untouched(td_env, td_dir):
    mine = td_env.PROJECT.create('containerCOMP')     # 사용자가 먼저 만든 container1
    res = run_build(td_dir)
    assert res['container'] == '/project1/container2'
    run_build(td_dir)                                 # 다시 빌드해도
    assert mine.path == '/project1/container1' and not mine.destroyed
    assert td_env.op('/project1/container2') is not None


def test_bad_dir_reports_fatal(td_env, td_dir, tmp_path):
    res = run_build(td_dir, SONIFY_DIR=str(tmp_path))
    assert 'fatal' in res and '폴더가 없습니다' in res['fatal']


def test_verify_script(td_env, td_dir, udp_listener):
    port, recv_all = udp_listener
    res, root, names = build_offline(td_env, td_dir, port)
    frames(root, names, 30, sleep=0.01)
    ns = {}
    path = os.path.join(td_dir, 'td', 'verify_sonify.py')
    with open(path, encoding='utf-8') as fh:
        exec(compile(fh.read(), path, 'exec'), ns)
    v = ns['SONIFY_VERIFY']
    assert 'fatal' not in v, v
    assert v['ext']['error'] is None and v['ext']['engine']
    assert v['scan']['samples'] == 1 and 'lum' in v['scan']['chans']
    assert v['bands']['samples'] == 24
    assert v['tops']['overlay']['res'] == (1280, 720)
    assert v['engine']['image'] == (512, 256) and len(v['engine']['palette']) == 5
    assert v['status'][0][0] == 'feed1'

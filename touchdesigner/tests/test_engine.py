import numpy as np
import pytest

from sonify_td import SonifyEngine
from sonify_td.oscmap import DEFAULT_ROWS, HEADER, apply, parse_rows


def star_image():
    """검은 바탕에 위쪽 x=0.5 근처 작은 별 하나(2x2 px, TD 규약: 0행 = 아래)."""
    img = np.zeros((64, 128, 3), np.float32)
    img[51:53, 63:65] = 1.0
    return img


def make(**kw):
    kw.setdefault('osc_enabled', False)
    return SonifyEngine(**kw)


def test_loop_pingpong_once():
    e = make(sweep_seconds=10.0)
    e.set_image(star_image())
    for _ in range(60):
        e.tick(0.1)                 # 6초
    assert e.pos == pytest.approx(0.6)
    for _ in range(50):
        e.tick(0.1)                 # +5초 → 1.1 → 0.1 (loop)
    assert e.pos == pytest.approx(0.1, abs=1e-6)

    e = make(sweep_seconds=1.0, mode='pingpong')
    e.set_image(star_image())
    for _ in range(12):
        e.tick(0.1)
    assert e.direction == -1 and e.pos == pytest.approx(0.8, abs=1e-6)

    e = make(sweep_seconds=1.0, mode='once')
    e.set_image(star_image())
    for _ in range(15):
        e.tick(0.1)
    assert e.pos == 1.0 and not e.playing and e.finished
    e.play(True)                    # 끝난 뒤 다시 재생 → 처음부터
    assert e.pos == 0.0 and e.playing


def test_no_advance_without_image_or_when_paused():
    e = make()
    e.tick(0.1)
    assert e.pos == 0.0
    e.set_image(star_image())
    e.play(False)
    e.tick(0.1)
    assert e.pos == 0.0


def test_star_triggers_once_with_hysteresis():
    e = make(sweep_seconds=1.0, bands=16, threshold=0.5, scan_width=1)
    e.set_image(star_image())
    trigs = []
    for _ in range(10):              # 0 → 1 을 프레임당 ~13px 씩 빠르게 훑어도 2px 별을 놓치지 않는다
        e.tick(0.1, now=0)
        trigs += e.frame_trigs
    assert len(trigs) >= 1
    bands = {b for b, n, v in trigs}
    assert bands == {12, 13}                      # 행 51(대역 12), 52(대역 13) = 위쪽 = 높은 음
    assert len(trigs) == len(bands)               # 같은 별에서 대역마다 한 번만
    assert all(n == e.notes[b] for b, n, v in trigs)
    assert all(0 < v <= 1 for b, n, v in trigs)


def test_configure_changes():
    e = make()
    ch = e.configure(bands=12, scale='minor', note_low=48, note_high=72, bogus=1, osc_port='9001')
    assert {'bands', 'scale', 'note_low', 'note_high', 'osc_port'} <= ch
    assert len(e.notes) == 12 and e.notes[0] == 48 and e.notes[-1] == 72
    assert e.configure(bands=12) == set()
    e.configure(feed1_provider='binance', feed1_symbol='btc')
    assert e.feeds[0].symbol == 'BTCUSDT'


def test_ingest_routes_results():
    e = make()
    assert e.ingest({'job': 'feed2', 'ok': True, 'data': {'price': 10.0, 'chg24': 1.0}, 'url': 'u'}, now=1)
    assert e.feeds[1].price == 10.0 and e.feeds[1].ok
    assert not e.ingest({'job': 'feed3', 'ok': False, 'error': 'HTTP 451 (지역 차단)'})
    assert e.feeds[2].error.startswith('HTTP 451')
    assert e.ingest({'job': 'iss', 'ok': True, 'data': {'lat': 1.0, 'lon': 2.0, 'alt': 400.0, 'vel': 27000.0}})
    assert not e.ingest({'job': 'feed1', 'ok': True, 'data': {'price': -1}})
    assert '값 오류' in e.feeds[0].error
    assert not e.ingest({'job': 'nope', 'ok': True})


def test_generic_osc_stream(udp_listener):
    port, recv_all = udp_listener
    e = make(osc_enabled=True, osc_port=port, osc_rate=10.0, osc_mode='generic', bands=8, threshold=0.5)
    e.set_image(star_image())
    e.ingest({'job': 'feed1', 'ok': True, 'data': {'price': 100.0, 'chg24': 1.0}})
    e.tick(0.1)
    got = dict()
    for a, args in recv_all():
        got.setdefault(a, args)
    for addr in ['/sonify/scan/pos', '/sonify/scan/lum', '/sonify/scan/centroid', '/sonify/scan/note',
                 '/sonify/scan/lumn', '/sonify/scan/centroidn', '/sonify/scan/bandsn',
                 '/sonify/scan/rgb', '/sonify/scan/bands', '/sonify/scan/mix', '/sonify/feed1/zs',
                 '/sonify/iss/latn', '/sonify/meta/bandnotes', '/sonify/image/palette', '/sonify/feed1/name',
                 '/sonify/feed1/price']:
        assert addr in got, addr
    assert len(got['/sonify/scan/bands']) == 8
    assert isinstance(got['/sonify/scan/note'][0], int)
    assert got['/sonify/feed1/name'] == ['UPBIT', 'KRW-BTC']
    assert len(got['/sonify/image/palette']) == 3 * 5


def test_osc_rate_and_prefix(udp_listener):
    port, recv_all = udp_listener
    e = make(osc_enabled=True, osc_port=port, osc_rate=10.0, osc_prefix='space/', osc_mode='generic')
    for _ in range(10):
        e.tick(1 / 60.0)            # 1/6 초 → 10Hz 면 1번만
    pos = [a for a, _ in recv_all() if a.endswith('/scan/pos')]
    assert pos == ['/space/scan/pos']


def test_trigger_and_tick_events(udp_listener):
    port, recv_all = udp_listener
    e = make(osc_enabled=True, osc_port=port, osc_mode='generic', bands=16, threshold=0.5, scan_width=1)
    e.set_image(star_image())
    e.seek(64 / 127.0)
    e.ingest({'job': 'feed1', 'ok': True, 'data': {'price': 100.0}})
    e.tick(0.0)
    msgs = recv_all()
    trig = [args for a, args in msgs if a == '/sonify/scan/trig']
    assert trig and all(len(t) == 3 for t in trig)


def test_mapped_mode(udp_listener):
    port, recv_all = udp_listener
    e = make(osc_enabled=True, ableton_port=port, osc_port=1, osc_mode='mapped', osc_rate=60.0)
    rows = [HEADER] + [r[:] for r in DEFAULT_ROWS]
    rows[1][0] = '1'               # scan/lum → device param
    rows[4][0] = '1'               # feed1/zs → track volume
    e.set_mapping_rows(rows)
    assert len(e.mapping) == len(DEFAULT_ROWS) and not e.mapping_errors
    e.tick(1 / 30.0)
    msgs = recv_all()
    addrs = [a for a, _ in msgs]
    assert addrs.count('/live/device/set/parameter/value') == 1
    vol = [args for a, args in msgs if a == '/live/track/set/volume']
    assert vol == [[1, pytest.approx(0.65)]]      # zs=0 → -1..1 의 중간 → 0.45..0.85 의 중간
    e.tick(1 / 30.0)
    assert recv_all() == []                       # 값이 그대로면 다시 보내지 않음(1초 keepalive 전)


def test_mapping_parse_errors():
    rows, errors = parse_rows([['1', 'scan/lum', 'live/no-slash', '', '0', '1', '0', '1'],
                               ['1', 'scan/lum', '/x', '1 2.5 name', '0', '0', '0', '1'],
                               ['1', '/scan/lum', '/x', '', '', '', '', '']])
    assert len(errors) == 2 and len(rows) == 1
    assert rows[0]['source'] == 'scan/lum' and rows[0]['inmax'] == 1.0
    assert apply(rows[0], 2.0) == 1.0 and apply(rows[0], -1) == 0.0
    r, _ = parse_rows([['1', 'a', '/x', '1 2.5 name', '0', '1', '0', '1']])
    assert r[0]['args'] == [1, 2.5, 'name']


def test_channels_groups():
    e = make(bands=6, palette_size=3)
    e.set_image(star_image())
    e.tick(0.1)
    scan = dict(e.channels('scan'))
    assert 'lum' in scan and 'centroid' in scan and 'trig' in scan
    feeds = dict(e.channels('feeds'))
    assert 'feed1_zs' in feeds and 'iss_latn' in feeds
    b = e.channels('bands')
    assert all(len(v) == 6 for v in b.values())
    p = e.channels('palette')
    assert len(p['r']) == 3 and len(p['mix']) == 3


def test_poller_lifecycle_with_sim():
    import time
    e = make(feed1_provider='sim', feed2_provider='sim', feed3_enabled=False, space_enabled=False,
             poll_interval=0.2)
    e.start()
    t0 = time.time()
    while time.time() - t0 < 2.0 and not (e.feeds[0].ticks >= 2 and e.feeds[1].ticks >= 2):
        e.tick(0.05)
        time.sleep(0.05)
    assert e.feeds[0].ticks >= 2 and e.feeds[1].ticks >= 2
    assert e.feeds[2].ticks == 0
    old = e.poller
    for k in range(30):                # 슬라이더 드래그: 매 프레임 설정 변경
        e.configure(poll_interval=0.3 + k * 0.01)
        e.tick(1 / 60.0)
    assert e.poller is old             # 디바운스: 아직 재시작 안 함
    time.sleep(0.45)
    e.tick(1 / 60.0)
    assert e.poller is not old and old._stop.is_set()
    assert e.poller.jobs[0].interval == pytest.approx(0.59)
    e.close()
    assert e.poller is None

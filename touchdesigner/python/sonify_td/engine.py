"""SonifyEngine — 이미지 스캔 + 실시간 피드 + OSC 송신을 한데 묶은 본체.

TD 에 의존하지 않는다. TD 쪽(SonifyExt)은 매 프레임 tick(dt) 을 부르고,
결과(self.scan, self.feeds, self.space)를 CHOP/화면에 옮기기만 한다.
"""
import math
import time
from collections import deque

import numpy as np

from . import music, oscmap
from .feeds import PROVIDERS, ISS_URLS, FeedState, SpaceState, SimSource, parse_iss
from .image_scan import ImageAnalyzer
from .osc import OscSender
from .poller import Job, Poller

NUM_FEEDS = 3

DEFAULTS = {
    # 데이터 (API 3개 + 우주 1개)
    'feed1_enabled': True, 'feed1_provider': 'upbit', 'feed1_symbol': 'KRW-BTC',
    'feed2_enabled': True, 'feed2_provider': 'binance', 'feed2_symbol': 'ETHUSDT',
    'feed3_enabled': True, 'feed3_provider': 'coinbase', 'feed3_symbol': 'SOL-USD',
    'space_enabled': True,
    'poll_interval': 1.0, 'space_interval': 2.0, 'ssl_mode': 'auto', 'window': 60,
    'smoothing': 0.4, 'release': 0.6,
    # 스캔
    'playing': True, 'sweep_seconds': 20.0, 'mode': 'loop',
    'bands': 24, 'scan_width': 3, 'palette_size': 5, 'threshold': 0.55,
    'note_low': 36, 'note_high': 96, 'scale': 'majorpentatonic', 'root': 0,
    # OSC
    'osc_enabled': True, 'osc_host': '127.0.0.1', 'osc_port': 9000, 'osc_rate': 30.0,
    'osc_prefix': '/sonify', 'osc_mode': 'both', 'osc_bundle': False, 'ableton_port': 11000,
}

MODES = ['loop', 'pingpong', 'once']
OSC_MODES = ['generic', 'mapped', 'both']
SSL_MODES = ['auto', 'verify', 'off']

FEED_KEYS = {'feed%d_%s' % (i, k) for i in range(1, NUM_FEEDS + 1) for k in ('enabled', 'provider', 'symbol')}
POLL_KEYS = FEED_KEYS | {'space_enabled', 'poll_interval', 'space_interval', 'ssl_mode', 'window'}
NOTE_KEYS = {'bands', 'note_low', 'note_high', 'scale', 'root'}
INT_KEYS = {'scan/note', 'scan/palidx', 'scan/trigband', 'scan/trignote'}
# 피드 값 중 매 OSC 틱마다 보내는 연속값 (나머지는 새 데이터가 올 때 + 2초마다)
CONTINUOUS_FEED = {'zs': 'z_s', 'norms': 'norm_s', 'moms': 'mom_s', 'act': 'act'}
CONTINUOUS_ISS = ('iss/latn', 'iss/lonn')


def _coerce(key, value):
    d = DEFAULTS[key]
    if isinstance(d, bool):
        return bool(value)
    if isinstance(d, int):
        return int(round(float(value)))
    if isinstance(d, float):
        return float(value)
    return str(value)


class SonifyEngine:
    def __init__(self, **cfg):
        self.cfg = dict(DEFAULTS)
        for k, v in cfg.items():
            if k in DEFAULTS:
                self.cfg[k] = _coerce(k, v)
        self.analyzer = ImageAnalyzer()
        self.feeds = []
        for i in range(1, NUM_FEEDS + 1):
            self.feeds.append(FeedState(i, self.cfg['feed%d_provider' % i], self.cfg['feed%d_symbol' % i],
                                        self.cfg['window']))
        self.space = SpaceState()
        self.pos = 0.0
        self.direction = 1.0
        self.playing = self.cfg['playing']
        self.finished = False
        self.clock = 0.0
        self.notes = []
        self.armed = np.ones(0, dtype=bool)
        self.events = deque(maxlen=128)      # (time, band, note, vel, pos) — 화면 표시용
        self.frame_trigs = []
        self.last_trig = (0, 0, 0.0)
        self.trig_count = 0
        self.peaks = np.zeros(self.cfg['bands'], dtype=np.float32)
        self.mapping = []
        self.mapping_errors = []
        self.poller = None
        self._restart_due = None
        self.osc = OscSender(self.cfg['osc_host'], self.cfg['osc_port'])
        self.live = OscSender(self.cfg['osc_host'], self.cfg['ableton_port'])
        self._osc_acc = 0.0
        self._meta_acc = 1e9                 # 첫 틱에 메타 정보부터 보낸다
        self._recompute_notes()
        self.scan = self.analyzer.analyze(self.pos, self.cfg['bands'], self.cfg['scan_width'], self.cfg['threshold'])

    # ------------------------------------------------------------ 설정

    def configure(self, **kw):
        changed = set()
        for k, v in kw.items():
            if k not in DEFAULTS:
                continue
            try:
                v = _coerce(k, v)
            except (TypeError, ValueError):
                continue
            if self.cfg.get(k) != v:
                self.cfg[k] = v
                changed.add(k)
        if not changed:
            return changed
        if changed & POLL_KEYS:
            for i, f in enumerate(self.feeds, 1):
                f.configure(self.cfg['feed%d_provider' % i], self.cfg['feed%d_symbol' % i], self.cfg['window'])
            if self.poller is not None:
                # 슬라이더를 끄는 동안 매 프레임 스레드를 새로 만들지 않도록 마지막 변경 0.4초 뒤에 재시작
                self._restart_due = time.monotonic() + self.RESTART_DEBOUNCE
        if changed & {'osc_host', 'osc_port', 'ableton_port'}:
            self.osc.configure(self.cfg['osc_host'], self.cfg['osc_port'])
            self.live.configure(self.cfg['osc_host'], self.cfg['ableton_port'])
        if changed & NOTE_KEYS:
            self._recompute_notes()
        if 'palette_size' in changed and self.analyzer.ready:
            self.analyzer.compute_palette(self.cfg['palette_size'])
        if 'playing' in changed:
            self.play(self.cfg['playing'])
        if changed & ({'osc_prefix', 'osc_mode', 'palette_size'} | NOTE_KEYS | FEED_KEYS):
            self._meta_acc = 1e9
        return changed

    def _recompute_notes(self):
        c = self.cfg
        self.notes = music.band_notes(c['bands'], c['note_low'], c['note_high'], c['scale'], c['root'])
        self.armed = np.ones(c['bands'], dtype=bool)

    def set_mapping_rows(self, rows):
        self.mapping, self.mapping_errors = oscmap.parse_rows(rows)

    # ------------------------------------------------------------ 데이터 폴링

    def jobs(self):
        c = self.cfg
        out = []
        for i, f in enumerate(self.feeds, 1):
            if not c['feed%d_enabled' % i]:
                continue
            prov = PROVIDERS[f.provider]
            if prov.key == 'sim':
                src = SimSource(seed=i, start=(100.0, 50.0, 20.0)[(i - 1) % 3])
                out.append(Job('feed%d' % i, [], None, c['poll_interval'], source=src.sample))
            else:
                out.append(Job('feed%d' % i, prov.build_urls(f.symbol), prov.parse, c['poll_interval']))
        if c['space_enabled']:
            out.append(Job('iss', ISS_URLS, parse_iss, c['space_interval']))
        return out

    RESTART_DEBOUNCE = 0.4

    def start(self):
        """폴러를 (다시) 시작한다. 이전 스레드는 멈추라고만 알리고 기다리지 않는다."""
        self._restart_due = None
        if self.poller is not None:
            self.poller.stop()
        self.poller = Poller(self.jobs(), ssl_mode=self.cfg['ssl_mode']).start()

    def flush_restart(self):
        """미뤄 둔 폴러 재시작이 있으면 지금 한다."""
        if self._restart_due is not None and self.poller is not None:
            self.start()

    def stop(self):
        self._restart_due = None
        if self.poller is not None:
            self.poller.stop()
            self.poller = None

    def close(self):
        self.stop()
        self.osc.close()
        self.live.close()

    def ingest(self, result, now=None):
        """폴러 결과 하나를 해당 슬롯에 반영. 새 값이 들어왔으면 True."""
        job = result.get('job', '')
        if job == 'iss':
            st = self.space
        elif job.startswith('feed') and job[4:].isdigit() and 1 <= int(job[4:]) <= NUM_FEEDS:
            st = self.feeds[int(job[4:]) - 1]
        else:
            return False
        st.url = result.get('url') or st.url
        st.latency = result.get('latency')
        st.insecure = bool(result.get('insecure'))
        if result.get('ok'):
            try:
                st.update(result['data'], now)
                return True
            except Exception as e:
                st.fail('값 오류: %s' % e)
        else:
            st.fail(result.get('error') or 'unknown')
        return False

    # ------------------------------------------------------------ 스캔

    def set_image(self, arr, palette=True, stats=True):
        first = not self.analyzer.ready
        self.analyzer.set_image(arr, self.cfg['palette_size'], palette=palette, stats=stats)
        if first or palette:
            self.armed[:] = True
            self._meta_acc = 1e9

    def play(self, on=True):
        on = bool(on)
        if on and self.finished:
            self.pos = 0.0
            self.finished = False
        self.playing = on
        self.cfg['playing'] = on

    def seek(self, x):
        self.pos = min(1.0, max(0.0, float(x)))
        self.finished = False
        self.armed[:] = True

    def reset(self):
        self.pos = 0.0
        self.direction = 1.0
        self.finished = False
        self.armed[:] = True

    def _advance(self, dt):
        step = dt / max(0.1, self.cfg['sweep_seconds'])
        mode = self.cfg['mode']
        if mode == 'pingpong':
            self.pos += step * self.direction
            if self.pos >= 1.0:
                self.pos, self.direction = max(0.0, 2.0 - self.pos), -1.0
                self.armed[:] = True
            elif self.pos <= 0.0:
                self.pos, self.direction = min(1.0, -self.pos), 1.0
                self.armed[:] = True
        elif mode == 'once':
            self.pos += step
            if self.pos >= 1.0:
                self.pos = 1.0
                self.playing = False
                self.cfg['playing'] = False
                self.finished = True
        else:
            self.pos += step
            if self.pos >= 1.0:
                self.pos %= 1.0
                self.armed[:] = True

    def _detect_triggers(self, now):
        bl = self.peaks
        thr = self.cfg['threshold']
        if len(self.armed) != len(bl):
            self.armed = np.ones(len(bl), dtype=bool)
        fire = self.armed & (bl > thr)
        for b in np.nonzero(fire)[0]:
            vel = 0.25 + 0.75 * (float(bl[b]) - thr) / max(1e-3, 1.0 - thr)
            ev = (int(b), int(self.notes[b]) if b < len(self.notes) else 60, float(min(1.0, max(0.0, vel))))
            self.frame_trigs.append(ev)
            self.events.append((now,) + ev + (self.pos,))
            self.last_trig = ev
            self.trig_count += 1
        self.armed &= ~fire
        self.armed |= bl < thr * 0.8   # 히스테리시스: 충분히 어두워져야 다시 장전

    def main_note(self):
        c = self.cfg
        # 이미지별로 편 무게중심(centroidn)을 써서 음역 전체를 오가게 한다
        return music.quantize(c['note_low'] + self.scan['centroidn'] * (c['note_high'] - c['note_low']),
                              c['scale'], c['root'])

    # ------------------------------------------------------------ 프레임

    def tick(self, dt, now=None):
        now = time.time() if now is None else now
        dt = max(0.0, min(float(dt), 0.5))
        self.clock += dt
        self.frame_trigs = []
        prev = self.pos
        if self.playing and self.analyzer.ready:
            self._advance(dt)
        c = self.cfg
        self.scan = self.analyzer.analyze(self.pos, c['bands'], c['scan_width'], c['threshold'])
        if self.analyzer.ready:
            # 이번 프레임에 지나간 구간(되감기/점프면 현재 위치만)의 대역별 최대 밝기
            x0 = prev if abs(self.pos - prev) < 0.25 else self.pos
            self.peaks = self.analyzer.band_peaks(x0, self.pos, c['bands'], c['scan_width'])
            self._detect_triggers(now)
        updates = []
        if self._restart_due is not None and time.monotonic() >= self._restart_due:
            self.flush_restart()
        if self.poller is not None:
            for r in self.poller.drain():
                if self.ingest(r, now):
                    updates.append(r['job'])
        for f in self.feeds:
            f.smooth(dt, c['smoothing'], c['release'])
        if c['osc_enabled']:
            self._send_osc(dt, updates, now)
        return updates

    # ------------------------------------------------------------ 값

    def scan_values(self):
        s = self.scan
        trig = self.last_trig
        return [
            ('scan/pos', self.pos), ('scan/lum', s['lum']), ('scan/r', s['r']), ('scan/g', s['g']),
            ('scan/b', s['b']), ('scan/hue', s['hue']), ('scan/sat', s['sat']),
            ('scan/centroid', s['centroid']), ('scan/spread', s['spread']), ('scan/peak', s['peak']),
            ('scan/contrast', s['contrast']), ('scan/edge', s['edge']), ('scan/density', s['density']),
            ('scan/lumn', s['lumn']), ('scan/centroidn', s['centroidn']), ('scan/edgen', s['edgen']),
            ('scan/satn', s['satn']), ('scan/contrastn', s['contrastn']),
            ('scan/note', float(self.main_note())), ('scan/palidx', float(s['palidx'])),
            ('scan/playing', 1.0 if self.playing else 0.0),
            ('scan/trig', float(len(self.frame_trigs))), ('scan/trigband', float(trig[0])),
            ('scan/trignote', float(trig[1])), ('scan/trigvel', float(trig[2])),
        ]

    def values(self, now=None):
        out = self.scan_values()
        for i, f in enumerate(self.feeds, 1):
            out += f.values('feed%d' % i, now)
        out += self.space.values(now)
        return out

    def channels(self, group, now=None):
        """TD Script CHOP 용: [(채널이름, 값)] 또는 {채널이름: [샘플...]}."""
        if group == 'scan':
            return [(k[5:], v) for k, v in self.scan_values()]
        if group == 'feeds':
            out = []
            for i, f in enumerate(self.feeds, 1):
                out += f.values('feed%d' % i, now)
            out += self.space.values(now)
            return [(k.replace('/', '_'), v) for k, v in out]
        if group == 'bands':
            s = self.scan
            n = len(s['bands'])
            return {
                'lum': [float(v) for v in s['bands']],
                'lumn': [float(v) for v in s['bandsn']],
                'r': [float(v) for v in s['band_rgb'][:, 0]],
                'g': [float(v) for v in s['band_rgb'][:, 1]],
                'b': [float(v) for v in s['band_rgb'][:, 2]],
                'peak': [float(v) for v in self.peaks[:n]] + [0.0] * max(0, n - len(self.peaks)),
                'note': [float(v) for v in (self.notes + [0] * n)[:n]],
                'armed': [1.0 if a else 0.0 for a in self.armed[:n]] + [0.0] * max(0, n - len(self.armed)),
            }
        if group == 'palette':
            a = self.analyzer
            k = len(a.palette)
            mix = self.scan['mix']
            return {
                'r': [float(v) for v in a.palette[:, 0]] if k else [],
                'g': [float(v) for v in a.palette[:, 1]] if k else [],
                'b': [float(v) for v in a.palette[:, 2]] if k else [],
                'weight': [float(v) for v in a.weights],
                'mix': [float(v) for v in mix[:k]] + [0.0] * max(0, k - len(mix)),
            }
        raise KeyError(group)

    # ------------------------------------------------------------ OSC

    def _prefix(self):
        p = '/' + self.cfg['osc_prefix'].strip().strip('/')
        return '' if p == '/' else p

    def _send_osc(self, dt, updates, now):
        c = self.cfg
        mode = c['osc_mode']
        generic = mode in ('generic', 'both')
        mapped = mode in ('mapped', 'both')
        P = self._prefix()
        msgs = []

        if generic:
            for band, note, vel in self.frame_trigs:
                msgs.append((P + '/scan/trig', [band, note, vel]))
            for job in updates:
                if job == 'iss':
                    msgs += [(P + '/' + k, [v]) for k, v in self.space.values(now)]
                else:
                    f = self.feeds[int(job[4:]) - 1]
                    msgs.append((P + '/%s/tick' % job, [f.up, f.ret, f.price]))
                    msgs += [(P + '/' + k, [v]) for k, v in f.values(job, now)]

        period = 1.0 / max(0.5, c['osc_rate'])
        self._osc_acc += dt
        if self._osc_acc >= period:
            self._osc_acc = 0.0 if self._osc_acc > 2 * period else self._osc_acc - period
            vals = self.values(now)
            if generic:
                s = self.scan
                for k, v in self.scan_values():
                    msgs.append((P + '/' + k, [int(v) if k in INT_KEYS else v]))
                msgs.append((P + '/scan/rgb', [s['r'], s['g'], s['b']]))
                msgs.append((P + '/scan/bands', [float(v) for v in s['bands']]))
                msgs.append((P + '/scan/bandsn', [float(v) for v in s['bandsn']]))
                if len(s['mix']):
                    msgs.append((P + '/scan/mix', [float(v) for v in s['mix']]))
                for i in range(1, NUM_FEEDS + 1):
                    for k, attr in CONTINUOUS_FEED.items():
                        msgs.append((P + '/feed%d/%s' % (i, k), [getattr(self.feeds[i - 1], attr)]))
                d = dict(vals)
                for k in CONTINUOUS_ISS:
                    msgs.append((P + '/' + k, [d[k]]))
            if mapped and self.mapping:
                self._send_mapped(dict(vals))

        self._meta_acc += dt
        if generic and self._meta_acc >= 2.0:
            self._meta_acc = 0.0
            msgs.append((P + '/meta/bandnotes', list(self.notes)))
            a = self.analyzer
            if len(a.palette):
                msgs.append((P + '/image/palette', [float(v) for v in a.palette.ravel()]))
                msgs.append((P + '/image/weights', [float(v) for v in a.weights]))
            for i, f in enumerate(self.feeds, 1):
                msgs.append((P + '/feed%d/name' % i, [f.label, f.symbol]))
                msgs += [(P + '/' + k, [v]) for k, v in f.values('feed%d' % i, now)]
            msgs += [(P + '/' + k, [v]) for k, v in self.space.values(now)]

        if msgs:
            self.osc.send_many(msgs, bundle=c['osc_bundle'])

    def _send_mapped(self, vals):
        msgs = []
        for row in self.mapping:
            if not row['active']:
                continue
            v = vals.get(row['source'])
            if v is None or not math.isfinite(v):
                continue
            out = oscmap.apply(row, v)
            last = row.get('_last')
            if last is not None and abs(out - last) < 1e-4 and self.clock - row.get('_t', 0.0) < 1.0:
                continue
            row['_last'] = out
            row['_t'] = self.clock
            msgs.append((row['address'], row['args'] + [out]))
        if msgs:
            self.live.send_many(msgs)

    def osc_test(self):
        P = self._prefix()
        self.osc.send(P + '/test', 1, 'sonify')
        self.live.send('/live/test')

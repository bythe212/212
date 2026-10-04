"""SonifyExt — Sonify 컨테이너의 TouchDesigner 확장(Extension).

컨테이너의 커스텀 파라미터(컨트롤) ↔ sonify_td 엔진(순수 파이썬)을 잇는다.
  - Execute DAT 이 매 프레임 Tick() 을 부른다.
  - Parameter Execute DAT 이 파라미터 변경/펄스를 OnParChange()/OnPulse() 로 넘긴다.
  - Script CHOP 4개가 FillChop(), Script TOP 하나가 RenderOverlay() 를 부른다.
이 파일은 repo 의 touchdesigner/td/SonifyExt.py 와 동기화(Sync to File)되어 있다.
"""
import os
import sys
import time
import traceback

import numpy as np

_REGISTRY = '_sonify_td_engines'   # 확장이 다시 초기화돼도 이전 엔진(스레드)을 확실히 끄기 위한 전역 보관소

# 커스텀 파라미터 이름 → 엔진 설정 키
PAR_MAP = {
    'Feed1active': 'feed1_enabled', 'Feed1provider': 'feed1_provider', 'Feed1symbol': 'feed1_symbol',
    'Feed2active': 'feed2_enabled', 'Feed2provider': 'feed2_provider', 'Feed2symbol': 'feed2_symbol',
    'Feed3active': 'feed3_enabled', 'Feed3provider': 'feed3_provider', 'Feed3symbol': 'feed3_symbol',
    'Spaceactive': 'space_enabled', 'Pollinterval': 'poll_interval', 'Spaceinterval': 'space_interval',
    'Sslmode': 'ssl_mode', 'Window': 'window', 'Smoothing': 'smoothing', 'Release': 'release',
    'Scanplay': 'playing', 'Sweepseconds': 'sweep_seconds', 'Scanmode': 'mode', 'Bands': 'bands',
    'Scanwidth': 'scan_width', 'Palettesize': 'palette_size', 'Threshold': 'threshold',
    'Notelow': 'note_low', 'Notehigh': 'note_high', 'Scale': 'scale', 'Rootnote': 'root',
    'Oscactive': 'osc_enabled', 'Oschost': 'osc_host', 'Oscport': 'osc_port', 'Oscrate': 'osc_rate',
    'Oscprefix': 'osc_prefix', 'Oscmode': 'osc_mode', 'Oscbundle': 'osc_bundle', 'Abletonport': 'ableton_port',
}


def _val(pv):
    """PanelValue/Par → float."""
    return float(getattr(pv, 'val', pv))


class SonifyExt:
    def __init__(self, ownerComp):
        self.ownerComp = ownerComp
        self.engine = None
        self.dash = None
        self.lib = None
        self.error = None
        self._last = None
        self._frame = 0
        self._fps = 60.0
        self._written_pos = None
        self._img_sig = None
        self._img_res = (0, 0)
        self._map_text = None
        self._overlay_acc = 1e9
        self._status_acc = 1e9
        self._log_t = {}
        self.Load()

    # ------------------------------------------------------------ 수명

    def Load(self):
        """sonify_td 모듈을 (다시) 불러오고 엔진을 새로 만든다. Setup 페이지의 Reload 펄스."""
        self._shutdown()
        try:
            lib = self._par('Libpath', '')
            if lib and os.path.isdir(lib) and lib not in sys.path:
                sys.path.insert(0, lib)
            import sonify_td
            self.lib = sonify_td.reload_all()
            reg = getattr(sys, _REGISTRY, None)
            if reg is None:
                reg = {}
                setattr(sys, _REGISTRY, reg)
            old = reg.pop(self.ownerComp.path, None)
            if old is not None:
                old.close()
            self.engine = self.lib.SonifyEngine(**self._config())
            reg[self.ownerComp.path] = self.engine
            self.dash = self.lib.render.Dashboard()
            self._img_sig = None
            self._map_text = None
            self.engine.start()
            self.error = None
            print('[sonify] 엔진 시작 (sonify_td %s, %s)' % (self.lib.__version__, os.path.dirname(self.lib.__file__)))
        except Exception as e:
            self.engine = None
            self.error = '%s: %s' % (type(e).__name__, e)
            print('[sonify] 로드 실패:', self.error)
            print('[sonify] Setup 페이지의 Libpath 가 repo 의 touchdesigner/python 폴더인지 확인하세요.')
            traceback.print_exc()

    def _shutdown(self):
        if self.engine is not None:
            try:
                self.engine.close()
            except Exception:
                pass
            reg = getattr(sys, _REGISTRY, {})
            if reg.get(self.ownerComp.path) is self.engine:
                reg.pop(self.ownerComp.path, None)
        self.engine = None

    def onDestroyTD(self):
        # 확장이 다시 초기화되거나 컨테이너가 지워질 때 TD 가 부른다 → 폴링 스레드/소켓 정리
        self._shutdown()

    # ------------------------------------------------------------ 도우미

    def _par(self, name, default=None):
        p = getattr(self.ownerComp.par, name, None)
        if p is None:
            return default
        try:
            return p.eval()
        except Exception:
            return default

    def _op(self, key):
        name = self.ownerComp.fetch('sonify_ops', {}, search=False).get(key)
        return self.ownerComp.op(name) if name else None

    def _log(self, key, msg, every=5.0):
        t = time.time()
        if t - self._log_t.get(key, 0) >= every:
            self._log_t[key] = t
            print('[sonify]', msg)

    def _config(self):
        cfg = {}
        for pname, key in PAR_MAP.items():
            v = self._par(pname)
            if v is None:
                continue
            if key == 'osc_prefix' and not str(v).strip():
                v = '/'
            cfg[key] = v
        return cfg

    # ------------------------------------------------------------ 파라미터

    def OnParChange(self, par):
        if self.engine is None:
            if par.name == 'Libpath':
                self.Load()
            return
        name = par.name
        if name == 'Scanpos':
            v = float(par.eval())
            if self._written_pos is not None and abs(v - self._written_pos) < 1e-6:
                return                               # 우리가 쓴 값 → 무시
            self.engine.seek(v)
        elif name == 'Libpath':
            self.Load()
        elif name in ('Imagefile', 'Livesource', 'Sourcetop'):
            self._img_sig = None
        elif name in PAR_MAP:
            self.engine.configure(**self._config())

    def OnPulse(self, par):
        name = par.name
        if name == 'Reload':
            self.Load()
            return
        if name == 'Openwindow' or name == 'Closewindow':
            w = self._op('window')
            if w is not None:
                getattr(w.par, 'winopen' if name == 'Openwindow' else 'winclose').pulse()
            return
        if self.engine is None:
            return
        if name == 'Scanreset':
            self.engine.reset()
        elif name == 'Reloadimage':
            mf = self._op('movie')
            if mf is not None and hasattr(mf.par, 'reloadpulse'):
                mf.par.reloadpulse.pulse()
            self._img_sig = None
        elif name == 'Reconnect':
            self.engine.start()
        elif name == 'Resetfeeds':
            for f in self.engine.feeds:
                f.reset()
            self.engine.space.reset()
        elif name == 'Testosc':
            self.engine.osc_test()
            print('[sonify] OSC 테스트 전송: %s/test → %s:%s, /live/test → %s:%s' % (
                self.engine._prefix(), self.engine.cfg['osc_host'], self.engine.cfg['osc_port'],
                self.engine.cfg['osc_host'], self.engine.cfg['ableton_port']))

    # ------------------------------------------------------------ 프레임

    def Tick(self):
        if self.engine is None:
            return
        now = time.perf_counter()
        dt = 1.0 / 60.0 if self._last is None else now - self._last
        self._last = now
        if dt > 0:
            self._fps += (1.0 / dt - self._fps) * 0.05
        self._frame += 1
        try:
            self._refresh_image()
            self._poll_click()
            self.engine.tick(dt)
            self._sync_pars()
            self._cook_outputs(dt)
        except Exception as e:
            self._log('tick', 'Tick 오류: %s: %s\n%s' % (type(e).__name__, e, traceback.format_exc()))

    def _refresh_image(self):
        live = bool(self._par('Livesource', False)) or bool(self._par('Sourcetop', None))
        every = 1 if live else 20
        if self._img_sig is not None and self._frame % every:
            return
        top = self._op('analysis')
        if top is None:
            return
        try:
            arr = top.numpyArray(delayed=live)
        except Exception as e:
            self._log('img', 'numpyArray 실패: %s' % e)
            return
        if arr is None or getattr(arr, 'size', 0) == 0:
            return
        sig = (arr.shape, round(float(arr[::7, ::7, :3].sum()), 2))
        if sig == self._img_sig:
            return
        self._img_sig = sig
        # 영상 입력이면 팔레트(k-means)는 2초마다, 정규화 범위는 0.5초마다만 다시 계산
        ready = self.engine.analyzer.ready
        palette = (not live) or self._frame % 120 == 0 or not ready
        stats = (not live) or self._frame % 30 == 0 or not ready
        self.engine.set_image(arr, palette=palette, stats=stats)
        src = self._op('source')
        if src is not None:
            self._img_res = (int(src.width), int(src.height))

    def _poll_click(self):
        """이미지 위를 클릭/드래그하면 그 위치로 스캔선을 옮긴다."""
        view = self._op('view')
        if view is None:
            return
        try:
            if not _val(view.panel.lselect):
                return
            u, v = _val(view.panel.u), _val(view.panel.v)
        except Exception:
            return
        R = self.lib.render
        px, py = u * R.WIDTH, (1.0 - v) * R.HEIGHT
        w, h = self._img_res if self._img_res[0] else self.engine.analyzer.size
        fx, fy, fw, fh = R.fit_rect(w, h)
        if fx <= px <= fx + fw and fy <= py <= fy + fh and fw > 0:
            self.engine.seek((px - fx) / fw)

    def _sync_pars(self):
        p = getattr(self.ownerComp.par, 'Scanpos', None)
        if p is not None and abs(float(p.eval()) - self.engine.pos) > 1e-6:
            self._written_pos = self.engine.pos
            p.val = self.engine.pos
        play = getattr(self.ownerComp.par, 'Scanplay', None)
        if play is not None and bool(play.eval()) != self.engine.playing:
            play.val = self.engine.playing

    def _cook_outputs(self, dt):
        for key in ('chop_scan', 'chop_feeds', 'chop_bands', 'chop_palette'):
            o = self._op(key)
            if o is not None:
                o.cook(force=True)
        rate = max(1.0, float(self._par('Uirate', 30.0) or 30.0))
        self._overlay_acc += dt
        if self._overlay_acc >= 1.0 / rate:
            self._overlay_acc = 0.0
            o = self._op('overlay')
            if o is not None:
                o.cook(force=True)
        self._status_acc += dt
        if self._status_acc >= 0.5:
            self._status_acc = 0.0
            self._write_status()
            self._read_mapping()

    # ------------------------------------------------------------ 출력

    def FillChop(self, scriptOp, group):
        scriptOp.clear()
        if self.engine is None:
            return
        ch = self.engine.channels(group)
        if isinstance(ch, dict):
            n = max([len(v) for v in ch.values()] + [1])
            scriptOp.numSamples = n
            for name, vals in ch.items():
                c = scriptOp.appendChan(name)
                for i, v in enumerate(vals):
                    c[i] = v
        else:
            scriptOp.numSamples = 1
            for name, v in ch:
                scriptOp.appendChan(name)[0] = float(v)

    def RenderOverlay(self, scriptOp):
        if self.engine is None or self.dash is None:
            return
        src = self._par('Sourcetop', None)
        name = getattr(src, 'name', None) or os.path.basename(str(self._par('Imagefile', '') or ''))
        info = {'image_res': self._img_res, 'fps': self._fps, 'image_name': name.upper()}
        buf = self.dash.render(self.engine, info)
        if self._par('Overlayflip', True):
            buf = buf[::-1]                          # numpy(위→아래) → TD(아래→위)
        scriptOp.copyNumpyArray(np.ascontiguousarray(buf))

    def _write_status(self):
        t = self._op('status')
        if t is None:
            return
        e = self.engine
        rows = [['slot', 'provider', 'symbol', 'price', 'chg24', 'z', 'mom', 'vol_bp', 'age_s', 'status', 'url']]
        for i, f in enumerate(e.feeds, 1):
            enabled = e.cfg['feed%d_enabled' % i]
            st = 'off' if not enabled else (f.error or ('ok' if f.ok else 'waiting'))
            if f.insecure:
                st += ' (no-ssl-verify)'
            rows.append(['feed%d' % i, f.provider, f.symbol, '%.8g' % f.price if f.ticks else '',
                         '%.3f' % f.chg24, '%.3f' % f.z, '%.3f' % f.mom, '%.2f' % f.vol,
                         '%.1f' % f.age() if f.ticks else '', st, f.url or ''])
        sp = e.space
        st = 'off' if not e.cfg['space_enabled'] else (sp.error or ('ok' if sp.ok else 'waiting'))
        rows.append(['iss', 'wheretheiss', 'ISS', '%.4f,%.4f' % (sp.lat, sp.lon), '', '', '', '',
                     '%.1f' % sp.age() if sp.updated_at else '', st, sp.url or ''])
        osc = e.osc
        rows.append(['osc', '%s:%s' % (osc.host, osc.port), e.cfg['osc_mode'], 'sent %d' % osc.sent, '', '', '', '',
                     '', osc.last_error or ('ok' if e.cfg['osc_enabled'] else 'off'), ''])
        live = e.live
        rows.append(['ableton', '%s:%s' % (live.host, live.port), '%d rows' % len(e.mapping),
                     'sent %d' % live.sent, '', '', '', '', '',
                     '; '.join(e.mapping_errors) or live.last_error or 'ok', ''])
        t.clear()
        for r in rows:
            t.appendRow(r)

    def _read_mapping(self):
        t = self._op('oscmap')
        if t is None:
            return
        text = t.text
        if text == self._map_text:
            return
        self._map_text = text
        rows = [[c.val for c in r] for r in t.rows()]
        self.engine.set_mapping_rows(rows)
        if self.engine.mapping_errors:
            print('[sonify] OSC 매핑 표 오류:', '; '.join(self.engine.mapping_errors))

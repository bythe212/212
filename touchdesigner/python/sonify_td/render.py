"""대시보드 오버레이 렌더러 (numpy → TD Script TOP).

화면 구성 (1280x720, 위→아래 좌표):
  ┌ 헤더 ───────────────────────────────────────────────────┐
  │ 이미지 영역(GLSL 이 사진+스캔선을 그림)   │ 피드 1 카드      │
  │                                            │ 피드 2 카드      │
  │ └ 스캔 수치 줄                             │ 피드 3 카드      │
  ├ 대역(밴드) 미터            │ 팔레트       │ ISS 카드(지도)   │
  └─────────────────────────────────────────────────────────┘
이미지 영역은 알파 0 으로 비워 두고, GLSL TOP 이 사진을 그 자리에 깐 뒤 이 오버레이를 덮는다.
"""
import math
import time

import numpy as np

from . import music
from .font import draw_text, text_width

WIDTH, HEIGHT = 1280, 720
HEADER = (0, 0, WIDTH, 44)
IMAGE = (16, 52, 848, 480)          # x, y(위), w, h
BANDS = (16, 544, 520, 160)
PALETTE = (548, 544, 316, 160)
FEED_X, FEED_W, FEED_H = 880, 384, 146
FEED_Y = (52, 206, 360)
ISS = (880, 514, 384, 190)

BG = (10, 11, 16, 255)
PANEL = (17, 19, 27, 255)
BORDER = (44, 48, 64, 255)
TEXT = (226, 230, 238)
DIM = (128, 136, 152)
FAINT = (64, 70, 86)
ACCENT = (255, 196, 90)
UP = (255, 86, 86)       # 한국식: 상승 빨강
DOWN = (86, 142, 255)    # 하락 파랑
GOOD = (96, 214, 140)
BAD = (255, 96, 96)


def image_rect_gl():
    """GLSL 유니폼용: 아래 기준 (x, y, w, h)."""
    x, y, w, h = IMAGE
    return (x, HEIGHT - (y + h), w, h)


def fit_rect(img_w, img_h, area=IMAGE):
    """이미지 영역 안에 비율 유지로 맞춘 사진의 실제 위치 (x, y, w, h), 위 기준. GLSL 과 같은 계산."""
    ax, ay, aw, ah = area
    img_w, img_h = max(1, img_w), max(1, img_h)
    s = min(aw / img_w, ah / img_h)
    w, h = img_w * s, img_h * s
    return ax + (aw - w) / 2.0, ay + (ah - h) / 2.0, w, h


def fmt_price(p):
    if not math.isfinite(p) or p <= 0:
        return '--'
    if p >= 1000:
        return '{:,.0f}'.format(p)
    if p >= 1:
        return '{:,.2f}'.format(p)
    return '{:.5f}'.format(p)


def _c(color, alpha=255):
    c = tuple(int(v) for v in color[:3])
    return c + (int(alpha),)


class Canvas:
    def __init__(self, w, h):
        self.buf = np.zeros((h, w, 4), dtype=np.uint8)

    def rect(self, x, y, w, h, color):
        b = self.buf
        x0, y0 = max(0, int(x)), max(0, int(y))
        x1, y1 = min(b.shape[1], int(x + w)), min(b.shape[0], int(y + h))
        if x1 > x0 and y1 > y0:
            b[y0:y1, x0:x1] = color

    def frame(self, x, y, w, h, color, t=1):
        self.rect(x, y, w, t, color)
        self.rect(x, y + h - t, w, t, color)
        self.rect(x, y, t, h, color)
        self.rect(x + w - t, y, t, h, color)

    def text(self, x, y, s, color, scale=1, align='left'):
        return draw_text(self.buf, x, y, s, _c(color), scale, align)

    def polyline(self, xs, ys, color, thick=1):
        """x 가 1px 씩 증가하는 선(스파크라인). 인접 점 사이 세로로 채운다."""
        prev = None
        for x, y in zip(xs, ys):
            if prev is not None:
                y0, y1 = sorted((prev, y))
                self.rect(x, y0, thick, y1 - y0 + thick, color)
            else:
                self.rect(x, y, thick, thick, color)
            prev = y

    def hbar(self, x, y, w, h, value, color, centered=False):
        """value: centered 면 -1..1 (가운데 기준), 아니면 0..1."""
        self.rect(x, y, w, h, _c(FAINT, 255))
        if centered:
            mid = x + w // 2
            v = max(-1.0, min(1.0, value))
            n = int(round(abs(v) * (w // 2)))
            if v >= 0:
                self.rect(mid, y, n, h, color)
            else:
                self.rect(mid - n, y, n, h, color)
            self.rect(mid, y - 1, 1, h + 2, _c(DIM))
        else:
            self.rect(x, y, int(round(max(0.0, min(1.0, value)) * w)), h, color)


def _vivid(rgb, lum=None):
    """밴드 평균색은 어둡고 탁하다 → 채도를 살려서 표시."""
    rgb = np.asarray(rgb, dtype=np.float32)
    m = float(rgb.max())
    base = rgb / m if m > 1e-4 else np.array([0.5, 0.5, 0.5], np.float32)
    k = 0.35 + 0.65 * (m if lum is None else min(1.0, lum * 1.6))
    return tuple(int(v) for v in np.clip(base * k * 255.0 + 30, 0, 255)) + (255,)


class Dashboard:
    def __init__(self, width=WIDTH, height=HEIGHT):
        self.width, self.height = width, height
        self.canvas = Canvas(width, height)
        self.static = None

    def _build_static(self):
        cv = Canvas(self.width, self.height)
        cv.rect(0, 0, self.width, self.height, BG)
        x, y, w, h = IMAGE
        cv.rect(x, y, w, h, (0, 0, 0, 0))                 # 사진 자리: 투명
        cv.frame(x - 1, y - 1, w + 2, h + 2, BORDER)
        for (px, py, pw, ph) in (BANDS, PALETTE, ISS) + tuple((FEED_X, fy, FEED_W, FEED_H) for fy in FEED_Y):
            cv.rect(px, py, pw, ph, PANEL)
            cv.frame(px, py, pw, ph, BORDER)
        cv.rect(0, HEADER[3] - 1, self.width, 1, BORDER)
        # ISS 지도 격자 (정거원통도법)
        mx, my, mw, mh = self.iss_map_rect()
        cv.rect(mx, my, mw, mh, (12, 16, 26, 255))
        for lat in (-60, -30, 0, 30, 60):
            yy = my + int((90 - lat) / 180.0 * (mh - 1))
            cv.rect(mx, yy, mw, 1, _c(FAINT if lat else DIM, 255))
        for lon in range(-180, 181, 60):
            xx = mx + int((lon + 180) / 360.0 * (mw - 1))
            cv.rect(xx, my, 1, mh, _c(FAINT if lon else DIM, 255))
        # 궤도 경사각 한계(±51.6°)
        for lat in (51.6, -51.6):
            yy = my + int((90 - lat) / 180.0 * (mh - 1))
            for xx in range(mx, mx + mw, 4):
                cv.rect(xx, yy, 2, 1, _c((70, 60, 40)))
        cv.frame(mx - 1, my - 1, mw + 2, mh + 2, BORDER)
        self.static = cv.buf

    @staticmethod
    def iss_map_rect():
        x, y, w, h = ISS
        return x + 10, y + 34, 228, 114

    # ------------------------------------------------------------------

    def render(self, eng, info=None, now=None):
        """eng: SonifyEngine. info: TD 쪽 부가 정보 {'image_res': (w, h), 'fps': float, 'image_name': str}.
        위→아래 좌표의 (H, W, 4) uint8 을 돌려준다(TD 로 보낼 때 뒤집는 건 호출 측 몫)."""
        info = info or {}
        now = time.time() if now is None else now
        if self.static is None:
            self._build_static()
        cv = self.canvas
        np.copyto(cv.buf, self.static)
        self._header(cv, eng, info)
        self._image_overlay(cv, eng, info, now)
        self._bands(cv, eng, now)
        self._palette(cv, eng)
        for i, f in enumerate(eng.feeds):
            self._feed(cv, eng, i, f, FEED_Y[i], now)
        self._iss(cv, eng, now)
        return cv.buf

    def _header(self, cv, eng, info):
        x = 16 + cv.text(16, 12, 'SONIFY', ACCENT, 3) + 14
        cv.text(x, 18, 'IMAGE SCAN + LIVE DATA', DIM, 2)
        c = eng.cfg
        state = '▶ PLAY' if eng.playing else '■ STOP'
        mid = '%s  %s  %dS  BANDS %d' % (state, c['mode'].upper(), round(c['sweep_seconds']), c['bands'])
        cv.text(560, 18, mid, TEXT if eng.playing else DIM, 2)
        if c['osc_enabled']:
            ok = eng.osc.ok
            s = 'OSC %s:%d  TX %d' % (c['osc_host'], c['osc_port'], eng.osc.sent)
            col = GOOD if ok else BAD
        else:
            s, col = 'OSC OFF', DIM
        x1 = WIDTH - 16
        w = cv.text(x1, 18, s, TEXT, 2, align='right')
        cv.text(x1 - w - 8, 18, '■', col, 2, align='right')
        fps = info.get('fps')
        if fps:
            cv.text(x1, 4, '%.0f FPS' % fps, FAINT, 1, align='right')

    def _image_overlay(self, cv, eng, info, now):
        ix, iy, iw, ih = IMAGE
        a = eng.analyzer
        if not a.ready:
            cv.text(ix + iw // 2, iy + ih // 2 - 7, 'NO IMAGE - SET IMAGEFILE', DIM, 2, align='center')
            return
        res = info.get('image_res') or a.size
        fx, fy, fw, fh = fit_rect(res[0], res[1])
        lx = int(round(fx + eng.pos * fw))
        s = eng.scan
        n = len(s['bands'])
        # 스캔선 옆 '빗살': 각 대역의 밝기를 가로 막대로 (아래 대역 = 아래)
        bh = fh / max(1, n)
        for b in range(n):
            lum = float(s['bands'][b])
            yb = int(round(fy + fh - (b + 1) * bh))
            length = int(4 + lum * 46)
            cv.rect(lx + 3, yb + max(1, int(bh * 0.35)), length, max(1, int(bh * 0.3)),
                    _vivid(s['band_rgb'][b], lum)[:3] + (210,))
        # 최근 트리거(별을 지날 때) 표시
        for (t, band, note, vel, pos) in eng.events:
            age = now - t
            if age > 0.8 or age < 0:
                continue
            fade = 1.0 - age / 0.8
            ex = int(round(fx + pos * fw))
            ey = int(round(fy + fh - (band + 0.5) * bh))
            r = int(4 + 8 * vel * (1.0 + age))
            col = ACCENT + (int(255 * fade),)
            cv.frame(ex - r, ey - r, 2 * r + 1, 2 * r + 1, col)
        # 아래쪽 수치 줄 (반투명)
        sy = iy + ih - 22
        cv.rect(ix, sy, iw, 22, (0, 0, 0, 170))
        line = 'POS %.3f  LUM %.2f  HUE %.2f  SAT %.2f  CEN %.2f  EDGE %.2f  DENS %.2f  NOTE %s' % (
            eng.pos, s['lum'], s['hue'], s['sat'], s['centroid'], s['edge'], s['density'],
            music.note_name(eng.main_note()))
        cv.text(ix + 8, sy + 4, line, TEXT, 2) if text_width(line, 2) < iw - 16 else cv.text(ix + 8, sy + 8, line, TEXT, 1)
        name = info.get('image_name')
        if name:
            cv.rect(ix, iy, min(iw, text_width(name, 1) + 16), 16, (0, 0, 0, 150))
            cv.text(ix + 8, iy + 5, name, DIM, 1)

    def _bands(self, cv, eng, now):
        x, y, w, h = BANDS
        s = eng.scan
        n = len(s['bands'])
        notes = eng.notes
        title = 'BANDS %d' % n
        if notes:
            title += '  %s-%s  %s' % (music.note_name(notes[0]), music.note_name(notes[-1]), eng.cfg['scale'].upper())
        cv.text(x + 10, y + 10, title, DIM, 1)
        cv.text(x + w - 10, y + 10, 'TRIG %d' % eng.trig_count, DIM, 1, align='right')
        bx, by, bw, bh = x + 10, y + 26, w - 20, h - 50
        thr = eng.cfg['threshold']
        ty = by + bh - int(math.sqrt(thr) * bh)
        for xx in range(bx, bx + bw, 6):
            cv.rect(xx, ty, 3, 1, _c(FAINT))
        recent = {}
        for (t, band, note, vel, pos) in eng.events:
            if 0 <= now - t < 0.35:
                recent[band] = max(recent.get(band, 0.0), 1.0 - (now - t) / 0.35)
        slot = bw / max(1, n)
        peaks = eng.peaks
        for b in range(n):
            lum = float(s['bands'][b])
            # 우주 사진은 대부분 어두워서 sqrt 로 펴서 보여준다 (임계선도 같은 눈금)
            hh = int(round(math.sqrt(min(1.0, lum)) * bh))
            x0 = int(bx + b * slot)
            ww = max(1, int(slot) - 2)
            cv.rect(x0, by + bh - hh, ww, hh, _vivid(s['band_rgb'][b], lum))
            if b < len(peaks):
                py = by + bh - int(round(math.sqrt(min(1.0, float(peaks[b]))) * bh))
                cv.rect(x0, py, ww, 1, _c(TEXT, 200))
            if b in recent:
                cv.rect(x0, by + bh - hh - 4, ww, 3, ACCENT + (int(255 * recent[b]),))
        cv.rect(bx, by + bh, bw, 1, _c(DIM))
        step = max(1, int(math.ceil(n / 8.0)))
        for b in range(0, n, step):
            if b < len(notes):
                cv.text(int(bx + b * slot), by + bh + 6, music.note_name(notes[b]), FAINT, 1)

    def _palette(self, cv, eng):
        x, y, w, h = PALETTE
        a = eng.analyzer
        k = len(a.palette)
        cv.text(x + 10, y + 10, 'PALETTE K=%d' % k, DIM, 1)
        if not k:
            return
        mix = eng.scan['mix']
        cur = eng.scan['palidx']
        size = int(min(44, (w - 20) / k - 8))
        gap = (w - 20 - size * k) / max(1, k - 1) if k > 1 else 0
        for j in range(k):
            sx = int(x + 10 + j * (size + gap))
            sy = y + 26
            col = tuple(int(v) for v in np.clip(a.palette[j] * 255, 0, 255)) + (255,)
            cv.rect(sx, sy, size, size, col)
            if j == cur:
                cv.frame(sx - 3, sy - 3, size + 6, size + 6, ACCENT + (255,), 2)
            cv.text(sx + size // 2, sy + size + 6, '%d%%' % round(a.weights[j] * 100), DIM, 1, align='center')
            m = float(mix[j]) if j < len(mix) else 0.0
            mh = int(round(m * 52))
            cv.rect(sx, y + h - 12 - 52, size, 52, _c(FAINT))
            cv.rect(sx, y + h - 12 - mh, size, mh, _vivid(a.palette[j]))
        cv.text(x + w - 10, y + 10, 'SCAN MIX', FAINT, 1, align='right')

    def _feed(self, cv, eng, i, f, y, now):
        x, w, h = FEED_X, FEED_W, FEED_H
        enabled = eng.cfg.get('feed%d_enabled' % (i + 1), True)
        cv.text(x + 10, y + 10, str(i + 1), ACCENT, 2)
        cv.text(x + 28, y + 14, f.label, DIM, 1)
        cv.text(x + 28 + text_width(f.label, 1) + 8, y + 10, f.symbol, TEXT, 2)
        if not enabled:
            cv.text(x + w - 10, y + 12, 'OFF', DIM, 1, align='right')
            return
        if f.error:
            st, col = 'ERR', BAD
        elif f.updated_at is None:
            st, col = 'WAIT', DIM
        else:
            st, col = '%.1fS' % max(0.0, now - f.updated_at), GOOD
        if f.insecure:
            st = 'NOSSL ' + st
        wst = cv.text(x + w - 10, y + 12, st, DIM, 1, align='right')
        cv.text(x + w - 14 - wst, y + 12, '■', col, 1, align='right')

        cv.text(x + 10, y + 34, fmt_price(f.price), TEXT, 3)
        chg = f.chg24
        cv.text(x + w - 10, y + 38, '%+.2f%%' % chg, UP if chg > 0 else DOWN if chg < 0 else DIM, 2, align='right')

        sx, sy, sw, sh = x + 10, y + 64, w - 20, 44
        cv.rect(sx, sy + sh, sw, 1, _c(FAINT))
        hist = list(f.history)
        if f.error and not hist:
            cv.text(sx, sy + 16, f.error[:60], BAD, 1)
        elif len(hist) >= 2:
            hist = hist[-sw:]
            lo, hi = min(hist), max(hist)
            span = hi - lo if hi > lo else 1.0
            xs = [sx + sw - len(hist) + j for j in range(len(hist))]
            ys = [sy + sh - 1 - int(round((p - lo) / span * (sh - 2))) if hi > lo else sy + sh // 2 for p in hist]
            col = UP if hist[-1] > hist[0] else DOWN if hist[-1] < hist[0] else DIM
            cv.polyline(xs, ys, _c(col), 2)
            cv.rect(xs[-1] - 2, ys[-1] - 2, 5, 5, _c(TEXT))
            if f.error:
                cv.text(sx, sy, f.error[:60], BAD, 1)
        my = y + 118
        cv.text(x + 10, my, 'Z', DIM, 1)
        cv.hbar(x + 22, my, 70, 7, f.z_s, _c(UP if f.z_s > 0 else DOWN), centered=True)
        cv.text(x + 102, my, 'MOM', DIM, 1)
        cv.hbar(x + 124, my, 70, 7, f.mom_s, _c(UP if f.mom_s > 0 else DOWN), centered=True)
        cv.text(x + 204, my, 'ACT', DIM, 1)
        cv.hbar(x + 226, my, 50, 7, f.act, _c(ACCENT))
        cv.text(x + w - 10, my, 'VOL %.1fBP' % f.vol, DIM, 1, align='right')
        arrow = '↑' if f.up > 0 else '↓' if f.up < 0 else '-'
        cv.text(x + w - 10, y + 128, '%s %+.2fBP  #%d' % (arrow, f.ret, f.ticks), FAINT, 1, align='right')

    def _iss(self, cv, eng, now):
        x, y, w, h = ISS
        sp = eng.space
        cv.text(x + 10, y + 10, '4', ACCENT, 2)
        cv.text(x + 28, y + 14, 'ISS', TEXT, 1)
        cv.text(x + 52, y + 14, 'WHERETHEISS.AT', DIM, 1)
        if not eng.cfg.get('space_enabled', True):
            cv.text(x + w - 10, y + 12, 'OFF', DIM, 1, align='right')
        elif sp.error:
            cv.text(x + w - 10, y + 12, 'ERR', BAD, 1, align='right')
        elif sp.updated_at is not None:
            cv.text(x + w - 10, y + 12, '%.1fS' % max(0.0, now - sp.updated_at), GOOD, 1, align='right')
        mx, my, mw, mh = self.iss_map_rect()
        pts = list(sp.track)
        for j, (lat, lon) in enumerate(pts):
            px = mx + int((lon + 180.0) / 360.0 * (mw - 1))
            py = my + int((90.0 - lat) / 180.0 * (mh - 1))
            a = 60 + int(160 * (j + 1) / len(pts))
            cv.rect(px, py, 1, 1, ACCENT[:3] + (a,))
        if sp.updated_at is not None:
            px = mx + int((sp.lon + 180.0) / 360.0 * (mw - 1))
            py = my + int((90.0 - sp.lat) / 180.0 * (mh - 1))
            cv.rect(px - 2, py - 2, 5, 5, _c(ACCENT))
            cv.frame(px - 5, py - 5, 11, 11, ACCENT[:3] + (150,))
        tx = mx + mw + 14
        rows = [
            ('LAT', '%+.2f' % sp.lat), ('LON', '%+.2f' % sp.lon),
            ('ALT', '%.0f KM' % sp.alt if sp.alt else '--'),
            ('VEL', '%.0f KM/H' % sp.vel if sp.vel else '--'),
            ('SUN', 'DAY' if sp.day >= 0.5 else 'NIGHT' if sp.updated_at else '--'),
        ]
        for j, (k, v) in enumerate(rows):
            cv.text(tx, my + 2 + j * 22, k, DIM, 1)
            cv.text(tx + 26, my + j * 22, v, TEXT, 2 if len(v) <= 8 else 1)
        if sp.error:
            cv.text(x + 10, y + h - 14, sp.error[:58], BAD, 1)

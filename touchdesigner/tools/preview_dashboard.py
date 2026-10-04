"""TD 없이 대시보드 모습을 PNG 로 미리 본다 (가짜 시세 + 시험 이미지).

    python3 touchdesigner/tools/preview_dashboard.py [출력.png] [이미지]
GLSL 합성(사진 + 스캔선 + 오버레이)을 numpy 로 똑같이 흉내 낸다.
"""
import math
import os
import sys
import time

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'python'))

from sonify_td import SonifyEngine  # noqa: E402
from sonify_td.render import Dashboard, fit_rect, WIDTH, HEIGHT  # noqa: E402


def composite(photo_top_down, overlay, pos, line=(1.0, 0.77, 0.35), glow=0.35, dim=0.6):
    """glsl_dashboard.frag 와 같은 계산 (위→아래 좌표)."""
    out = np.zeros((HEIGHT, WIDTH, 3), np.float32)
    out[:] = (0.035, 0.040, 0.055)
    ih, iw = photo_top_down.shape[:2]
    fx, fy, fw, fh = fit_rect(iw, ih)
    x0, y0 = int(round(fx)), int(round(fy))
    w, h = int(round(fw)), int(round(fh))
    img = np.asarray(Image.fromarray(photo_top_down).resize((w, h), Image.BILINEAR), np.float32) / 255.0
    u = (np.arange(w) + 0.5) / w
    played = (u <= pos).astype(np.float32)
    img *= (dim + (1 - dim) * played)[None, :, None]
    d = np.abs(u - pos) * w
    add = np.clip(1 - d / 1.5, 0, 1) + glow * np.exp(-d * 0.06)
    img += np.array(line)[None, None, :] * add[None, :, None]
    out[y0:y0 + h, x0:x0 + w] = img
    a = overlay[:, :, 3:4].astype(np.float32) / 255.0
    out = out * (1 - a) + overlay[:, :, :3].astype(np.float32) / 255.0 * a
    return (np.clip(out, 0, 1) * 255).astype(np.uint8)


def main(out_path, image_path):
    photo = np.asarray(Image.open(image_path).convert('RGB'))
    eng = SonifyEngine(osc_enabled=False, sweep_seconds=8.0, bands=24, palette_size=5)
    eng.set_image(np.ascontiguousarray(photo[::-1]))          # TD 규약(0행 = 아래)

    rng = np.random.RandomState(3)
    t0 = 1_000_000.0
    prices = [142_350_000.0, 4512.37, 234.70]
    chg = [-1.23, 2.31, 0.84]
    lat, lon = 10.0, -120.0
    now = t0
    for k in range(200):                                   # 가짜 시세 200틱 (1초 간격)
        for i in range(3):
            prices[i] *= math.exp(rng.normal(0.00005 * (1 if i else -1), 0.0007))
            eng.ingest({'job': 'feed%d' % (i + 1), 'ok': True,
                        'data': {'price': prices[i], 'chg24': chg[i] + rng.normal(0, 0.02)}}, now=now)
        if k % 2 == 0:
            lon = (lon + 1.0 + 180) % 360 - 180
            lat = 51.6 * math.sin(math.radians(lon * 1.0 + 40))
            eng.ingest({'job': 'iss', 'ok': True, 'data': {'lat': lat, 'lon': lon, 'alt': 418.0,
                                                           'vel': 27580.0, 'day': 1.0}}, now=now)
        now += 1.0
    eng.ingest({'job': 'feed3', 'ok': False, 'error': 'HTTP 451 (지역 차단) / 연결 실패'}, now=now)
    eng.ingest({'job': 'feed3', 'ok': True, 'data': {'price': prices[2], 'chg24': chg[2]}}, now=now)

    eng.seek(0.30)
    dash = Dashboard()
    for _ in range(60):                                    # 스캔 진행 (트리거 생성)
        eng.tick(1 / 60.0, now=now)
        now += 1 / 60.0
    t = time.perf_counter()
    n = 30
    for _ in range(n):
        overlay = dash.render(eng, {'image_res': (photo.shape[1], photo.shape[0]), 'fps': 60.0,
                                    'image_name': os.path.basename(image_path)}, now=now)
    ms = (time.perf_counter() - t) / n * 1000
    img = composite(photo, overlay, eng.pos)
    Image.fromarray(img).save(out_path)
    print('render %.2f ms/frame -> %s' % (ms, out_path))
    return ms


if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else 'dashboard_preview.png'
    src = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, '..', 'assets', 'deep_field.jpg')
    main(out, src)

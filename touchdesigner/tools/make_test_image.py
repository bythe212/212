"""시험용 '우주' 이미지 생성기 (별 + 성운). 저작권 걱정 없는 결정적(seed 고정) 이미지.

    python3 touchdesigner/tools/make_test_image.py  → touchdesigner/assets/deep_field.jpg
실제 작업에는 NASA/ESA(허블·제임스웹) 공개 이미지를 Imagefile 에 넣으면 된다.
"""
import os
import sys

import numpy as np
from PIL import Image

W, H = 1024, 512


def fractal_noise(rng, w, h, octaves=6):
    out = np.zeros((h, w), np.float32)
    amp, total = 1.0, 0.0
    for o in range(octaves):
        cw, ch = max(2, w >> (octaves - o)), max(2, h >> (octaves - o))
        small = rng.rand(ch, cw).astype(np.float32)
        big = np.array(Image.fromarray((small * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC), np.float32) / 255
        out += big * amp
        total += amp
        amp *= 0.55
    return out / total


def blob(w, h, cx, cy, sx, sy):
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    return np.exp(-(((x - cx) / sx) ** 2 + ((y - cy) / sy) ** 2))


def main(path):
    rng = np.random.RandomState(212)
    img = np.zeros((H, W, 3), np.float32)
    img += np.array([0.012, 0.014, 0.03])  # 깊은 남색 바탕

    n1, n2 = fractal_noise(rng, W, H), fractal_noise(rng, W, H)
    clouds = [
        (blob(W, H, 260, 300, 230, 150), np.array([0.85, 0.25, 0.55])),   # 자홍
        (blob(W, H, 620, 190, 260, 120), np.array([0.15, 0.65, 0.75])),   # 청록
        (blob(W, H, 860, 360, 170, 140), np.array([0.95, 0.55, 0.15])),   # 주황
    ]
    for m, col in clouds:
        dens = np.clip(m * (n1 * 1.6 - 0.35), 0, 1) ** 1.4
        img += dens[:, :, None] * col[None, None, :] * 0.9
    img += (np.clip(n2 - 0.55, 0, 1) * 0.25)[:, :, None] * np.array([0.6, 0.5, 0.9])  # 먼지

    # 별: 작은 별 다수 + 밝은 별 몇 개(회절 스파이크)
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    for _ in range(900):
        sx, sy = rng.uniform(0, W), rng.uniform(0, H)
        b = rng.pareto(2.2) * 0.25 + 0.15
        r = 0.6 + min(2.0, b)
        x0, x1 = int(max(0, sx - 6)), int(min(W, sx + 7))
        y0, y1 = int(max(0, sy - 6)), int(min(H, sy + 7))
        psf = np.exp(-((x[y0:y1, x0:x1] - sx) ** 2 + (y[y0:y1, x0:x1] - sy) ** 2) / (2 * r * r))
        tint = np.array([1.0, 0.95, 0.85]) if rng.rand() < 0.6 else np.array([0.75, 0.85, 1.0])
        img[y0:y1, x0:x1] += psf[:, :, None] * tint * min(b, 1.5)
    for _ in range(9):
        sx, sy = rng.uniform(40, W - 40), rng.uniform(30, H - 30)
        d2 = (x - sx) ** 2 + (y - sy) ** 2
        core = np.exp(-d2 / 18.0) * 2.0
        spikes = (np.exp(-np.abs(y - sy) / 0.9) * np.exp(-np.abs(x - sx) / 14.0)
                  + np.exp(-np.abs(x - sx) / 0.9) * np.exp(-np.abs(y - sy) / 14.0)) * 0.7
        spikes *= np.exp(-d2 / (2 * 45.0 ** 2))
        img += (core + spikes)[:, :, None] * np.array([1.0, 0.92, 0.8])

    img = 1.0 - np.exp(-img * 1.4)  # 톤매핑
    out = (np.clip(img, 0, 1) ** (1 / 1.1) * 255).astype(np.uint8)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.fromarray(out).save(path, quality=90)
    print(path, os.path.getsize(path), 'bytes')


if __name__ == '__main__':
    here = os.path.dirname(os.path.abspath(__file__))
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, '..', 'assets', 'deep_field.jpg'))

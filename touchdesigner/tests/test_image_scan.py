import os

import numpy as np
import pytest

from sonify_td.image_scan import ImageAnalyzer, kmeans_palette, rgb_to_hsv, circular_mean


def td_array(img_top_down):
    """PIL 처럼 위→아래 배열을 TD numpyArray 규약(0번 행 = 아래)으로."""
    return np.ascontiguousarray(img_top_down[::-1])


def test_band0_is_bottom():
    # 위쪽 절반만 밝은 이미지 → 위쪽 대역이 밝고, 무게중심이 위(>0.5)
    img = np.zeros((64, 32, 3), np.float32)
    img[:32] = 1.0                                   # 위→아래 기준 위쪽
    a = ImageAnalyzer()
    a.set_image(td_array(img), palette_size=2)
    r = a.analyze(0.5, bands=8)
    assert r['bands'][-1] > 0.99 and r['bands'][0] < 0.01
    assert r['centroid'] > 0.7
    assert r['peak'] > 0.5


def test_scan_reads_columns_left_to_right():
    img = np.zeros((40, 100, 3), np.float32)
    img[:, :50] = [1, 0, 0]
    img[:, 50:] = [0, 0, 1]
    a = ImageAnalyzer()
    a.set_image(td_array(img), palette_size=2)
    left, right = a.analyze(0.1), a.analyze(0.9)
    assert left['r'] > 0.99 and left['b'] < 0.01
    assert right['b'] > 0.99
    assert abs(left['hue'] - 0.0) < 0.02 and abs(right['hue'] - 2 / 3) < 0.02
    edge = a.analyze(0.5)
    assert edge['edge'] > left['edge']               # 경계에서 변화량이 크다
    # 팔레트 2색과 비율, 구성비(mix)
    pal = {tuple(np.round(c, 2)) for c in a.palette}
    assert pal == {(1.0, 0.0, 0.0), (0.0, 0.0, 1.0)}
    assert np.allclose(a.weights, [0.5, 0.5], atol=0.05)
    assert left['mix'].max() == 1.0 and left['palidx'] != right['palidx']


def test_density_and_bands_count_independent_of_height():
    img = np.zeros((10, 10, 3), np.float32)
    img[5, 5] = 1.0
    a = ImageAnalyzer()
    a.set_image(td_array(img))
    r = a.analyze(5 / 9.0, bands=32, width_px=1, threshold=0.5)   # 5번째 열. 행(10) < 대역(32) 이어도 동작
    assert len(r['bands']) == 32
    assert r['density'] == pytest.approx(0.1)


def test_uint8_rgba_and_empty():
    a = ImageAnalyzer()
    empty = a.analyze(0.3, bands=5)
    assert empty['lum'] == 0 and len(empty['bands']) == 5
    img = np.full((8, 8, 4), 255, np.uint8)
    a.set_image(img)
    assert a.analyze(0.0)['lum'] == pytest.approx(1.0)
    with pytest.raises(ValueError):
        a.set_image(np.zeros((1, 1, 3)))


def test_hsv_and_circular_mean():
    h, s, v = rgb_to_hsv(np.array([[1, 0, 0], [0, 1, 0], [0, 0, 1], [0.5, 0.5, 0.5]], np.float32))
    assert np.allclose(h[:3], [0, 1 / 3, 2 / 3], atol=1e-6) and s[3] == 0
    m, conf = circular_mean(np.array([0.95, 0.05]), np.array([1.0, 1.0]))
    assert min(m, 1 - m) < 1e-6 and conf > 0.9


def test_kmeans_deterministic():
    rng = np.random.RandomState(0)
    px = np.concatenate([rng.normal(c, 0.02, (300, 3)) for c in ([0.9, 0.1, 0.1], [0.1, 0.8, 0.2], [0.2, 0.2, 0.9])])
    p1, w1 = kmeans_palette(px, 3)
    p2, w2 = kmeans_palette(px, 3)
    assert np.array_equal(p1, p2) and np.allclose(w1, 1 / 3, atol=0.02)


def test_real_test_image(td_dir):
    from PIL import Image
    img = np.asarray(Image.open(os.path.join(td_dir, 'assets', 'deep_field.jpg')).convert('RGB'))
    a = ImageAnalyzer()
    a.set_image(td_array(img), palette_size=6)
    assert len(a.palette) == 6 and abs(float(a.weights.sum()) - 1) < 1e-5
    lums = [a.analyze(x / 50.0, bands=24)['lum'] for x in range(51)]
    assert max(lums) > min(lums) * 1.5    # 왼쪽→오른쪽으로 가며 소리가 실제로 변한다

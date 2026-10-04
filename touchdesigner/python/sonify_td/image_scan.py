"""사진 색 추출 + 세로선 스캔 분석 (NASA 식 이미지 소니피케이션의 기본형).

배열 규약: TD 의 TOP.numpyArray() 와 같다 — shape (H, W, 3|4), float 0..1,
**0번 행이 이미지의 맨 아래**. 그래서 대역(band) 0 = 아래 = 낮은 음.

스캔선이 x 위치(0=왼쪽, 1=오른쪽)에 있을 때 그 세로줄을 분석해서
대역별 밝기(= 음량), 대표 색(= 음색), 밝기 무게중심(= 음높이) 등을 낸다.
"""
import numpy as np

LUMA = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)


def to_rgb(arr):
    a = np.asarray(arr)
    if a.dtype == np.uint8:
        a = a.astype(np.float32) / 255.0
    else:
        a = a.astype(np.float32, copy=False)
    if a.ndim == 2:
        a = np.repeat(a[:, :, None], 3, axis=2)
    if a.shape[2] == 4:
        a = a[:, :, :3]
    elif a.shape[2] == 1:
        a = np.repeat(a, 3, axis=2)
    return np.clip(np.nan_to_num(a), 0.0, 1.0)


def rgb_to_hsv(rgb):
    """(..., 3) → h, s, v (각각 0..1)."""
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mx = rgb.max(axis=-1)
    mn = rgb.min(axis=-1)
    d = mx - mn
    safe = np.where(d > 1e-6, d, 1.0)
    h = np.where(mx == r, ((g - b) / safe) % 6.0,
                 np.where(mx == g, (b - r) / safe + 2.0, (r - g) / safe + 4.0)) / 6.0
    h = np.where(d > 1e-6, h, 0.0)
    s = np.where(mx > 1e-6, d / np.where(mx > 1e-6, mx, 1.0), 0.0)
    return h, s, mx


def circular_mean(h, w):
    """색상(hue)은 원형이라 그냥 평균내면 안 된다(0.95 와 0.05 의 평균은 0.0)."""
    sw = float(w.sum())
    if sw <= 1e-9:
        return 0.0, 0.0
    ang = h * 2.0 * np.pi
    x = float((np.cos(ang) * w).sum() / sw)
    y = float((np.sin(ang) * w).sum() / sw)
    return (np.arctan2(y, x) / (2.0 * np.pi)) % 1.0, float(np.hypot(x, y))


def kmeans_palette(pixels, k=5, iters=12, seed=7):
    """대표 색 k 개와 비율. 결정적(seed 고정)이라 같은 사진이면 항상 같은 팔레트."""
    pixels = np.asarray(pixels, dtype=np.float32).reshape(-1, 3)
    n = len(pixels)
    k = max(1, min(int(k), n))
    rng = np.random.RandomState(seed)
    centers = np.empty((k, 3), dtype=np.float32)
    centers[0] = pixels[rng.randint(n)]
    d2 = ((pixels - centers[0]) ** 2).sum(axis=1)
    for j in range(1, k):  # k-means++ 초기화
        p = d2.astype(np.float64)
        total = float(p.sum())
        idx = rng.randint(n) if total <= 1e-12 else rng.choice(n, p=p / total)
        centers[j] = pixels[idx]
        d2 = np.minimum(d2, ((pixels - centers[j]) ** 2).sum(axis=1))
    labels = np.zeros(n, dtype=np.int64)
    for _ in range(iters):
        dist = ((pixels[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
        new = dist.argmin(axis=1)
        for j in range(k):
            m = new == j
            if m.any():
                centers[j] = pixels[m].mean(axis=0)
        if np.array_equal(new, labels):
            break
        labels = new
    weights = np.bincount(labels, minlength=k).astype(np.float32) / n
    order = np.argsort(-weights, kind='stable')
    return centers[order], weights[order]


class ImageAnalyzer:
    def __init__(self):
        self.img = None
        self.lum = None
        self.labels = None
        self.palette = np.zeros((0, 3), dtype=np.float32)
        self.weights = np.zeros(0, dtype=np.float32)
        self.version = 0     # 이미지가 바뀔 때마다 +1 (렌더러 캐시 무효화용)

    @property
    def ready(self):
        return self.img is not None

    @property
    def size(self):
        return (0, 0) if self.img is None else (self.img.shape[1], self.img.shape[0])

    def set_image(self, arr, palette_size=5, palette=True):
        """palette=False 면 팔레트(k-means)는 그대로 두고 픽셀 라벨만 다시 계산한다(영상 입력용, 더 싸다)."""
        img = to_rgb(arr)
        if img.shape[0] < 2 or img.shape[1] < 2:
            raise ValueError('이미지가 너무 작습니다: %s' % (img.shape,))
        self.img = img
        self.lum = img @ LUMA
        self.version += 1
        if palette or len(self.palette) == 0:
            self.compute_palette(palette_size)
        else:
            self._label()

    def compute_palette(self, k):
        if self.img is None:
            return
        h, w = self.img.shape[:2]
        step = max(1, int(np.sqrt(h * w / 4096.0)))
        sample = self.img[::step, ::step].reshape(-1, 3)
        self.palette, self.weights = kmeans_palette(sample, k)
        self._label()

    def _label(self):
        """모든 픽셀이 어느 팔레트 색에 가장 가까운지 (스캔 중 색 구성비 계산용)."""
        h, w = self.img.shape[:2]
        flat = self.img.reshape(-1, 3)
        dist = ((flat[:, None, :] - self.palette[None, :, :]) ** 2).sum(axis=2)
        self.labels = dist.argmin(axis=1).reshape(h, w).astype(np.int16)

    def _cols(self, x, width_px):
        w = self.img.shape[1]
        c = int(round(min(max(x, 0.0), 1.0) * (w - 1)))
        half = max(0, int(width_px) // 2)
        return max(0, c - half), min(w, c + half + 1), c

    def band_peaks(self, x0, x1, bands=24, width_px=3):
        """x0→x1 사이를 지나간 모든 열에서 대역별 최대 밝기 (트리거용).
        평균은 작은 별을 희석시키고, 빠르게 훑으면 프레임 사이 열을 건너뛰므로 '지나간 구간의 최댓값'을 쓴다."""
        bands = max(1, int(bands))
        if self.img is None:
            return np.zeros(bands, np.float32)
        a0, _, _ = self._cols(min(x0, x1), width_px)
        _, b1, _ = self._cols(max(x0, x1), width_px)
        colmax = self.lum[:, a0:max(b1, a0 + 1)].max(axis=1)      # (H,)
        h = len(colmax)
        idx = np.arange(bands)
        lo = np.minimum((idx * h) // bands, h - 1)
        hi = np.maximum(((idx + 1) * h) // bands, lo + 1)
        return np.array([colmax[a:b].max() for a, b in zip(lo, hi)], np.float32)

    def analyze(self, x, bands=24, width_px=3, threshold=0.55):
        bands = max(1, int(bands))
        k = len(self.palette)
        if self.img is None:
            z = np.zeros(bands, dtype=np.float32)
            return {
                'pos': float(x), 'r': 0.0, 'g': 0.0, 'b': 0.0, 'lum': 0.0, 'hue': 0.0, 'sat': 0.0,
                'centroid': 0.5, 'spread': 0.0, 'peak': 0.0, 'contrast': 0.0, 'edge': 0.0,
                'density': 0.0, 'palidx': 0, 'bands': z, 'band_rgb': np.zeros((bands, 3), np.float32),
                'mix': np.zeros(k, np.float32),
            }
        c0, c1, c = self._cols(x, width_px)
        col = self.img[:, c0:c1].mean(axis=1)            # (H, 3)
        lum = self.lum[:, c0:c1].mean(axis=1)            # (H,)
        h = len(lum)

        # 대역: 아래(0)→위. 행 수가 대역 수보다 적어도 동작하도록 경계를 정수로 나눈다.
        idx = np.arange(bands)
        lo = np.minimum((idx * h) // bands, h - 1)
        hi = np.maximum(((idx + 1) * h) // bands, lo + 1)
        cnt = (hi - lo).astype(np.float32)
        cs = np.concatenate([[0.0], np.cumsum(lum, dtype=np.float64)])
        band_lum = ((cs[hi] - cs[lo]) / cnt).astype(np.float32)
        cs3 = np.concatenate([np.zeros((1, 3)), np.cumsum(col, axis=0, dtype=np.float64)])
        band_rgb = ((cs3[hi] - cs3[lo]) / cnt[:, None]).astype(np.float32)

        mean_rgb = col.mean(axis=0)
        hh, ss, vv = rgb_to_hsv(col)
        hue, _ = circular_mean(hh, ss * vv)
        y = (np.arange(h, dtype=np.float32) + 0.5) / h
        total = float(lum.sum())
        if total > 1e-6:
            centroid = float((lum * y).sum() / total)
            spread = float(np.sqrt((lum * (y - centroid) ** 2).sum() / total) * 2.0)
        else:
            centroid, spread = 0.5, 0.0

        # 가로 방향 변화량(경계/구조): 스캔선 양옆 기둥의 밝기 차
        w = self.img.shape[1]
        left = self.lum[:, max(0, c - 2)]
        right = self.lum[:, min(w - 1, c + 2)]
        edge = float(np.clip(np.abs(right - left).mean() * 4.0, 0.0, 1.0))

        if self.labels is not None and k:
            mix = np.bincount(self.labels[:, c0:c1].ravel(), minlength=k)[:k].astype(np.float32)
            mix /= max(1.0, float(mix.sum()))
            palidx = int(mix.argmax())
        else:
            mix, palidx = np.zeros(k, np.float32), 0

        return {
            'pos': float(x),
            'r': float(mean_rgb[0]), 'g': float(mean_rgb[1]), 'b': float(mean_rgb[2]),
            'lum': float(lum.mean()),
            'hue': float(hue),
            'sat': float(ss.mean()),
            'centroid': centroid,
            'spread': float(min(1.0, spread)),
            'peak': float(band_lum.argmax()) / max(1, bands - 1),
            'contrast': float(min(1.0, lum.std() * 3.0)),
            'edge': edge,
            'density': float((lum > threshold).mean()),
            'palidx': palidx,
            'bands': band_lum,
            'band_rgb': band_rgb,
            'mix': mix,
        }

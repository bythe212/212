"""실시간 데이터 소스(API) 정의와, 들어온 값을 소리에 쓰기 좋은 신호로 바꾸는 상태 객체.

공급자(provider)마다 URL 템플릿과 파서를 둔다. 파서는 응답 JSON 을 받아
{'price': float, 'chg24': float(%), 'volume': float|None, 'ts': float|None} 를 돌려주고,
API 가 에러 형식으로 응답하면 ValueError 를 던진다.
"""
import math
import random
import time
from collections import deque


# ---------------------------------------------------------------- 파서

def _f(v):
    return float(v) if v is not None and v != '' else None


def parse_upbit(data):
    # https://api.upbit.com/v1/ticker?markets=KRW-BTC → [ {...} ]
    if isinstance(data, dict) and 'error' in data:
        err = data['error']
        raise ValueError(err.get('message') or err.get('name') or 'upbit error')
    if not data:
        raise ValueError('upbit: 빈 응답 (마켓 코드 확인)')
    d = data[0]
    ts = d.get('trade_timestamp') or d.get('timestamp')
    return {
        'price': float(d['trade_price']),
        'chg24': float(d['signed_change_rate']) * 100.0,
        'volume': _f(d.get('acc_trade_volume_24h')),
        'ts': ts / 1000.0 if ts else None,
    }


def parse_binance(data):
    # https://api.binance.com/api/v3/ticker/24hr?symbol=ETHUSDT
    if 'lastPrice' not in data:
        raise ValueError(data.get('msg') or 'binance: 예상치 못한 응답')
    ts = data.get('closeTime')
    return {
        'price': float(data['lastPrice']),
        'chg24': float(data['priceChangePercent']),
        'volume': _f(data.get('volume')),
        'ts': ts / 1000.0 if ts else None,
    }


def parse_coinbase(data):
    # https://api.exchange.coinbase.com/products/SOL-USD/stats → open/high/low/last/volume (문자열)
    if 'last' not in data:
        raise ValueError(data.get('message') or 'coinbase: 예상치 못한 응답')
    last = float(data['last'])
    opn = _f(data.get('open'))
    return {
        'price': last,
        'chg24': (last - opn) / opn * 100.0 if opn else 0.0,
        'volume': _f(data.get('volume')),
        'ts': None,
    }


def parse_bithumb(data):
    # https://api.bithumb.com/public/ticker/BTC_KRW → {"status":"0000","data":{...}}
    if data.get('status') != '0000':
        raise ValueError(data.get('message') or 'bithumb status %s' % data.get('status'))
    d = data['data']
    date = d.get('date')
    return {
        'price': float(d['closing_price']),
        'chg24': float(d.get('fluctate_rate_24H') or 0.0),
        'volume': _f(d.get('units_traded_24H')),
        'ts': int(date) / 1000.0 if date else None,
    }


def parse_iss(data):
    # https://api.wheretheiss.at/v1/satellites/25544
    if 'latitude' in data:
        vis = data.get('visibility')
        return {
            'lat': float(data['latitude']),
            'lon': float(data['longitude']),
            'alt': _f(data.get('altitude')),
            'vel': _f(data.get('velocity')),
            'day': None if vis is None else (1.0 if vis == 'daylight' else 0.0),
            'ts': _f(data.get('timestamp')),
        }
    # http://api.open-notify.org/iss-now.json (대체 경로, 고도/속도 없음)
    if 'iss_position' in data:
        pos = data['iss_position']
        return {
            'lat': float(pos['latitude']),
            'lon': float(pos['longitude']),
            'alt': None,
            'vel': None,
            'day': None,
            'ts': _f(data.get('timestamp')),
        }
    raise ValueError(data.get('error') or data.get('message') or 'iss: 예상치 못한 응답')


# ---------------------------------------------------------------- 공급자

class Provider:
    def __init__(self, key, label, urls, parse, default_symbol, quote, sep, base_first=True):
        self.key = key
        self.label = label
        self.urls = urls            # 앞에서부터 시도, 실패하면 다음 URL
        self.parse = parse
        self.default_symbol = default_symbol
        self.quote = quote          # 'BTC' 만 입력했을 때 붙일 기준 통화
        self.sep = sep
        self.base_first = base_first

    def normalize_symbol(self, symbol):
        """'btc' 처럼 짧게 써도 공급자 형식(KRW-BTC, BTCUSDT, BTC-USD, BTC_KRW)으로 맞춘다."""
        s = (symbol or '').strip().upper()
        if not s:
            return self.default_symbol
        if any(c in s for c in '-_/') or len(s) > 5:
            s = s.replace('/', self.sep)
            if self.sep == '':
                s = s.replace('-', '').replace('_', '')
            return s
        return (s + self.sep + self.quote) if self.base_first else (self.quote + self.sep + s)

    def build_urls(self, symbol):
        sym = self.normalize_symbol(symbol)
        return [u.format(symbol=sym) for u in self.urls]


PROVIDERS = {
    'upbit': Provider('upbit', 'UPBIT', ['https://api.upbit.com/v1/ticker?markets={symbol}'],
                      parse_upbit, 'KRW-BTC', 'KRW', '-', base_first=False),
    'binance': Provider('binance', 'BINANCE', [
        'https://api.binance.com/api/v3/ticker/24hr?symbol={symbol}',
        # api.binance.com 이 지역 차단(HTTP 451)일 때 쓰는 공개 시세 전용 도메인
        'https://data-api.binance.vision/api/v3/ticker/24hr?symbol={symbol}',
    ], parse_binance, 'ETHUSDT', 'USDT', ''),
    'coinbase': Provider('coinbase', 'COINBASE', ['https://api.exchange.coinbase.com/products/{symbol}/stats'],
                         parse_coinbase, 'SOL-USD', 'USD', '-'),
    'bithumb': Provider('bithumb', 'BITHUMB', ['https://api.bithumb.com/public/ticker/{symbol}'],
                        parse_bithumb, 'BTC_KRW', 'KRW', '_'),
    # 네트워크 없이 시험할 때 쓰는 랜덤워크(HTTP 요청 없음)
    'sim': Provider('sim', 'SIM', [], None, 'SIM-A', 'SIM', '-'),
}

ISS_URLS = [
    'https://api.wheretheiss.at/v1/satellites/25544',
    'http://api.open-notify.org/iss-now.json',
]

PROVIDER_KEYS = list(PROVIDERS.keys())


class SimSource:
    """랜덤워크 시세. 변동성이 뭉쳤다 풀렸다 하도록(volatility clustering) 만들어 소리 시험에 쓴다."""

    def __init__(self, seed=None, start=100.0):
        self.rng = random.Random(seed)
        self.price = start
        self.open = start
        self.sigma = 0.0008

    def sample(self):
        self.sigma = min(0.01, max(0.0002, self.sigma * math.exp(self.rng.gauss(0, 0.25))))
        self.price *= math.exp(self.rng.gauss(0, self.sigma))
        return {'price': self.price, 'chg24': (self.price / self.open - 1) * 100.0, 'volume': None, 'ts': time.time()}


# ---------------------------------------------------------------- 신호 처리

def _tanh_clip(x):
    return math.tanh(x)


class FeedState:
    """시세 하나의 상태. 새 값이 들어올 때마다 소리용 지표를 계산한다.

    price  : 현재가
    chg24  : 24시간 등락률(%)
    ret    : 직전 값 대비 수익률(bp, 1bp = 0.01%)
    vel    : ret 의 지수이동평균(모멘텀, bp)
    vol    : 최근 window 개 ret 의 표준편차(변동성, bp)
    z      : 최근 window 가격 안에서의 위치를 표준점수로 → tanh(z/2), -1..1
    norm   : 최근 window 의 최저~최고 사이 위치, 0..1
    mom    : vel / vol 을 tanh 로 눌러 -1..1 (변동성 대비 방향성)
    act    : 큰 틱이 오면 튀었다가 감쇠하는 엔벨로프, 0..1 (타악기 트리거용)
    up     : 직전 대비 +1 / 0 / -1
    *_s    : 프레임마다 부드럽게 따라가는 값(소리 파라미터용; 1초마다 계단처럼 튀지 않게)
    """

    VEL_SPAN = 8

    def __init__(self, slot, provider='upbit', symbol='', window=60):
        self.slot = slot
        self.history = deque(maxlen=240)   # 화면 스파크라인용
        self.configure(provider, symbol, window)

    def configure(self, provider, symbol, window=60):
        prov = PROVIDERS.get(provider, PROVIDERS['upbit'])
        sym = prov.normalize_symbol(symbol)
        changed = getattr(self, 'provider', None) != prov.key or getattr(self, 'symbol', None) != sym
        self.provider = prov.key
        self.label = prov.label
        self.symbol = sym
        self.window = max(5, int(window))
        if changed or not hasattr(self, 'prices'):
            self.reset()
        else:
            self.prices = deque(self.prices, maxlen=self.window)
            self.returns = deque(self.returns, maxlen=self.window)

    def reset(self):
        self.prices = deque(maxlen=self.window)
        self.returns = deque(maxlen=self.window)
        self.history.clear()
        self.price = float('nan')
        self.chg24 = 0.0
        self.volume = None
        self.ret = 0.0
        self.vel = 0.0
        self.vol = 0.0
        self.z = 0.0
        self.norm = 0.5
        self.mom = 0.0
        self.act = 0.0
        self.up = 0
        self.ticks = 0
        self.updated_at = None
        self.error = None
        self.errors = 0
        self.url = None
        self.latency = None
        self.insecure = False
        self.z_s = 0.0
        self.norm_s = 0.5
        self.mom_s = 0.0

    @property
    def ok(self):
        return self.updated_at is not None and self.error is None

    def update(self, sample, now=None):
        now = time.time() if now is None else now
        p = float(sample['price'])
        if not math.isfinite(p) or p <= 0:
            raise ValueError('잘못된 가격: %r' % p)
        ret = (math.log(p) - math.log(self.prices[-1])) * 1e4 if self.prices else 0.0
        self.prices.append(p)
        if self.ticks > 0:
            self.returns.append(ret)
        self.history.append(p)
        self.price = p
        self.chg24 = float(sample.get('chg24') or 0.0)
        self.volume = sample.get('volume')
        self.ret = ret
        a = 2.0 / (self.VEL_SPAN + 1)
        self.vel = a * ret + (1 - a) * self.vel
        n = len(self.returns)
        if n >= 2:
            m = sum(self.returns) / n
            self.vol = math.sqrt(sum((r - m) ** 2 for r in self.returns) / (n - 1))
        n = len(self.prices)
        mean = sum(self.prices) / n
        sd = math.sqrt(sum((x - mean) ** 2 for x in self.prices) / n)
        self.z = _tanh_clip((p - mean) / sd / 2.0) if sd > 0 else 0.0
        lo, hi = min(self.prices), max(self.prices)
        self.norm = (p - lo) / (hi - lo) if hi > lo else 0.5
        eps = 1e-6
        self.mom = _tanh_clip(self.vel / (self.vol + eps)) if self.vol > 0 else 0.0
        if self.vol > 0:
            self.act = max(self.act, min(1.0, abs(ret) / (2.5 * self.vol)))
        self.up = (ret > 0) - (ret < 0)
        self.ticks += 1
        self.updated_at = now
        self.error = None

    def fail(self, error):
        self.error = str(error)[:120]
        self.errors += 1

    def smooth(self, dt, tau=0.4, release=0.6):
        """프레임마다 호출. tau 초 시정수로 목표값을 따라간다."""
        k = 1.0 - math.exp(-dt / max(tau, 1e-3))
        self.z_s += (self.z - self.z_s) * k
        self.norm_s += (self.norm - self.norm_s) * k
        self.mom_s += (self.mom - self.mom_s) * k
        self.act *= math.exp(-dt / max(release, 1e-3))

    def age(self, now=None):
        if self.updated_at is None:
            return -1.0
        return (time.time() if now is None else now) - self.updated_at

    def values(self, prefix, now=None):
        price = self.price if math.isfinite(self.price) else 0.0
        return [
            (prefix + '/price', price),
            (prefix + '/chg24', self.chg24),
            (prefix + '/ret', self.ret),
            (prefix + '/vel', self.vel),
            (prefix + '/vol', self.vol),
            (prefix + '/z', self.z),
            (prefix + '/norm', self.norm),
            (prefix + '/mom', self.mom),
            (prefix + '/zs', self.z_s),
            (prefix + '/norms', self.norm_s),
            (prefix + '/moms', self.mom_s),
            (prefix + '/act', self.act),
            (prefix + '/up', float(self.up)),
            (prefix + '/age', self.age(now)),
            (prefix + '/ok', 1.0 if self.ok else 0.0),
        ]


class SpaceState:
    """ISS 위치. 위도는 궤도 경사각(51.6°)으로 나눠 -1..1 로 정규화한다."""

    INCLINATION = 51.64

    def __init__(self):
        self.track = deque(maxlen=400)   # 지도에 그릴 궤적 (lat, lon)
        self.reset()

    def reset(self):
        self.lat = 0.0
        self.lon = 0.0
        self.alt = 0.0
        self.vel = 0.0
        self.day = 0.0
        self.updated_at = None
        self.error = None
        self.errors = 0
        self.url = None
        self.latency = None
        self.insecure = False
        self.track.clear()

    @property
    def ok(self):
        return self.updated_at is not None and self.error is None

    def update(self, sample, now=None):
        self.lat = float(sample['lat'])
        self.lon = float(sample['lon'])
        if sample.get('alt') is not None:
            self.alt = float(sample['alt'])
        if sample.get('vel') is not None:
            self.vel = float(sample['vel'])
        if sample.get('day') is not None:
            self.day = float(sample['day'])
        self.track.append((self.lat, self.lon))
        self.updated_at = time.time() if now is None else now
        self.error = None

    def fail(self, error):
        self.error = str(error)[:120]
        self.errors += 1

    def age(self, now=None):
        if self.updated_at is None:
            return -1.0
        return (time.time() if now is None else now) - self.updated_at

    def values(self, now=None):
        return [
            ('iss/lat', self.lat),
            ('iss/lon', self.lon),
            ('iss/alt', self.alt),
            ('iss/vel', self.vel),
            ('iss/latn', max(-1.0, min(1.0, self.lat / self.INCLINATION))),
            ('iss/lonn', self.lon / 180.0),
            ('iss/day', self.day),
            ('iss/age', self.age(now)),
            ('iss/ok', 1.0 if self.ok else 0.0),
        ]

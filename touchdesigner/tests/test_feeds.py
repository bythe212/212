import math

import pytest

from sonify_td.feeds import (PROVIDERS, FeedState, SimSource, SpaceState, parse_binance, parse_bithumb,
                             parse_coinbase, parse_iss, parse_upbit)

# 각 API 의 공개 문서 형식에 맞춘 응답 예시(필드 일부)
UPBIT = [{"market": "KRW-BTC", "trade_price": 142350000.0, "signed_change_rate": -0.0123,
          "acc_trade_volume_24h": 2843.12, "trade_timestamp": 1759561200000, "timestamp": 1759561200123}]
BINANCE = {"symbol": "ETHUSDT", "priceChangePercent": "2.315", "lastPrice": "4512.37000000",
           "volume": "312345.1234", "closeTime": 1759561200999}
COINBASE = {"open": "230.10", "high": "240.00", "low": "225.00", "last": "234.70", "volume": "123456.7"}
BITHUMB = {"status": "0000", "data": {"opening_price": "141000000", "closing_price": "142000000",
                                      "fluctate_rate_24H": "0.71", "units_traded_24H": "1234.5",
                                      "date": "1759561200000"}}
ISS = {"name": "iss", "id": 25544, "latitude": 12.3456, "longitude": -45.678, "altitude": 418.2,
       "velocity": 27580.5, "visibility": "daylight", "timestamp": 1759561200}
OPEN_NOTIFY = {"message": "success", "timestamp": 1759561200,
               "iss_position": {"latitude": "-10.5", "longitude": "100.25"}}


def test_parsers():
    u = parse_upbit(UPBIT)
    assert u['price'] == 142350000.0 and abs(u['chg24'] + 1.23) < 1e-9 and u['ts'] == 1759561200.0
    b = parse_binance(BINANCE)
    assert abs(b['price'] - 4512.37) < 1e-9 and abs(b['chg24'] - 2.315) < 1e-9
    c = parse_coinbase(COINBASE)
    assert abs(c['price'] - 234.7) < 1e-9 and abs(c['chg24'] - (234.7 - 230.1) / 230.1 * 100) < 1e-9
    t = parse_bithumb(BITHUMB)
    assert t['price'] == 142000000.0 and abs(t['chg24'] - 0.71) < 1e-9
    i = parse_iss(ISS)
    assert i['lat'] == 12.3456 and i['alt'] == 418.2 and i['day'] == 1.0
    o = parse_iss(OPEN_NOTIFY)
    assert o['lat'] == -10.5 and o['lon'] == 100.25 and o['alt'] is None


@pytest.mark.parametrize('fn,data', [
    (parse_upbit, {"error": {"name": "404", "message": "Code not found"}}),
    (parse_upbit, []),
    (parse_binance, {"code": -1121, "msg": "Invalid symbol."}),
    (parse_coinbase, {"message": "NotFound"}),
    (parse_bithumb, {"status": "5500", "message": "Invalid Parameter"}),
    (parse_iss, {"error": "rate limited"}),
])
def test_parser_errors(fn, data):
    with pytest.raises(ValueError):
        fn(data)


def test_symbol_normalization():
    assert PROVIDERS['upbit'].normalize_symbol('btc') == 'KRW-BTC'
    assert PROVIDERS['upbit'].normalize_symbol('KRW-ETH') == 'KRW-ETH'
    assert PROVIDERS['binance'].normalize_symbol('eth') == 'ETHUSDT'
    assert PROVIDERS['binance'].normalize_symbol('ETH-USDT') == 'ETHUSDT'
    assert PROVIDERS['coinbase'].normalize_symbol('sol') == 'SOL-USD'
    assert PROVIDERS['bithumb'].normalize_symbol('xrp') == 'XRP_KRW'
    assert PROVIDERS['upbit'].normalize_symbol('') == 'KRW-BTC'
    assert PROVIDERS['binance'].build_urls('btc')[1].endswith('symbol=BTCUSDT')


def test_feed_state_metrics():
    f = FeedState(1, 'upbit', 'btc', window=10)
    prices = [100, 100.1, 100.05, 100.3, 100.2, 100.6, 100.9, 100.7, 101.2, 101.5]
    for k, p in enumerate(prices):
        f.update({'price': p, 'chg24': 1.0}, now=k)
    assert f.ticks == 10
    assert abs(f.ret - math.log(101.5 / 101.2) * 1e4) < 1e-9
    assert f.up == 1
    assert f.norm == 1.0                   # 창 안에서 최고가
    assert 0 < f.z < 1                     # 평균보다 위
    assert f.vol > 0 and -1 < f.mom < 1
    assert f.mom > 0                       # 상승 추세
    f.update({'price': 100.0, 'chg24': 0.5}, now=11)
    assert f.up == -1 and f.ret < 0 and f.act > 0.5   # 큰 하락 틱 → act 튐
    a = f.act
    f.smooth(1.0, tau=0.4, release=0.6)
    assert f.act < a                       # 감쇠
    assert f.z_s != 0
    names = [k for k, _ in f.values('feed1')]
    assert 'feed1/zs' in names and 'feed1/price' in names


def test_feed_state_rejects_bad_price():
    f = FeedState(1)
    with pytest.raises(ValueError):
        f.update({'price': float('nan')})
    with pytest.raises(ValueError):
        f.update({'price': 0})


def test_reconfigure_resets_only_when_symbol_changes():
    f = FeedState(1, 'upbit', 'KRW-BTC')
    f.update({'price': 1.0})
    f.configure('upbit', 'btc')        # 같은 심볼(정규화 후) → 유지
    assert f.ticks == 1
    f.configure('upbit', 'eth')
    assert f.ticks == 0 and f.symbol == 'KRW-ETH'


def test_sim_source_moves():
    s = SimSource(seed=1)
    ps = [s.sample()['price'] for _ in range(50)]
    assert len(set(ps)) > 40 and all(p > 0 for p in ps)


def test_space_state():
    sp = SpaceState()
    sp.update(parse_iss(ISS), now=5)
    d = dict(sp.values(now=6))
    assert abs(d['iss/latn'] - 12.3456 / 51.64) < 1e-9 and d['iss/age'] == 1 and d['iss/ok'] == 1
    sp.update(parse_iss(OPEN_NOTIFY))          # 고도 없음 → 이전 값 유지
    assert sp.alt == 418.2 and len(sp.track) == 2

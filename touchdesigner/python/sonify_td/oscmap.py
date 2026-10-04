"""에이블톤(AbletonOSC 등)으로 보낼 '매핑' 표.

표의 각 행: active | source | address | args | inmin | inmax | outmin | outmax
  source : 엔진 값 이름 (예: scan/lum, feed1/zs, iss/latn) — README 의 채널 표 참조
  address: 보낼 OSC 주소 (예: /live/device/set/parameter/value)
  args   : 값 앞에 붙일 고정 인자 (공백 구분, 예: "0 1 3" = 트랙0 디바이스1 파라미터3)
  in/out : source 값을 inmin..inmax → outmin..outmax 로 직선 변환(잘라냄)
"""

HEADER = ['active', 'source', 'address', 'args', 'inmin', 'inmax', 'outmin', 'outmax']

# 기본 예시 행은 전부 비활성(active=0). AbletonOSC 를 켜고 원하는 행만 1 로 바꾼다.
DEFAULT_ROWS = [
    ['0', 'scan/lumn', '/live/device/set/parameter/value', '0 0 1', '0', '1', '0', '1'],
    ['0', 'scan/centroidn', '/live/device/set/parameter/value', '0 0 2', '0', '1', '0', '1'],
    ['0', 'scan/edgen', '/live/track/set/send', '0 0', '0', '1', '0', '0.8'],
    ['0', 'feed1/zs', '/live/track/set/volume', '1', '-1', '1', '0.45', '0.85'],
    ['0', 'feed2/moms', '/live/track/set/panning', '2', '-1', '1', '-1', '1'],
    ['0', 'feed3/act', '/live/track/set/volume', '3', '0', '1', '0', '0.85'],
    ['0', 'iss/latn', '/live/device/set/parameter/value', '4 0 1', '-1', '1', '0', '1'],
]


def _num(s, default):
    try:
        return float(s)
    except (TypeError, ValueError):
        return default


def _arg(tok):
    try:
        return int(tok)
    except ValueError:
        try:
            return float(tok)
        except ValueError:
            return tok


def parse_rows(rows):
    """rows: 문자열 리스트의 리스트(첫 행이 헤더면 건너뜀). 잘못된 행은 건너뛰고 오류 목록을 같이 돌려준다."""
    out, errors = [], []
    for n, row in enumerate(rows):
        cells = [str(c).strip() for c in row] + [''] * 8
        if n == 0 and cells[0].lower() == 'active':
            continue
        if not any(cells[:8]):
            continue
        active, source, address, args = cells[0], cells[1], cells[2], cells[3]
        if not source or not address.startswith('/'):
            errors.append('row %d: source/address 확인' % n)
            continue
        inmin, inmax = _num(cells[4], 0.0), _num(cells[5], 1.0)
        if inmax == inmin:
            errors.append('row %d: inmin == inmax' % n)
            continue
        out.append({
            'active': active not in ('', '0', 'false', 'False', 'off'),
            'source': source.lstrip('/'),
            'address': address,
            'args': [_arg(t) for t in args.split()],
            'inmin': inmin, 'inmax': inmax,
            'outmin': _num(cells[6], 0.0), 'outmax': _num(cells[7], 1.0),
        })
    return out, errors


def apply(row, value):
    t = (value - row['inmin']) / (row['inmax'] - row['inmin'])
    t = min(1.0, max(0.0, t))
    return row['outmin'] + t * (row['outmax'] - row['outmin'])

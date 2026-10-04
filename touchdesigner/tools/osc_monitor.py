"""OSC 수신 모니터 — 에이블톤 없이 TD 가 보내는 값을 확인한다.

    python3 touchdesigner/tools/osc_monitor.py              # 9000 번 포트, 주소별 최신값 표
    python3 touchdesigner/tools/osc_monitor.py 9000 --raw   # 들어오는 메시지를 그대로 출력
    python3 touchdesigner/tools/osc_monitor.py 11000        # AbletonOSC 매핑 출력 확인(Live 를 끈 상태에서)

같은 포트를 Max/에이블톤이 이미 쓰고 있으면 열 수 없다(한 포트는 한 프로그램만).
"""
import argparse
import os
import socket
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'python'))
from sonify_td.osc import decode_packet  # noqa: E402


def fmt(args, width=60):
    parts = []
    for a in args:
        parts.append('%.4f' % a if isinstance(a, float) else repr(a) if isinstance(a, str) else str(a))
    s = ' '.join(parts)
    return s if len(s) <= width else s[:width - 3] + '...'


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('port', nargs='?', type=int, default=9000)
    ap.add_argument('--host', default='0.0.0.0')
    ap.add_argument('--raw', action='store_true', help='메시지를 받는 대로 출력')
    ap.add_argument('--filter', default='', help='주소에 이 문자열이 있는 것만')
    ap.add_argument('--seconds', type=float, default=0, help='이 시간 후 종료(0 = 계속)')
    a = ap.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((a.host, a.port))
    sock.settimeout(0.2)
    print('OSC 수신 대기 %s:%d  (Ctrl+C 로 종료)' % (a.host, a.port))
    latest, counts = {}, {}
    t0 = last_draw = time.time()
    total = 0
    try:
        while not a.seconds or time.time() - t0 < a.seconds:
            try:
                data, src = sock.recvfrom(65535)
                for addr, args in decode_packet(data):
                    if a.filter and a.filter not in addr:
                        continue
                    total += 1
                    latest[addr] = args
                    counts[addr] = counts.get(addr, 0) + 1
                    if a.raw:
                        print('%s %s' % (addr, fmt(args, 200)))
            except socket.timeout:
                pass
            except ValueError as e:
                print('해석 실패:', e)
            if not a.raw and time.time() - last_draw > 0.5:
                last_draw = time.time()
                el = max(1e-6, last_draw - t0)
                lines = ['\x1b[2J\x1b[H%d 메시지, %.0f msg/s, 주소 %d 개' % (total, total / el, len(latest))]
                for addr in sorted(latest):
                    lines.append('%-34s %6.1f/s  %s' % (addr, counts[addr] / el, fmt(latest[addr])))
                print('\n'.join(lines), flush=True)
    except KeyboardInterrupt:
        pass
    finally:
        sock.close()
    return latest


if __name__ == '__main__':
    main()

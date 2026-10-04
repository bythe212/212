"""OSC 1.0 인코더/디코더와 UDP 송신기.

TouchDesigner 의 OSC Out 연산자에 의존하지 않고 순수 파이썬으로 구현해서,
TD 밖(테스트, 모니터 도구)에서도 똑같이 동작한다.
"""
import math
import socket
import struct

INT32_MIN = -(2 ** 31)
INT32_MAX = 2 ** 31 - 1


def _pad(b):
    """OSC 문자열/블롭은 4바이트 경계로 0 패딩한다."""
    return b + b'\x00' * ((4 - len(b) % 4) % 4)


def _osc_string(s):
    return _pad(s.encode('utf-8') + b'\x00')


def _normalize_arg(a):
    """numpy 스칼라·bool 등을 OSC 가 아는 파이썬 타입으로 바꾼다."""
    if isinstance(a, bool):
        return int(a)
    if isinstance(a, (int, float, str, bytes)):
        return a
    # numpy.float32, numpy.int64 등
    if hasattr(a, 'item'):
        return _normalize_arg(a.item())
    return float(a)


def encode_message(address, args=()):
    if not address.startswith('/'):
        raise ValueError('OSC 주소는 / 로 시작해야 합니다: %r' % address)
    if isinstance(args, (str, bytes)) or not hasattr(args, '__iter__'):
        args = (args,)
    tags = ','
    payload = b''
    for a in args:
        a = _normalize_arg(a)
        if isinstance(a, int):
            if INT32_MIN <= a <= INT32_MAX:
                tags += 'i'
                payload += struct.pack('>i', a)
            else:
                tags += 'f'
                payload += struct.pack('>f', float(a))
        elif isinstance(a, float):
            if not math.isfinite(a):
                a = 0.0  # NaN/inf 는 수신 측(Max, Live)을 망가뜨리므로 0 으로
            tags += 'f'
            payload += struct.pack('>f', a)
        elif isinstance(a, str):
            tags += 's'
            payload += _osc_string(a)
        elif isinstance(a, bytes):
            tags += 'b'
            payload += struct.pack('>i', len(a)) + _pad(a)
        else:
            raise TypeError('지원하지 않는 OSC 인자: %r' % (a,))
    return _osc_string(address) + _osc_string(tags) + payload


def encode_bundle(messages, timetag=1):
    """messages: 이미 인코딩된 메시지(bytes) 목록. timetag 1 = 즉시."""
    out = _osc_string('#bundle') + struct.pack('>Q', timetag)
    for m in messages:
        out += struct.pack('>i', len(m)) + m
    return out


def _read_string(data, i):
    end = data.index(b'\x00', i)
    s = data[i:end].decode('utf-8', 'replace')
    i = end + 1
    i += (4 - i % 4) % 4
    return s, i


def decode_message(data):
    """(address, [args]) 를 돌려준다."""
    address, i = _read_string(data, 0)
    if i >= len(data):
        return address, []
    tags, i = _read_string(data, i)
    args = []
    for t in tags[1:]:
        if t == 'i':
            args.append(struct.unpack('>i', data[i:i + 4])[0]); i += 4
        elif t == 'f':
            args.append(struct.unpack('>f', data[i:i + 4])[0]); i += 4
        elif t == 'd':
            args.append(struct.unpack('>d', data[i:i + 8])[0]); i += 8
        elif t == 'h':
            args.append(struct.unpack('>q', data[i:i + 8])[0]); i += 8
        elif t == 's':
            s, i = _read_string(data, i); args.append(s)
        elif t == 'b':
            n = struct.unpack('>i', data[i:i + 4])[0]; i += 4
            args.append(data[i:i + n]); i += n + (4 - n % 4) % 4
        elif t == 'T':
            args.append(True)
        elif t == 'F':
            args.append(False)
        elif t == 'N':
            args.append(None)
        else:
            raise ValueError('알 수 없는 OSC 타입 태그: %r' % t)
    return address, args


def decode_packet(data):
    """메시지 또는 번들을 풀어서 [(address, args), ...] 로."""
    if data.startswith(b'#bundle\x00'):
        out = []
        i = 16
        while i < len(data):
            n = struct.unpack('>i', data[i:i + 4])[0]
            out.extend(decode_packet(data[i + 4:i + 4 + n]))
            i += 4 + n
        return out
    return [decode_message(data)]


class OscSender:
    """논블로킹 UDP OSC 송신기. 실패해도 예외를 던지지 않고 last_error 에 남긴다."""

    MAX_BUNDLE = 1400  # 이더넷 MTU 안쪽으로 번들을 쪼갠다

    def __init__(self, host='127.0.0.1', port=9000):
        self.sock = None
        self.addr = None
        self.host = None
        self.port = None
        self.sent = 0
        self.errors = 0
        self.last_error = None
        self.configure(host, port)

    def configure(self, host, port):
        host = (host or '127.0.0.1').strip()
        port = int(port)
        if (host, port) == (self.host, self.port) and self.addr:
            return
        self.host, self.port = host, port
        self.addr = None
        try:
            info = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_DGRAM)
            self.addr = info[0][4]
            if self.sock is None:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                self.sock.setblocking(False)
            self.last_error = None
        except (OSError, ValueError) as e:
            self.last_error = 'host %s: %s' % (host, e)

    @property
    def ok(self):
        return self.addr is not None and self.last_error is None

    def _send_raw(self, packet):
        if self.addr is None:
            return False
        try:
            self.sock.sendto(packet, self.addr)
            self.last_error = None
            return True
        except OSError as e:
            # 수신 측이 없을 때 일부 OS 는 ECONNREFUSED 를 돌려준다 — 무시하고 기록만.
            self.errors += 1
            self.last_error = str(e)
            return False

    def send(self, address, *args):
        if self._send_raw(encode_message(address, args)):
            self.sent += 1

    def send_many(self, messages, bundle=False):
        """messages: [(address, args), ...]"""
        encoded = [encode_message(a, args) for a, args in messages]
        if not bundle:
            for m in encoded:
                if self._send_raw(m):
                    self.sent += 1
            return
        chunk, size = [], 16
        for m in encoded:
            if chunk and size + 4 + len(m) > self.MAX_BUNDLE:
                if self._send_raw(encode_bundle(chunk)):
                    self.sent += len(chunk)
                chunk, size = [], 16
            chunk.append(m)
            size += 4 + len(m)
        if chunk and self._send_raw(encode_bundle(chunk)):
            self.sent += len(chunk)

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
        self.sock = None
        self.addr = None

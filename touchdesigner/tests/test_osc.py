import struct

import numpy as np

from sonify_td.osc import OscSender, decode_message, decode_packet, encode_bundle, encode_message


def test_encode_matches_spec():
    # OSC 1.0 스펙 예시: "/oscillator/4/frequency" ,f 440.0
    m = encode_message('/oscillator/4/frequency', [440.0])
    assert m == (b'/oscillator/4/frequency\x00' + b',f\x00\x00' + struct.pack('>f', 440.0))
    assert len(m) % 4 == 0


def test_roundtrip_types():
    m = encode_message('/a', [1, 2.5, 'hi', b'\x01\x02\x03', True, np.float32(0.25), np.int64(7)])
    addr, args = decode_message(m)
    assert addr == '/a'
    assert args[0] == 1 and abs(args[1] - 2.5) < 1e-6 and args[2] == 'hi' and args[3] == b'\x01\x02\x03'
    assert args[4] == 1 and abs(args[5] - 0.25) < 1e-6 and args[6] == 7


def test_nan_and_big_int_are_safe():
    _, args = decode_message(encode_message('/x', [float('nan'), 2 ** 40]))
    assert args[0] == 0.0
    assert abs(args[1] - 2 ** 40) / 2 ** 40 < 1e-6


def test_bundle_decode():
    b = encode_bundle([encode_message('/a', [1]), encode_message('/b', ['x'])])
    assert decode_packet(b) == [('/a', [1]), ('/b', ['x'])]


def test_sender_udp(udp_listener):
    port, recv_all = udp_listener
    s = OscSender('127.0.0.1', port)
    s.send('/one', 1.0)
    s.send_many([('/two', [2]), ('/three', [3, 'x'])])
    s.send_many([('/b%d' % i, [float(i)] * 40) for i in range(20)], bundle=True)  # 여러 번들로 쪼개짐
    got = recv_all()
    addrs = [a for a, _ in got]
    assert addrs[:3] == ['/one', '/two', '/three']
    assert addrs[3:] == ['/b%d' % i for i in range(20)]
    assert s.sent == 23
    s.close()


def test_sender_bad_host_does_not_raise():
    s = OscSender('no-such-host.invalid', 9000)
    s.send('/x', 1)
    assert not s.ok
    assert s.last_error

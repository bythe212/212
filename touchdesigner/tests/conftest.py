import os
import socket
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
TD_DIR = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(TD_DIR, 'python'))


@pytest.fixture
def udp_listener():
    """로컬 UDP 수신 소켓 (port, recv_all)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('127.0.0.1', 0))
    sock.settimeout(0.3)

    def recv_all():
        from sonify_td.osc import decode_packet
        out = []
        while True:
            try:
                data, _ = sock.recvfrom(65535)
            except socket.timeout:
                return out
            out.extend(decode_packet(data))

    yield sock.getsockname()[1], recv_all
    sock.close()


@pytest.fixture
def td_dir():
    return TD_DIR

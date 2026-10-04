import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from sonify_td.poller import Job, Poller


class Handler(BaseHTTPRequestHandler):
    hits = []

    def do_GET(self):
        Handler.hits.append((self.path, self.headers.get('User-Agent')))
        if self.path.startswith('/ok'):
            body, code = json.dumps({'price': 42}).encode(), 200
        elif self.path.startswith('/blocked'):
            body, code = b'{"code":0,"msg":"restricted location"}', 451
        elif self.path.startswith('/limit'):
            body, code = b'{}', 429
        else:
            body, code = b'not json', 200
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


@pytest.fixture
def server():
    srv = HTTPServer(('127.0.0.1', 0), Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    Handler.hits = []
    yield 'http://127.0.0.1:%d' % srv.server_address[1]
    srv.shutdown()


def wait_for(poller, n, timeout=3.0):
    got = []
    end = time.time() + timeout
    while len(got) < n and time.time() < end:
        got += poller.drain()
        time.sleep(0.02)
    return got


def parse(d):
    return {'price': float(d['price'])}


def test_fallback_url_and_errors(server):
    jobs = [
        Job('feed1', [server + '/blocked', server + '/ok'], parse, interval=0.2),   # 451 → 대체 URL 성공
        Job('feed2', [server + '/garbage'], parse, interval=0.2),                   # 해석 실패
        Job('feed3', ['http://127.0.0.1:1/x'], parse, interval=0.2),                # 연결 실패
    ]
    p = Poller(jobs, timeout=1.0).start()
    got = wait_for(p, 6)
    p.stop(join_timeout=2.0)
    by = {}
    for r in got:
        by.setdefault(r['job'], r)
    assert by['feed1']['ok'] and by['feed1']['data'] == {'price': 42.0} and by['feed1']['url'].endswith('/ok')
    assert not by['feed2']['ok'] and '해석' in by['feed2']['error']
    assert not by['feed3']['ok'] and '연결' in by['feed3']['error']
    assert all(ua and ua.startswith('sonify-td') for _, ua in Handler.hits)
    assert not p.alive


def test_rate_limit_backoff(server):
    p = Poller([Job('feed1', [server + '/limit'], parse, interval=0.2)], timeout=1.0).start()
    time.sleep(1.2)
    p.stop(join_timeout=2.0)
    got = p.drain()
    assert got and got[0]['status'] == 429 and '요청 한도' in got[0]['error']
    # 0.2s 간격이면 6번 이상이지만, 백오프(0.2→0.4→0.8) 때문에 훨씬 적어야 한다
    assert len(Handler.hits) <= 4


def test_sim_source_job():
    n = [0]

    def src():
        n[0] += 1
        return {'price': 100.0 + n[0]}

    p = Poller([Job('feed1', [], None, interval=0.2, source=src)]).start()
    got = wait_for(p, 2)
    p.stop(join_timeout=1.0)
    assert len(got) >= 2 and got[0]['ok'] and got[0]['url'] == 'sim'

"""백그라운드 HTTP 폴러.

TD 의 메인 스레드(쿡)를 절대 막지 않도록, API 하나당 데몬 스레드 하나가
주기적으로 요청하고 결과를 큐에 넣는다. 메인 스레드는 매 프레임 drain() 으로 꺼내 쓴다.
스레드 안에서는 TD 객체를 건드리지 않는다.
"""
import json
import queue
import ssl
import threading
import time
import urllib.error
import urllib.request

USER_AGENT = 'sonify-td/0.1 (+TouchDesigner data sonification)'


def _ssl_context(verify=True):
    if not verify:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    try:
        import certifi  # TD 에 들어 있으면 그 인증서 묶음을 쓴다
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _is_cert_error(e):
    if isinstance(e, ssl.SSLCertVerificationError):
        return True
    reason = getattr(e, 'reason', None)
    return isinstance(reason, ssl.SSLCertVerificationError) or 'CERTIFICATE_VERIFY_FAILED' in str(e)


class Job:
    """name: 결과를 받을 슬롯 이름, urls: 시도 순서, parse: JSON → dict, interval: 초.
    source: urls 대신 호출할 함수(시뮬레이션용)."""

    def __init__(self, name, urls, parse, interval=1.0, source=None):
        self.name = name
        self.urls = list(urls)
        self.parse = parse
        self.interval = max(0.2, float(interval))
        self.source = source


class _Worker(threading.Thread):
    def __init__(self, poller, job):
        super().__init__(name='sonify-' + job.name, daemon=True)
        self.poller = poller
        self.job = job
        self.insecure = False   # auto 모드에서 인증서 검증을 끈 상태인지
        self.backoff = 1.0

    def run(self):
        stop = self.poller._stop
        while not stop.is_set():
            t0 = time.monotonic()
            result = self.fetch_once()
            if stop.is_set():
                break
            self.poller.results.put(result)
            if result['ok']:
                self.backoff = 1.0
            elif result.get('status') == 429:
                self.backoff = min(self.backoff * 2.0, 30.0)  # 요청 한도 초과 → 점점 느리게
            else:
                self.backoff = min(self.backoff * 1.5, 10.0)
            wait = self.job.interval * self.backoff - (time.monotonic() - t0)
            stop.wait(max(0.05, wait))

    def _get(self, url, verify):
        req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT, 'Accept': 'application/json'})
        with urllib.request.urlopen(req, timeout=self.poller.timeout, context=_ssl_context(verify)) as r:
            return json.loads(r.read().decode('utf-8'))

    def fetch_once(self):
        job = self.job
        t0 = time.monotonic()
        base = {'job': job.name, 'ok': False, 'data': None, 'error': None, 'url': None,
                'status': None, 'latency': None, 'time': time.time(), 'insecure': False}
        if job.source is not None:
            try:
                base.update(ok=True, data=job.source(), url='sim', latency=0.0)
            except Exception as e:
                base['error'] = 'sim: %s' % e
            return base

        mode = self.poller.ssl_mode
        errors = []
        for url in job.urls:
            verify = mode == 'verify' or (mode == 'auto' and not self.insecure)
            try:
                try:
                    raw = self._get(url, verify)
                except Exception as e:
                    # macOS 의 TD 파이썬은 CA 인증서를 못 찾는 경우가 있다 → auto 면 검증 없이 재시도
                    if verify and mode == 'auto' and url.startswith('https') and _is_cert_error(e):
                        raw = self._get(url, False)
                        self.insecure = True
                    else:
                        raise
                data = job.parse(raw)
                base.update(ok=True, data=data, url=url, latency=time.monotonic() - t0,
                            insecure=self.insecure and url.startswith('https'))
                return base
            except urllib.error.HTTPError as e:
                base['status'] = e.code
                hint = {451: ' (지역 차단)', 429: ' (요청 한도)', 403: ' (차단)', 404: ' (심볼 확인)', 400: ' (심볼 확인)'}
                errors.append('HTTP %d%s' % (e.code, hint.get(e.code, '')))
            except urllib.error.URLError as e:
                if _is_cert_error(e):
                    errors.append('SSL 인증서 오류 → Sslmode=auto/off')
                else:
                    errors.append('연결 실패: %s' % (e.reason,))
            except (ValueError, KeyError, TypeError, IndexError) as e:
                errors.append('응답 해석 실패: %s' % e)
            except Exception as e:  # 타임아웃, 소켓 오류 등
                errors.append('%s: %s' % (type(e).__name__, e))
        base['error'] = ' / '.join(errors) or 'URL 없음'
        base['latency'] = time.monotonic() - t0
        return base


class Poller:
    def __init__(self, jobs, ssl_mode='auto', timeout=4.0):
        self.jobs = list(jobs)
        self.ssl_mode = ssl_mode if ssl_mode in ('verify', 'auto', 'off') else 'auto'
        self.timeout = timeout
        self.results = queue.Queue()
        self._stop = threading.Event()
        self.workers = []

    def start(self):
        for job in self.jobs:
            w = _Worker(self, job)
            w.start()
            self.workers.append(w)
        return self

    def drain(self, limit=200):
        out = []
        for _ in range(limit):
            try:
                out.append(self.results.get_nowait())
            except queue.Empty:
                break
        return out

    def stop(self, join_timeout=0.0):
        self._stop.set()
        if join_timeout:
            for w in self.workers:
                w.join(join_timeout)

    @property
    def alive(self):
        return any(w.is_alive() for w in self.workers)

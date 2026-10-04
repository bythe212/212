"""sonify_td — TouchDesigner 용 데이터/이미지 소니피케이션 코어 (TD 비의존 순수 파이썬)."""
import importlib
import sys

__version__ = '0.1.0'

_MODULES = ['osc', 'feeds', 'poller', 'music', 'image_scan', 'oscmap', 'font', 'render', 'engine']


def reload_all():
    """TD 에서 파일을 고친 뒤 다시 불러올 때 쓴다(의존 순서대로)."""
    for name in _MODULES:
        full = __name__ + '.' + name
        if full in sys.modules:
            importlib.reload(sys.modules[full])
        else:
            importlib.import_module(full)
    pkg = sys.modules[__name__]
    eng = sys.modules[__name__ + '.engine']
    for attr in ('SonifyEngine', 'DEFAULTS', 'MODES', 'OSC_MODES', 'SSL_MODES'):
        setattr(pkg, attr, getattr(eng, attr))
    return pkg


from .engine import SonifyEngine, DEFAULTS, MODES, OSC_MODES, SSL_MODES  # noqa: E402
from .feeds import PROVIDER_KEYS  # noqa: E402
from .music import SCALE_KEYS, NOTE_NAMES  # noqa: E402

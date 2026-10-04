"""Max for Live 수신 패치(.maxpat) 생성기.

    python3 touchdesigner/tools/make_maxpat.py  → touchdesigner/ableton/sonify_receive.maxpat

Ableton 에서 'Max MIDI Effect' 를 트랙에 넣고 편집(Max 열기) → 이 파일을 Max 에서 열어 전체 복사 → 붙여넣기.
  - /sonify/scan/trig (band note vel) → MIDI 노트 → 같은 트랙의 악기가 소리를 낸다 (별 = 음)
  - 연속값(lumn, centroidn, hue, edgen, note, feed*/zs ...) → 숫자 상자로 표시 (원하는 곳에 연결)
  - /sonify/scan/bandsn → 막대 미터
"""
import json
import os
import sys

SCALARS = [
    ('/sonify/scan/lumn', '밝기 0..1 (음량)'),
    ('/sonify/scan/centroidn', '밝기 무게중심 0..1 (음높이)'),
    ('/sonify/scan/hue', '색상 0..1 (음색)'),
    ('/sonify/scan/edgen', '경계/질감 0..1'),
    ('/sonify/scan/note', '주 음 (MIDI)'),
    ('/sonify/feed1/zs', '피드1 위치 -1..1'),
    ('/sonify/feed2/zs', '피드2 위치 -1..1'),
    ('/sonify/feed3/zs', '피드3 위치 -1..1'),
    ('/sonify/feed1/act', '피드1 큰 틱 0..1'),
    ('/sonify/iss/latn', 'ISS 위도 -1..1'),
]


class Patch:
    def __init__(self):
        self.boxes, self.lines, self.n = [], [], 0

    def box(self, maxclass, x, y, w, h, text=None, inlets=1, outlets=0, outlettype=None, **extra):
        self.n += 1
        oid = 'obj-%d' % self.n
        b = {'id': oid, 'maxclass': maxclass, 'numinlets': inlets, 'numoutlets': outlets,
             'patching_rect': [float(x), float(y), float(w), float(h)]}
        if outlets:
            b['outlettype'] = outlettype or [''] * outlets
        if text is not None:
            b['text'] = text
        b.update(extra)
        self.boxes.append({'box': b})
        return oid

    def obj(self, text, x, y, w=None, inlets=1, outlets=1, outlettype=None):
        return self.box('newobj', x, y, w or max(40, 7 * len(text) + 16), 22, text, inlets, outlets, outlettype)

    def comment(self, text, x, y, w=300):
        return self.box('comment', x, y, w, 20, text, 1, 0)

    def flonum(self, x, y):
        return self.box('flonum', x, y, 60, 22, None, 1, 2, ['', 'bang'], parameter_enable=0, format=6)

    def wire(self, a, ao, b, bi):
        self.lines.append({'patchline': {'source': [a, ao], 'destination': [b, bi]}})

    def dump(self):
        return {'patcher': {
            'fileversion': 1,
            'appversion': {'major': 8, 'minor': 6, 'revision': 0, 'architecture': 'x64', 'modernui': 1},
            'classnamespace': 'box', 'rect': [80.0, 80.0, 1040.0, 640.0],
            'bglocked': 0, 'openinpresentation': 0, 'default_fontsize': 12.0, 'default_fontface': 0,
            'default_fontname': 'Arial', 'gridonopen': 1, 'gridsize': [15.0, 15.0],
            'boxes': self.boxes, 'lines': self.lines,
        }}


def build():
    p = Patch()
    p.comment('Sonify OSC receiver - TouchDesigner -> UDP 9000 (Oscport). Max MIDI Effect 안에 붙여넣기', 20, 10, 600)
    port = p.box('number', 20, 40, 60, 22, None, 1, 2, ['', 'bang'], parameter_enable=0)
    pmsg = p.obj('prepend port', 90, 40, outlets=1)
    p.wire(port, 0, pmsg, 0)
    lb = p.obj('loadmess 9000', 20, 15 + 50, outlets=1)
    udp = p.obj('udpreceive 9000', 20, 100, outlets=1)
    p.wire(pmsg, 0, udp, 0)
    p.wire(lb, 0, port, 0)

    addrs = ['/sonify/scan/trig', '/sonify/scan/bandsn'] + [a for a, _ in SCALARS]
    route = p.obj('route ' + ' '.join(addrs), 20, 140, w=900, outlets=len(addrs) + 1)
    p.wire(udp, 0, route, 0)

    # 별(트리거) → MIDI 노트
    p.comment('/scan/trig = band note vel -> MIDI note', 20, 180, 320)
    un = p.obj('unpack 0 0 0.', 20, 205, outlets=3, outlettype=['int', 'int', 'float'])
    p.wire(route, 0, un, 0)
    mul = p.obj('* 127.', 120, 235, inlets=2, outlets=1)
    p.wire(un, 2, mul, 0)
    mk = p.obj('makenote 100 250', 20, 265, inlets=3, outlets=2, outlettype=['float', 'float'])
    p.wire(un, 1, mk, 0)
    p.wire(mul, 0, mk, 1)
    pk = p.obj('pack 0 0', 20, 295, inlets=2, outlets=1)
    p.wire(mk, 0, pk, 0)
    p.wire(mk, 1, pk, 1)
    mf = p.obj('midiformat', 20, 325, inlets=7, outlets=1, outlettype=['int'])
    p.wire(pk, 0, mf, 0)
    mo = p.obj('midiout', 20, 385, outlets=0)
    p.wire(mf, 0, mo, 0)
    mi = p.obj('midiin', 120, 355, outlets=1, outlettype=['int'])
    p.wire(mi, 0, mo, 0)
    p.comment('midiin -> midiout: 원래 MIDI 도 통과', 170, 355, 260)

    # 대역 미터
    p.comment('/scan/bandsn (아래 -> 위 대역 밝기, 0..1)', 360, 180, 300)
    ms = p.box('multislider', 360, 205, 260, 120, None, 1, 2, ['', ''],
               parameter_enable=0, size=24, setminmax=[0.0, 1.0], orientation=0)
    p.wire(route, 1, ms, 0)

    # 연속값
    for k, (addr, label) in enumerate(SCALARS):
        y = 205 + k * 30
        f = p.flonum(660, y)
        p.wire(route, 2 + k, f, 0)
        p.comment('%s  %s' % (addr, label), 725, y, 300)
    p.comment('나머지 주소는 오른쪽 끝 출구 (route 의 마지막 출구)', 660, 520, 340)
    pr = p.obj('print sonify-other', 660, 545, outlets=0)
    p.wire(route, len(addrs), pr, 0)
    return p.dump()


if __name__ == '__main__':
    here = os.path.dirname(os.path.abspath(__file__))
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, '..', 'ableton', 'sonify_receive.maxpat')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, 'w', encoding='utf-8') as fh:
        json.dump(build(), fh, ensure_ascii=False, indent=1)
    print(out)

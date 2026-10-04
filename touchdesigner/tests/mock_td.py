"""TouchDesigner 파이썬 API 의 최소 모의(mock).

빌드 스크립트·확장·콜백이 쓰는 API 만 흉내 낸다. 목적은 파이썬 수준의 버그(오타, 호출 순서,
로직)를 TD 없이 잡는 것이다. 파라미터 이름이 실제 TD 에 있는지는 확인하지 못한다(관대하게 만든다).
"""
import sys
import types

import numpy as np

FAMILIES = ('COMP', 'TOP', 'CHOP', 'DAT', 'SOP', 'MAT')
# 실제 TD 메뉴 항목 (일부)
MENUS = {
    'outputresolution': ['useinput', 'eighth', 'quarter', 'half', '2x', '4x', '8x', 'fit', 'limit', 'custom'],
    'format': ['useinput', 'rgba8fixed', 'srgba8fixed', 'rgba16float', 'rgba32float'],
}
SPECIAL_NAMES = {'parameterexecute': 'parexec'}


class PanelValue:
    def __init__(self, val=0.0):
        self.val = val


class Par:
    def __init__(self, owner, name, val=None, style='Float', custom=False):
        self.owner = owner
        self.name = name
        self._val = val
        self.expr = None
        self.style = style
        self.custom = custom
        self.default = None
        self.normMin, self.normMax, self.min, self.max = 0.0, 1.0, 0.0, 1.0
        self.clampMin = self.clampMax = False
        self.menuNames, self.menuLabels = [], []
        self.help = ''
        self.readOnly = False
        self.pulses = 0

    @property
    def isPulse(self):
        return self.style == 'Pulse'

    @property
    def val(self):
        return self._val

    @val.setter
    def val(self, v):
        prev = self._val
        if self.style == 'Toggle':
            v = bool(v)
        elif self.style == 'Int':
            v = int(v)
        elif self.style == 'Float':
            v = float(v)
        self._val = v
        if self.custom and prev != v:
            self.owner._par_changed(self, prev)

    def eval(self):
        if self.expr:
            ctx = {'parent': lambda n=1: self.owner.parent(n), 'op': self.owner.op, 'me': self.owner}
            try:
                return eval(self.expr, ctx)
            except Exception:
                return self._val
        return self._val

    def pulse(self):
        self.pulses += 1
        self.owner._pulsed(self)


class ParCollection:
    def __init__(self, owner):
        object.__setattr__(self, '_owner', owner)
        object.__setattr__(self, '_pars', {})

    def __getattr__(self, name):
        pars = object.__getattribute__(self, '_pars')
        if name not in pars:
            if name[:1].isupper():                  # 커스텀 파라미터는 만든 것만 존재
                raise AttributeError(name)
            p = Par(object.__getattribute__(self, '_owner'), name, style='Any')
            p.menuNames = list(MENUS.get(name, []))
            pars[name] = p
        return pars[name]

    def __setattr__(self, name, value):
        getattr(self, name).val = value

    def _add(self, par):
        object.__getattribute__(self, '_pars')[par.name] = par


class Page:
    def __init__(self, owner, name):
        self.owner = owner
        self.name = name
        self.pars = []

    def _append(self, style, name, n=1, suffixes=None, default=None):
        out = []
        for i in range(n):
            pname = name + (suffixes[i] if suffixes else '')
            p = Par(self.owner, pname, default, style, custom=True)
            self.owner.par._add(p)
            self.pars.append(p)
            out.append(p)
        return tuple(out)

    def appendFloat(self, name, label=None):
        return self._append('Float', name, default=0.0)

    def appendInt(self, name, label=None):
        return self._append('Int', name, default=0)

    def appendStr(self, name, label=None):
        return self._append('Str', name, default='')

    def appendToggle(self, name, label=None):
        return self._append('Toggle', name, default=False)

    def appendPulse(self, name, label=None):
        return self._append('Pulse', name)

    def appendMenu(self, name, label=None):
        return self._append('Menu', name, default='')

    def appendFile(self, name, label=None):
        return self._append('File', name, default='')

    def appendFolder(self, name, label=None):
        return self._append('Folder', name, default='')

    def appendTOP(self, name, label=None):
        return self._append('TOP', name, default=None)

    def appendRGB(self, name, label=None):
        return self._append('Float', name, 3, ['r', 'g', 'b'], default=0.0)


class Connector:
    def __init__(self, owner, index):
        self.owner = owner
        self.index = index

    def connect(self, src):
        ins = self.owner.inputs
        while len(ins) <= self.index:
            ins.append(None)
        ins[self.index] = src


class Cell:
    def __init__(self, val):
        self.val = val


class Chan:
    def __init__(self, name, n):
        self.name = name
        self.vals = [0.0] * n

    def __setitem__(self, i, v):
        self.vals[i] = float(v)

    def __getitem__(self, i):
        return self.vals[i]


class OP:
    def __init__(self, optype, name, parent):
        self.OPType = optype
        self.name = name
        self._parent = parent
        self._children = {}
        self.par = ParCollection(self)
        self.tags = set()
        self.comment = ''
        self.nodeX = self.nodeY = 0
        self.color = (0.5, 0.5, 0.5)
        self.storage = {}
        self._text = ''
        self._module = None
        self._module_text = None
        self.inputs = []
        self.inputConnectors = [Connector(self, i) for i in range(4)]
        self.pages = []
        self.ext = types.SimpleNamespace()
        self.seq = types.SimpleNamespace(vec=types.SimpleNamespace(numBlocks=1),
                                         ext=types.SimpleNamespace(numBlocks=1))
        self.panel = types.SimpleNamespace(u=PanelValue(0.0), v=PanelValue(0.0), lselect=PanelValue(0))
        self._rows = []
        self._array = None
        self.width, self.height = 0, 0
        self.numSamples = 1
        self._chans = []
        self.cooks = 0
        self.destroyed = False

    # --- 경로/계층
    @property
    def path(self):
        if self._parent is None:
            return '/'
        pp = self._parent.path
        return (pp if pp != '/' else '') + '/' + self.name

    def parent(self, n=1):
        o = self
        for _ in range(n):
            o = o._parent
        return o

    @property
    def children(self):
        return list(self._children.values())

    def findChildren(self, depth=1):
        return self.children

    def _autoname(self, optype):
        base = optype
        for fam in FAMILIES:
            if base.endswith(fam):
                base = base[:-len(fam)]
                break
        base = SPECIAL_NAMES.get(base, base)
        i = 1
        while '%s%d' % (base, i) in self._children:
            i += 1
        return '%s%d' % (base, i)

    def create(self, optype, name=None):
        if not isinstance(optype, str):
            raise TypeError('optype')
        name = name or self._autoname(optype)
        if name in self._children:
            raise ValueError('name exists: ' + name)
        o = OP(optype, name, self)
        self._children[name] = o
        if optype in ('scriptCHOP', 'scriptTOP'):
            cb = self.create('textDAT', name + '_callbacks')
            o.par.callbacks._val = cb
        if optype == 'glslTOP':
            px = self.create('textDAT', name + '_pixel')
            self.create('textDAT', name + '_info')
            o.par.pixeldat._val = px
        if optype == 'containerCOMP':
            o.par.w._val, o.par.h._val = 100, 100
        return o

    def destroy(self):
        ext = getattr(self.ext, 'SonifyExt', None)
        if ext is not None and hasattr(ext, 'onDestroyTD'):
            ext.onDestroyTD()
        for c in self.children:
            c.destroy()
        if self._parent is not None:
            self._parent._children.pop(self.name, None)
        self.destroyed = True

    def op(self, path):
        if not path:
            return None
        if isinstance(path, OP):
            return path
        if path.startswith('/'):
            o = ROOT
            parts = [p for p in path.split('/') if p]
        else:
            o = self
            parts = [p for p in path.split('/') if p and p != '.']
        for p in parts:
            if o is None:
                return None
            o = o._parent if p == '..' else o._children.get(p)
        return o

    def errors(self, recurse=False):
        return ''

    def warnings(self, recurse=False):
        return ''

    # --- storage
    def store(self, key, value):
        self.storage[key] = value

    def fetch(self, key, default=None, search=True, storeDefault=False):
        return self.storage.get(key, default)

    # --- custom pars
    def appendCustomPage(self, name):
        pg = Page(self, name)
        self.pages.append(pg)
        return pg

    @property
    def customPars(self):
        return [p for pg in self.pages for p in pg.pars]

    def _par_changed(self, par, prev):
        hook = getattr(self, '_parexec', None)
        if hook is not None:
            hook.module.onValueChange(par, prev)

    def _pulsed(self, par):
        if par.name == 'reinitextensions':
            expr = self.par.extension1.val
            if expr:
                old = getattr(self.ext, 'SonifyExt', None)
                if old is not None and hasattr(old, 'onDestroyTD'):
                    old.onDestroyTD()
                self.ext.SonifyExt = eval(expr, {'op': self.op, 'me': self})
            return
        if par.custom:
            hook = getattr(self, '_parexec', None)
            if hook is not None:
                hook.module.onPulse(par)

    # --- DAT
    @property
    def text(self):
        if self.OPType == 'tableDAT':
            return '\n'.join('\t'.join(r) for r in self._rows)
        return self._text

    @text.setter
    def text(self, t):
        self._text = t

    @property
    def module(self):
        if self._module is None or self._module_text != self._text:
            m = types.ModuleType(self.name)
            m.__dict__.update({'me': self, 'parent': self.parent, 'op': self.op})
            exec(compile(self._text, self.name, 'exec'), m.__dict__)
            self._module, self._module_text = m, self._text
        return self._module

    def clear(self):
        if self.OPType == 'tableDAT':
            self._rows = []
        else:
            self._chans = []

    def appendRow(self, row):
        self._rows.append([str(c) for c in row])

    def rows(self):
        return [[Cell(c) for c in r] for r in self._rows]

    # --- TOP/CHOP
    def numpyArray(self, delayed=False):
        return self._array

    def copyNumpyArray(self, arr):
        assert arr.flags['C_CONTIGUOUS']
        self._array = np.array(arr)
        self.height, self.width = arr.shape[:2]

    def appendChan(self, name):
        c = Chan(name, self.numSamples)
        self._chans.append(c)
        return c

    def chans(self, *pattern):
        return list(self._chans)

    def cook(self, force=False):
        self.cooks += 1
        if self.OPType in ('scriptCHOP', 'scriptTOP'):
            self.par.callbacks.eval().module.onCook(self)


ROOT = OP('containerCOMP', '', None)
PROJECT = ROOT.create('containerCOMP', 'project1')


def install():
    """sys.modules['td'] 로 등록하고 모듈을 돌려준다."""
    mod = types.ModuleType('td')
    mod.op = ROOT.op
    mod.ROOT = ROOT
    mod.PROJECT = PROJECT

    def __getattr__(name):
        if name.endswith(FAMILIES):
            return name
        raise AttributeError(name)

    mod.__getattr__ = __getattr__
    sys.modules['td'] = mod
    return mod


def reset():
    for c in PROJECT.children:
        c.destroy()

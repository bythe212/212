# Sonify: 컨테이너 커스텀 파라미터가 바뀌거나 펄스가 눌리면 확장으로 넘긴다.

def _ext(par):
    return getattr(par.owner.ext, 'SonifyExt', None)


def onValueChange(par, prev):
    ext = _ext(par)
    if ext is not None:
        ext.OnParChange(par)
    return


def onPulse(par):
    ext = _ext(par)
    if ext is not None:
        ext.OnPulse(par)
    return


def onExpressionChange(par, val, prev):
    return


def onExportChange(par, val, prev):
    return


def onEnableChange(par, val, prev):
    return


def onModeChange(par, val, prev):
    return

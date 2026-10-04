# Sonify: 엔진 값을 CHOP 채널로 꺼낸다. GROUP 은 빌드 스크립트가 채운다.
GROUP = '{group}'


def onSetupParameters(scriptOp):
    return


def onPulse(par):
    return


def onCook(scriptOp):
    ext = getattr(scriptOp.parent().ext, 'SonifyExt', None)
    if ext is None:
        scriptOp.clear()
        return
    ext.FillChop(scriptOp, GROUP)
    return

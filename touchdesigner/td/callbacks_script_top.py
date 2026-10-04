# Sonify: 대시보드 오버레이(그래프·글자)를 numpy 로 그려 TOP 으로 보낸다.

def onSetupParameters(scriptOp):
    return


def onPulse(par):
    return


def onCook(scriptOp):
    ext = getattr(scriptOp.parent().ext, 'SonifyExt', None)
    if ext is not None:
        ext.RenderOverlay(scriptOp)
    return

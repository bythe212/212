# Sonify: 매 프레임 엔진을 한 번 돌린다 (SonifyExt.Tick).

def onFrameStart(frame):
    ext = getattr(me.parent().ext, 'SonifyExt', None)
    if ext is not None:
        ext.Tick()
    return

# TD MCP 작업 지시서 (로컬 Claude 세션용)

이 저장소의 `touchdesigner/`는 클라우드 세션에서 만들었다. 그 세션은 TouchDesigner에 연결할 수 없었다.
그래서 **실제 TD에서 한 번도 실행되지 않았다.** 파이썬 로직은 `tests/`의 모의 TD 환경에서 검증했다(51개 테스트 통과). GLSL은 glslang으로 컴파일만 확인했다.
TD MCP가 연결된 로컬 세션에서 아래 순서로 빌드하고 검증한다. `td-workflow` 스킬 규칙을 따른다(한 스크립트로 빌드, 숫자 먼저 확인, 이미지는 마지막에 한 번).

## 0. 준비
- 저장소 경로를 확인한다. `get_device_info`의 `connectedFolders` 또는 사용자에게 묻는다. 아래에서 `<DIR>`은 `.../212/touchdesigner`다.
- 브랜치: `claude/jolly-wozniak-h79x96`

## 1. 빌드 (execute_python_script 한 번)
```python
SONIFY_DIR = r'<DIR>'; exec(open(SONIFY_DIR + '/build_sonify.py', encoding='utf-8').read())
```
출력 JSON 보는 법:
- `fatal` — 경로나 import 문제다.
- `rep` — 반드시 고칠 것. 대부분 TD 버전별 파라미터 이름 차이다.
- `soft` — 부가 설정이라 무시해도 된다.
- `node_errors` — 노드 에러.

빌드는 멱등이다. 같은 줄을 다시 실행해도 된다. 타임아웃이 나면 재실행 전에 `/project1` children부터 확인한다.

## 2. 검증 (몇 프레임 뒤, 별도 호출)
```python
SONIFY_DIR = r'<DIR>'; exec(open(SONIFY_DIR + '/td/verify_sonify.py', encoding='utf-8').read())
```
기대값:
- `ext.error` 가 None, `ext.engine` 가 True, `node_errors` 가 비어 있음
- `tops.source.res`가 (1024, 512)이다(기본 이미지). `tops.analysis.res`는 (512, 256)이다.
- `tops.overlay.res`는 (1280, 720)이고 `alpha_mean`은 약 0.57이다(이미지 영역만 투명).
- `tops.out.res`는 (1280, 720)이고, `rgb_mean`은 0보다 크며 NaN이 없다.
- `scan.chans.pos`가 시간에 따라 증가하고, `bands.samples`는 24다.
- `status`에서 feed1~3과 iss가 `ok`다. `ERR`이면 오류 문자열을 본다.
- `engine.palette`에 색이 5개 있다.

## 3. 실제 TD에서 확인 못 한 API
문서 사이트(docs.derivative.ca)는 클라우드 세션에서 막혀 있었다. 그래서 웹 검색 요약으로 확인할 수 있는 만큼만 확인했다.

| 위치 | 가정 | 검색으로 확인 | 틀리면 |
|---|---|---|---|
| 이미지 방향 | `numpyArray()`는 왼쪽 아래 원점(0행 = 아래). 분석 대역 0 = 아래, 오버레이는 뒤집어서 `copyNumpyArray` | ✅ (Derivative OpenCV 문서: TD는 bottom/left 기준) | 글자가 뒤집히면 `Overlayflip` 끄기 |
| Script TOP | `copyNumpyArray(arr)`, uint8/uint16/float32, (h, w, c) | ✅ | |
| GLSL 유니폼 | `vec{i}name`, `vec{i}value{x..w}` + `glsl.seq.vec.numBlocks` | 이름 ✅ / `seq.vec` 미확인 | `rep`의 SET glsl1.vec… → `[p.name for p in g.pars() if 'vec' in p.name][:12]` |
| Parameter Execute | OP=`..`, Parameters=`*`, Built-In 끄기, 콜백 `onValueChange`/`onPulse` | 동작 ✅ / 파이썬 이름(`op` `pars` `custom` `builtin` `valuechange` `onpulse`) 미확인 | 컨트롤이 안 먹으면 확인 |
| Execute DAT | `framestart` | ✅ | |
| Window COMP | `winop`, `winw`, `winh`, `winopen.pulse()` | ✅ | |
| Container 배경 | `top` (Background TOP), 채우기 `topfill` | ✅ | |
| Parameter COMP | `op`, `builtin`, `custom`, `pagenames` | `builtin` `custom` `pagenames` ✅ / `op` 미확인 | 패널이 비면 `op` 이름 확인 |
| 확장 | `extension1`, `promoteextension1`, `extname1`, `reinitextensions` (없으면 `seq.ext`/`ext0object`) | Re-Init Extensions 존재 ✅ / 이름 미확인 | `rep`에 EXT |
| Resolution TOP | 타입 `resolutionTOP` (없으면 `fitTOP`) | 미확인 | |
| 패널 값 | `panel.u`, `panel.v`, `panel.lselect` | 미확인 | 클릭 시크가 안 되면 확인 |

고친 내용은 `build_sonify.py`에 반영한다. TD에서 손으로만 고치지 않는다. 같은 가정을 쓰는 `tests/mock_td.py`도 맞춰 고치고 `python3 -m pytest -q touchdesigner/tests`를 통과시킨다.

## 4. 눈으로 확인 (마지막에 한 번)
`get_top_image`로 `<container>/null2`(최종 대시보드)를 maxSize 700으로 본다.
`docs/dashboard_preview.png`와 비슷하게 나와야 한다. 왼쪽은 사진과 금색 스캔선, 오른쪽은 시세 카드 3개와 ISS 지도, 아래는 대역 미터와 팔레트다.

## 5. OSC 확인
- 컨테이너 OSC 페이지에서 Send Test를 누른다.
- 터미널에서 `python3 <DIR>/tools/osc_monitor.py 9000`을 실행해 `/sonify/*`가 30Hz로 오는지 본다. 같은 포트를 Max가 쓰고 있으면 끄고 확인한다.

## 6. 마무리
- 바뀐 파일을 커밋하고 브랜치에 푸시한다.
- 사용자에게 TD 버전, 고친 파라미터 이름, 남은 문제를 짧게 보고한다.

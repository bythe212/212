# 데이터 소니피케이션 프레임워크 (Sonify)

데이터를 소리로 바꿔 듣기 위한 기본 틀. 소리는 Web Audio API 로 직접 만들기 때문에
p5.js 없이도 동작하고, 예제(`sketch.js`)에서는 p5 를 그림 그리는 데만 쓴다.

## 실행

`fetch` 와 오디오는 `file://` 로 열면 막히므로 로컬 서버로 연다.

```bash
python3 -m http.server     # 저장소 루트에서
# → http://localhost:8000/sonification/
```

(VS Code 의 Live Server 도 된다.) 페이지를 연 뒤 <kbd>Space</kbd> 로 재생.

## 구조

데이터 → 매핑(스케일) → 소리 의 흐름을 파일 하나씩 담당한다. `index.html` 에서 이 순서로 로드한다.

| 파일 | 역할 |
| --- | --- |
| `lib/core.js` | `Sonify` 네임스페이스, `clamp`·`normalize`·`midiToFreq`·`extent` |
| `lib/data.js` | `Sonify.loadCSV(url)`, `Dataset.fromCSV/fromRows`, `column()`, `extent()` |
| `lib/scales.js` | `scale.linear`, `scale.log`, `scale.pitch`(음계 양자화), `scale.quantize`, `SCALES` |
| `lib/engine.js` | `AudioEngine` — 오실레이터 + 엔벨로프 + 팬으로 음 하나를 정확한 시각에 예약 |
| `lib/player.js` | `Player` — 한 행 = 한 스텝, 레이어별로 음을 예약하는 룩어헤드 스케줄러 |

## 사용법

```js
const engine = new Sonify.AudioEngine();
const ds = await Sonify.loadCSV('data/seoul-climate.csv');

const player = new Sonify.Player(engine, ds, { bpm: 150 });

player.addLayer('기온', {
  note: { field: 'temp', scale: Sonify.scale.pitch({ domain: ds.extent('temp'), scale: 'majorPentatonic' }) },
  wave: 'triangle',
  pan: (row, i) => i / (ds.length - 1) * 2 - 1,
});

player.addLayer('강수', {
  note: 36,
  gain: { field: 'rain', to: [0.05, 0.6] },   // 데이터 최소~최대 → 0.05~0.6
});

player.on('step', (i, row, notes) => { /* 시각화 갱신 */ });
player.play();   // 사용자 입력(클릭·키) 이후에 호출해야 소리가 난다
```

### 레이어 매핑

각 파라미터는 상수, 함수 `(row, i, dataset) => 값`, `{ field, scale }`, `{ field, to: [최소, 최대] }` 중 하나로 쓴다.

| 파라미터 | 의미 | 기본값 |
| --- | --- | --- |
| `note` / `freq` | 음높이(MIDI 번호 / Hz). 결측이면 그 스텝은 소리 없음 | — |
| `gain` | 음량 0~1 | 0.5 |
| `pan` | 좌우 -1~1 | 0 |
| `duration` | 음 길이(초) | 스텝 길이의 90% |
| `wave` | `sine` `triangle` `square` `sawtooth` | `sine` |
| `attack`, `release` | 엔벨로프(초) | 0.01, 0.1 |
| `when` | `(row, i) => boolean`, false 면 건너뜀 | — |

### Player

`play()` `pause()` `stop()` `toggle()` `seek(i)` `preview(i)` `setMuted(name, bool)`,
속성 `bpm`(분당 행 수) `loop` `state` `position`, 이벤트 `step` `end` `state`.

## 테스트

소리와 무관한 부분(CSV 파싱, 스케일, 매핑)은 Node 로 검사한다.

```bash
node sonification/test/run.js
```

## 예제 데이터

`data/seoul-climate.csv` 는 서울 월평균 기온·강수량의 대략적인 평년값으로, 예제용이다.
분석에 쓰려면 기상청 기상자료개방포털의 원자료를 받아 쓰자.

## 다음 단계 아이디어

- 샘플(wav) 재생 보이스 — 저장소의 `kick.wav` 등을 이벤트 소리로
- 시간 컬럼 기반 스케줄링(행 간격이 일정하지 않은 데이터)
- 필터 컷오프·디튠 등 음색 파라미터, 오디오 녹음(내보내기)

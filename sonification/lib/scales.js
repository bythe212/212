// 스케일 계층: 데이터 값 → 소리 파라미터(음높이, 음량, 팬 등)로 바꾸는 함수들.
(function (root) {
  const Sonify = root.Sonify;
  const { clamp, lerp, normalize } = Sonify.util;

  // 옥타브 안의 반음 위치(0 = 으뜸음).
  const SCALES = {
    chromatic: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11],
    major: [0, 2, 4, 5, 7, 9, 11],
    minor: [0, 2, 3, 5, 7, 8, 10],
    majorPentatonic: [0, 2, 4, 7, 9],
    minorPentatonic: [0, 3, 5, 7, 10],
    wholeTone: [0, 2, 4, 6, 8, 10],
  };

  // domain [d0, d1] → range [r0, r1] 직선 매핑. 기본적으로 범위 밖 값은 잘라낸다.
  function linear(domain, range = [0, 1], { clamp: doClamp = true } = {}) {
    const [d0, d1] = domain;
    const [r0, r1] = range;
    return (v) => {
      let t = normalize(v, d0, d1);
      if (doClamp) t = clamp(t, 0, 1);
      return lerp(r0, r1, t);
    };
  }

  // 로그 매핑: 값의 분포가 몇 자릿수에 걸쳐 있을 때(인구, 강수량 등). domain 은 양수여야 한다.
  function log(domain, range = [0, 1], options) {
    const [d0, d1] = domain;
    if (d0 <= 0 || d1 <= 0) throw new Error('log 스케일의 domain 은 양수여야 합니다.');
    const inner = linear([Math.log(d0), Math.log(d1)], range, options);
    return (v) => inner(Math.log(Math.max(v, Number.MIN_VALUE)));
  }

  // MIDI 음을 주어진 음계에서 가장 가까운 음으로 맞춘다. root: 0 = C, 2 = D, ...
  function quantize(midi, scale = 'majorPentatonic', rootNote = 0) {
    const steps = Array.isArray(scale) ? scale : SCALES[scale];
    if (!steps) throw new Error(`알 수 없는 음계: ${scale}`);
    const rounded = Math.round(midi);
    let best = rounded;
    let bestDist = Infinity;
    // 위아래 한 옥타브 안에서 가장 가까운 음계 음을 찾는다.
    for (let octave = -1; octave <= 1; octave++) {
      const base = Math.floor((rounded - rootNote) / 12) * 12 + rootNote + octave * 12;
      for (const s of steps) {
        const candidate = base + s;
        const dist = Math.abs(candidate - midi);
        if (dist < bestDist || (dist === bestDist && candidate < best)) {
          best = candidate;
          bestDist = dist;
        }
      }
    }
    return best;
  }

  // 데이터 값 → MIDI 음. low/high 는 MIDI 번호(60 = 가운데 도).
  function pitch({ domain, low = 48, high = 84, scale = 'majorPentatonic', root: rootNote = 0, clamp: doClamp = true } = {}) {
    const toMidi = linear(domain, [low, high], { clamp: doClamp });
    return (v) => (scale ? quantize(toMidi(v), scale, rootNote) : toMidi(v));
  }

  Sonify.SCALES = SCALES;
  Sonify.scale = { linear, log, quantize, pitch };
})(globalThis);

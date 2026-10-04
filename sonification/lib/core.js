// Sonify — 데이터 소니피케이션 프레임워크의 네임스페이스와 공통 유틸.
// 브라우저(window)와 Node(테스트) 모두에서 globalThis.Sonify 로 접근한다.
(function (root) {
  const Sonify = root.Sonify || (root.Sonify = {});

  Sonify.version = '0.1.0';

  Sonify.util = {
    clamp(v, lo, hi) {
      return Math.min(hi, Math.max(lo, v));
    },

    lerp(a, b, t) {
      return a + (b - a) * t;
    },

    // 값이 [min, max] 사이 어디쯤인지 0~1 로. 범위가 0이면 가운데(0.5).
    normalize(v, min, max) {
      return max === min ? 0.5 : (v - min) / (max - min);
    },

    midiToFreq(midi) {
      return 440 * Math.pow(2, (midi - 69) / 12);
    },

    isNumber(v) {
      return typeof v === 'number' && Number.isFinite(v);
    },

    // 숫자 배열의 [최솟값, 최댓값]. 숫자가 아닌 값(결측치)은 무시한다.
    extent(values) {
      let min = Infinity;
      let max = -Infinity;
      for (const v of values) {
        if (!Sonify.util.isNumber(v)) continue;
        if (v < min) min = v;
        if (v > max) max = v;
      }
      return min === Infinity ? [NaN, NaN] : [min, max];
    },
  };
})(globalThis);

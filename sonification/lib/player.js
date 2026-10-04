// 플레이어: Dataset 의 각 행을 시간축 위 한 스텝으로 보고, 레이어(매핑)마다 음을 예약한다.
//
// 레이어 매핑의 각 파라미터(note, freq, gain, pan, duration, wave, attack, release)는
//   - 상수:            gain: 0.4
//   - 함수:            pan: (row, i, ds) => ...
//   - 필드 + 스케일:   note: { field: 'temp', scale: Sonify.scale.pitch({ domain: [-5, 30] }) }
//   - 필드 + 범위:     gain: { field: 'rain', to: [0.05, 0.6] }   ← 데이터 최소~최대를 자동으로 사용
// 중 하나로 지정한다. note(MIDI) 또는 freq(Hz) 가 결측이면 그 스텝은 소리를 내지 않는다.
// when: (row, i) => boolean 을 주면 false 인 스텝은 건너뛴다.
(function (root) {
  const Sonify = root.Sonify;
  const { isNumber, midiToFreq } = Sonify.util;

  const PARAMS = ['note', 'freq', 'gain', 'pan', 'duration', 'wave', 'attack', 'release'];

  function resolveParam(spec, row, i, dataset) {
    if (typeof spec === 'function') return spec(row, i, dataset);
    if (spec && typeof spec === 'object' && 'field' in spec) {
      const v = row[spec.field];
      if (!isNumber(v)) return null;
      if (spec.scale) return spec.scale(v);
      if (spec.to) return Sonify.scale.linear(dataset.extent(spec.field), spec.to)(v);
      return v;
    }
    return spec;
  }

  // 한 레이어 매핑을 한 행에 적용해 엔진에 넘길 파라미터를 만든다. 재생하지 않을 스텝이면 null.
  function resolveLayer(mapping, row, i, dataset) {
    if (mapping.when && !mapping.when(row, i, dataset)) return null;
    const p = {};
    for (const key of PARAMS) {
      if (mapping[key] !== undefined) p[key] = resolveParam(mapping[key], row, i, dataset);
    }
    if (p.freq === undefined || p.freq === null) {
      p.freq = isNumber(p.note) ? midiToFreq(p.note) : null;
    }
    if (!isNumber(p.freq)) return null;
    for (const key of ['gain', 'pan', 'duration', 'attack', 'release']) {
      if (p[key] === null || (p[key] !== undefined && !isNumber(p[key]))) delete p[key];
    }
    return p;
  }

  class Player {
    constructor(engine, dataset, { bpm = 120, loop = false, lookahead = 0.1, interval = 25 } = {}) {
      this.engine = engine;
      this.dataset = dataset;
      this.layers = [];
      this.bpm = bpm; // 분당 스텝(=행) 수
      this.loop = loop;
      this.lookahead = lookahead; // 몇 초 앞까지 미리 예약할지
      this.interval = interval; // 스케줄러 주기(ms)
      this.index = 0; // 다음에 예약할 행
      this.position = -1; // 마지막으로 소리가 난 행(시각화용)
      this.state = 'stopped'; // 'playing' | 'paused' | 'stopped'
      this._timer = null;
      this._nextTime = 0;
      this._pending = new Set();
      this._listeners = {};
    }

    get stepDuration() {
      return 60 / this.bpm;
    }

    addLayer(name, mapping) {
      this.layers.push({ name, mapping, muted: false });
      return this;
    }

    removeLayer(name) {
      this.layers = this.layers.filter((l) => l.name !== name);
      return this;
    }

    setMuted(name, muted) {
      const layer = this.layers.find((l) => l.name === name);
      if (layer) layer.muted = muted;
      return this;
    }

    // 이벤트: 'step' (i, row, notes), 'end', 'state' (state)
    on(event, fn) {
      (this._listeners[event] || (this._listeners[event] = [])).push(fn);
      return this;
    }

    _emit(event, ...args) {
      (this._listeners[event] || []).forEach((fn) => fn(...args));
    }

    _setState(state) {
      if (this.state === state) return;
      this.state = state;
      this._emit('state', state);
    }

    // 소리 없이 i 번째 행이 만들어낼 레이어별 파라미터를 계산한다(시각화·디버깅용).
    preview(i) {
      const row = this.dataset.row(i);
      const notes = {};
      for (const layer of this.layers) {
        notes[layer.name] = layer.muted ? null : resolveLayer(layer.mapping, row, i, this.dataset);
      }
      return notes;
    }

    async play() {
      if (this.state === 'playing' || this.dataset.length === 0) return;
      await this.engine.start();
      if (this.index >= this.dataset.length) this.index = 0;
      this._nextTime = this.engine.now + 0.05;
      this._setState('playing');
      this._timer = setInterval(() => this._schedule(), this.interval);
      this._schedule();
    }

    pause() {
      if (this.state !== 'playing') return;
      this._clearTimers();
      // 미리 예약만 되고 아직 들리지 않은 스텝은 다시 재생되도록 되감는다.
      this.index = this.position + 1;
      this._setState('paused');
    }

    stop() {
      this._clearTimers();
      this.index = 0;
      this.position = -1;
      this._setState('stopped');
    }

    toggle() {
      return this.state === 'playing' ? this.pause() : this.play();
    }

    seek(i) {
      this.index = Math.max(0, Math.min(this.dataset.length - 1, i));
      this.position = this.index - 1;
      if (this.state === 'playing') {
        this._pending.forEach(clearTimeout);
        this._pending.clear();
        this._nextTime = this.engine.now + 0.05;
      }
    }

    _clearTimers() {
      clearInterval(this._timer);
      this._timer = null;
      this._pending.forEach(clearTimeout);
      this._pending.clear();
    }

    // 룩어헤드 스케줄러: setInterval 은 부정확하므로, 오디오 시계 기준으로 조금 앞까지 미리 예약한다.
    _schedule() {
      const horizon = this.engine.now + this.lookahead;
      while (this.state === 'playing' && this._nextTime < horizon) {
        if (this.index >= this.dataset.length) {
          if (this.loop) {
            this.index = 0;
          } else {
            this._finishAt(this._nextTime);
            return;
          }
        }
        this._scheduleStep(this.index, this._nextTime);
        this.index++;
        this._nextTime += this.stepDuration;
      }
    }

    _scheduleStep(i, time) {
      const row = this.dataset.row(i);
      const notes = this.preview(i);
      const defaults = { duration: this.stepDuration * 0.9 };
      for (const name in notes) {
        if (notes[name]) this.engine.playNote({ ...defaults, ...notes[name], time });
      }
      // 소리가 실제로 나는 순간에 맞춰 'step' 이벤트를 보낸다(시각화 동기화).
      this._later(time, () => {
        this.position = i;
        this._emit('step', i, row, notes);
      });
    }

    _finishAt(time) {
      clearInterval(this._timer);
      this._timer = null;
      this._later(time, () => {
        this.index = 0;
        this.position = -1;
        this._setState('stopped');
        this._emit('end');
      });
    }

    _later(time, fn) {
      const id = setTimeout(() => {
        this._pending.delete(id);
        fn();
      }, Math.max(0, (time - this.engine.now) * 1000));
      this._pending.add(id);
    }
  }

  Sonify.Player = Player;
  Sonify.resolveLayer = resolveLayer;
})(globalThis);

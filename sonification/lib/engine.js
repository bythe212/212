// 오디오 엔진: Web Audio API 위에서 음 하나(오실레이터 + 엔벨로프 + 팬)를 정확한 시각에 예약한다.
// p5.sound 에 의존하지 않으므로 p5 없이도, 다른 시각화 라이브러리와도 쓸 수 있다.
(function (root) {
  const Sonify = root.Sonify;
  const { clamp } = Sonify.util;

  class AudioEngine {
    constructor({ volume = 0.8 } = {}) {
      this.ctx = null;
      this.master = null;
      this._volume = volume;
    }

    // 브라우저 정책상 사용자 입력(클릭/키) 이후에 호출해야 소리가 난다.
    async start() {
      if (!this.ctx) {
        const Ctx = root.AudioContext || root.webkitAudioContext;
        this.ctx = new Ctx();
        // 여러 레이어가 겹쳐도 찢어지지 않도록 컴프레서를 마스터 앞에 둔다.
        this.compressor = this.ctx.createDynamicsCompressor();
        this.master = this.ctx.createGain();
        this.master.gain.value = this._volume;
        this.compressor.connect(this.master);
        this.master.connect(this.ctx.destination);
      }
      if (this.ctx.state === 'suspended') await this.ctx.resume();
      return this;
    }

    get now() {
      return this.ctx ? this.ctx.currentTime : 0;
    }

    setVolume(v) {
      this._volume = clamp(v, 0, 1);
      if (this.master) this.master.gain.setTargetAtTime(this._volume, this.now, 0.02);
    }

    // time 은 AudioContext 기준 초. 생략하면 즉시 재생.
    playNote({ freq, gain = 0.5, pan = 0, duration = 0.3, wave = 'sine', attack = 0.01, release = 0.1, time } = {}) {
      if (!this.ctx || !Number.isFinite(freq) || freq <= 0) return;
      const ctx = this.ctx;
      const t = Math.max(time === undefined ? ctx.currentTime : time, ctx.currentTime);
      const peak = clamp(gain, 0, 1);
      const hold = Math.max(duration, attack);
      const end = t + hold + release;

      const osc = ctx.createOscillator();
      osc.type = wave;
      osc.frequency.setValueAtTime(freq, t);

      const env = ctx.createGain();
      env.gain.setValueAtTime(0, t);
      env.gain.linearRampToValueAtTime(peak, t + attack);
      env.gain.setValueAtTime(peak, t + hold);
      env.gain.linearRampToValueAtTime(0, end);

      let out = env;
      if (ctx.createStereoPanner) {
        const panner = ctx.createStereoPanner();
        panner.pan.setValueAtTime(clamp(pan, -1, 1), t);
        env.connect(panner);
        out = panner;
      }

      osc.connect(env);
      out.connect(this.compressor);
      osc.start(t);
      osc.stop(end + 0.05);
      osc.onended = () => {
        osc.disconnect();
        out.disconnect();
        if (out !== env) env.disconnect();
      };
    }
  }

  Sonify.AudioEngine = AudioEngine;
})(globalThis);

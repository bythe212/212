// 소리 없이 검증 가능한 부분(데이터·스케일·매핑)을 Node 로 테스트한다.
// 실행: node sonification/test/run.js
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const lib = path.join(__dirname, '..', 'lib');
for (const f of ['core.js', 'data.js', 'scales.js', 'engine.js', 'player.js']) {
  require(path.join(lib, f));
}
const { Sonify } = globalThis;

const tests = [];
const test = (name, fn) => tests.push({ name, fn });

test('CSV: 따옴표, CRLF, 결측치, 숫자 변환', () => {
  const ds = Sonify.Dataset.fromCSV('name,value\r\n"Seoul, KR",3.5\r\nBusan,\r\n\r\n"say ""hi""",-2\r\n');
  assert.deepEqual(ds.columns, ['name', 'value']);
  assert.equal(ds.length, 3);
  assert.equal(ds.row(0).name, 'Seoul, KR');
  assert.equal(ds.row(0).value, 3.5);
  assert.equal(ds.row(1).value, null);
  assert.equal(ds.row(2).name, 'say "hi"');
  assert.deepEqual(ds.extent('value'), [-2, 3.5]);
});

test('예제 데이터 로드', () => {
  const text = fs.readFileSync(path.join(__dirname, '..', 'data', 'seoul-climate.csv'), 'utf8');
  const ds = Sonify.Dataset.fromCSV(text);
  assert.equal(ds.length, 12);
  assert.deepEqual(ds.columns, ['month', 'label', 'temp', 'rain']);
  ds.column('temp').forEach((v) => assert.equal(typeof v, 'number'));
});

test('linear: 매핑과 clamp', () => {
  const s = Sonify.scale.linear([0, 10], [100, 200]);
  assert.equal(s(5), 150);
  assert.equal(s(20), 200);
  assert.equal(Sonify.scale.linear([0, 10], [100, 200], { clamp: false })(20), 300);
  assert.equal(Sonify.scale.linear([3, 3], [0, 1])(3), 0.5);
});

test('log 스케일', () => {
  const s = Sonify.scale.log([1, 100], [0, 1]);
  assert.ok(Math.abs(s(10) - 0.5) < 1e-9);
  assert.throws(() => Sonify.scale.log([0, 10]));
});

test('quantize: 음계 안의 가장 가까운 음', () => {
  // C 메이저 펜타토닉: C D E G A
  assert.equal(Sonify.scale.quantize(61, 'majorPentatonic'), 60); // C# → C
  assert.equal(Sonify.scale.quantize(65, 'majorPentatonic'), 64); // F → E
  assert.equal(Sonify.scale.quantize(71, 'majorPentatonic'), 72); // B → C
  assert.equal(Sonify.scale.quantize(66, 'major', 2), 66); // D 메이저의 F#
  assert.throws(() => Sonify.scale.quantize(60, 'nope'));
});

test('pitch: 범위 끝이 low/high 로', () => {
  const s = Sonify.scale.pitch({ domain: [0, 1], low: 60, high: 72, scale: 'major' });
  assert.equal(s(0), 60);
  assert.equal(s(1), 72);
  assert.equal(Sonify.util.midiToFreq(69), 440);
});

test('resolveLayer: 상수/함수/field+scale/field+to/결측', () => {
  const ds = Sonify.Dataset.fromRows([{ a: 0, b: 10 }, { a: 10, b: null }]);
  const mapping = {
    note: { field: 'a', scale: (v) => 60 + v },
    gain: { field: 'a', to: [0.1, 0.5] },
    pan: (row, i) => (i === 0 ? -1 : 1),
    wave: 'square',
  };
  const p0 = Sonify.resolveLayer(mapping, ds.row(0), 0, ds);
  assert.equal(p0.freq, Sonify.util.midiToFreq(60));
  assert.equal(p0.gain, 0.1);
  assert.equal(p0.pan, -1);
  assert.equal(p0.wave, 'square');
  assert.equal(Sonify.resolveLayer(mapping, ds.row(1), 1, ds).gain, 0.5);

  // 음높이가 결측이면 그 스텝은 소리를 내지 않는다.
  assert.equal(Sonify.resolveLayer({ note: { field: 'b' } }, ds.row(1), 1, ds), null);
  // when 이 false 면 건너뛴다.
  assert.equal(Sonify.resolveLayer({ freq: 440, when: () => false }, ds.row(0), 0, ds), null);
  // 볼륨 등 부가 파라미터가 결측이면 기본값을 쓰도록 빠진다.
  const p = Sonify.resolveLayer({ freq: 440, gain: { field: 'b' } }, ds.row(1), 1, ds);
  assert.equal(p.freq, 440);
  assert.ok(!('gain' in p));
});

test('Player.preview: 레이어별 결과와 mute', () => {
  const ds = Sonify.Dataset.fromRows([{ v: 1 }]);
  const player = new Sonify.Player(new Sonify.AudioEngine(), ds)
    .addLayer('a', { note: 60 })
    .addLayer('b', { freq: { field: 'v', scale: (v) => v * 100 } })
    .setMuted('a', true);
  const notes = player.preview(0);
  assert.equal(notes.a, null);
  assert.equal(notes.b.freq, 100);
  assert.equal(player.stepDuration, 0.5);
});

let failed = 0;
for (const { name, fn } of tests) {
  try {
    fn();
    console.log(`ok   ${name}`);
  } catch (e) {
    failed++;
    console.log(`FAIL ${name}\n     ${e.message}`);
  }
}
console.log(`\n${tests.length - failed}/${tests.length} 통과`);
process.exit(failed ? 1 : 0);

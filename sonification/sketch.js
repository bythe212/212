// 예제: 서울 월평균 기온·강수량을 소리로 듣기.
//  - 기온 레이어: 기온 → 음높이(펜타토닉), 1월→12월 → 왼쪽→오른쪽 팬
//  - 강수 레이어: 강수량 → 낮은 음의 크기와 길이
// 프레임워크(Sonify)는 소리를, p5 는 그림만 담당한다.

const W = 720;
const H = 420;
const PAD = 60;

let data = null;
let player = null;
let flash = 0;
let error = null;

const engine = new Sonify.AudioEngine({ volume: 0.8 });

function setup() {
  createCanvas(W, H);
  textFont('system-ui');

  Sonify.loadCSV('data/seoul-climate.csv')
    .then((ds) => {
      data = ds;
      player = buildPlayer(ds);
    })
    .catch((e) => {
      error = e.message + '\n(로컬 서버로 열었는지 확인하세요)';
    });
}

function buildPlayer(ds) {
  const p = new Sonify.Player(engine, ds, { bpm: 150, loop: false });

  p.addLayer('기온', {
    note: { field: 'temp', scale: Sonify.scale.pitch({ domain: ds.extent('temp'), low: 57, high: 84, scale: 'majorPentatonic' }) },
    wave: 'triangle',
    gain: 0.45,
    pan: (row, i) => Sonify.scale.linear([0, ds.length - 1], [-0.8, 0.8])(i),
  });

  p.addLayer('강수', {
    note: 36,
    wave: 'sine',
    gain: { field: 'rain', scale: Sonify.scale.log(ds.extent('rain'), [0.08, 0.7]) },
    duration: { field: 'rain', to: [0.1, 0.38] },
    release: 0.2,
  });

  p.on('step', () => (flash = 1));
  return p;
}

function draw() {
  background(17);

  if (error) return message(error, color(255, 120, 120));
  if (!data) return message('데이터 불러오는 중…', color(180));

  const n = data.length;
  const x = (i) => map(i, 0, n - 1, PAD, W - PAD);
  const [tMin, tMax] = data.extent('temp');
  const [, rMax] = data.extent('rain');
  const yTemp = (v) => map(v, tMin, tMax, H - PAD, PAD + 20);
  const current = player.position;

  // 강수량 막대
  noStroke();
  for (let i = 0; i < n; i++) {
    const r = data.row(i).rain;
    const h = map(r, 0, rMax, 0, H - PAD * 2 - 20);
    fill(i === current ? color(90, 170, 255) : color(50, 90, 140, 160));
    rect(x(i) - 14, H - PAD - h, 28, h, 3, 3, 0, 0);
  }

  // 기온 선
  noFill();
  stroke(255, 140, 90);
  strokeWeight(2);
  beginShape();
  for (let i = 0; i < n; i++) vertex(x(i), yTemp(data.row(i).temp));
  endShape();

  for (let i = 0; i < n; i++) {
    const active = i === current;
    noStroke();
    fill(active ? color(255, 220, 120) : color(255, 140, 90));
    const d = active ? 10 + 18 * flash : 8;
    circle(x(i), yTemp(data.row(i).temp), d);
    fill(150);
    textAlign(CENTER, TOP);
    textSize(12);
    text(data.row(i).label, x(i), H - PAD + 8);
  }

  // 재생 헤드
  if (current >= 0) {
    stroke(255, 255, 255, 60);
    strokeWeight(1);
    line(x(current), PAD, x(current), H - PAD);
  }

  drawStatus(current);
  flash *= 0.88;
}

function drawStatus(current) {
  noStroke();
  textAlign(LEFT, TOP);
  textSize(14);
  fill(230);
  text('서울 월평균 기온(선) · 강수량(막대)', PAD, 18);

  textAlign(RIGHT, TOP);
  fill(160);
  const mutes = player.layers.map((l, k) => `${k + 1}:${l.name}${l.muted ? '(꺼짐)' : ''}`).join('  ');
  text(`${player.state} · ${player.bpm} bpm${player.loop ? ' · 반복' : ''}   ${mutes}`, W - PAD, 18);

  if (current >= 0) {
    const row = data.row(current);
    textAlign(LEFT, TOP);
    fill(255, 220, 120);
    text(`${row.label}  ${row.temp}°C  ${row.rain}mm`, PAD, 40);
  }
}

function message(msg, c) {
  noStroke();
  fill(c);
  textAlign(CENTER, CENTER);
  textSize(16);
  text(msg, W / 2, H / 2);
}

function keyPressed() {
  if (!player) return;
  if (key === ' ') {
    player.toggle();
    return false; // 페이지 스크롤 방지
  }
  if (key === 's' || key === 'S') player.stop();
  if (key === 'l' || key === 'L') player.loop = !player.loop;
  if (keyCode === UP_ARROW) player.bpm = min(600, player.bpm + 10);
  if (keyCode === DOWN_ARROW) player.bpm = max(30, player.bpm - 10);
  const k = Number(key);
  if (k >= 1 && k <= player.layers.length) {
    const layer = player.layers[k - 1];
    player.setMuted(layer.name, !layer.muted);
  }
  if (keyCode === UP_ARROW || keyCode === DOWN_ARROW) return false;
}

// 그래프를 클릭하면 그 달로 이동하고 그 달 소리를 한 번 들려준다.
function mousePressed() {
  if (!data || mouseY < PAD || mouseY > H) return;
  const i = round(map(mouseX, PAD, W - PAD, 0, data.length - 1));
  if (i < 0 || i >= data.length) return;
  player.seek(i);
  if (player.state === 'playing') return; // 재생 중이면 그 자리부터 이어서 재생된다.
  engine.start().then(() => {
    const notes = player.preview(i);
    for (const name in notes) if (notes[name]) engine.playNote(notes[name]);
    player.position = i;
    flash = 1;
  });
}

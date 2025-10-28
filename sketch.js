let kick, snare, hihat;
let music;
let kickSize = 0;
let snareSize = 0;
let hihatSize = 0;

let musicPlaying = false;
let showMessage = false;
let myPhoto;

function preload() {
  kick = loadSound('kick.wav');
  snare = loadSound('snare.wav');
  hihat = loadSound('hihat.wav');
  music = loadSound('music.wav');
  myPhoto = loadImage('photo.png'); 
}

function setup() {
  createCanvas(600, 400);
  rectMode(CENTER);
  textAlign(CENTER, CENTER);
  textSize(28);
  imageMode(CENTER);
  noStroke();
  background(0);
}

function draw() {
  background(0, 30);
  translate(width / 2, height / 2);

  // 킥
  if (kickSize > 1) {
    fill(255, 80, 120, 200);
    ellipse(0, 0, kickSize, kickSize);
    kickSize *= 0.9;
  }

  // 스네어
  if (snareSize > 1) {
    fill(100, 200, 255, 200);
    rect(0, 0, snareSize, 30);
    rect(0, 0, 30, snareSize);
    snareSize *= 0.9;
  }

  // 하이헷
  if (hihatSize > 1) {
    fill(180, 255, 100, 200);
    rect(0, -hihatSize, 10, 40);
    rect(0, hihatSize, 10, 40);
    rect(-hihatSize, 0, 40, 10);
    rect(hihatSize, 0, 40, 10);
    rect(-hihatSize * 0.7, -hihatSize * 0.7, 15, 15);
    rect(hihatSize * 0.7, -hihatSize * 0.7, 15, 15);
    rect(-hihatSize * 0.7, hihatSize * 0.7, 15, 15);
    rect(hihatSize * 0.7, hihatSize * 0.7, 15, 15);
    hihatSize *= 0.85;
  }

  // 
  if (musicPlaying) {
    fill(255, 200, 250);
    text("노브레인-넌 내게 반했어", 0, -height / 2 + 40);
  }

  //
  if (showMessage) {
    fill(255, 255, 180);
    text("모두들 1학기 수고하셨습니다 ♡", 0, -height / 2 + 80);
    image(myPhoto, 0, -height / 2 + 250, 300, 300); 
  }
}

function keyPressed() {
  if (keyCode === LEFT_ARROW) {
    kick.play();
    kickSize = 400;
  } else if (keyCode === DOWN_ARROW) {
    snare.play();
    snareSize = 300;
  } else if (keyCode === RIGHT_ARROW) {
    hihat.play();
    hihatSize = 120;
  } else if (key === ' ') {
    if (!musicPlaying) {
      music.play();
      musicPlaying = true;
    }
  } else if (keyCode === UP_ARROW) {
    showMessage = true;
  }
}

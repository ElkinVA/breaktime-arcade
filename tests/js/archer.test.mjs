import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "../..");
vm.runInThisContext(readFileSync(resolve(root, "games-src/archer/js/core.js"), "utf8"));
const C = globalThis.ArcherCore;
const source = readFileSync(resolve(root, "games-src/archer/js/game.js"), "utf8");

let passed = 0;
function test(name, fn) {
  fn();
  passed += 1;
  console.log(`ok ${passed} - ${name}`);
}

test("draw power is bounded and monotonic", () => {
  assert.equal(C.powerFromHold(-10), C.MIN_POWER);
  assert.ok(C.powerFromHold(300) < C.powerFromHold(700));
  assert.equal(C.powerFromHold(1200), 1);
  assert.equal(C.powerFromHold(99999), 1);
  assert.ok(C.speedForPower(C.MIN_POWER) >= C.MIN_SPEED);
  assert.ok(C.speedForPower(1) <= C.MAX_SPEED);
});

test("aiming is clamped to the upward arc", () => {
  const origin = { x: 480, y: 500 };
  const right = C.angleFromPoint(origin, { x: 900, y: 100 });
  const down = C.angleFromPoint(origin, { x: 480, y: 900 });
  const left = C.angleFromPoint(origin, { x: 0, y: 100 });
  assert.ok(right >= C.MIN_ANGLE && right <= C.MAX_ANGLE);
  assert.ok(down <= C.MAX_ANGLE && down >= C.MIN_ANGLE);
  assert.ok(left >= C.MIN_ANGLE && left <= C.MAX_ANGLE);
});

test("ballistic path is deterministic and gravity curves it", () => {
  const origin = { x: 480, y: 500 };
  const a = C.arrowFromShot(origin, -Math.PI / 3, 0.8, 0);
  const b = C.arrowFromShot(origin, -Math.PI / 3, 0.8, 0);
  for (let i = 0; i < 50; i += 1) {
    C.stepArrow(a, C.STEP_SECONDS);
    C.stepArrow(b, C.STEP_SECONDS);
  }
  assert.equal(a.x, b.x);
  assert.equal(a.y, b.y);
  assert.ok(a.vy > b.vy - 1);
  const path = C.previewPath(origin, -Math.PI / 3, 0.8, { width: 960, height: 640 }, 10);
  assert.ok(path.length > 2);
  assert.ok(path[path.length - 1].y < path[0].y);
});

test("segment collision detects a hit and ignores empty space", () => {
  const arrow = C.arrowFromShot({ x: 100, y: 100 }, 0, 1, 0);
  arrow.previousX = 100;
  arrow.previousY = 100;
  arrow.x = 200;
  arrow.y = 100;
  const target = C.makeTarget("sun", 150, 100, 1);
  assert.equal(C.hits(arrow, target), true);
  target.y = 300;
  assert.equal(C.hits(arrow, target), false);
});

test("combo raises every three hits, pays the active multiplier and resets on miss", () => {
  const score = C.createScore();
  const target = { value: 20 };
  let last = C.registerShot(score, target);
  assert.equal(last.points, 20);
  assert.equal(score.multiplier, 1);
  C.registerShot(score, target);
  last = C.registerShot(score, target);
  assert.equal(score.multiplier, 2);
  assert.equal(last.points, 40);
  assert.equal(score.bestStreak, 3);
  C.registerShot(score, target);
  C.registerShot(score, target);
  C.registerShot(score, target);
  assert.equal(score.multiplier, 3);
  C.registerShot(score, null);
  assert.equal(score.streak, 0);
  assert.equal(score.multiplier, 1);
  assert.equal(score.misses, 1);
  assert.equal(score.shots, 7);
});

test("accuracy includes misses and handles a zero-shot round", () => {
  const score = C.createScore();
  assert.equal(C.accuracy(score), 0);
  C.registerShot(score, { value: 10 });
  C.registerShot(score, null);
  assert.equal(score.shots, 2);
  assert.equal(score.hits, 1);
  assert.equal(C.formatAccuracy(score), 50);
});

test("sixty-second round ends exactly once", () => {
  assert.equal(C.roundFinished(59.99), false);
  assert.equal(C.roundFinished(60), true);
  assert.equal(C.roundFinished(61), true);
});

test("pause/resume and single-result submission are idempotent", () => {
  const pause = C.createPauseState();
  assert.equal(C.pause(pause, "blur", 10), true);
  assert.equal(C.pause(pause, "blur", 10), false);
  assert.equal(pause.reason, "blur");
  assert.equal(C.resume(pause), true);
  assert.equal(C.resume(pause), false);
  const submit = C.createSubmitState();
  assert.equal(C.beginSubmit(submit, { value: 1 }), true);
  assert.equal(C.beginSubmit(submit, { value: 2 }), false);
  assert.equal(C.completeSubmit(submit, true), true);
  assert.equal(C.beginSubmit(submit, { value: 3 }), false);
});

test("spawn plan grows composition and caps targets by phase", () => {
  const phases = [0, 1, 2, 3].map((p) => C.spawnPlan(p));
  for (let i = 1; i < phases.length; i += 1) {
    assert.ok(phases[i].interval <= phases[i - 1].interval);
    assert.ok(phases[i].max >= phases[i - 1].max);
  }
  assert.ok(phases[3].mix.includes("phoenix"));
  assert.ok(phases[0].interval > phases[3].interval);
});

test("targets only spawn inside the playable composition", () => {
  const rng = { int: (m) => Math.floor(Math.random() * m), float: () => Math.random() };
  const field = { width: 960, height: 640 };
  for (const kind of ["sun", "wisp", "guardian", "phoenix"]) {
    const target = C.spawnTarget(kind, field, rng);
    assert.ok(target.radius > 0);
    assert.ok(target.value > 0);
    assert.ok(target.baseX >= -60 && target.baseX <= field.width + 60);
    assert.ok(target.baseY >= 90 && target.baseY <= 500);
  }
});

test("game wires fixed timestep, single submit and SDK handshake", () => {
  assert.match(source, /CORE\.STEP_SECONDS/);
  assert.match(source, /createSubmitState/);
  assert.match(source, /state\.ba\.submitResult/);
  assert.match(source, /BreaktimeArcade\.init/);
  assert.doesNotMatch(source, /Math\.random/);
  assert.doesNotMatch(source, /localStorage/);
  assert.doesNotMatch(source, /postMessage/);
});

console.log(`\n${passed} Archer core tests passed`);

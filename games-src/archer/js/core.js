/* Archer — pure, deterministic game rules.
 *
 * Exposed as ArcherCore in the browser and module.exports in Node so the same
 * code is exercised by the package tests and by the cartridge. No rendering,
 * DOM, storage or unseeded randomness lives here.
 */
(function (root, factory) {
    "use strict";
    const api = factory();
    if (typeof module === "object" && module.exports) {
        module.exports = api;
    }
    root.ArcherCore = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
    "use strict";

    const STEP_SECONDS = 1 / 120;
    const ROUND_SECONDS = 60;
    const GRAVITY = 980;
    const MIN_SPEED = 520;
    const MAX_SPEED = 1180;
    const MIN_ANGLE = -Math.PI + 0.18;
    const MAX_ANGLE = -0.18;
    const MIN_POWER = 0.18;
    const MAX_HOLD_MS = 1200;
    const ARROW_RADIUS = 4;
    const MAX_MULTIPLIER = 5;
    const HITS_PER_MULTIPLIER = 3;
    const MAX_TARGETS = 6;

    const TARGET_TYPES = Object.freeze({
        sun: Object.freeze({
            key: "sun", radius: 34, value: 20, speed: 28, lifetime: 0,
            label: "target_sun",
        }),
        wisp: Object.freeze({
            key: "wisp", radius: 21, value: 35, speed: 74, lifetime: 0,
            label: "target_wisp",
        }),
        guardian: Object.freeze({
            key: "guardian", radius: 54, value: 12, speed: 18, lifetime: 0,
            label: "target_guardian",
        }),
        phoenix: Object.freeze({
            key: "phoenix", radius: 30, value: 75, speed: 55, lifetime: 4200,
            label: "target_phoenix",
        }),
    });

    function clamp(value, low, high) {
        return Math.min(high, Math.max(low, value));
    }

    function angleFromPoint(origin, point) {
        const dx = Number(point && point.x) - origin.x;
        const dy = Number(point && point.y) - origin.y;
        return clamp(Math.atan2(dy, dx), MIN_ANGLE, MAX_ANGLE);
    }

    function powerFromHold(holdMs) {
        const ratio = clamp(Number(holdMs) || 0, 0, MAX_HOLD_MS) / MAX_HOLD_MS;
        return MIN_POWER + (1 - MIN_POWER) * (ratio * ratio * (3 - 2 * ratio));
    }

    function speedForPower(power) {
        return MIN_SPEED + (MAX_SPEED - MIN_SPEED) * clamp(Number(power) || 0, 0, 1);
    }

    function spawnPlan(phase) {
        const index = clamp(Math.floor(Number(phase) || 0), 0, 3);
        return [
            { interval: 1.7, mix: ["sun", "guardian"], max: 3 },
            { interval: 1.25, mix: ["sun", "guardian", "wisp"], max: 4 },
            { interval: 0.95, mix: ["sun", "wisp", "guardian"], max: 5 },
            { interval: 0.72, mix: ["sun", "wisp", "guardian", "phoenix"], max: 6 },
        ][index];
    }

    function phaseFor(elapsedSeconds) {
        return clamp(Math.floor((Number(elapsedSeconds) || 0) / 15), 0, 3);
    }

    function makeTarget(kind, x, y, direction) {
        const spec = TARGET_TYPES[kind] || TARGET_TYPES.sun;
        return {
            kind: spec.key,
            x,
            y,
            baseX: x,
            baseY: y,
            radius: spec.radius,
            value: spec.value,
            speed: spec.speed,
            direction: direction < 0 ? -1 : 1,
            age: 0,
            life: spec.lifetime,
            alive: true,
            phase: 0,
        };
    }

    function updateTarget(target, dt, field) {
        if (!target || !target.alive) {
            return target;
        }
        target.age += dt;
        if (target.life > 0 && target.age >= target.life / 1000) {
            target.alive = false;
            return target;
        }
        const elapsed = target.age;
        if (target.kind === "sun") {
            target.x = target.baseX + Math.sin(elapsed * 0.9 + target.phase) * 90;
            target.y = target.baseY + Math.cos(elapsed * 0.7 + target.phase) * 34;
        } else if (target.kind === "wisp") {
            target.x += target.direction * target.speed * 1.7 * dt;
            target.y = target.baseY + Math.sin(elapsed * 3.4 + target.phase) * 54;
        } else if (target.kind === "guardian") {
            target.y = target.baseY + Math.sin(elapsed * 0.55 + target.phase) * 115;
            target.x = target.baseX + Math.sin(elapsed * 0.35) * 30;
        } else if (target.kind === "phoenix") {
            target.x = target.baseX + Math.cos(elapsed * 1.6) * 150;
            target.y = target.baseY + Math.sin(elapsed * 1.6) * 70;
        }
        const margin = target.radius + 18;
        if (target.x < margin || target.x > field.width - margin) {
            target.direction *= -1;
            target.x = clamp(target.x, margin, field.width - margin);
        }
        return target;
    }

    function arrowFromShot(origin, angle, power, seedIndex) {
        const speed = speedForPower(power);
        return {
            x: origin.x,
            y: origin.y,
            previousX: origin.x,
            previousY: origin.y,
            vx: Math.cos(angle) * speed,
            vy: Math.sin(angle) * speed,
            angle,
            alive: true,
            stuck: false,
            life: 0,
            seedIndex: Number(seedIndex) || 0,
        };
    }

    function stepArrow(arrow, dt) {
        if (!arrow || !arrow.alive) {
            return arrow;
        }
        arrow.previousX = arrow.x;
        arrow.previousY = arrow.y;
        arrow.life += dt;
        arrow.vy += GRAVITY * dt;
        arrow.x += arrow.vx * dt;
        arrow.y += arrow.vy * dt;
        arrow.angle = Math.atan2(arrow.vy, arrow.vx);
        return arrow;
    }

    function arrowInBounds(arrow, field) {
        return arrow.x > -80 && arrow.x < field.width + 80
            && arrow.y > -80 && arrow.y < field.height + 100;
    }

    function segmentDistanceSquared(ax, ay, bx, by, px, py) {
        const dx = bx - ax;
        const dy = by - ay;
        const lengthSquared = dx * dx + dy * dy;
        if (lengthSquared <= 0.000001) {
            const sx = px - ax;
            const sy = py - ay;
            return sx * sx + sy * sy;
        }
        let t = ((px - ax) * dx + (py - ay) * dy) / lengthSquared;
        t = clamp(t, 0, 1);
        const cx = ax + t * dx;
        const cy = ay + t * dy;
        const ex = px - cx;
        const ey = py - cy;
        return ex * ex + ey * ey;
    }

    function hits(arrow, target) {
        if (!arrow || !target || !target.alive) {
            return false;
        }
        const limit = target.radius + ARROW_RADIUS;
        return segmentDistanceSquared(
            arrow.previousX, arrow.previousY, arrow.x, arrow.y, target.x, target.y,
        ) <= limit * limit;
    }

    function previewPath(origin, angle, power, field, stepCount) {
        const points = [];
        const arrow = arrowFromShot(origin, angle, power, 0);
        const steps = Math.max(1, Math.floor(stepCount || 36));
        for (let index = 0; index < steps; index += 1) {
            for (let sub = 0; sub < 4; sub += 1) {
                stepArrow(arrow, STEP_SECONDS);
            }
            if (!arrowInBounds(arrow, field)) {
                break;
            }
            points.push({ x: arrow.x, y: arrow.y });
        }
        return points;
    }

    function createScore() {
        return {
            score: 0,
            shots: 0,
            hits: 0,
            misses: 0,
            streak: 0,
            bestStreak: 0,
            multiplier: 1,
            resolvedShots: 0,
        };
    }

    function multiplierForStreak(streak) {
        return clamp(1 + Math.floor(streak / HITS_PER_MULTIPLIER), 1, MAX_MULTIPLIER);
    }

    function registerShot(score, hitTarget) {
        score.shots += 1;
        score.resolvedShots += 1;
        if (hitTarget) {
            score.hits += 1;
            score.streak += 1;
            score.bestStreak = Math.max(score.bestStreak, score.streak);
            score.multiplier = multiplierForStreak(score.streak);
            const points = hitTarget.value * score.multiplier;
            score.score += points;
            return { hit: true, points: points, multiplier: score.multiplier };
        }
        score.misses += 1;
        score.streak = 0;
        score.multiplier = 1;
        return { hit: false, points: 0, multiplier: 1 };
    }

    function accuracy(score) {
        return score.shots === 0 ? 0 : score.hits / score.shots;
    }

    function formatAccuracy(score) {
        return Math.round(accuracy(score) * 100);
    }

    function roundFinished(elapsedSeconds) {
        return elapsedSeconds >= ROUND_SECONDS;
    }

    function createPauseState() {
        return { paused: false, reason: "", pausedAt: 0 };
    }

    function pause(state, reason, gameTime) {
        if (state.paused) {
            return false;
        }
        state.paused = true;
        state.reason = String(reason || "manual");
        state.pausedAt = gameTime;
        return true;
    }

    function resume(state) {
        if (!state.paused) {
            return false;
        }
        state.paused = false;
        state.reason = "";
        state.pausedAt = 0;
        return true;
    }

    function createSubmitState() {
        return { submitted: false, submitting: false, attempts: 0, pending: null };
    }

    function beginSubmit(state, payload) {
        if (state.submitted || state.submitting) {
            return false;
        }
        state.submitting = true;
        state.attempts += 1;
        state.pending = payload;
        return true;
    }

    function completeSubmit(state, accepted) {
        state.submitting = false;
        state.submitted = Boolean(accepted);
        return state.submitted;
    }

    function spawnTarget(kind, field, rng) {
        const spec = TARGET_TYPES[kind] || TARGET_TYPES.sun;
        const y = 90 + rng.int(Math.max(1, Math.floor(field.height * 0.52)));
        let x;
        let direction;
        if (kind === "wisp") {
            const fromLeft = rng.int(2) === 0;
            x = fromLeft ? -60 : field.width + 60;
            direction = fromLeft ? 1 : -1;
        } else {
            x = 100 + rng.int(Math.max(1, Math.floor(field.width - 200)));
            direction = rng.int(2) === 0 ? -1 : 1;
        }
        const target = makeTarget(kind, x, y, direction);
        target.baseX = x;
        target.baseY = y;
        target.radius = spec.radius;
        target.value = spec.value;
        target.phase = rng.float() * Math.PI * 2;
        return target;
    }

    return Object.freeze({
        STEP_SECONDS,
        ROUND_SECONDS,
        GRAVITY,
        MIN_SPEED,
        MAX_SPEED,
        MIN_ANGLE,
        MAX_ANGLE,
        MIN_POWER,
        MAX_HOLD_MS,
        ARROW_RADIUS,
        MAX_MULTIPLIER,
        HITS_PER_MULTIPLIER,
        MAX_TARGETS,
        TARGET_TYPES,
        clamp,
        angleFromPoint,
        powerFromHold,
        speedForPower,
        spawnPlan,
        phaseFor,
        makeTarget,
        updateTarget,
        arrowFromShot,
        stepArrow,
        arrowInBounds,
        hits,
        previewPath,
        createScore,
        multiplierForStreak,
        registerShot,
        accuracy,
        formatAccuracy,
        roundFinished,
        createPauseState,
        pause,
        resume,
        createSubmitState,
        beginSubmit,
        completeSubmit,
        spawnTarget,
    });
});

/* Neon Snake — complete browser cartridge for Breaktime Arcade.
 *
 * The game talks to the platform only through the official BA SDK loaded from
 * js/ba-sdk.js. It is a classic grid snake: eat energy orbs, grow, avoid the
 * walls and yourself. All randomness is seeded from ba.context.seed.
 */
(function () {
    "use strict";

    const COLS = 30;
    const ROWS = 20;
    const BASE_STEP_MS = 150;
    const FASTEST_STEP_MS = 70;
    const STEP_ACCELERATION_MS = 12;
    const APPLES_PER_LEVEL = 5;
    const POINTS_PER_APPLE = 5;
    const POINTS_PER_LEVEL = 15;
    const MAX_SCORE = 100000;
    const MAX_EVENTS = 20000;
    const MAX_EVENT_BYTES = 1500000;
    const AUTOTEST_STEP_MS = 40;
    const AUTOTEST_LIMIT_TICKS = 400;
    const MAX_PARTICLES = 180;
    const STORAGE_KEY = "settings.v1";
    const STORAGE_DEBOUNCE_MS = 1000;
    const AVAILABLE_LANGUAGES = Object.freeze(["en", "de", "nl", "ru", "fr", "es"]);
    const DIRECTION_ORDER = ["right", "down", "left", "up"];
    const DIRECTIONS = Object.freeze({
        right: { x: 1, y: 0 },
        left: { x: -1, y: 0 },
        up: { x: 0, y: -1 },
        down: { x: 0, y: 1 },
    });
    const EVENT_KINDS = Object.freeze(["start", "eat", "turn", "level", "collide", "end"]);
    const REQUIRED_KEYS = Object.freeze([
        "game_title", "start", "pause", "resume", "restart", "game_over", "your_score",
        "best_score", "new_record", "play_again", "exit", "loading", "error_sdk",
        "error_network", "result_saving", "result_rejected", "result_retry",
        "session_expired", "guest_notice", "register_cta", "controls_hint",
        "orientation_hint", "sound_on", "sound_off", "rank", "top_scores",
    ]);
    const FALLBACK_EN = Object.freeze({
        game_title: "Neon Snake",
        loading: "Loading…",
        error_sdk: "The game could not start.",
        error_network: "Connection problem.",
        result_retry: "Retry sending",
        retry: "Retry",
    });

    const dom = {};
    const state = {
        ba: null,
        context: null,
        strings: {},
        language: "en",
        mode: "boot",
        seed: "",
        rng: null,
        soundEnabled: true,
        audioContext: null,
        storageTimer: 0,
        running: false,
        paused: false,
        pauseReason: "",
        submitted: false,
        submitting: false,
        submitFailed: false,
        retryAllowed: false,
        autotestDone: false,
        autoWatchdog: 0,
        roundId: 0,
        transitioning: false,
        sessionExpired: false,
        rafId: 0,
        lastFrame: 0,
        accumulator: 0,
        clockMs: 0,
        tick: 0,
        stepMs: BASE_STEP_MS,
        autoLimitTicks: 0,
        snake: [],
        direction: DIRECTIONS.right,
        queuedDirection: null,
        food: null,
        score: 0,
        level: 1,
        applesEaten: 0,
        eventLog: { v: 1, seed: "", events: [] },
        eventBytes: 0,
        particles: [],
        pendingResult: null,
        lastResult: null,
        bestValue: null,
        resultRank: null,
        reduceMotion: false,
        touchMode: false,
        view: { width: 0, height: 0, dpr: 1, cell: 32, offsetX: 0, offsetY: 0 },
        swipe: { x: 0, y: 0, active: false },
    };

    function byId(id) {
        return document.getElementById(id);
    }

    function cacheDom() {
        [
            "app", "stage", "game-canvas", "hud", "hud-score-label", "hud-score",
            "hud-level-label", "hud-level", "hud-target-label", "hud-target",
            "pause-button", "boot-screen", "boot-message", "boot-retry",
            "start-screen", "start-kicker", "start-title", "start-rule",
            "start-button", "controls-title", "controls-hint", "orientation-hint",
            "sound-label", "sound-toggle", "sound-toggle-text", "start-guest-notice",
            "pause-screen", "pause-title", "pause-reason", "resume-button",
            "restart-button", "pause-exit-button", "result-screen", "result-kicker",
            "result-title", "new-record", "your-score-label", "your-score",
            "best-score-label", "best-score", "rank-label", "rank-value",
            "level-label", "result-level", "result-status", "guest-notice",
            "top-scores-label", "top-scores", "play-again-button",
            "retry-submit-button", "result-exit-button", "register-cta",
            "network-banner", "focus-hint", "touch-controls", "live-region",
        ].forEach(function (id) {
            dom[id] = byId(id);
        });
        dom.canvas = dom["game-canvas"];
    }

    function safeText(value) {
        return typeof value === "string" ? value : "";
    }

    function pluralCategory(language, count) {
        const value = Math.abs(Math.trunc(Number(count) || 0));
        if (String(language).slice(0, 2) === "ru") {
            const mod10 = value % 10;
            const mod100 = value % 100;
            if (mod10 === 1 && mod100 !== 11) {
                return "one";
            }
            if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) {
                return "few";
            }
            return "many";
        }
        return value === 1 ? "one" : "other";
    }

    function formatMessage(template, params) {
        if (typeof template !== "string" || template.length === 0) {
            return "";
        }
        let text = template;
        const values = params && typeof params === "object" ? params : {};
        const pluralPattern = /\{(\w+),\s*plural,\s*((?:(?:zero|one|two|few|many|other)\s*\{[^{}]*\}\s*)+)\}/g;
        text = text.replace(pluralPattern, function (whole, name, body) {
            const count = Number(values[name]);
            if (!Number.isFinite(count)) {
                return whole;
            }
            const clauses = {};
            const clausePattern = /(zero|one|two|few|many|other)\s*\{([^{}]*)\}/g;
            let clause = clausePattern.exec(body);
            while (clause !== null) {
                clauses[clause[1]] = clause[2];
                clause = clausePattern.exec(body);
            }
            const category = pluralCategory(state.language, count);
            const selected = clauses[category] || clauses.other || "";
            return selected.split("#").join(String(count));
        });
        return text.replace(/\{([A-Za-z_][A-Za-z0-9_]*)\}/g, function (whole, name) {
            if (Object.prototype.hasOwnProperty.call(values, name)) {
                return String(values[name]);
            }
            return whole;
        });

    }

    function t(key, params) {
        if (state.ba && typeof state.ba.t === "function") {
            const value = state.ba.t(key);
            if (typeof value === "string" && value.length > 0 && value !== key) {
                return formatMessage(value, params);
            }
        }
        if (Object.prototype.hasOwnProperty.call(state.strings, key)) {
            return formatMessage(state.strings[key], params);
        }
        if (Object.prototype.hasOwnProperty.call(FALLBACK_EN, key)) {
            return formatMessage(FALLBACK_EN[key], params);
        }
        return "";
    }

    function setNode(node, key, params) {
        if (!node) {
            return;
        }
        node.textContent = t(key, params);
    }

    function setNodeText(node, text) {
        if (node) {
            node.textContent = safeText(text);
        }
    }

    function setHidden(node, hidden) {
        if (node) {
            node.hidden = Boolean(hidden);
        }
    }

    function announce(key, params) {
        setNode(dom["live-region"], key, params);
    }

    function normalizeLanguage(value) {
        const text = typeof value === "string" ? value.trim().toLowerCase() : "";
        return /^[a-z]{2,3}(?:[-_][a-z0-9]{2,8})?$/.test(text) ? text : "en";
    }

    function loadJson(path) {
        return fetch(path, { cache: "no-store", credentials: "same-origin" }).then(function (response) {
            if (!response.ok) {
                throw new Error("BA_LOCALE_HTTP");
            }
            return response.json();
        });
    }

    function mergeLocale(base, overlay) {
        const result = {};
        if (base && typeof base === "object") {
            Object.keys(base).forEach(function (key) {
                result[key] = base[key];
            });
        }
        if (overlay && typeof overlay === "object") {
            Object.keys(overlay).forEach(function (key) {
                if (typeof overlay[key] === "string" && overlay[key].length > 0) {
                    result[key] = overlay[key];
                }
            });
        }
        return result;
    }

    function loadStrings(context) {
        const requested = normalizeLanguage(context && context.language);
        const fallback = normalizeLanguage(context && context.fallbackLanguage);
        const cache = {};
        function load(code) {
            if (AVAILABLE_LANGUAGES.indexOf(code) === -1) {
                return Promise.resolve(null);
            }
            if (cache[code]) {
                return Promise.resolve(cache[code]);
            }
            return loadJson("locales/" + code + ".json").then(function (data) {
                cache[code] = data && typeof data === "object" ? data : {};
                return cache[code];
            }).catch(function () {
                cache[code] = null;
                return null;
            });
        }
        return load("en").then(function (english) {
            if (!english) {
                state.language = requested;
                return mergeLocale(FALLBACK_EN, context && context.strings);
            }
            return Promise.all([
                fallback !== "en" ? load(fallback) : Promise.resolve(null),
                requested !== "en" && requested !== fallback ? load(requested) : Promise.resolve(null),
            ]).then(function (extra) {
                let merged = mergeLocale(english, extra[0]);
                merged = mergeLocale(merged, extra[1]);
                merged = mergeLocale(merged, context && context.strings);
                state.language = requested;
                return merged;
            });
        });
    }

    function applyLocaleMetadata() {
        document.documentElement.lang = state.language;
        document.title = t("page_title") || t("game_title");
        dom.canvas.setAttribute("aria-label", t("game_title"));
    }

    function applyStaticLabels() {
        setNode(dom["start-kicker"], "kicker");
        setNode(dom["start-title"], "game_title");
        setNode(dom["start-rule"], "rule");
        setNode(dom["start-button"], "start");
        setNode(dom["controls-title"], "controls_title");
        setNode(dom["controls-hint"], "controls_hint");
        setNode(dom["orientation-hint"], "orientation_hint");
        setNode(dom["sound-label"], "sound_label");
        setNode(dom["sound-toggle-text"], state.soundEnabled ? "sound_on" : "sound_off");
        setNode(dom["start-guest-notice"], "guest_notice");
        setNode(dom["pause-title"], "pause_title");
        setNode(dom["resume-button"], "resume");
        setNode(dom["restart-button"], "restart");
        setNode(dom["pause-exit-button"], "exit");
        setNode(dom["result-kicker"], "session_kicker");
        setNode(dom["result-status"], "loading");
        setNode(dom["result-title"], "game_over");
        setNode(dom["new-record"], "new_record");
        setNode(dom["your-score-label"], "your_score");
        setNode(dom["best-score-label"], "best_score");
        setNode(dom["rank-label"], "rank");
        setNode(dom["level-label"], "level_label");
        setNode(dom["top-scores-label"], "top_scores");
        setNode(dom["play-again-button"], "play_again");
        setNode(dom["retry-submit-button"], "result_retry");
        setNode(dom["result-exit-button"], "exit");
        setNode(dom["register-cta"], "register_cta");
        setNode(dom["hud-score-label"], "score_label");
        setNode(dom["hud-level-label"], "level_label");
        setNode(dom["hud-target-label"], "target_label");
        dom["sound-toggle"].setAttribute("aria-pressed", state.soundEnabled ? "true" : "false");
        dom["sound-toggle"].setAttribute("aria-label", t("sound_label"));
        dom["pause-button"].setAttribute("aria-label", t("pause"));
        dom["pause-button"].setAttribute("aria-pressed", "false");
        dom["boot-retry"].textContent = t("retry");
        dom["retry-submit-button"].textContent = t("result_retry");
        dom["new-record"].textContent = t("new_record");
        const hasGuest = state.mode === "guest" || state.mode === "preview";
        setHidden(dom["start-guest-notice"], !hasGuest);
        setHidden(dom["guest-notice"], true);
        setHidden(dom["register-cta"], !hasGuest);
        if (hasGuest) {
            setNode(dom["register-cta"], "register_cta");
        }
        const directions = {
            up: "move_up",
            down: "move_down",
            left: "move_left",
            right: "move_right",
        };
        dom["touch-controls"].querySelectorAll("[data-direction]").forEach(function (button) {
            const name = button.getAttribute("data-direction");
            button.setAttribute("aria-label", t(directions[name] || "controls_title"));
            button.textContent = name === "up" ? "▲" : name === "down" ? "▼" : name === "left" ? "◀" : "▶";
        });
    }

    function showBootMessage(key, showRetry) {
        dom["boot-message"].textContent = t(key);
        dom["boot-retry"].textContent = t("retry");
        setHidden(dom["boot-retry"], !showRetry);
        setHidden(dom["boot-screen"], false);
    }

    function showOnly(screen) {
        ["start-screen", "pause-screen", "result-screen", "boot-screen"].forEach(function (id) {
            if (id !== screen) {
                setHidden(dom[id], true);
            }
        });
        if (screen) {
            setHidden(dom[screen], false);
        }
    }

    function setAppState(value) {
        dom.app.setAttribute("data-state", value);
        if (document.body) {
            document.body.setAttribute("data-game-state", value);
        }
    }

    function setSoundEnabled(enabled, persist) {
        state.soundEnabled = Boolean(enabled);
        setNode(dom["sound-toggle-text"], state.soundEnabled ? "sound_on" : "sound_off");
        dom["sound-toggle"].setAttribute("aria-pressed", state.soundEnabled ? "true" : "false");
        if (!state.soundEnabled && state.audioContext) {
            state.audioContext.suspend().catch(function () {});
        }
        if (persist) {
            persistSettings();
        }
    }

    function persistSettings() {
        if (!state.ba) {
            return;
        }
        if (state.storageTimer) {
            globalThis.clearTimeout(state.storageTimer);
        }
        state.storageTimer = globalThis.setTimeout(function () {
            state.storageTimer = 0;
            state.ba.storage.set(STORAGE_KEY, { soundEnabled: state.soundEnabled }).catch(function () {});
        }, STORAGE_DEBOUNCE_MS);
    }

    function loadSettings() {
        if (!state.ba) {
            return Promise.resolve();
        }
        return state.ba.storage.get(STORAGE_KEY).then(function (value) {
            if (value && typeof value === "object" && typeof value.soundEnabled === "boolean") {
                setSoundEnabled(value.soundEnabled, false);
            }
        }).catch(function () {});
    }

    function ensureAudio() {
        if (!state.soundEnabled) {
            return;
        }
        const Ctor = globalThis.AudioContext || globalThis.webkitAudioContext;
        if (!Ctor) {
            return;
        }
        try {
            if (!state.audioContext) {
                state.audioContext = new Ctor();
            }
            if (state.audioContext.state === "suspended") {
                state.audioContext.resume().catch(function () {});
            }
        } catch (error) {
            state.audioContext = null;
        }
    }

    function tone(frequency, offsetSeconds, durationSeconds, type, volume) {
        if (!state.soundEnabled || !state.audioContext || state.paused || state.mode === "autotest") {
            return;
        }
        try {
            const now = state.audioContext.currentTime + Math.max(0, offsetSeconds);
            const oscillator = state.audioContext.createOscillator();
            const gain = state.audioContext.createGain();
            oscillator.type = type || "square";
            oscillator.frequency.setValueAtTime(frequency, now);
            gain.gain.setValueAtTime(0.0001, now);
            gain.gain.exponentialRampToValueAtTime(volume || 0.05, now + 0.012);
            gain.gain.exponentialRampToValueAtTime(0.0001, now + durationSeconds);
            oscillator.connect(gain);
            gain.connect(state.audioContext.destination);
            oscillator.start(now);
            oscillator.stop(now + durationSeconds + 0.02);
        } catch (error) {
            /* audio is optional */
        }
    }

    function playEatSound() {
        tone(880, 0, 0.09, "triangle", 0.045);
        tone(1320, 0.06, 0.08, "triangle", 0.03);
    }

    function playTurnSound() {
        tone(420, 0, 0.035, "square", 0.016);
    }

    function playCrashSound() {
        tone(180, 0, 0.24, "sawtooth", 0.05);
        tone(120, 0.06, 0.3, "sawtooth", 0.04);
    }

    function playFanfare() {
        tone(523, 0, 0.12, "triangle", 0.05);
        tone(659, 0.12, 0.12, "triangle", 0.05);
        tone(784, 0.24, 0.16, "triangle", 0.055);
        tone(1047, 0.42, 0.3, "triangle", 0.06);
    }

    function resetRound() {
        if (state.rafId) {
            globalThis.cancelAnimationFrame(state.rafId);
            state.rafId = 0;
        }
        if (state.autoWatchdog) {
            globalThis.clearTimeout(state.autoWatchdog);
            state.autoWatchdog = 0;
        }
        state.roundId += 1;
        state.running = false;
        state.paused = false;
        state.pauseReason = "";
        state.clockMs = 0;
        state.accumulator = 0;
        state.tick = 0;
        state.lastFrame = 0;
        state.score = 0;
        state.level = 1;
        state.applesEaten = 0;
        state.particles.length = 0;
        state.pendingResult = null;
        state.lastResult = null;
        state.resultRank = null;
        state.submitted = false;
        state.submitting = false;
        state.submitFailed = false;
        state.retryAllowed = false;
        state.autotestDone = false;
        state.sessionExpired = false;
        state.direction = DIRECTIONS.right;
        state.queuedDirection = null;
        state.stepMs = state.mode === "autotest" ? AUTOTEST_STEP_MS : BASE_STEP_MS;
        state.autoLimitTicks = state.mode === "autotest" ? AUTOTEST_LIMIT_TICKS : 0;
        state.rng = globalThis.NeonRng ? globalThis.NeonRng.create(state.seed) : null;
        state.eventLog = { v: 1, seed: state.seed, events: [] };
        state.eventBytes = 0;
        state.snake = [
            { x: 8, y: 10 },
            { x: 7, y: 10 },
            { x: 6, y: 10 },
            { x: 5, y: 10 },
        ];
        state.food = spawnFood();
        dom["new-record"].hidden = true;
        dom["retry-submit-button"].hidden = true;
        dom["result-status"].classList.remove("is-error");
        dom["result-status"].textContent = "";
        dom["top-scores"].replaceChildren();
        dom["guest-notice"].hidden = true;
        dom["register-cta"].hidden = state.mode !== "guest" && state.mode !== "preview";
        updateHud();
        draw();
    }

    function cellKey(cell) {
        return cell.x + ":" + cell.y;
    }

    function occupiedSet() {
        const occupied = new Set();
        state.snake.forEach(function (cell) {
            occupied.add(cellKey(cell));
        });
        return occupied;
    }

    function spawnFood() {
        if (!state.rng) {
            return { x: COLS - 4, y: ROWS - 4 };
        }
        const occupied = occupiedSet();
        const free = [];
        for (let y = 0; y < ROWS; y += 1) {
            for (let x = 0; x < COLS; x += 1) {
                if (!occupied.has(x + ":" + y)) {
                    free.push({ x: x, y: y });
                }
            }
        }
        if (free.length === 0) {
            return null;
        }
        return free[state.rng.int(free.length)];
    }

    function logEvent(kind, data) {
        if (EVENT_KINDS.indexOf(kind) === -1) {
            return;
        }
        if (state.eventLog.events.length >= MAX_EVENTS || state.eventBytes >= MAX_EVENT_BYTES) {
            return;
        }
        const last = state.eventLog.events.length > 0
            ? state.eventLog.events[state.eventLog.events.length - 1].t
            : 0;
        const at = Math.max(last, Math.max(0, Math.round(state.clockMs)));
        const event = { t: at, k: kind, d: data && typeof data === "object" ? data : {} };
        state.eventLog.events.push(event);
        state.eventBytes += JSON.stringify(event).length + 1;
    }

    function clampScore(value) {
        const maxValue = state.context && state.context.score && Number.isFinite(state.context.score.maxValue)
            ? state.context.score.maxValue
            : MAX_SCORE;
        return Math.max(0, Math.min(Math.round(value), Math.min(MAX_SCORE, Math.round(maxValue))));
    }

    function currentMaxSeconds() {
        const value = state.context && state.context.limits
            ? Number(state.context.limits.maxSessionSeconds)
            : 1800;
        return Number.isFinite(value) && value > 0 ? value : 1800;
    }

    function isOpposite(first, second) {
        return Boolean(first && second && first.x + second.x === 0 && first.y + second.y === 0);
    }

    function queueDirection(name) {
        const vector = DIRECTIONS[name];
        if (!vector || !state.running || state.paused) {
            return;
        }
        if (isOpposite(vector, state.direction)) {
            return;
        }
        if (vector.x === state.direction.x && vector.y === state.direction.y) {
            return;
        }
        state.queuedDirection = vector;
    }

    function chooseAutotestDirection() {
        const head = state.snake[0];
        const food = state.food;
        if (!head || !food) {
            return;
        }
        const preferred = [];
        if (food.x > head.x) {
            preferred.push("right");
        } else if (food.x < head.x) {
            preferred.push("left");
        }
        if (food.y > head.y) {
            preferred.push("down");
        } else if (food.y < head.y) {
            preferred.push("up");
        }
        const candidates = preferred.concat(DIRECTION_ORDER);
        const tail = state.snake[state.snake.length - 1];
        const body = occupiedSet();
        for (let index = 0; index < candidates.length; index += 1) {
            const name = candidates[index];
            const vector = DIRECTIONS[name];
            if (!vector || isOpposite(vector, state.direction)) {
                continue;
            }
            const next = { x: head.x + vector.x, y: head.y + vector.y };
            if (next.x < 0 || next.y < 0 || next.x >= COLS || next.y >= ROWS) {
                continue;
            }
            const willGrow = next.x === food.x && next.y === food.y;
            const key = cellKey(next);
            const tailKey = cellKey(tail);
            if (body.has(key) && (willGrow || key !== tailKey)) {
                continue;
            }
            state.queuedDirection = vector;
            return;
        }
    }

    function canMove(vector) {
        const head = state.snake[0];
        const next = { x: head.x + vector.x, y: head.y + vector.y };
        if (next.x < 0 || next.y < 0 || next.x >= COLS || next.y >= ROWS) {
            return null;
        }
        const body = occupiedSet();
        const tail = state.snake[state.snake.length - 1];
        const willGrow = state.food && next.x === state.food.x && next.y === state.food.y;
        const key = cellKey(next);
        if (body.has(key) && (willGrow || key !== cellKey(tail))) {
            return null;
        }
        return next;
    }

    function spawnParticles(cell, color, count) {
        if (state.reduceMotion) {
            return;
        }
        for (let index = 0; index < count; index += 1) {
            if (state.particles.length >= MAX_PARTICLES) {
                break;
            }
            const angle = (Math.PI * 2 * index) / count + (index % 3) * 0.17;
            const speed = 0.4 + (index % 5) * 0.12;
            state.particles.push({
                x: cell.x + 0.5,
                y: cell.y + 0.5,
                vx: Math.cos(angle) * speed,
                vy: Math.sin(angle) * speed,
                life: 1,
                color: color,
            });
        }
    }

    function updateParticles(dt) {
        const seconds = dt / 1000;
        for (let index = state.particles.length - 1; index >= 0; index -= 1) {
            const particle = state.particles[index];
            particle.x += particle.vx * seconds;
            particle.y += particle.vy * seconds;
            particle.life -= seconds * 1.8;
            if (particle.life <= 0) {
                state.particles.splice(index, 1);
            }
        }
    }

    function step() {
        if (!state.running || state.paused) {
            return;
        }
        if (state.mode === "autotest") {
            chooseAutotestDirection();
        }
        if (state.queuedDirection) {
            if (!isOpposite(state.queuedDirection, state.direction)) {
                if (state.queuedDirection.x !== state.direction.x || state.queuedDirection.y !== state.direction.y) {
                    state.direction = state.queuedDirection;
                    logEvent("turn", {
                        x: state.snake[0].x,
                        y: state.snake[0].y,
                        dx: state.direction.x,
                        dy: state.direction.y,
                    });
                    playTurnSound();
                }
            }
            state.queuedDirection = null;
        }
        const next = canMove(state.direction);
        if (!next) {
            logEvent("collide", {
                x: state.snake[0].x,
                y: state.snake[0].y,
                reason: "wall_or_body",
            });
            finishRound("collide");
            return;
        }
        const eating = state.food && next.x === state.food.x && next.y === state.food.y;
        state.snake.unshift(next);
        if (eating) {
            state.applesEaten += 1;
            state.score = clampScore(state.score + POINTS_PER_APPLE);
            logEvent("eat", { x: next.x, y: next.y, value: state.score });
            spawnParticles(next, "#ffd166", 14);
            playEatSound();
            if (state.applesEaten % APPLES_PER_LEVEL === 0) {
                state.level += 1;
                state.score = clampScore(state.score + POINTS_PER_LEVEL);
                state.stepMs = state.mode === "autotest"
                    ? AUTOTEST_STEP_MS
                    : Math.max(
                        FASTEST_STEP_MS,
                        BASE_STEP_MS - (state.level - 1) * STEP_ACCELERATION_MS,
                    );
                logEvent("level", { level: state.level, value: state.score });
                spawnParticles(next, "#41e8ff", 18);
            }
            state.food = spawnFood();
            if (!state.food) {
                finishRound("filled");
                return;
            }
        } else {
            state.snake.pop();
        }
        state.clockMs += state.stepMs;
        state.tick += 1;
        if (state.clockMs >= currentMaxSeconds() * 1000) {
            finishRound("timeout");
            return;
        }
        if (state.autoLimitTicks > 0 && state.tick >= state.autoLimitTicks) {
            finishRound("autotest_limit");
            return;
        }
        updateHud();
    }

    function updateHud() {
        setNodeText(dom["hud-score"], String(state.score));
        setNodeText(dom["hud-level"], String(state.level));
        setNodeText(dom["hud-target"], (state.applesEaten % APPLES_PER_LEVEL) + "/" + APPLES_PER_LEVEL);
    }

    function finishRound(reason) {
        if (!state.running) {
            return;
        }
        state.running = false;
        state.paused = false;
        state.pauseReason = "";
        if (state.rafId) {
            globalThis.cancelAnimationFrame(state.rafId);
            state.rafId = 0;
        }
        if (state.autoWatchdog) {
            globalThis.clearTimeout(state.autoWatchdog);
            state.autoWatchdog = 0;
        }
        logEvent("end", {
            reason: reason,
            score: state.score,
            level: state.level,
            apples: state.applesEaten,
        });
        const maxDuration = currentMaxSeconds() * 1000;
        const durationMs = Math.max(0, Math.min(Math.round(state.clockMs), maxDuration));
        state.pendingResult = {
            value: clampScore(state.score),
            durationMs: durationMs,
            eventLog: state.eventLog,
            seed: state.seed,
            clientMeta: {
                gameVersion: state.context ? state.context.gameVersion : "",
                level: state.level,
                apples: state.applesEaten,
            },
        };
        dom["pause-button"].setAttribute("aria-pressed", "false");
        setHidden(dom["hud"], true);
        setHidden(dom["touch-controls"], true);
        playCrashSound();
        draw();
        if (state.mode === "autotest") {
            setAppState("autotest-finished");
            void submitPendingResult();
            return;
        }
        showResultScreen();
        void submitPendingResult();
    }

    function showResultScreen() {
        setAppState("result");
        showOnly("result-screen");
        setNode(dom["result-title"], "game_over");
        setNodeText(dom["your-score"], String(clampScore(state.score)));
        setNodeText(dom["result-level"], String(state.level));
        setNodeText(dom["best-score"], state.bestValue === null ? t("best_unknown") : String(state.bestValue));
        setNodeText(dom["rank-value"], state.resultRank === null ? t("best_unknown") : String(state.resultRank));
        setHidden(dom["new-record"], true);
        setHidden(dom["retry-submit-button"], true);
        setHidden(dom["guest-notice"], state.mode !== "guest" && state.mode !== "preview");
        setHidden(dom["register-cta"], state.mode !== "guest" && state.mode !== "preview");
        dom["result-status"].classList.remove("is-error");
        dom["result-status"].textContent = t("result_saving");
        renderLeaderboard(null);
        announce("game_over");
        draw();
    }

    function isRetryableCode(code) {
        if (!code) {
            return true;
        }
        if (code === "E_GUEST_FORBIDDEN" || code === "E_TIMEOUT" || code === "E_NETWORK"
            || code === "E_INTERNAL") {
            return code !== "E_GUEST_FORBIDDEN";
        }
        if (code.indexOf("E_SESSION_") === 0 || code.indexOf("E_SCORE_") === 0
            || code.indexOf("E_DURATION_") === 0 || code.indexOf("E_MESSAGE_") === 0
            || code === "E_OWNERSHIP") {
            return false;
        }
        return true;
    }

    function delay(milliseconds) {
        return new Promise(function (resolve) {
            globalThis.setTimeout(resolve, milliseconds);
        });
    }

    function submitPendingResult() {
        if (!state.pendingResult || state.submitting || state.submitted || !state.ba) {
            return Promise.resolve();
        }
        state.submitting = true;
        state.submitFailed = false;
        state.retryAllowed = false;
        setNode(dom["result-status"], "result_saving");
        dom["result-status"].classList.remove("is-error");
        setHidden(dom["retry-submit-button"], true);
        const pending = state.pendingResult;
        const roundId = state.roundId;
        let attempt = 0;
        function run() {
            if (state.roundId !== roundId) {
                return Promise.resolve();
            }
            return state.ba.submitResult(pending).then(function (response) {
                if (state.roundId !== roundId) {
                    return undefined;
                }
                state.submitting = false;
                state.submitted = true;
                handleSubmitResponse(response, roundId);
                return undefined;
            }).catch(function (error) {
                if (state.roundId !== roundId) {
                    return undefined;
                }
                const code = error && typeof error.code === "string" ? error.code : "";
                if (code === "E_GUEST_FORBIDDEN") {
                    state.submitting = false;
                    state.submitted = true;
                    handleSubmitResponse({
                        status: "guest",
                        code: "E_GUEST_FORBIDDEN",
                        rank: null,
                        isPersonalBest: false,
                        isRecord: false,
                        trustLevel: "client_reported",
                    }, roundId);
                    return undefined;
                }
                attempt += 1;
                state.retryAllowed = isRetryableCode(code);
                if (attempt >= 3 || !state.retryAllowed) {
                    state.submitting = false;
                    state.submitFailed = true;
                    const expired = code.indexOf("E_SESSION_") === 0;
                    if (expired) {
                        state.sessionExpired = true;
                    }
                    setNode(dom["result-status"], expired ? "session_expired" : "result_rejected");
                    dom["result-status"].classList.add("is-error");
                    setHidden(
                        dom["retry-submit-button"],
                        state.mode === "autotest" || !state.retryAllowed,
                    );
                    announce(expired ? "session_expired" : "result_rejected");
                    return undefined;
                }
                return delay(400 * Math.pow(2, attempt - 1)).then(run);
            });
        }
        return run();
    }

    function handleSubmitResponse(response, roundId) {
        if (state.roundId !== roundId) {
            return Promise.resolve();
        }
        const result = response && typeof response === "object" ? response : {};
        state.lastResult = result;
        state.resultRank = Number.isInteger(result.rank) ? result.rank : null;
        if (result.status === "guest" || state.mode === "guest" || state.mode === "preview") {
            if (state.mode !== "autotest") {
                setNode(dom["result-status"], "guest_notice");
                dom["result-status"].classList.remove("is-error");
                setHidden(dom["guest-notice"], false);
                setHidden(dom["register-cta"], false);
            }
            announce("guest_notice");
            return loadLeaderboard(roundId);
        }
        if (result.status === "quarantined") {
            if (state.mode !== "autotest") {
                setNode(dom["result-status"], "result_rejected");
                dom["result-status"].classList.add("is-error");
            }
            announce("result_rejected");
            return loadLeaderboard(roundId);
        }
        if (state.mode !== "autotest") {
            setNode(dom["result-status"], "result_saved");
            setNodeText(dom["rank-value"], state.resultRank === null ? t("best_unknown") : String(state.resultRank));
            setHidden(dom["new-record"], result.isRecord !== true);
            if (result.isRecord === true) {
                announce("new_record");
            }
            playFanfare();
        }
        return loadLeaderboard(roundId);
    }

    function loadLeaderboard(roundId) {
        if (state.mode === "autotest" || !state.ba) {
            return Promise.resolve();
        }
        return Promise.allSettled([
            state.ba.leaderboard.top(10),
            state.ba.leaderboard.myBest(),
        ]).then(function (outcomes) {
            if (state.roundId !== roundId) {
                return undefined;
            }
            const top = outcomes[0].status === "fulfilled" ? outcomes[0].value : null;
            const best = outcomes[1].status === "fulfilled" ? outcomes[1].value : null;
            if (best && typeof best.value === "number") {
                state.bestValue = best.value;
            }
            if (state.mode !== "autotest") {
                setNodeText(
                    dom["best-score"],
                    state.bestValue === null ? t("best_unknown") : String(state.bestValue),
                );
            }
            if (top && Array.isArray(top.entries)) {
                renderLeaderboard(top.entries);
                if (top.myRank !== null && top.myRank !== undefined && state.resultRank === null) {
                    state.resultRank = top.myRank;
                    setNodeText(dom["rank-value"], String(top.myRank));
                }
            } else {
                renderLeaderboard([]);
            }
            return undefined;
        });
    }

    function renderLeaderboard(entries) {
        const list = dom["top-scores"];
        list.replaceChildren();
        if (!Array.isArray(entries) || entries.length === 0) {
            const empty = document.createElement("li");
            empty.className = "empty-row";
            empty.textContent = t("no_scores");
            list.appendChild(empty);
            return;
        }
        entries.slice(0, 10).forEach(function (entry) {
            if (!entry || typeof entry !== "object") {
                return;
            }
            const row = document.createElement("li");
            const rank = document.createElement("span");
            rank.className = "rank-number";
            rank.textContent = "#" + String(entry.rank);
            const name = document.createElement("span");
            name.className = "player-name";
            name.textContent = typeof entry.nickname === "string" && entry.nickname
                ? entry.nickname
                : t("anonymous");
            const value = document.createElement("span");
            value.className = "player-value";
            value.textContent = String(entry.value);
            row.appendChild(rank);
            row.appendChild(name);
            row.appendChild(value);
            list.appendChild(row);
        });
    }

    function resetUiForNewRound() {
        setHidden(dom["start-screen"], true);
        setHidden(dom["pause-screen"], true);
        setHidden(dom["result-screen"], true);
        setHidden(dom["boot-screen"], true);
        setHidden(dom["hud"], false);
        setHidden(dom["network-banner"], true);
        dom["result-status"].textContent = "";
        dom["result-status"].classList.remove("is-error");
        dom["top-scores"].replaceChildren();
        dom["new-record"].hidden = true;
        dom["retry-submit-button"].hidden = true;
        dom["guest-notice"].hidden = true;
        dom["register-cta"].hidden = true;
        updateHud();
        if (state.touchMode && state.mode !== "autotest") {
            setHidden(dom["touch-controls"], false);
        }
    }

    function startRound() {
        if (state.running) {
            return;
        }
        if (state.snake.length === 0) {
            resetRound();
        }
        if (state.mode !== "autotest" && state.soundEnabled) {
            ensureAudio();
        }
        setAppState("playing");
        resetUiForNewRound();
        state.running = true;
        state.paused = false;
        state.pauseReason = "";
        state.lastFrame = 0;
        state.accumulator = 0;
        logEvent("start", { mode: state.mode });
        updateHud();
        draw();
        if (state.mode !== "autotest") {
            dom.canvas.focus({ preventScroll: true });
        } else {
            state.autoWatchdog = globalThis.setTimeout(function () {
                state.autoWatchdog = 0;
                if (state.running) {
                    finishRound("autotest_budget");
                } else {
                    void submitPendingResult();
                }
            }, 24000);
        }
        state.rafId = globalThis.requestAnimationFrame(loop);
    }

    function startFromGesture() {
        if (state.running || state.transitioning) {
            return;
        }
        ensureAudio();
        startRound();
    }

    function manualPause(reason) {
        if (!state.running || state.paused) {
            return;
        }
        pauseRound(reason || "manual", true);
    }

    function pauseRound(reason, showOverlay) {
        if (!state.running || state.paused) {
            return;
        }
        state.paused = true;
        state.pauseReason = reason;
        state.accumulator = 0;
        if (state.rafId) {
            globalThis.cancelAnimationFrame(state.rafId);
            state.rafId = 0;
        }
        dom["pause-button"].setAttribute("aria-pressed", "true");
        setHidden(dom["touch-controls"], true);
        if (state.audioContext) {
            state.audioContext.suspend().catch(function () {});
        }
        if (showOverlay && state.mode !== "autotest") {
            setAppState("paused");
            setNode(dom["pause-title"], reason === "network" ? "error_network" : "pause");
            setNode(dom["pause-reason"], reason === "network" ? "network_lost" : "pause_hint");
            showOnly("pause-screen");
        }
        draw();
    }

    function resumeRound() {
        if (!state.running || !state.paused) {
            return;
        }
        state.paused = false;
        state.pauseReason = "";
        state.lastFrame = 0;
        state.accumulator = 0;
        dom["pause-button"].setAttribute("aria-pressed", "false");
        if (state.soundEnabled && state.mode !== "autotest") {
            ensureAudio();
        }
        setAppState("playing");
        setHidden(dom["pause-screen"], true);
        if (state.touchMode && state.mode !== "autotest") {
            setHidden(dom["touch-controls"], false);
        }
        if (state.mode !== "autotest") {
            dom.canvas.focus({ preventScroll: true });
        }
        state.rafId = globalThis.requestAnimationFrame(loop);
    }

    function manualResume() {
        resumeRound();
    }

    function restartFromPause() {
        if (!state.running) {
            return;
        }
        state.running = false;
        state.paused = false;
        if (state.rafId) {
            globalThis.cancelAnimationFrame(state.rafId);
            state.rafId = 0;
        }
        state.seed = state.context && state.context.seed ? state.context.seed : state.seed;
        resetRound();
        startRound();
    }

    function exitGame() {
        if (state.ba) {
            state.ba.exit();
        }
        setAppState("exited");
        setHidden(dom["pause-screen"], true);
        setHidden(dom["result-screen"], true);
    }

    function toggleSound() {
        setSoundEnabled(!state.soundEnabled, true);
        if (state.soundEnabled) {
            ensureAudio();
            tone(660, 0, 0.08, "triangle", 0.04);
        }
        announce(state.soundEnabled ? "sound_on" : "sound_off");
    }

    async function playAgain() {
        if (state.transitioning || !state.ba) {
            return;
        }
        state.transitioning = true;
        dom["play-again-button"].disabled = true;
        try {
            const context = await state.ba.newSession();
            if (context && typeof context === "object") {
                state.context = context;
                state.mode = typeof context.mode === "string" ? context.mode : state.mode;
                state.seed = typeof context.seed === "string" ? context.seed : "";
                state.strings = await loadStrings(context);
                if (state.ba.context) {
                    state.ba.context.strings = state.strings;
                }
                applyLocaleMetadata();
                applyStaticLabels();
            }
            resetRound();
            startRound();
        } catch (error) {
            state.sessionExpired = true;
            setNode(dom["result-status"], "session_expired");
            dom["result-status"].classList.add("is-error");
            announce("session_expired");
        } finally {
            state.transitioning = false;
            dom["play-again-button"].disabled = false;
        }
    }

    function retrySubmit() {
        if (state.submitting || state.mode === "autotest" || !state.retryAllowed) {
            return;
        }
        state.submitted = false;
        void submitPendingResult();
    }

    function updateAccumulator(now) {
        if (!state.lastFrame) {
            state.lastFrame = now;
            return 0;
        }
        const delta = Math.min(250, Math.max(0, now - state.lastFrame));
        state.lastFrame = now;
        state.accumulator += delta;
        return delta;
    }

    function loop(now) {
        if (!state.running || state.paused) {
            state.rafId = 0;
            return;
        }
        const delta = updateAccumulator(now);
        updateParticles(delta);
        let safety = 0;
        while (state.accumulator >= state.stepMs && state.running && !state.paused && safety < 8) {
            state.accumulator -= state.stepMs;
            step();
            safety += 1;
        }
        if (state.accumulator > state.stepMs * 8) {
            state.accumulator = 0;
        }
        draw();
        if (state.running && !state.paused) {
            state.rafId = globalThis.requestAnimationFrame(loop);
        } else {
            state.rafId = 0;
        }
    }

    function resizeCanvas() {
        const canvas = dom.canvas;
        const rect = canvas.getBoundingClientRect();
        const cssWidth = Math.max(1, Math.round(rect.width));
        const cssHeight = Math.max(1, Math.round(rect.height));
        const dpr = Math.min(2, Math.max(1, globalThis.devicePixelRatio || 1));
        const width = Math.round(cssWidth * dpr);
        const height = Math.round(cssHeight * dpr);
        if (canvas.width !== width || canvas.height !== height) {
            canvas.width = width;
            canvas.height = height;
        }
        const cell = Math.floor(Math.min(width / COLS, height / ROWS));
        state.view = {
            width: width,
            height: height,
            dpr: dpr,
            cell: Math.max(4, cell),
            offsetX: Math.floor((width - cell * COLS) / 2),
            offsetY: Math.floor((height - cell * ROWS) / 2),
        };
        draw();
    }

    function roundRectPath(context, x, y, width, height, radius) {
        const r = Math.min(radius, width / 2, height / 2);
        context.beginPath();
        context.moveTo(x + r, y);
        context.lineTo(x + width - r, y);
        context.quadraticCurveTo(x + width, y, x + width, y + r);
        context.lineTo(x + width, y + height - r);
        context.quadraticCurveTo(x + width, y + height, x + width - r, y + height);
        context.lineTo(x + r, y + height);
        context.quadraticCurveTo(x, y + height, x, y + height - r);
        context.lineTo(x, y + r);
        context.quadraticCurveTo(x, y, x + r, y);
        context.closePath();
    }

    function drawBackdrop(context, width, height) {
        const gradient = context.createLinearGradient(0, 0, width, height);
        gradient.addColorStop(0, "#07131a");
        gradient.addColorStop(0.55, "#050a10");
        gradient.addColorStop(1, "#0b0714");
        context.fillStyle = gradient;
        context.fillRect(0, 0, width, height);
        const glow = context.createRadialGradient(
            width * 0.2, height * 0.12, 0,
            width * 0.2, height * 0.12, width * 0.6,
        );
        glow.addColorStop(0, "rgba(57, 255, 136, 0.12)");
        glow.addColorStop(1, "rgba(57, 255, 136, 0)");
        context.fillStyle = glow;
        context.fillRect(0, 0, width, height);
        const glow2 = context.createRadialGradient(
            width * 0.86, height * 0.9, 0,
            width * 0.86, height * 0.9, width * 0.5,
        );
        glow2.addColorStop(0, "rgba(255, 79, 216, 0.1)");
        glow2.addColorStop(1, "rgba(255, 79, 216, 0)");
        context.fillStyle = glow2;
        context.fillRect(0, 0, width, height);
    }

    function drawGrid(context, view) {
        const { width, height, cell, offsetX, offsetY } = view;
        context.fillStyle = "rgba(4, 12, 14, 0.88)";
        context.fillRect(offsetX, offsetY, cell * COLS, cell * ROWS);
        context.strokeStyle = "rgba(57, 255, 136, 0.1)";
        context.lineWidth = Math.max(1, view.dpr * 0.5);
        for (let x = 0; x <= COLS; x += 1) {
            const px = offsetX + x * cell;
            context.beginPath();
            context.moveTo(px, offsetY);
            context.lineTo(px, offsetY + cell * ROWS);
            context.stroke();
        }
        for (let y = 0; y <= ROWS; y += 1) {
            const py = offsetY + y * cell;
            context.beginPath();
            context.moveTo(offsetX, py);
            context.lineTo(offsetX + cell * COLS, py);
            context.stroke();
        }
        context.strokeStyle = "rgba(65, 232, 255, 0.45)";
        context.lineWidth = Math.max(1, view.dpr);
        context.strokeRect(offsetX, offsetY, cell * COLS, cell * ROWS);
        const edge = context.createLinearGradient(offsetX, offsetY, offsetX + cell * COLS, offsetY);
        edge.addColorStop(0, "rgba(57, 255, 136, 0)");
        edge.addColorStop(0.3, "rgba(57, 255, 136, 0.18)");
        edge.addColorStop(0.7, "rgba(65, 232, 255, 0.14)");
        edge.addColorStop(1, "rgba(255, 79, 216, 0)");
        context.strokeStyle = edge;
        context.strokeRect(offsetX - 2, offsetY - 2, cell * COLS + 4, cell * ROWS + 4);
        context.globalAlpha = 1;
        context.strokeStyle = "rgba(57, 255, 136, 0.06)";
        context.beginPath();
        context.moveTo(offsetX, offsetY + cell * ROWS * 0.5);
        context.lineTo(offsetX + cell * COLS, offsetY + cell * ROWS * 0.5);
        context.stroke();
    }

    function drawSnake(context, view) {
        const { cell, offsetX, offsetY } = view;
        const size = cell * 0.82;
        const inset = (cell - size) / 2;
        for (let index = state.snake.length - 1; index >= 0; index -= 1) {
            const segment = state.snake[index];
            const x = offsetX + segment.x * cell + inset;
            const y = offsetY + segment.y * cell + inset;
            const ratio = 1 - index / (state.snake.length + 2);
            context.save();
            context.shadowColor = index === 0 ? "#39ff88" : "#1fd96a";
            context.shadowBlur = index === 0 ? cell * 0.7 : cell * 0.28;
            roundRectPath(context, x, y, size, size, size * 0.34);
            context.fillStyle = index === 0
                ? "#c9ffdd"
                : "rgba(57, 255, 136, " + (0.42 + ratio * 0.45).toFixed(3) + ")";
            context.fill();
            if (index === 0) {
                context.shadowBlur = 0;
                context.fillStyle = "#062516";
                const eye = Math.max(2, cell * 0.09);
                const dir = state.direction;
                const eyeX = x + size / 2 + dir.x * size * 0.17;
                const eyeY = y + size / 2 + dir.y * size * 0.17;
                context.beginPath();
                context.arc(eyeX - dir.y * size * 0.18, eyeY - dir.x * size * 0.18, eye, 0, Math.PI * 2);
                context.arc(eyeX + dir.y * size * 0.18, eyeY + dir.x * size * 0.18, eye, 0, Math.PI * 2);
                context.fill();
            }
            context.restore();
        }
    }

    function drawFood(context, view, now) {
        if (!state.food) {
            return;
        }
        const { cell, offsetX, offsetY } = view;
        const pulse = state.reduceMotion ? 1 : 1 + Math.sin(now / 260) * 0.08;
        const x = offsetX + (state.food.x + 0.5) * cell;
        const y = offsetY + (state.food.y + 0.5) * cell;
        const radius = cell * 0.29 * pulse;
        const halo = context.createRadialGradient(x, y, radius * 0.25, x, y, cell * 0.72);
        halo.addColorStop(0, "rgba(255, 209, 102, 0.55)");
        halo.addColorStop(1, "rgba(255, 209, 102, 0)");
        context.fillStyle = halo;
        context.beginPath();
        context.arc(x, y, cell * 0.72, 0, Math.PI * 2);
        context.fill();
        context.save();
        context.shadowColor = "#ffd166";
        context.shadowBlur = cell * 0.6;
        context.fillStyle = "#ffe9a8";
        context.beginPath();
        context.arc(x, y, radius, 0, Math.PI * 2);
        context.fill();
        context.restore();
        context.fillStyle = "rgba(255, 255, 255, 0.82)";
        context.beginPath();
        context.arc(x - radius * 0.3, y - radius * 0.32, radius * 0.28, 0, Math.PI * 2);
        context.fill();
    }

    function drawParticles(context, view) {
        const { cell, offsetX, offsetY } = view;
        context.save();
        state.particles.forEach(function (particle) {
            context.globalAlpha = Math.max(0, particle.life);
            context.fillStyle = particle.color;
            context.beginPath();
            context.arc(
                offsetX + particle.x * cell,
                offsetY + particle.y * cell,
                Math.max(1, cell * 0.06),
                0,
                Math.PI * 2,
            );
            context.fill();
        });
        context.restore();
    }

    function drawAmbient(context, view, now) {
        const { cell, offsetX, offsetY } = view;
        const snake = [
            { x: 10, y: 8 }, { x: 9, y: 8 }, { x: 8, y: 8 }, { x: 7, y: 8 }, { x: 6, y: 8 },
        ];
        snake.forEach(function (segment, index) {
            const x = offsetX + segment.x * cell + cell * 0.09;
            const y = offsetY + segment.y * cell + cell * 0.09;
            const size = cell * 0.82;
            context.save();
            context.shadowColor = "#39ff88";
            context.shadowBlur = index === 0 ? cell * 0.7 : cell * 0.25;
            roundRectPath(context, x, y, size, size, size * 0.34);
            context.fillStyle = index === 0
                ? "#c9ffdd"
                : "rgba(57, 255, 136, " + (0.75 - index * 0.09).toFixed(3) + ")";
            context.fill();
            context.restore();
        });
        const foodX = offsetX + 19.5 * cell;
        const foodY = offsetY + 12.5 * cell;
        const pulse = state.reduceMotion ? 1 : 1 + Math.sin(now / 300) * 0.1;
        const halo = context.createRadialGradient(foodX, foodY, 2, foodX, foodY, cell * 0.8);
        halo.addColorStop(0, "rgba(255, 209, 102, 0.55)");
        halo.addColorStop(1, "rgba(255, 209, 102, 0)");
        context.fillStyle = halo;
        context.beginPath();
        context.arc(foodX, foodY, cell * 0.8, 0, Math.PI * 2);
        context.fill();
        context.save();
        context.shadowColor = "#ffd166";
        context.shadowBlur = cell * 0.6;
        context.fillStyle = "#ffe9a8";
        context.beginPath();
        context.arc(foodX, foodY, cell * 0.29 * pulse, 0, Math.PI * 2);
        context.fill();
        context.restore();
    }

    function draw(now) {
        const canvas = dom.canvas;
        const context = canvas.getContext("2d");
        if (!context) {
            return;
        }
        const view = state.view;
        if (!view.width || !view.height) {
            return;
        }
        const time = typeof now === "number" ? now : globalThis.performance.now();
        context.setTransform(1, 0, 0, 1, 0, 0);
        drawBackdrop(context, view.width, view.height);
        drawGrid(context, view);
        if (state.snake.length > 0) {
            drawSnake(context, view);
            drawFood(context, view, time);
            drawParticles(context, view);
        } else {
            drawAmbient(context, view, time);
        }
    }

    function detectTouchMode() {
        const coarse = globalThis.matchMedia && globalThis.matchMedia("(pointer: coarse)").matches;
        state.touchMode = Boolean(coarse || (globalThis.navigator && globalThis.navigator.maxTouchPoints > 0));
        if (state.touchMode && state.running && state.mode !== "autotest") {
            setHidden(dom["touch-controls"], false);
        }
    }

    function onKeyDown(event) {
        if (!state.running || state.paused) {
            return;
        }
        const key = event.key;
        const code = event.code;
        const map = {
            ArrowUp: "up", KeyW: "up",
            ArrowDown: "down", KeyS: "down",
            ArrowLeft: "left", KeyA: "left",
            ArrowRight: "right", KeyD: "right",
        };
        if (Object.prototype.hasOwnProperty.call(map, code)) {
            event.preventDefault();
            queueDirection(map[code]);
            return;
        }
        if (key === "Escape" || code === "KeyP") {
            event.preventDefault();
            manualPause("manual");
        }
    }

    function onCanvasPointerDown(event) {
        if (!state.running || state.paused) {
            return;
        }
        state.swipe.x = event.clientX;
        state.swipe.y = event.clientY;
        state.swipe.active = true;
    }

    function onCanvasPointerUp(event) {
        if (!state.swipe.active) {
            return;
        }
        state.swipe.active = false;
        const dx = event.clientX - state.swipe.x;
        const dy = event.clientY - state.swipe.y;
        if (Math.max(Math.abs(dx), Math.abs(dy)) < 24) {
            return;
        }
        if (Math.abs(dx) > Math.abs(dy)) {
            queueDirection(dx > 0 ? "right" : "left");
        } else {
            queueDirection(dy > 0 ? "down" : "up");
        }
    }

    function onVisibilityChange() {
        if (document.visibilityState === "hidden") {
            if (state.running && !state.paused) {
                pauseRound("visibility", true);
            }
            return;
        }
        if (state.running && state.paused && state.pauseReason === "visibility") {
            resumeRound();
        }
    }

    function onWindowBlur() {
        if (state.running && !state.paused) {
            pauseRound("visibility", true);
        }
    }

    function onWindowFocus() {
        if (state.running && state.paused && state.pauseReason === "visibility"
            && document.visibilityState === "visible") {
            resumeRound();
        }
    }

    function onOffline() {
        setNode(dom["network-banner"], "error_network");
        setHidden(dom["network-banner"], false);
        if (state.running && !state.paused) {
            pauseRound("network", true);
        }
    }

    function onOnline() {
        setHidden(dom["network-banner"], true);
        if (state.running && state.paused && state.pauseReason === "network") {
            resumeRound();
        }
    }

    function bindEvents() {
        dom["start-button"].addEventListener("click", startFromGesture);
        dom["sound-toggle"].addEventListener("click", toggleSound);
        dom["pause-button"].addEventListener("click", function () {
            manualPause("manual");
        });
        dom["resume-button"].addEventListener("click", manualResume);
        dom["restart-button"].addEventListener("click", restartFromPause);
        dom["pause-exit-button"].addEventListener("click", exitGame);
        dom["play-again-button"].addEventListener("click", function () {
            void playAgain();
        });
        dom["retry-submit-button"].addEventListener("click", retrySubmit);
        dom["result-exit-button"].addEventListener("click", exitGame);
        dom["boot-retry"].addEventListener("click", function () {
            globalThis.location.reload();
        });
        dom.canvas.addEventListener("pointerdown", onCanvasPointerDown);
        dom.canvas.addEventListener("pointerup", onCanvasPointerUp);
        dom.canvas.addEventListener("pointercancel", function () {
            state.swipe.active = false;
        });
        dom["touch-controls"].querySelectorAll("[data-direction]").forEach(function (button) {
            button.addEventListener("pointerdown", function (event) {
                event.preventDefault();
                queueDirection(button.getAttribute("data-direction"));
            });
        });
        document.addEventListener("keydown", onKeyDown);
        document.addEventListener("visibilitychange", onVisibilityChange);
        globalThis.addEventListener("blur", onWindowBlur);
        globalThis.addEventListener("focus", onWindowFocus);
        globalThis.addEventListener("offline", onOffline);
        globalThis.addEventListener("online", onOnline);
        globalThis.addEventListener("resize", resizeCanvas);
        globalThis.addEventListener("orientationchange", resizeCanvas);
        if (globalThis.matchMedia) {
            const query = globalThis.matchMedia("(prefers-reduced-motion: reduce)");
            state.reduceMotion = query.matches;
            if (typeof query.addEventListener === "function") {
                query.addEventListener("change", function (event) {
                    state.reduceMotion = event.matches;
                    draw();
                });
            }
        }
    }

    function bindSdkEvents() {
        state.ba.on("pause", function () {
            if (state.running && !state.paused) {
                pauseRound("host", true);
            }
        });
        state.ba.on("resume", function () {
            if (state.running && state.paused && state.pauseReason === "host") {
                resumeRound();
            }
        });
        state.ba.on("autotest:finish", function () {
            if (state.mode === "autotest" && !state.autotestDone) {
                state.autotestDone = true;
                if (state.running) {
                    finishRound("autotest_finish");
                } else {
                    void submitPendingResult();
                }
            }
        });
        state.ba.on("visibility", function (payload) {
            const visible = !payload || payload.visible !== false;
            if (!visible && state.running && !state.paused) {
                pauseRound("visibility", true);
            } else if (visible && state.running && state.paused && state.pauseReason === "visibility") {
                resumeRound();
            }
        });
        state.ba.on("session", function (context) {
            if (context && typeof context === "object" && typeof context.seed === "string") {
                state.context = context;
                state.seed = context.seed;
            }
        });
    }

    async function boot() {
        cacheDom();
        bindEvents();
        detectTouchMode();
        showBootMessage("loading", false);
        let sdk;
        try {
            sdk = await globalThis.BreaktimeArcade.init({ timeoutMs: 5000 });
        } catch (error) {
            showBootMessage("error_sdk", true);
            setAppState("boot-error");
            return;
        }
        state.ba = sdk;
        state.context = sdk.context || {};
        state.mode = typeof state.context.mode === "string" ? state.context.mode : "guest";
        state.seed = typeof state.context.seed === "string" ? state.context.seed : "";
        state.ba.ready();
        try {
            state.strings = await loadStrings(state.context);
        } catch (error) {
            showBootMessage("error_network", true);
            setAppState("boot-error");
            return;
        }
        if (state.ba.context) {
            state.ba.context.strings = state.strings;
        }
        applyLocaleMetadata();
        applyStaticLabels();
        await loadSettings();
        applyStaticLabels();
        bindSdkEvents();
        setHidden(dom["boot-screen"], true);
        resizeCanvas();
        if (state.mode === "autotest") {
            resetRound();
            startRound();
            return;
        }
        setAppState("ready");
        showOnly("start-screen");
        setHidden(dom["hud"], true);
        draw();
        announce("game_title");
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", function () {
            void boot();
        }, { once: true });
    } else {
        void boot();
    }
})();

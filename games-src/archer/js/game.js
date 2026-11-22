/* Archer — complete Breaktime Arcade cartridge.
 *
 * The archer stands at the centre of a layered sunset valley. Point at the
 * sky, hold to draw, release to loose a ballistic arrow. All platform traffic
 * goes through js/ba-sdk.js; this file owns only rendering, input, the fixed
 * simulation and the local UI. Randomness is seeded from ba.context.seed.
 */
(function () {
    "use strict";

    const LOGICAL_WIDTH = 960;
    const LOGICAL_HEIGHT = 640;
    const ARCHER = Object.freeze({ x: 480, y: 548, bowY: 496 });
    const COLORS = Object.freeze({
        ink: "#fff4df", muted: "#d7b7c8", gold: "#ffd28a",
        orange: "#ff974f", rose: "#ff5b7f", violet: "#6f3a7c",
        green: "#9fffc4", cyan: "#8be9ff",
    });
    const MAX_PARTICLES = 240;
    const MAX_POPUPS = 12;
    const MAX_EVENTS = 400;
    const EVENT_KINDS = Object.freeze(["start", "shoot", "hit", "miss", "combo", "end"]);
    const FALLBACK_LOCALE = Object.freeze({
        page_title: "Archer", game_title: "Archer", loading: "Loading…",
        error_sdk: "The range could not be opened.", error_network: "Connection problem.",
        start: "Begin", controls_title: "Controls", controls_hint: "Aim, hold, release.",
        pause: "Pause", resume: "Resume", game_over: "Round complete",
        best_unknown: "—", retry: "Retry",
    });
    const REQUIRED_KEYS = Object.freeze([
        "page_title", "game_title", "kicker", "rule", "start", "controls_title",
        "controls_hint", "orientation_hint", "sound_label", "sound_on", "sound_off",
        "guest_notice", "register_cta", "score_label", "combo_label", "time_label",
        "pause", "pause_title", "pause_reason", "resume", "restart", "exit",
        "session_kicker", "game_over", "your_score", "best_score", "rank",
        "hits_label", "shots_label", "accuracy_label", "best_combo_label",
        "top_scores", "play_again", "result_retry", "loading", "error_sdk",
        "error_network", "result_saving", "result_saved", "result_rejected",
        "session_expired", "best_unknown", "retry",
    ]);

    const dom = {};
    const state = {
        ba: null,
        context: null,
        strings: {},
        language: "en",
        mode: "boot",
        seed: "",
        rng: null,
        reduceMotion: false,
        soundEnabled: true,
        audioContext: null,
        audioUnlocked: false,
        storageTimer: 0,
        stage: null,
        canvas: null,
        ctx: null,
        view: { width: LOGICAL_WIDTH, height: LOGICAL_HEIGHT, dpr: 1 },
        round: null,
        submit: ArcherCore.createSubmitState(),
        roundId: 0,
        lastFrame: 0,
        accumulator: 0,
        rafId: 0,
        transitioning: false,
        sessionExpired: false,
        autoTimer: 0,
        autotestDone: false,
        networkLost: false,
        pointer: { x: ARCHER.x, y: 280, active: false, id: null },
        aim: { angle: -Math.PI / 2, holdMs: 0, drawing: false, source: "pointer" },
        touchMode: false,
        uiTimer: 0,
        lastHud: "",
    };

    const CORE = ArcherCore;

    function byId(id) {
        return document.getElementById(id);
    }

    function cacheDom() {
        [
            "app", "stage", "game-canvas", "hud", "hud-score-label", "hud-score",
            "hud-combo-label", "hud-combo", "hud-streak", "hud-time-label", "hud-time",
            "pause-button", "power-fill", "boot-screen", "boot-message", "boot-retry",
            "start-screen", "start-kicker", "start-title", "start-rule", "start-button",
            "controls-title", "controls-hint", "orientation-hint", "sound-label",
            "sound-toggle", "sound-toggle-text", "start-guest-notice", "pause-screen",
            "pause-title", "pause-reason", "resume-button", "restart-button",
            "pause-exit-button", "result-screen", "result-kicker", "result-title",
            "new-record", "your-score-label", "your-score", "best-score-label",
            "best-score", "rank-label", "rank-value", "hits-label", "result-hits",
            "shots-label", "result-shots", "accuracy-label", "result-accuracy",
            "best-combo-label", "result-best-combo", "result-status", "guest-notice",
            "top-scores-label", "top-scores", "play-again-button", "retry-submit-button",
            "result-exit-button", "register-cta", "network-banner", "focus-hint",
            "live-region",
        ].forEach(function (id) {
            dom[id] = byId(id);
        });
        state.stage = dom.stage;
        state.canvas = dom["game-canvas"];
        state.ctx = state.canvas.getContext("2d");
    }

    function safeText(value) {
        return typeof value === "string" ? value : "";
    }

    function t(key, params) {
        const strings = state.strings || {};
        let value = strings[key];
        if (typeof value !== "string" || value.length === 0) {
            value = FALLBACK_LOCALE[key] || key;
        }
        if (params && typeof params === "object") {
            Object.keys(params).forEach(function (name) {
                value = value.split("{" + name + "}").join(String(params[name]));
            });
        }
        return value;
    }

    function setNode(node, key, params) {
        if (node) {
            node.textContent = t(key, params);
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
            Object.keys(base).forEach(function (key) { result[key] = base[key]; });
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
            if (["en", "de", "nl", "ru", "fr", "es"].indexOf(code) === -1) {
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
                return mergeLocale(FALLBACK_LOCALE, context && context.strings);
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
        if (state.canvas) {
            state.canvas.setAttribute("aria-label", t("game_title"));
        }
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
        setNode(dom["pause-reason"], "pause_reason");
        setNode(dom["resume-button"], "resume");
        setNode(dom["restart-button"], "restart");
        setNode(dom["pause-exit-button"], "exit");
        setNode(dom["result-kicker"], "session_kicker");
        setNode(dom["result-title"], "game_over");
        setNode(dom["new-record"], "new_record");
        setNode(dom["your-score-label"], "your_score");
        setNode(dom["best-score-label"], "best_score");
        setNode(dom["rank-label"], "rank");
        setNode(dom["hits-label"], "hits_label");
        setNode(dom["shots-label"], "shots_label");
        setNode(dom["accuracy-label"], "accuracy_label");
        setNode(dom["best-combo-label"], "best_combo_label");
        setNode(dom["top-scores-label"], "top_scores");
        setNode(dom["play-again-button"], "play_again");
        setNode(dom["retry-submit-button"], "result_retry");
        setNode(dom["result-exit-button"], "exit");
        setNode(dom["register-cta"], "register_cta");
        setNode(dom["hud-score-label"], "score_label");
        setNode(dom["hud-combo-label"], "combo_label");
        setNode(dom["hud-time-label"], "time_label");
        dom["pause-button"].textContent = "";
        dom["pause-button"].setAttribute("aria-label", t("pause"));
        dom["pause-button"].setAttribute("aria-pressed", "false");
        dom["sound-toggle"].setAttribute("aria-pressed", state.soundEnabled ? "true" : "false");
        dom["sound-toggle"].setAttribute("aria-label", t("sound_label"));
        dom["boot-retry"].textContent = t("retry");
        dom["retry-submit-button"].textContent = t("result_retry");
        const guest = state.mode === "guest" || state.mode === "preview";
        setHidden(dom["start-guest-notice"], !guest);
        setHidden(dom["guest-notice"], true);
        setHidden(dom["register-cta"], !guest);
    }

    function setAppState(value) {
        dom.app.setAttribute("data-state", value);
        if (document.body) {
            document.body.setAttribute("data-game-state", value);
        }
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

    function showBootMessage(key, retry) {
        setNode(dom["boot-message"], key);
        dom["boot-retry"].textContent = t("retry");
        setHidden(dom["boot-retry"], !retry);
        setHidden(dom["boot-screen"], false);
        setAppState("boot");
    }

    function detectTouchMode() {
        state.touchMode = Boolean(
            (globalThis.matchMedia && globalThis.matchMedia("(pointer: coarse)").matches)
            || ("ontouchstart" in globalThis)
        );
    }

    function resizeCanvas() {
        const rect = state.stage.getBoundingClientRect();
        const width = Math.max(320, Math.round(rect.width));
        const height = Math.max(220, Math.round(rect.height));
        const dpr = Math.min(2, Math.max(1, globalThis.devicePixelRatio || 1));
        const pixelWidth = Math.round(width * dpr);
        const pixelHeight = Math.round(height * dpr);
        if (state.canvas.width !== pixelWidth || state.canvas.height !== pixelHeight) {
            state.canvas.width = pixelWidth;
            state.canvas.height = pixelHeight;
        }
        state.view = { width: LOGICAL_WIDTH, height: LOGICAL_HEIGHT, dpr: dpr };
        draw();
    }

    function nowMs() {
        return globalThis.performance && globalThis.performance.now
            ? globalThis.performance.now() : Date.now();
    }

    // ---------------------------------------------------------------- audio
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
            state.audioUnlocked = true;
        } catch (error) {
            state.audioContext = null;
        }
    }

    function tone(frequency, offset, duration, type, volume) {
        if (!state.soundEnabled || !state.audioContext || state.mode === "autotest") {
            return;
        }
        try {
            const audio = state.audioContext;
            const start = audio.currentTime + offset;
            const oscillator = audio.createOscillator();
            const gain = audio.createGain();
            oscillator.type = type || "sine";
            oscillator.frequency.setValueAtTime(frequency, start);
            gain.gain.setValueAtTime(0.0001, start);
            gain.gain.exponentialRampToValueAtTime(volume || 0.025, start + 0.012);
            gain.gain.exponentialRampToValueAtTime(0.0001, start + duration);
            oscillator.connect(gain);
            gain.connect(audio.destination);
            oscillator.start(start);
            oscillator.stop(start + duration + 0.02);
        } catch (error) {
            /* audio is optional */
        }
    }

    function soundDraw() { tone(170, 0, 0.12, "triangle", 0.018); }
    function soundShoot() { tone(620, 0, 0.09, "sawtooth", 0.025); }
    function soundHit(kind) {
        const base = kind === "phoenix" ? 880 : kind === "guardian" ? 210 : 520;
        tone(base, 0, 0.08, "triangle", 0.03);
        tone(base * 1.5, 0.05, 0.12, "sine", 0.025);
    }
    function soundCombo() { tone(740, 0, 0.09, "sine", 0.022); tone(1110, 0.07, 0.12, "sine", 0.02); }
    function soundEnd() { tone(330, 0, 0.4, "triangle", 0.03); tone(220, 0.2, 0.5, "sine", 0.02); }

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
        if (!state.ba || state.mode === "autotest") {
            return;
        }
        if (state.storageTimer) {
            globalThis.clearTimeout(state.storageTimer);
        }
        state.storageTimer = globalThis.setTimeout(function () {
            state.storageTimer = 0;
            state.ba.storage.set("archer.settings.v1", {
                soundEnabled: state.soundEnabled,
            }).catch(function () {});
        }, 800);
    }

    function loadSettings() {
        if (!state.ba) {
            return Promise.resolve();
        }
        return state.ba.storage.get("archer.settings.v1").then(function (value) {
            if (value && typeof value === "object" && typeof value.soundEnabled === "boolean") {
                setSoundEnabled(value.soundEnabled, false);
            }
        }).catch(function () {});
    }

    // ------------------------------------------------------------- round model
    function makeTarget(kind) {
        return CORE.spawnTarget(kind, { width: LOGICAL_WIDTH, height: LOGICAL_HEIGHT }, state.rng);
    }

    function resetRound() {
        const roundId = (state.round ? state.round.id : 0) + 1;
        state.roundId = roundId;
        state.round = {
            id: roundId,
            elapsed: 0,
            running: false,
            paused: false,
            pauseReason: "",
            score: CORE.createScore(),
            targets: [],
            arrows: [],
            particles: [],
            popups: [],
            spawnTimer: 0.8,
            phase: 0,
            starting: true,
            finished: false,
            eventLog: { v: 1, seed: state.seed, events: [] },
            eventBytes: 0,
            lastShotAt: -1,
            autoTimer: 0,
        };
        state.submit = CORE.createSubmitState();
        state.aim.holdMs = 0;
        state.aim.drawing = false;
        state.pointer.active = false;
        state.autotestDone = false;
        state.autoTimer = 0;
        state.lastHud = "";
        setHidden(dom["power-fill"], true);
        dom["power-fill"].style.width = "0%";
        stageAim(false);
        updateHud(true);
    }

    function stageAim(active) {
        if (state.stage) {
            state.stage.setAttribute("data-aiming", active ? "true" : "false");
        }
    }

    function logEvent(kind, data) {
        const round = state.round;
        if (!round || round.finished || EVENT_KINDS.indexOf(kind) === -1) {
            return;
        }
        if (round.eventLog.events.length >= MAX_EVENTS) {
            return;
        }
        const event = {
            t: Math.max(0, Math.min(60000, Math.round(round.elapsed * 1000))),
            k: kind,
            d: data && typeof data === "object" ? data : {},
        };
        const size = JSON.stringify(event).length;
        if (round.eventBytes + size > 150000) {
            return;
        }
        round.eventBytes += size;
        round.eventLog.events.push(event);
    }

    function startRound() {
        if (!state.round || state.round.running || state.round.finished) {
            return;
        }
        ensureAudio();
        state.round.running = true;
        state.round.starting = false;
        state.round.startedAt = nowMs();
        logEvent("start", { mode: state.mode });
        showOnly(null);
        setHidden(dom.hud, false);
        setAppState("playing");
        announce("game_title");
        renderHud(true);
        startLoop();
    }

    function pauseRound(reason, show) {
        const round = state.round;
        if (!round || !round.running || round.paused) {
            return;
        }
        round.paused = true;
        round.pauseReason = reason || "manual";
        state.aim.drawing = false;
        state.pointer.active = false;
        stageAim(false);
        if (state.audioContext) {
            state.audioContext.suspend().catch(function () {});
        }
        if (show) {
            setNode(dom["pause-reason"], reason === "network" ? "network_lost" : "pause_reason");
            showOnly("pause-screen");
            setAppState("paused");
            announce("pause_title");
        }
    }

    function resumeRound() {
        const round = state.round;
        if (!round || !round.paused || round.finished) {
            return;
        }
        round.paused = false;
        round.pauseReason = "";
        showOnly(null);
        setHidden(dom.hud, false);
        setAppState("playing");
        state.lastFrame = 0;
        ensureAudio();
        startLoop();
    }

    function finishRound(reason) {
        const round = state.round;
        if (!round || round.finished) {
            return;
        }
        for (const arrow of round.arrows) {
            if (arrow.alive) {
                arrow.alive = false;
                CORE.registerShot(round.score, null);
                logEvent("miss", { reason: "round_end" });
            }
        }
        round.arrows = [];
        round.targets.forEach(function (target) { target.alive = false; });
        logEvent("end", { score: round.score.score, reason: reason || "time" });
        round.finished = true;
        round.running = false;
        round.paused = false;
        state.aim.drawing = false;
        state.pointer.active = false;
        stageAim(false);
        if (state.rafId) {
            globalThis.cancelAnimationFrame(state.rafId);
            state.rafId = 0;
        }
        soundEnd();
        renderResult();
        pendingSubmit();
    }

    function pendingSubmit() {
        const round = state.round;
        if (!round || !state.ba) {
            return;
        }
        const payload = {
            value: Math.max(0, Math.min(100000, Math.round(round.score.score))),
            durationMs: Math.max(0, Math.min(60000, Math.round(round.elapsed * 1000))),
            seed: state.seed,
            eventLog: round.eventLog,
            clientMeta: {
                hits: round.score.hits,
                shots: round.score.shots,
                bestCombo: round.score.bestStreak,
                source: "archer-1.0.0",
            },
        };
        if (!CORE.beginSubmit(state.submit, payload)) {
            return;
        }
        setNode(dom["result-status"], "result_saving");
        dom["result-status"].classList.remove("is-error");
        setHidden(dom["retry-submit-button"], true);
        sendResult(round.id, 1);
    }

    function retryable(code) {
        if (!code) {
            return true;
        }
        if (code === "E_GUEST_FORBIDDEN") {
            return false;
        }
        return code.indexOf("E_SESSION_") !== 0
            && code.indexOf("E_SCORE_") !== 0
            && code.indexOf("E_DURATION_") !== 0
            && code.indexOf("E_MESSAGE_") !== 0
            && code !== "E_OWNERSHIP";
    }

    function sendResult(roundId, attempt) {
        if (!state.submit.pending || !state.ba) {
            return;
        }
        state.ba.submitResult(state.submit.pending).then(function (response) {
            if (!state.round || state.round.id !== roundId) {
                return;
            }
            CORE.completeSubmit(state.submit, true);
            handleResult(response);
        }).catch(function (error) {
            if (!state.round || state.round.id !== roundId) {
                return;
            }
            const code = error && typeof error.code === "string" ? error.code : "";
            if (code === "E_GUEST_FORBIDDEN") {
                CORE.completeSubmit(state.submit, true);
                handleResult({ status: "guest", rank: null, isRecord: false, isPersonalBest: false });
                return;
            }
            const canRetry = retryable(code) && attempt < 3;
            state.submit.submitting = false;
            if (canRetry) {
                globalThis.setTimeout(function () { sendResult(roundId, attempt + 1); }, 350 * attempt);
                return;
            }
            state.submit.retryable = retryable(code);
            setNode(dom["result-status"], code.indexOf("E_SESSION_") === 0 ? "session_expired" : "result_rejected");
            dom["result-status"].classList.add("is-error");
            setHidden(dom["retry-submit-button"], !state.submit.retryable || state.mode === "autotest");
            setNode(dom["retry-submit-button"], "result_retry");
            announce("result_rejected");
        });
    }

    function handleResult(response) {
        const result = response && typeof response === "object" ? response : {};
        const guest = result.status === "guest" || state.mode === "guest" || state.mode === "preview";
        if (state.mode !== "autotest") {
            if (guest) {
                setNode(dom["result-status"], "result_guest");
                dom["result-status"].classList.remove("is-error");
                setHidden(dom["guest-notice"], false);
                setHidden(dom["register-cta"], false);
            } else if (result.status === "quarantined") {
                setNode(dom["result-status"], "result_rejected");
                dom["result-status"].classList.add("is-error");
            } else {
                setNode(dom["result-status"], "result_saved");
                setHidden(dom["new-record"], result.isRecord !== true);
                if (result.rank !== null && result.rank !== undefined) {
                    dom["rank-value"].textContent = String(result.rank);
                }
            }
        }
        if (!guest) {
            loadLeaderboard();
        }
    }

    function loadLeaderboard() {
        if (!state.ba || state.mode === "autotest") {
            return;
        }
        Promise.allSettled([
            state.ba.leaderboard.top(10),
            state.ba.leaderboard.myBest(),
        ]).then(function (outcomes) {
            if (outcomes[0].status === "fulfilled" && outcomes[0].value) {
                renderLeaderboard(outcomes[0].value.entries || []);
            }
            if (outcomes[1].status === "fulfilled" && outcomes[1].value
                && typeof outcomes[1].value.value === "number") {
                dom["best-score"].textContent = String(outcomes[1].value.value);
            }
        });
    }

    function renderLeaderboard(entries) {
        const list = dom["top-scores"];
        list.replaceChildren();
        if (!Array.isArray(entries) || entries.length === 0) {
            const item = document.createElement("li");
            item.className = "leaderboard-empty";
            item.textContent = t("best_unknown");
            list.appendChild(item);
            return;
        }
        entries.slice(0, 10).forEach(function (entry) {
            const item = document.createElement("li");
            const rank = document.createElement("span");
            rank.textContent = "#" + String(entry.rank || 0);
            const name = document.createElement("span");
            name.textContent = entry.nickname || "—";
            const value = document.createElement("strong");
            value.textContent = String(entry.value ?? "—");
            item.append(rank, name, value);
            list.appendChild(item);
        });
    }

    function renderResult() {
        const score = state.round.score;
        dom["your-score"].textContent = String(score.score);
        dom["result-hits"].textContent = String(score.hits);
        dom["result-shots"].textContent = String(score.shots);
        dom["result-accuracy"].textContent = CORE.formatAccuracy(score) + "%";
        dom["result-best-combo"].textContent = String(score.bestStreak);
        dom["best-score"].textContent = t("best_unknown");
        dom["rank-value"].textContent = "—";
        setNode(dom["result-title"], state.round.elapsed >= CORE.ROUND_SECONDS ? "game_over" : "round_finished");
        setHidden(dom["new-record"], true);
        showOnly("result-screen");
        setHidden(dom.hud, true);
        setAppState("result");
        announce("session_kicker");
    }

    function shoot(angle, power) {
        const round = state.round;
        if (!round || !round.running || round.paused || round.finished) {
            return false;
        }
        const arrow = CORE.arrowFromShot(
            { x: ARCHER.x + Math.cos(angle) * 34, y: ARCHER.bowY + Math.sin(angle) * 34 },
            angle, power, round.score.shots,
        );
        round.arrows.push(arrow);
        logEvent("shoot", {
            angle: Math.round(angle * 1000) / 1000,
            power: Math.round(power * 100) / 100,
        });
        soundShoot();
        return true;
    }

    function registerHit(arrow, target, points) {
        const round = state.round;
        target.alive = false;
        arrow.alive = false;
        round.targets = round.targets.filter(function (item) { return item.alive; });
        const outcome = CORE.registerShot(round.score, target);
        logEvent("hit", {
            kind: target.kind, points: outcome.points, combo: round.score.streak,
            multiplier: round.score.multiplier,
        });
        if (round.score.streak > 0 && round.score.multiplier > 1
            && round.score.streak % CORE.HITS_PER_MULTIPLIER === 0) {
            logEvent("combo", { multiplier: round.score.multiplier, streak: round.score.streak });
            soundCombo();
        }
        spawnImpact(target, outcome.points, target.kind);
        soundHit(target.kind);
        renderHud(true);
        return outcome;
    }

    function registerMiss(arrow) {
        const round = state.round;
        if (!round || !arrow || !arrow.alive) {
            return;
        }
        arrow.alive = false;
        CORE.registerShot(round.score, null);
        logEvent("miss", { reason: "bounds" });
        renderHud(true);
    }

    function spawnImpact(target, points, kind) {
        const round = state.round;
        const color = kind === "phoenix" ? COLORS.rose
            : kind === "wisp" ? COLORS.cyan
                : kind === "guardian" ? "#d8c5b2" : COLORS.gold;
        const count = state.reduceMotion ? 6 : 18;
        for (let index = 0; index < count && round.particles.length < MAX_PARTICLES; index += 1) {
            const angle = state.rng.float() * Math.PI * 2;
            const speed = 60 + state.rng.float() * 220;
            round.particles.push({
                x: target.x, y: target.y, vx: Math.cos(angle) * speed,
                vy: Math.sin(angle) * speed - 40, life: 0.45 + state.rng.float() * 0.55,
                maxLife: 1, color: color, size: 2 + state.rng.float() * 4,
            });
        }
        if (round.popups.length >= MAX_POPUPS) {
            round.popups.shift();
        }
        round.popups.push({
            x: target.x, y: target.y - target.radius, text: "+" + String(points),
            life: 1.1, color: color,
        });
    }

    function fireFromAim() {
        if (!state.aim.drawing || !state.round || state.round.finished) {
            return;
        }
        const power = CORE.powerFromHold(state.aim.holdMs);
        state.aim.drawing = false;
        state.aim.holdMs = 0;
        stageAim(false);
        setHidden(dom["power-fill"], true);
        shoot(state.aim.angle, power);
    }

    function aimAt(clientX, clientY) {
        const rect = state.canvas.getBoundingClientRect();
        const logicalX = ((clientX - rect.left) / Math.max(1, rect.width)) * LOGICAL_WIDTH;
        const logicalY = ((clientY - rect.top) / Math.max(1, rect.height)) * LOGICAL_HEIGHT;
        state.pointer.x = logicalX;
        state.pointer.y = logicalY;
        state.aim.angle = CORE.angleFromPoint(
            { x: ARCHER.x, y: ARCHER.bowY }, { x: logicalX, y: logicalY },
        );
    }

    function beginDraw() {
        if (!state.round || !state.round.running || state.round.paused || state.round.finished) {
            return;
        }
        ensureAudio();
        state.aim.drawing = true;
        state.aim.holdMs = 0;
        state.aim.source = "pointer";
        stageAim(true);
        soundDraw();
    }

    function cancelDraw() {
        if (!state.aim.drawing) {
            return;
        }
        state.aim.drawing = false;
        state.aim.holdMs = 0;
        stageAim(false);
        setHidden(dom["power-fill"], true);
    }

    // ------------------------------------------------------------------ input
    function onPointerDown(event) {
        if (event.button !== undefined && event.button !== 0) {
            return;
        }
        event.preventDefault();
        state.pointer.active = true;
        state.pointer.id = event.pointerId;
        aimAt(event.clientX, event.clientY);
        try {
            state.canvas.setPointerCapture(event.pointerId);
        } catch (error) { /* optional */ }
        beginDraw();
    }

    function onPointerMove(event) {
        if (event.pointerType === "mouse" || state.pointer.active) {
            aimAt(event.clientX, event.clientY);
        }
    }

    function onPointerUp(event) {
        if (state.pointer.id !== null && event.pointerId !== state.pointer.id) {
            return;
        }
        event.preventDefault();
        state.pointer.active = false;
        state.pointer.id = null;
        try {
            state.canvas.releasePointerCapture(event.pointerId);
        } catch (error) { /* optional */ }
        fireFromAim();
    }

    function onPointerCancel(event) {
        state.pointer.active = false;
        state.pointer.id = null;
        cancelDraw();
    }

    function onKeyDown(event) {
        const key = String(event.key || "").toLowerCase();
        const map = {
            arrowleft: "left", a: "left", arrowright: "right", d: "right",
            arrowup: "up", w: "up", arrowdown: "down", s: "down",
        };
        if (key === " " || key === "spacebar") {
            event.preventDefault();
            if (!event.repeat && state.round && state.round.running) {
                beginDraw();
            }
            return;
        }
        if (key === "p" || key === "escape") {
            if (state.round && state.round.running) {
                event.preventDefault();
                state.round.paused ? resumeRound() : pauseRound("manual", true);
            }
            return;
        }
        const dir = map[key];
        if (dir) {
            event.preventDefault();
            const step = 0.045;
            if (dir === "left") state.aim.angle = Math.max(CORE.MIN_ANGLE, state.aim.angle - step);
            if (dir === "right") state.aim.angle = Math.min(CORE.MAX_ANGLE, state.aim.angle + step);
            if (dir === "up") state.aim.angle = Math.max(CORE.MIN_ANGLE, state.aim.angle - step * 0.4);
            if (dir === "down") state.aim.angle = Math.min(CORE.MAX_ANGLE, state.aim.angle + step * 0.4);
        }
    }

    function onKeyUp(event) {
        if (event.key === " " || event.key === "spacebar") {
            event.preventDefault();
            fireFromAim();
        }
    }

    function onVisibilityChange() {
        if (document.visibilityState !== "visible") {
            cancelDraw();
            if (state.round && state.round.running && !state.round.paused) {
                pauseRound("visibility", true);
            }
        }
    }

    function onWindowBlur() {
        cancelDraw();
        if (state.round && state.round.running && !state.round.paused) {
            pauseRound("blur", true);
        }
    }

    function onWindowFocus() {
        if (state.round && state.round.paused && state.round.pauseReason === "focus") {
            resumeRound();
        }
    }

    // ------------------------------------------------------------------- loop
    function startLoop() {
        if (state.rafId) {
            return;
        }
        state.lastFrame = 0;
        state.accumulator = 0;
        state.rafId = globalThis.requestAnimationFrame(frame);
    }

    function frame(now) {
        if (!state.round || state.round.finished || state.round.paused) {
            state.rafId = 0;
            return;
        }
        if (!state.lastFrame) {
            state.lastFrame = now;
            state.rafId = globalThis.requestAnimationFrame(frame);
            return;
        }
        const delta = Math.min(0.1, Math.max(0, (now - state.lastFrame) / 1000));
        state.lastFrame = now;
        state.accumulator += delta;
        let safety = 0;
        while (state.accumulator >= CORE.STEP_SECONDS && safety < 240) {
            step(CORE.STEP_SECONDS);
            state.accumulator -= CORE.STEP_SECONDS;
            safety += 1;
        }
        draw();
        state.rafId = globalThis.requestAnimationFrame(frame);
    }

    function step(dt) {
        const round = state.round;
        if (!round || !round.running || round.paused || round.finished) {
            return;
        }
        round.elapsed = Math.min(CORE.ROUND_SECONDS, round.elapsed + dt);
        round.phase = CORE.phaseFor(round.elapsed);
        if (state.aim.drawing) {
            state.aim.holdMs = Math.min(CORE.MAX_HOLD_MS, state.aim.holdMs + dt * 1000);
        }
        if (state.mode === "autotest") {
            round.autoTimer -= dt;
            if (round.autoTimer <= 0) {
                autoShot();
                round.autoTimer = 0.42;
            }
        }
        for (const target of round.targets) {
            CORE.updateTarget(target, dt, { width: LOGICAL_WIDTH, height: LOGICAL_HEIGHT });
        }
        round.targets = round.targets.filter(function (target) {
            return target.alive && target.x > -180 && target.x < LOGICAL_WIDTH + 180;
        });
        for (const arrow of round.arrows) {
            if (!arrow.alive) {
                continue;
            }
            CORE.stepArrow(arrow, dt);
            let hit = null;
            for (const target of round.targets) {
                if (target.alive && CORE.hits(arrow, target)) {
                    hit = target;
                    break;
                }
            }
            if (hit) {
                registerHit(arrow, hit, 0);
            } else if (!CORE.arrowInBounds(arrow, { width: LOGICAL_WIDTH, height: LOGICAL_HEIGHT })) {
                registerMiss(arrow);
            }
        }
        round.arrows = round.arrows.filter(function (arrow) { return arrow.alive; });
        for (const particle of round.particles) {
            particle.life -= dt;
            particle.x += particle.vx * dt;
            particle.y += particle.vy * dt;
            particle.vy += 210 * dt;
        }
        round.particles = round.particles.filter(function (particle) { return particle.life > 0; });
        for (const popup of round.popups) {
            popup.life -= dt;
            popup.y -= 24 * dt;
        }
        round.popups = round.popups.filter(function (popup) { return popup.life > 0; });
        round.spawnTimer -= dt;
        const plan = CORE.spawnPlan(round.phase);
        if (round.spawnTimer <= 0 && round.targets.length < plan.max) {
            let kind = plan.mix[state.rng.int(plan.mix.length)];
            if (kind === "phoenix" && state.rng.float() > 0.22) {
                kind = state.rng.int(2) === 0 ? "sun" : "wisp";
            }
            round.targets.push(makeTarget(kind));
            round.spawnTimer = plan.interval * (0.78 + state.rng.float() * 0.44);
        }
        if (state.mode === "autotest" && round.elapsed >= 22) {
            state.autotestDone = true;
            finishRound("autotest_budget");
            return;
        }
        if (round.elapsed >= CORE.ROUND_SECONDS) {
            finishRound("time");
            return;
        }
        renderHud(false);
    }

    function autoShot() {
        const round = state.round;
        if (!round || round.targets.length === 0) {
            return;
        }
        let best = null;
        let bestDistance = Infinity;
        for (const target of round.targets) {
            const dx = target.x - ARCHER.x;
            const dy = target.y - ARCHER.bowY;
            const distance = dx * dx + dy * dy;
            if (distance < bestDistance) {
                bestDistance = distance;
                best = target;
            }
        }
        if (best) {
            state.aim.angle = CORE.angleFromPoint(
                { x: ARCHER.x, y: ARCHER.bowY }, { x: best.x, y: best.y },
            );
            shoot(state.aim.angle, 0.72);
        }
    }

    // --------------------------------------------------------------- rendering
    function draw() {
        const ctx = state.ctx;
        if (!ctx || !state.canvas) {
            return;
        }
        const dpr = state.view.dpr;
        ctx.setTransform(1, 0, 0, 1, 0, 0);
        ctx.clearRect(0, 0, state.canvas.width, state.canvas.height);
        ctx.setTransform(
            state.canvas.width / LOGICAL_WIDTH, 0, 0, state.canvas.height / LOGICAL_HEIGHT, 0, 0,
        );
        drawBackground(ctx, state.round ? state.round.elapsed : 0);
        if (state.round) {
            for (const target of state.round.targets) {
                drawTarget(ctx, target);
            }
            for (const arrow of state.round.arrows) {
                drawArrow(ctx, arrow);
            }
            for (const particle of state.round.particles) {
                drawParticle(ctx, particle);
            }
            for (const popup of state.round.popups) {
                drawPopup(ctx, popup);
            }
        }
        drawArcher(ctx);
        if (state.round && state.round.running && !state.round.paused && state.aim.drawing) {
            drawPreview(ctx);
            drawPower(ctx);
        }
        if (!state.round || !state.round.running) {
            drawIdleHint(ctx);
        }
    }

    function drawBackground(ctx, elapsed) {
        const sky = ctx.createLinearGradient(0, 0, 0, LOGICAL_HEIGHT);
        sky.addColorStop(0, "#160b23");
        sky.addColorStop(0.34, "#4a1f4d");
        sky.addColorStop(0.58, "#b64854");
        sky.addColorStop(0.73, "#ff9a5c");
        sky.addColorStop(1, "#241026");
        ctx.fillStyle = sky;
        ctx.fillRect(0, 0, LOGICAL_WIDTH, LOGICAL_HEIGHT);

        const glow = ctx.createRadialGradient(720, 240, 20, 720, 240, 320);
        glow.addColorStop(0, "rgba(255, 229, 168, 0.75)");
        glow.addColorStop(0.35, "rgba(255, 160, 92, 0.18)");
        glow.addColorStop(1, "rgba(255, 120, 90, 0)");
        ctx.fillStyle = glow;
        ctx.fillRect(0, 0, LOGICAL_WIDTH, LOGICAL_HEIGHT);

        ctx.save();
        ctx.globalAlpha = 0.85;
        const sun = ctx.createRadialGradient(720, 246, 4, 720, 246, 62);
        sun.addColorStop(0, "#fff6d6");
        sun.addColorStop(0.55, "#ffd48e");
        sun.addColorStop(1, "rgba(255, 150, 90, 0)");
        ctx.fillStyle = sun;
        ctx.beginPath();
        ctx.arc(720, 246, 66, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();

        drawStars(ctx);
        drawClouds(ctx, elapsed);
        drawMountainLayer(ctx, 430, "#35152f", 0.7, elapsed * 4, 0);
        drawMountainLayer(ctx, 486, "#24102b", 1.0, elapsed * 7, 120);
        drawMountainLayer(ctx, 548, "#160a20", 1.35, elapsed * 10, 260);
        drawGround(ctx, elapsed);
        drawEmbers(ctx, elapsed);
    }

    function drawStars(ctx) {
        const stars = [
            [80, 50, 1.5], [160, 92, 1], [260, 42, 1.2], [340, 105, 1],
            [440, 52, 1.5], [560, 28, 1], [880, 66, 1.4], [930, 130, 1],
            [620, 120, 1.2], [740, 86, 1],
        ];
        ctx.save();
        for (const [x, y, r] of stars) {
            ctx.globalAlpha = 0.35 + 0.2 * Math.sin((x + y) * 0.01);
            ctx.fillStyle = "#ffeacb";
            ctx.beginPath();
            ctx.arc(x, y, r, 0, Math.PI * 2);
            ctx.fill();
        }
        ctx.restore();
    }

    function drawClouds(ctx, elapsed) {
        ctx.save();
        ctx.globalAlpha = 0.16;
        ctx.fillStyle = "#ffd2b4";
        for (let index = 0; index < 4; index += 1) {
            const x = ((index * 290 + elapsed * (8 + index * 3)) % (LOGICAL_WIDTH + 220)) - 110;
            const y = 210 + index * 38;
            ctx.beginPath();
            ctx.ellipse(x, y, 120 + index * 18, 12 + index * 2, 0, 0, Math.PI * 2);
            ctx.fill();
        }
        ctx.restore();
    }

    function drawMountainLayer(ctx, baseY, color, scale, shift, offset) {
        ctx.save();
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.moveTo(-40, LOGICAL_HEIGHT);
        ctx.lineTo(-40, baseY);
        for (let index = 0; index < 9; index += 1) {
            const x = offset + index * 140 - (shift % 140);
            const peak = baseY - 60 * scale - (index % 3) * 34 * scale;
            ctx.lineTo(x, baseY - 24 * scale);
            ctx.lineTo(x + 38, peak);
            ctx.lineTo(x + 78, baseY - 18 * scale);
        }
        ctx.lineTo(LOGICAL_WIDTH + 40, baseY);
        ctx.lineTo(LOGICAL_WIDTH + 40, LOGICAL_HEIGHT);
        ctx.closePath();
        ctx.fill();
        ctx.restore();
    }

    function drawGround(ctx, elapsed) {
        const ground = ctx.createLinearGradient(0, 552, 0, LOGICAL_HEIGHT);
        ground.addColorStop(0, "#28122d");
        ground.addColorStop(1, "#0c0612");
        ctx.fillStyle = ground;
        ctx.fillRect(0, 552, LOGICAL_WIDTH, LOGICAL_HEIGHT - 552);
        ctx.save();
        ctx.strokeStyle = "rgba(255, 176, 112, 0.18)";
        ctx.lineWidth = 1;
        for (let index = 0; index < 28; index += 1) {
            const x = index * 37 + Math.sin(elapsed * 0.3 + index) * 5;
            const h = 4 + (index % 5) * 3;
            ctx.beginPath();
            ctx.moveTo(x, 600);
            ctx.lineTo(x + 2, 600 - h);
            ctx.stroke();
        }
        ctx.restore();
    }

    function drawEmbers(ctx, elapsed) {
        ctx.save();
        for (let index = 0; index < 18; index += 1) {
            const x = (index * 61 + elapsed * (8 + (index % 4) * 4)) % LOGICAL_WIDTH;
            const y = 560 - ((elapsed * 16 + index * 31) % 380);
            ctx.globalAlpha = 0.18 + 0.2 * Math.sin(elapsed + index);
            ctx.fillStyle = index % 3 === 0 ? "#ffcf8a" : "#ff8f72";
            ctx.beginPath();
            ctx.arc(x, y, 1.5 + (index % 3), 0, Math.PI * 2);
            ctx.fill();
        }
        ctx.restore();
    }

    function drawArcher(ctx) {
        const angle = state.aim.angle;
        const drawRatio = state.aim.drawing ? CORE.powerFromHold(state.aim.holdMs) : 0.3;
        const pull = 20 + drawRatio * 34;
        ctx.save();
        ctx.translate(ARCHER.x, ARCHER.y);
        ctx.scale(1.24, 1.24);
        // soft ground aura
        const aura = ctx.createRadialGradient(0, 34, 4, 0, 34, 94);
        aura.addColorStop(0, "rgba(255, 168, 92, 0.16)");
        aura.addColorStop(1, "rgba(255, 120, 90, 0)");
        ctx.fillStyle = aura;
        ctx.beginPath();
        ctx.ellipse(0, 42, 92, 26, 0, 0, Math.PI * 2);
        ctx.fill();
        // quiver behind the shoulders
        ctx.save();
        ctx.rotate(-0.28);
        ctx.fillStyle = "#40202f";
        ctx.beginPath();
        ctx.roundRect ? ctx.roundRect(-38, -12, 16, 48, 7) : ctx.rect(-38, -12, 16, 48);
        ctx.fill();
        ctx.strokeStyle = "#b07a5d";
        ctx.lineWidth = 1.5;
        for (let index = 0; index < 3; index += 1) {
            ctx.beginPath();
            ctx.moveTo(-35 + index * 4, -12);
            ctx.lineTo(-37 + index * 4, -30);
            ctx.stroke();
        }
        ctx.restore();
        // legs and boots
        ctx.fillStyle = "#1b0c22";
        ctx.beginPath();
        ctx.moveTo(-23, 24);
        ctx.lineTo(-6, 24);
        ctx.lineTo(-8, 62);
        ctx.lineTo(-28, 62);
        ctx.closePath();
        ctx.fill();
        ctx.beginPath();
        ctx.moveTo(7, 24);
        ctx.lineTo(24, 24);
        ctx.lineTo(30, 62);
        ctx.lineTo(9, 62);
        ctx.closePath();
        ctx.fill();
        // cloak silhouette
        const cloak = ctx.createLinearGradient(0, -66, 0, 58);
        cloak.addColorStop(0, "#6b2b4f");
        cloak.addColorStop(0.55, "#3a1636");
        cloak.addColorStop(1, "#110a19");
        ctx.fillStyle = cloak;
        ctx.beginPath();
        ctx.moveTo(-18, -46);
        ctx.quadraticCurveTo(-48, -30, -50, 4);
        ctx.lineTo(-60, 52);
        ctx.lineTo(-30, 44);
        ctx.lineTo(-17, 58);
        ctx.lineTo(-4, 44);
        ctx.lineTo(10, 57);
        ctx.lineTo(22, 42);
        ctx.lineTo(44, 50);
        ctx.lineTo(48, 12);
        ctx.quadraticCurveTo(46, -30, 18, -46);
        ctx.closePath();
        ctx.fill();
        // shoulder mantle / fur
        ctx.fillStyle = "#a17a6a";
        ctx.beginPath();
        ctx.ellipse(0, -39, 29, 11, -0.06, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = "#c59a7e";
        ctx.beginPath();
        ctx.ellipse(-8, -42, 14, 4, -0.2, 0, Math.PI * 2);
        ctx.fill();
        // armored torso
        const torso = ctx.createLinearGradient(-20, -30, 18, 22);
        torso.addColorStop(0, "#82425e");
        torso.addColorStop(0.5, "#562b48");
        torso.addColorStop(1, "#2b142c");
        ctx.fillStyle = torso;
        ctx.beginPath();
        ctx.moveTo(-20, -30);
        ctx.quadraticCurveTo(0, -40, 20, -30);
        ctx.lineTo(15, 20);
        ctx.quadraticCurveTo(0, 30, -15, 20);
        ctx.closePath();
        ctx.fill();
        ctx.strokeStyle = "rgba(255, 197, 143, 0.35)";
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(0, -27);
        ctx.lineTo(0, 18);
        ctx.stroke();
        // belt
        ctx.fillStyle = "#2a1327";
        ctx.fillRect(-20, 14, 40, 8);
        ctx.fillStyle = "#d09a58";
        ctx.beginPath();
        ctx.arc(0, 18, 3.5, 0, Math.PI * 2);
        ctx.fill();
        // hood / head
        ctx.fillStyle = "#34152f";
        ctx.beginPath();
        ctx.moveTo(-21, -46);
        ctx.quadraticCurveTo(-24, -78, 0, -86);
        ctx.quadraticCurveTo(24, -78, 21, -46);
        ctx.quadraticCurveTo(10, -56, 0, -56);
        ctx.quadraticCurveTo(-10, -56, -21, -46);
        ctx.closePath();
        ctx.fill();
        ctx.fillStyle = "#c18b70";
        ctx.beginPath();
        ctx.ellipse(0, -62, 13, 17, 0, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = "#2b102e";
        ctx.beginPath();
        ctx.arc(0, -74, 15, Math.PI * 1.02, Math.PI * 1.98);
        ctx.fill();
        ctx.fillStyle = "#ffd28a";
        ctx.beginPath();
        ctx.arc(4, -63, 1.8, 0, Math.PI * 2);
        ctx.fill();
        // bow group; the grip sits in the front hand
        const gripX = 0;
        const gripY = -38;
        const bowR = 67;
        const handX = Math.cos(angle) * 26;
        const handY = gripY + Math.sin(angle) * 26;
        ctx.strokeStyle = "#7b4050";
        ctx.lineWidth = 9;
        ctx.lineCap = "round";
        ctx.beginPath();
        ctx.moveTo(-16, -33);
        ctx.lineTo(handX * 0.55, handY * 0.72 - 8);
        ctx.lineTo(handX, handY);
        ctx.stroke();
        const stringX = handX - Math.cos(angle) * pull;
        const stringY = handY - Math.sin(angle) * pull;
        ctx.beginPath();
        ctx.moveTo(15, -34);
        ctx.lineTo(stringX * 0.7, stringY * 0.65 - 2);
        ctx.lineTo(stringX, stringY);
        ctx.stroke();
        ctx.save();
        ctx.translate(handX, handY);
        ctx.rotate(angle);
        const bowGradient = ctx.createLinearGradient(-16, 0, 0, bowR);
        bowGradient.addColorStop(0, "#ffe4a7");
        bowGradient.addColorStop(0.45, "#df9c5e");
        bowGradient.addColorStop(1, "#7e3950");
        ctx.strokeStyle = bowGradient;
        ctx.lineWidth = 6;
        ctx.lineCap = "round";
        ctx.beginPath();
        ctx.arc(0, 0, bowR, -Math.PI * 0.5, Math.PI * 0.5);
        ctx.stroke();
        ctx.strokeStyle = "#f5d19a";
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(Math.cos(-Math.PI * 0.5) * bowR, Math.sin(-Math.PI * 0.5) * bowR);
        ctx.lineTo(-pull, 0);
        ctx.lineTo(Math.cos(Math.PI * 0.5) * bowR, Math.sin(Math.PI * 0.5) * bowR);
        ctx.stroke();
        // arrow nocked and drawn
        ctx.strokeStyle = "#ffe9bd";
        ctx.lineWidth = 2.4;
        ctx.beginPath();
        ctx.moveTo(-pull, 0);
        ctx.lineTo(bowR - 2, 0);
        ctx.stroke();
        ctx.fillStyle = "#ffe0a1";
        ctx.beginPath();
        ctx.moveTo(bowR + 3, 0);
        ctx.lineTo(bowR - 10, -5);
        ctx.lineTo(bowR - 10, 5);
        ctx.closePath();
        ctx.fill();
        ctx.fillStyle = "#e86e6e";
        ctx.beginPath();
        ctx.moveTo(-pull, 0);
        ctx.lineTo(-pull - 8, -5);
        ctx.lineTo(-pull - 8, 5);
        ctx.closePath();
        ctx.fill();
        ctx.restore();
        // front hand / bracer
        ctx.fillStyle = "#402038";
        ctx.beginPath();
        ctx.arc(handX, handY, 6, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = "#d6a273";
        ctx.beginPath();
        ctx.arc(handX + Math.cos(angle) * 3, handY + Math.sin(angle) * 3, 3.4, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = "#d6a273";
        ctx.beginPath();
        ctx.arc(stringX, stringY, 4, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();
    }

    function drawTarget(ctx, target) {
        const pulse = 1 + Math.sin((state.round ? state.round.elapsed : 0) * 3 + target.phase) * 0.04;
        const radius = target.radius * (state.reduceMotion ? 1 : pulse);
        ctx.save();
        ctx.translate(target.x, target.y);
        if (target.kind === "sun") {
            ctx.rotate((state.round ? state.round.elapsed : 0) * 0.5 + target.phase);
            ctx.strokeStyle = "rgba(255, 208, 120, 0.35)";
            ctx.lineWidth = 3;
            for (let index = 0; index < 10; index += 1) {
                ctx.rotate(Math.PI / 5);
                ctx.beginPath();
                ctx.moveTo(radius + 9, 0);
                ctx.lineTo(radius + 25, 0);
                ctx.stroke();
            }
            ctx.rotate(-((state.round ? state.round.elapsed : 0) * 0.5 + target.phase));
            const sun = ctx.createRadialGradient(0, 0, 2, 0, 0, radius);
            sun.addColorStop(0, "#fff7d6");
            sun.addColorStop(0.48, "#ffc46a");
            sun.addColorStop(1, "rgba(255, 140, 60, 0.28)");
            ctx.fillStyle = sun;
            ctx.beginPath();
            ctx.arc(0, 0, radius, 0, Math.PI * 2);
            ctx.fill();
            ctx.strokeStyle = "rgba(255, 240, 190, 0.7)";
            ctx.lineWidth = 2;
            ctx.stroke();
        } else if (target.kind === "wisp") {
            ctx.fillStyle = "rgba(96, 231, 255, 0.15)";
            ctx.beginPath();
            ctx.arc(0, 0, radius * 1.9, 0, Math.PI * 2);
            ctx.fill();
            const flame = ctx.createLinearGradient(0, -radius, 0, radius);
            flame.addColorStop(0, "#e8fdff");
            flame.addColorStop(0.45, "#75e9ff");
            flame.addColorStop(1, "#4a72c8");
            ctx.fillStyle = flame;
            ctx.beginPath();
            ctx.moveTo(0, -radius * 1.35);
            ctx.quadraticCurveTo(radius * 0.95, -radius * 0.2, 0, radius);
            ctx.quadraticCurveTo(-radius * 0.95, -radius * 0.2, 0, -radius * 1.35);
            ctx.fill();
            ctx.fillStyle = "#ffffff";
            ctx.beginPath();
            ctx.arc(3, -2, radius * 0.25, 0, Math.PI * 2);
            ctx.fill();
        } else if (target.kind === "guardian") {
            ctx.fillStyle = "rgba(203, 180, 160, 0.12)";
            ctx.beginPath();
            ctx.arc(0, 0, radius * 1.2, 0, Math.PI * 2);
            ctx.fill();
            ctx.rotate(Math.PI / 8);
            const stone = ctx.createLinearGradient(-radius, -radius, radius, radius);
            stone.addColorStop(0, "#a69183");
            stone.addColorStop(0.45, "#665365");
            stone.addColorStop(1, "#30243b");
            ctx.fillStyle = stone;
            ctx.beginPath();
            for (let index = 0; index < 8; index += 1) {
                const angle = (index / 8) * Math.PI * 2;
                const x = Math.cos(angle) * radius;
                const y = Math.sin(angle) * radius;
                if (index === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
            }
            ctx.closePath();
            ctx.fill();
            ctx.strokeStyle = "#d8b68e";
            ctx.lineWidth = 2;
            ctx.stroke();
            ctx.fillStyle = "rgba(255, 178, 94, 0.6)";
            ctx.beginPath();
            ctx.arc(0, 0, radius * 0.22, 0, Math.PI * 2);
            ctx.fill();
        } else {
            const remaining = target.life ? Math.max(0, 1 - target.age / (target.life / 1000)) : 1;
            ctx.fillStyle = "rgba(255, 91, 127, 0.16)";
            ctx.beginPath();
            ctx.arc(0, 0, radius * 1.8, 0, Math.PI * 2);
            ctx.fill();
            const phoenix = ctx.createLinearGradient(0, -radius, 0, radius);
            phoenix.addColorStop(0, "#fff0bd");
            phoenix.addColorStop(0.4, "#ff8a5c");
            phoenix.addColorStop(1, "#c62d69");
            ctx.fillStyle = phoenix;
            ctx.beginPath();
            ctx.moveTo(0, -radius);
            ctx.quadraticCurveTo(radius * 1.25, -radius * 0.2, 0, radius);
            ctx.quadraticCurveTo(-radius * 1.25, -radius * 0.2, 0, -radius);
            ctx.fill();
            ctx.strokeStyle = "#ffe1a0";
            ctx.lineWidth = 2;
            ctx.beginPath();
            ctx.arc(0, 0, radius + 8, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * remaining);
            ctx.stroke();
        }
        ctx.restore();
    }

    function drawArrow(ctx, arrow) {
        ctx.save();
        ctx.translate(arrow.x, arrow.y);
        ctx.rotate(arrow.angle);
        ctx.strokeStyle = "rgba(255, 229, 183, 0.9)";
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(-15, 0);
        ctx.lineTo(12, 0);
        ctx.stroke();
        ctx.fillStyle = "#ffe1a0";
        ctx.beginPath();
        ctx.moveTo(17, 0);
        ctx.lineTo(8, -4);
        ctx.lineTo(8, 4);
        ctx.closePath();
        ctx.fill();
        ctx.fillStyle = "rgba(255, 124, 111, 0.8)";
        ctx.beginPath();
        ctx.moveTo(-15, 0);
        ctx.lineTo(-21, -4);
        ctx.lineTo(-21, 4);
        ctx.closePath();
        ctx.fill();
        ctx.restore();
    }

    function drawPreview(ctx) {
        const power = CORE.powerFromHold(state.aim.holdMs);
        const path = CORE.previewPath(
            { x: ARCHER.x, y: ARCHER.bowY }, state.aim.angle, power,
            { width: LOGICAL_WIDTH, height: LOGICAL_HEIGHT }, 32,
        );
        ctx.save();
        for (let index = 0; index < path.length; index += 1) {
            const point = path[index];
            const alpha = 0.4 * (1 - index / Math.max(1, path.length));
            ctx.fillStyle = "rgba(255, 224, 164, " + alpha.toFixed(3) + ")";
            ctx.beginPath();
            ctx.arc(point.x, point.y, index % 3 === 0 ? 2.4 : 1.4, 0, Math.PI * 2);
            ctx.fill();
        }
        ctx.restore();
    }

    function drawPower(ctx) {
        const ratio = state.aim.holdMs / CORE.MAX_HOLD_MS;
        dom["power-fill"].style.width = (Math.round(ratio * 100)) + "%";
        setHidden(dom["power-fill"], false);
    }

    function drawParticle(ctx, particle) {
        ctx.save();
        ctx.globalAlpha = Math.max(0, particle.life);
        ctx.fillStyle = particle.color;
        ctx.beginPath();
        ctx.arc(particle.x, particle.y, particle.size * Math.max(0.2, particle.life), 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();
    }

    function drawPopup(ctx, popup) {
        ctx.save();
        ctx.globalAlpha = Math.max(0, Math.min(1, popup.life));
        ctx.fillStyle = popup.color;
        ctx.font = "700 22px 'Trebuchet MS', sans-serif";
        ctx.textAlign = "center";
        ctx.fillText(popup.text, popup.x, popup.y);
        ctx.restore();
    }

    function drawIdleHint(ctx) {
        if (state.round && state.round.finished) {
            return;
        }
        ctx.save();
        ctx.globalAlpha = 0.75;
        ctx.fillStyle = "#ffe1a0";
        ctx.font = "600 17px 'Trebuchet MS', sans-serif";
        ctx.textAlign = "center";
        ctx.fillText(t("tap_to_aim"), LOGICAL_WIDTH / 2, 612);
        ctx.restore();
    }

    function renderHud(force) {
        const round = state.round;
        if (!round) {
            return;
        }
        const remaining = Math.max(0, Math.ceil(CORE.ROUND_SECONDS - round.elapsed));
        const values = [
            String(round.score.score), "×" + String(round.score.multiplier), String(remaining),
        ].join("|");
        if (!force && values === state.lastHud) {
            return;
        }
        state.lastHud = values;
        dom["hud-score"].textContent = values.split("|")[0];
        dom["hud-combo"].textContent = values.split("|")[1];
        dom["hud-time"].textContent = values.split("|")[2];
        dom["hud-streak"].textContent = round.score.streak > 0
            ? String(round.score.streak) : "";
        dom["hud-time"].classList.toggle("is-low", remaining <= 10);
    }

    function updateHud() {
        renderHud(true);
    }

    // ---------------------------------------------------------------- platform
    function bindEvents() {
        dom["start-button"].addEventListener("click", function () {
            ensureAudio();
            startRound();
        });
        dom["pause-button"].addEventListener("click", function () {
            if (state.round && state.round.running) {
                if (state.round.paused) resumeRound(); else pauseRound("manual", true);
            }
        });
        dom["resume-button"].addEventListener("click", resumeRound);
        dom["restart-button"].addEventListener("click", restartRound);
        dom["pause-exit-button"].addEventListener("click", exitGame);
        dom["play-again-button"].addEventListener("click", restartRound);
        dom["result-exit-button"].addEventListener("click", exitGame);
        dom["retry-submit-button"].addEventListener("click", function () {
            if (!state.submit.submitted && !state.submit.submitting) {
                state.submit.retryable = false;
                sendResult(state.round.id, 1);
            }
        });
        dom["sound-toggle"].addEventListener("click", function () {
            setSoundEnabled(!state.soundEnabled, true);
            if (state.soundEnabled) {
                ensureAudio();
                tone(660, 0, 0.08, "triangle", 0.02);
            }
        });
        dom["boot-retry"].addEventListener("click", function () {
            globalThis.location.reload();
        });
        state.canvas.addEventListener("pointerdown", onPointerDown);
        state.canvas.addEventListener("pointermove", onPointerMove);
        state.canvas.addEventListener("pointerup", onPointerUp);
        state.canvas.addEventListener("pointercancel", onPointerCancel);
        state.canvas.addEventListener("lostpointercapture", onPointerCancel);
        state.canvas.addEventListener("contextmenu", function (event) { event.preventDefault(); });
        document.addEventListener("keydown", onKeyDown);
        document.addEventListener("keyup", onKeyUp);
        document.addEventListener("visibilitychange", onVisibilityChange);
        globalThis.addEventListener("blur", onWindowBlur);
        globalThis.addEventListener("focus", onWindowFocus);
        globalThis.addEventListener("resize", resizeCanvas);
        globalThis.addEventListener("orientationchange", resizeCanvas);
        if (globalThis.ResizeObserver) {
            new ResizeObserver(resizeCanvas).observe(state.stage);
        }
        if (globalThis.matchMedia) {
            const query = globalThis.matchMedia("(prefers-reduced-motion: reduce)");
            state.reduceMotion = query.matches;
            if (typeof query.addEventListener === "function") {
                query.addEventListener("change", function (event) { state.reduceMotion = event.matches; });
            }
        }
    }

    function bindSdkEvents() {
        state.ba.on("pause", function () {
            if (state.round && state.round.running && !state.round.paused) pauseRound("host", true);
        });
        state.ba.on("resume", function () {
            if (state.round && state.round.paused && state.round.pauseReason === "host") resumeRound();
        });
        state.ba.on("autotest:finish", function () {
            if (state.mode === "autotest" && state.round && state.round.running && !state.autotestDone) {
                state.autotestDone = true;
                finishRound("autotest_finish");
            }
        });
        state.ba.on("visibility", function (payload) {
            const visible = !payload || payload.visible !== false;
            if (!visible && state.round && state.round.running && !state.round.paused) {
                pauseRound("visibility", true);
            } else if (visible && state.round && state.round.paused
                && state.round.pauseReason === "visibility") {
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

    async function restartRound() {
        if (state.transitioning || !state.ba) {
            return;
        }
        state.transitioning = true;
        try {
            const context = await state.ba.newSession();
            state.context = context && typeof context === "object" ? context : state.context;
            state.mode = state.context && typeof state.context.mode === "string"
                ? state.context.mode : state.mode;
            state.seed = state.context && typeof state.context.seed === "string"
                ? state.context.seed : state.seed;
            state.rng = globalThis.NeonRng.create(state.seed);
            state.strings = await loadStrings(state.context);
            if (state.ba.context) state.ba.context.strings = state.strings;
            applyLocaleMetadata();
            applyStaticLabels();
            resetRound();
            startRound();
        } catch (error) {
            state.sessionExpired = true;
            setNode(dom["result-status"], "session_expired");
            dom["result-status"].classList.add("is-error");
        } finally {
            state.transitioning = false;
        }
    }

    function exitGame() {
        if (state.ba && typeof state.ba.exit === "function") {
            state.ba.exit();
        }
        showOnly("result-screen");
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
            return;
        }
        state.ba = sdk;
        state.context = sdk.context || {};
        state.mode = typeof state.context.mode === "string" ? state.context.mode : "guest";
        state.seed = typeof state.context.seed === "string" ? state.context.seed : "";
        state.rng = globalThis.NeonRng.create(state.seed);
        sdk.ready();
        try {
            state.strings = await loadStrings(state.context);
        } catch (error) {
            showBootMessage("error_network", true);
            return;
        }
        if (sdk.context) sdk.context.strings = state.strings;
        applyLocaleMetadata();
        applyStaticLabels();
        await loadSettings();
        applyStaticLabels();
        bindSdkEvents();
        resetRound();
        setHidden(dom["boot-screen"], true);
        resizeCanvas();
        draw();
        if (state.mode === "autotest") {
            showOnly(null);
            setHidden(dom.hud, false);
            startRound();
        } else {
            showOnly("start-screen");
            setAppState("start");
        }
        announce("game_title");
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", function () { void boot(); }, { once: true });
    } else {
        void boot();
    }
})();

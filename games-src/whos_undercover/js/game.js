/* Who's Undercover? — Pass & Play UI, SDK integration and sound. */
(function () {
    "use strict";

    const C = globalThis.WhosUndercoverCore;
    const SDK = globalThis.BreaktimeArcade;
    const STORAGE_KEY = "whos_undercover.settings.v1";
    const SUPPORTED_LANGUAGES = ["en", "ru"];
    const TIMER_OPTIONS = [0, 30, 60, 90, 120];
    const MAX_PLAYERS = C ? C.MAX_PLAYERS : 12;

    const $ = (id) => document.getElementById(id);
    const app = $("app");

    let locale = null;
    let language = "en";
    let ba = null;
    let context = null;
    let settings = null;
    let game = null;
    let gameNumber = 0;
    let voteQueue = [];
    let voteIndex = 0;
    let voteChoice = null;
    let timerId = null;
    let timerRemaining = 0;
    let timerPaused = false;
    let sound = true;
    let projector = false;
    let toastTimer = null;
    let audioContext = null;

    function t(key, params) {
        const values = params || {};
        const raw = locale && typeof locale[key] === "string" ? locale[key] : key;
        return raw.replace(/\{(\w+)\}/g, (_, name) =>
            Object.prototype.hasOwnProperty.call(values, name) ? String(values[name]) : `{${name}}`,
        );
    }

    function setText(id, value) {
        const node = $(id);
        if (node) {
            node.textContent = value;
        }
    }

    function roleLabel(role) {
        if (role === C.ROLE_UNDERCOVER) {
            return t("role_undercover");
        }
        if (role === C.ROLE_MR_WHITE) {
            return t("role_mrwhite");
        }
        return t("role_civilian");
    }

    function roleClass(role) {
        return role === C.ROLE_UNDERCOVER
            ? "role-undercover"
            : role === C.ROLE_MR_WHITE
              ? "role-mrwhite"
              : "role-civilian";
    }

    function showScreen(name) {
        document.querySelectorAll(".screen").forEach((screen) => {
            screen.hidden = screen.id !== `${name}-screen`;
        });
        app.dataset.phase = name;
        const active = $(`${name}-screen`);
        if (active) {
            const focusTarget = active.querySelector("[data-autofocus], .btn-primary, input, select");
            if (focusTarget) {
                requestAnimationFrame(() => focusTarget.focus());
            }
        }
    }

    function toast(message) {
        const node = $("toast");
        if (!node) {
            return;
        }
        node.textContent = message;
        node.hidden = false;
        globalThis.clearTimeout(toastTimer);
        toastTimer = globalThis.setTimeout(() => {
            node.hidden = true;
        }, 3200);
    }

    function applyStaticI18n() {
        document.querySelectorAll("[data-i18n]").forEach((node) => {
            node.textContent = t(node.dataset.i18n);
        });
        document.querySelectorAll("[data-i18n-placeholder]").forEach((node) => {
            node.setAttribute("placeholder", t(node.dataset.i18nPlaceholder));
        });
        const brand = document.querySelector(".brand");
        if (brand) {
            brand.textContent = t("game_title");
        }
        document.documentElement.lang = language;
        document.title = t("page_title");
    }

    function fetchLocale(code) {
        return fetch(`locales/${code}.json`, { cache: "no-cache" }).then((response) => {
            if (!response.ok) {
                throw new Error(`locale ${code}: ${response.status}`);
            }
            return response.json();
        });
    }

    function defaultSettings() {
        const names = [];
        for (let index = 0; index < 4; index += 1) {
            names.push(t("player_default", { n: index + 1 }));
        }
        return {
            names,
            undercoverCount: 1,
            mrWhite: false,
            categoryId: "",
            timer: 60,
            sound: true,
        };
    }

    function sanitizeStoredSettings(value) {
        if (!value || typeof value !== "object") {
            return defaultSettings();
        }
        const names = Array.isArray(value.names)
            ? value.names
                  .slice(0, MAX_PLAYERS)
                  .map(
                      (name, index) =>
                          C.normalizeName(name).slice(0, C.MAX_NAME_LENGTH) ||
                          t("player_default", { n: index + 1 }),
                  )
            : [];
        if (names.length < 4) {
            return defaultSettings();
        }
        const undercoverCount = Number(value.undercoverCount);
        return {
            names,
            undercoverCount:
                Number.isInteger(undercoverCount) && undercoverCount >= 1 && undercoverCount <= 3
                    ? undercoverCount
                    : 1,
            mrWhite: Boolean(value.mrWhite),
            categoryId: typeof value.categoryId === "string" ? value.categoryId : "",
            timer: TIMER_OPTIONS.includes(Number(value.timer)) ? Number(value.timer) : 60,
            sound: value.sound !== false,
        };
    }

    async function hydrateSettings() {
        settings = defaultSettings();
        if (!ba || !ba.storage) {
            return;
        }
        try {
            const stored = await ba.storage.get(STORAGE_KEY);
            if (stored) {
                settings = sanitizeStoredSettings(stored);
                sound = settings.sound;
            }
        } catch (error) {
            /* storage is an enhancement; the game works without it */
        }
    }

    function saveSettings() {
        if (!ba || !ba.storage || !settings) {
            return;
        }
        ba.storage
            .set(STORAGE_KEY, {
                names: settings.names,
                undercoverCount: settings.undercoverCount,
                mrWhite: settings.mrWhite,
                categoryId: settings.categoryId,
                timer: settings.timer,
                sound,
            })
            .catch(() => undefined);
    }

    function renderPlayerList() {
        const list = $("player-list");
        if (!list) {
            return;
        }
        list.textContent = "";
        settings.names.forEach((name, index) => {
            const row = document.createElement("li");
            row.className = "player-row";
            const number = document.createElement("span");
            number.className = "player-number";
            number.textContent = String(index + 1);
            const input = document.createElement("input");
            input.type = "text";
            input.value = name;
            input.maxLength = C.MAX_NAME_LENGTH;
            input.autocomplete = "off";
            input.dataset.index = String(index);
            input.setAttribute("aria-label", `${t("players_label")} ${index + 1}`);
            input.placeholder = t("player_placeholder");
            const remove = document.createElement("button");
            remove.type = "button";
            remove.className = "player-remove";
            remove.dataset.index = String(index);
            remove.setAttribute("aria-label", `${t("remove_player")} ${index + 1}`);
            remove.textContent = "×";
            remove.disabled = settings.names.length <= 4;
            row.append(number, input, remove);
            list.append(row);
        });
        setText("player-count", t("players_count", { count: settings.names.length }));
        $("add-player").disabled = settings.names.length >= MAX_PLAYERS;
    }

    function populateSetupOptions() {
        const undercover = $("undercover-count");
        undercover.textContent = "";
        for (let count = 1; count <= 3; count += 1) {
            const option = document.createElement("option");
            option.value = String(count);
            option.textContent = `${count}`;
            undercover.append(option);
        }
        undercover.value = String(settings.undercoverCount);

        const category = $("category");
        category.textContent = "";
        const random = document.createElement("option");
        random.value = "";
        random.textContent = t("category_random");
        category.append(random);
        for (const deck of locale.words || []) {
            const option = document.createElement("option");
            option.value = deck.id;
            option.textContent = deck.name;
            category.append(option);
        }
        category.value = settings.categoryId || "";

        const timer = $("timer");
        timer.textContent = "";
        for (const seconds of TIMER_OPTIONS) {
            const option = document.createElement("option");
            option.value = String(seconds);
            option.textContent = seconds === 0 ? t("timer_none") : t(`timer_${seconds}`);
            timer.append(option);
        }
        timer.value = String(settings.timer);

        $("mr-white").checked = settings.mrWhite;
    }

    function renderSetup() {
        renderPlayerList();
        populateSetupOptions();
        setText("setup-error", "");
        $("setup-error").hidden = true;
        showScreen("setup");
    }

    function setupError(messageKey) {
        const node = $("setup-error");
        node.textContent = t(messageKey);
        node.hidden = false;
        node.focus();
    }

    function startGame() {
        const result = C.createGame({
            names: settings.names,
            undercoverCount: settings.undercoverCount,
            mrWhite: settings.mrWhite,
            pack: locale.words,
            categoryId: settings.categoryId,
            seed: `${context && context.seed ? context.seed : "local"}:${gameNumber + 1}`,
        });
        if (!result.ok) {
            if (result.code === "E_PACK" && settings.categoryId) {
                settings.categoryId = "";
                startGame();
                return;
            }
            if (result.code === "E_BALANCE") {
                setupError("error_setup_balance");
            } else if (result.code === "E_PACK" || result.code === "E_RNG") {
                setupError("error_generic");
            } else {
                setupError("error_setup_players");
            }
            return;
        }
        gameNumber += 1;
        game = result.state;
        saveSettings();
        enterReveal();
    }

    function enterReveal() {
        stopTimer();
        showScreen("reveal");
        renderRevealHandoff();
    }

    function renderRevealHandoff() {
        const player = C.currentRevealPlayer(game);
        if (!player) {
            enterBoard();
            return;
        }
        $("reveal-card").hidden = true;
        $("reveal-handoff").hidden = false;
        setText("reveal-handoff-title", t("reveal_handoff_title", { name: player.name }));
        setText("reveal-handoff-text", t("reveal_handoff_text", { name: player.name }));
        setText("reveal-open", t("reveal_button", { name: player.name }));
        $("reveal-open").dataset.autofocus = "true";
        $("reveal-open").focus();
        chime("handoff");
    }

    function openReveal() {
        const player = C.currentRevealPlayer(game);
        const secret = player ? C.secretFor(game, player.id) : null;
        if (!player || !secret) {
            return;
        }
        $("reveal-handoff").hidden = true;
        $("reveal-card").hidden = false;
        setText("reveal-player-label", player.name);
        const roleNode = $("reveal-role");
        roleNode.textContent = roleLabel(secret.role);
        roleNode.className = `role-name ${roleClass(secret.role)}`;
        const wordNode = $("reveal-word");
        wordNode.textContent = secret.word || t("mrwhite_no_word");
        wordNode.classList.toggle("is-empty", !secret.word);
        setText(
            "reveal-hint",
            secret.role === C.ROLE_MR_WHITE
                ? t("mrwhite_hint")
                : secret.role === C.ROLE_UNDERCOVER
                  ? t("role_hint_undercover")
                  : t("role_hint_civilian"),
        );
        $("reveal-last").hidden = game.revealIndex < game.players.length - 1;
        $("reveal-hide").focus();
        chime(secret.role === C.ROLE_CIVILIAN ? "reveal" : "warn");
    }

    function hideReveal() {
        const card = $("reveal-card");
        card.hidden = true;
        setText("reveal-word", "");
        setText("reveal-role", "");
        C.advanceReveal(game);
        if (game.phase === C.PHASE_CLUES) {
            enterBoard();
        } else {
            renderRevealHandoff();
        }
    }

    function enterBoard() {
        showScreen("board");
        renderBoard();
        startTimer();
        chime("board");
    }

    function renderBoard() {
        const snapshot = C.publicSnapshot(game);
        setText("board-round", t("board_round", { round: snapshot.round }));
        setText(
            "board-alive",
            t("board_alive", { alive: snapshot.aliveCount, total: snapshot.players.length }),
        );
        const speaker = snapshot.speakerId ? C.findPlayer(game, snapshot.speakerId) : null;
        setText("speaker-name", speaker ? speaker.name : "");
        setText("board-speaker-label", t("board_speaker", { name: speaker ? speaker.name : "" }));
        setText("roster-count", t("players_count", { count: snapshot.aliveCount }));
        const roster = $("roster");
        roster.textContent = "";
        for (const player of snapshot.players) {
            const item = document.createElement("li");
            if (!player.alive) {
                item.classList.add("is-out");
            }
            if (speaker && speaker.id === player.id) {
                item.classList.add("is-speaking");
            }
            const name = document.createElement("span");
            name.textContent = player.name;
            item.append(name);
            if (speaker && speaker.id === player.id) {
                const tag = document.createElement("span");
                tag.className = "speaker-tag";
                tag.textContent = "●";
                item.append(tag);
            }
            roster.append(item);
        }
        const voting = snapshot.phase === C.PHASE_VOTE;
        $("next-clue").hidden = voting;
        $("start-vote").hidden = !voting;
        $("clue-timer").hidden = !settings.timer || !voting;
        if (voting) {
            setTimerDisplay(0);
        }
    }

    function nextClue() {
        C.advanceSpeaker(game);
        renderBoard();
        if (game.phase === C.PHASE_VOTE) {
            stopTimer();
            chime("vote");
            $("start-vote").focus();
        } else {
            chime("clue");
        }
    }

    function startTimer() {
        stopTimer();
        if (!settings.timer || !game || game.phase !== C.PHASE_CLUES) {
            $("clue-timer").hidden = true;
            return;
        }
        timerRemaining = settings.timer;
        timerPaused = false;
        $("clue-timer").hidden = false;
        setTimerDisplay(timerRemaining);
        timerId = globalThis.setInterval(() => {
            if (timerPaused) {
                return;
            }
            timerRemaining = Math.max(0, timerRemaining - 1);
            setTimerDisplay(timerRemaining);
            if (timerRemaining === 0) {
                stopTimer();
                chime("warn");
            }
        }, 1000);
    }

    function stopTimer() {
        if (timerId) {
            globalThis.clearInterval(timerId);
            timerId = null;
        }
    }

    function setTimerDisplay(seconds) {
        setText("clue-timer-value", String(seconds));
        $("clue-timer").classList.toggle("urgent", seconds > 0 && seconds <= 10);
    }

    function beginVoteFlow() {
        stopTimer();
        voteQueue = C.alivePlayers(game).map((player) => player.id);
        voteIndex = 0;
        voteChoice = null;
        showScreen("vote");
        renderVoteHandoff();
    }

    function renderVoteHandoff() {
        const voter = voteIndex < voteQueue.length ? C.findPlayer(game, voteQueue[voteIndex]) : null;
        if (!voter) {
            afterVote();
            return;
        }
        $("vote-ballot").hidden = true;
        $("vote-handoff").hidden = false;
        setText("vote-handoff-title", t("vote_handoff_title", { name: voter.name }));
        setText("vote-handoff-text", t("vote_handoff_text", { name: voter.name }));
        setText("vote-open", t("reveal_button", { name: voter.name }));
        $("vote-open").focus();
        chime("handoff");
    }

    function openVote() {
        const voter = voteQueue[voteIndex] ? C.findPlayer(game, voteQueue[voteIndex]) : null;
        if (!voter) {
            return;
        }
        voteChoice = null;
        $("vote-handoff").hidden = true;
        $("vote-ballot").hidden = false;
        setText(
            "vote-progress",
            t("vote_progress", { cast: voteIndex, total: voteQueue.length }),
        );
        const targets = $("vote-targets");
        targets.textContent = "";
        for (const player of C.alivePlayers(game)) {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "vote-target";
            button.dataset.playerId = player.id;
            button.textContent = player.name;
            if (player.id === voter.id) {
                button.classList.add("is-self");
                button.disabled = true;
            }
            button.addEventListener("click", () => {
                voteChoice = player.id;
                targets.querySelectorAll(".vote-target").forEach((node) => {
                    node.classList.toggle("is-selected", node.dataset.playerId === voteChoice);
                });
                $("vote-confirm").disabled = false;
            });
            targets.append(button);
        }
        $("vote-confirm").disabled = true;
        const first = targets.querySelector(".vote-target:not(.is-self)");
        if (first) {
            first.focus();
        }
    }

    function confirmVote() {
        const voterId = voteQueue[voteIndex];
        if (!voterId || !voteChoice) {
            return;
        }
        const result = C.castVote(game, voterId, voteChoice);
        if (!result.ok) {
            toast(t("error_generic"));
            return;
        }
        chime("vote");
        voteIndex += 1;
        voteChoice = null;
        if (game.phase === C.PHASE_VOTE) {
            renderVoteHandoff();
        } else {
            afterVote();
        }
    }

    function afterVote() {
        if (game.phase === C.PHASE_MR_WHITE) {
            enterMrWhite();
        } else if (game.phase === C.PHASE_GAME_OVER) {
            enterGameOver();
        } else {
            enterVoteResult();
        }
    }

    function enterVoteResult() {
        const vote = game.lastVote;
        showScreen("vote-result");
        if (!vote) {
            setText("vote-result-title", t("vote_result_title"));
            setText("vote-result-role", "");
            return;
        }
        if (vote.tie) {
            setText("vote-result-title", t("vote_tie"));
            setText("vote-result-role", "");
        } else {
            const eliminated = C.findPlayer(game, vote.eliminatedId);
            setText(
                "vote-result-title",
                t("vote_eliminated", { name: eliminated ? eliminated.name : "" }),
            );
            setText("vote-result-role", t("vote_role", { role: roleLabel(vote.eliminatedRole) }));
        }
        chime(vote.tie ? "clue" : "out");
    }

    function enterMrWhite() {
        showScreen("mrwhite");
        const vote = game.lastVote;
        const player = vote && vote.eliminatedId ? C.findPlayer(game, vote.eliminatedId) : null;
        setText("mrwhite-name", player ? player.name : "");
        setText(
            "mrwhite-hint",
            t("mrwhite_guess_hint", { name: player ? player.name : "" }),
        );
        $("mrwhite-guess").value = "";
        $("mrwhite-guess").focus();
    }

    function submitMrWhite(event) {
        event.preventDefault();
        const guess = $("mrwhite-guess").value;
        const result = C.guessMrWhite(game, guess);
        if (!result.ok) {
            toast(t("error_generic"));
            return;
        }
        if (result.correct) {
            toast(t("mrwhite_correct"));
            enterGameOver();
        } else {
            toast(t("mrwhite_wrong"));
            if (game.phase === C.PHASE_GAME_OVER) {
                enterGameOver();
            } else {
                enterVoteResult();
            }
        }
    }

    function enterGameOver() {
        stopTimer();
        const snapshot = C.publicSnapshot(game);
        showScreen("gameover");
        const winnerKey =
            snapshot.winner === C.WIN_CIVILIANS
                ? "game_over_civilians"
                : snapshot.winner === C.WIN_UNDERCOVER
                  ? "game_over_undercover"
                  : "game_over_mrwhite";
        setText("winner-title", t(winnerKey));
        setText("winner-reason", snapshot.reasonKey ? t(`reason_${snapshot.reasonKey}`) : "");
        setText("civilian-word", snapshot.civilianWord || "—");
        setText("undercover-word", snapshot.undercoverWord || "—");
        const roster = $("final-roster");
        roster.textContent = "";
        for (const player of snapshot.players) {
            const item = document.createElement("li");
            const name = document.createElement("span");
            name.textContent = player.name;
            const role = document.createElement("span");
            role.className = roleClass(player.role);
            role.textContent = `${roleLabel(player.role)}${player.word ? ` · ${player.word}` : ""}`;
            item.append(name, role);
            roster.append(item);
        }
        const history = $("history-list");
        history.textContent = "";
        for (const entry of snapshot.history) {
            const item = document.createElement("li");
            if (entry.type === "mr_white_guess") {
                item.textContent = t("history_mrwhite", { guess: game.mrWhiteGuess?.guess || "" });
            } else if (entry.tie) {
                item.textContent = `${t("history_round", { round: entry.round })}: ${t("history_tie")}`;
            } else {
                const player = C.findPlayer(game, entry.eliminatedId);
                item.textContent = `${t("history_round", { round: entry.round })}: ${t("history_eliminated", {
                    name: player ? player.name : "",
                    role: roleLabel(entry.eliminatedRole || ""),
                })}`;
            }
            history.append(item);
        }
        chime("win");
        $("play-again").focus();
    }

    function playAgain() {
        startGame();
    }

    function newGame() {
        stopTimer();
        game = null;
        renderSetup();
    }

    function toggleProjector() {
        projector = !projector;
        app.classList.toggle("is-projector", projector);
        $("projector-toggle").textContent = projector ? t("exit_projector") : t("projector");
        if (projector && document.documentElement.requestFullscreen) {
            document.documentElement.requestFullscreen().catch(() => undefined);
        } else if (!projector && document.fullscreenElement && document.exitFullscreen) {
            document.exitFullscreen().catch(() => undefined);
        }
    }

    function updateSoundButton() {
        const button = $("sound-toggle");
        button.textContent = sound ? "♪" : "×";
        button.setAttribute("aria-label", sound ? t("mute") : t("unmute"));
        button.setAttribute("aria-pressed", sound ? "true" : "false");
    }

    function toggleSound() {
        sound = !sound;
        settings.sound = sound;
        updateSoundButton();
        saveSettings();
        if (sound) {
            chime("clue");
        }
    }

    function chime(kind) {
        if (!sound) {
            return;
        }
        const Audio = globalThis.AudioContext || globalThis.webkitAudioContext;
        if (!Audio) {
            return;
        }
        try {
            audioContext = audioContext || new Audio();
            if (audioContext.state === "suspended") {
                audioContext.resume().catch(() => undefined);
            }
            const now = audioContext.currentTime;
            const patterns = {
                handoff: [[392, 0, 0.08], [523, 0.06, 0.1]],
                clue: [[523, 0, 0.08]],
                vote: [[440, 0, 0.06], [554, 0.05, 0.08]],
                reveal: [[659, 0, 0.1], [880, 0.08, 0.16]],
                warn: [[220, 0, 0.14], [185, 0.12, 0.2]],
                out: [[330, 0, 0.12], [220, 0.1, 0.22]],
                board: [[440, 0, 0.06], [660, 0.05, 0.08]],
                win: [[523, 0, 0.12], [659, 0.1, 0.14], [784, 0.22, 0.26]],
            };
            const notes = patterns[kind] || patterns.clue;
            for (const [freq, delay, duration] of notes) {
                const oscillator = audioContext.createOscillator();
                const gain = audioContext.createGain();
                oscillator.type = kind === "warn" || kind === "out" ? "triangle" : "sine";
                oscillator.frequency.value = freq;
                gain.gain.setValueAtTime(0.0001, now + delay);
                gain.gain.exponentialRampToValueAtTime(0.045, now + delay + 0.01);
                gain.gain.exponentialRampToValueAtTime(0.0001, now + delay + duration);
                oscillator.connect(gain).connect(audioContext.destination);
                oscillator.start(now + delay);
                oscillator.stop(now + delay + duration + 0.02);
            }
        } catch (error) {
            /* sound is optional */
        }
    }

    function bindEvents() {
        $("add-player").addEventListener("click", () => {
            if (settings.names.length >= MAX_PLAYERS) {
                return;
            }
            settings.names.push(t("player_default", { n: settings.names.length + 1 }));
            renderPlayerList();
            const inputs = $("player-list").querySelectorAll("input");
            if (inputs.length) {
                inputs[inputs.length - 1].focus();
            }
        });
        $("player-list").addEventListener("input", (event) => {
            const input = event.target.closest("input[data-index]");
            if (!input) {
                return;
            }
            settings.names[Number(input.dataset.index)] = input.value;
        });
        $("player-list").addEventListener("click", (event) => {
            const button = event.target.closest(".player-remove");
            if (!button || settings.names.length <= 4) {
                return;
            }
            settings.names.splice(Number(button.dataset.index), 1);
            renderPlayerList();
        });
        $("undercover-count").addEventListener("change", (event) => {
            settings.undercoverCount = Number(event.target.value);
        });
        $("category").addEventListener("change", (event) => {
            settings.categoryId = event.target.value;
        });
        $("timer").addEventListener("change", (event) => {
            settings.timer = Number(event.target.value);
        });
        $("mr-white").addEventListener("change", (event) => {
            settings.mrWhite = event.target.checked;
        });
        $("reset-settings").addEventListener("click", () => {
            settings = defaultSettings();
            renderSetup();
        });
        $("start-game").addEventListener("click", startGame);
        $("reveal-open").addEventListener("click", openReveal);
        $("reveal-hide").addEventListener("click", hideReveal);
        $("next-clue").addEventListener("click", nextClue);
        $("start-vote").addEventListener("click", beginVoteFlow);
        $("vote-open").addEventListener("click", openVote);
        $("vote-confirm").addEventListener("click", confirmVote);
        $("vote-continue").addEventListener("click", () => {
            C.continueAfterVote(game);
            enterBoard();
        });
        $("mrwhite-form").addEventListener("submit", submitMrWhite);
        $("play-again").addEventListener("click", playAgain);
        $("new-game").addEventListener("click", newGame);
        $("sound-toggle").addEventListener("click", toggleSound);
        $("projector-toggle").addEventListener("click", toggleProjector);
        document.addEventListener("fullscreenchange", () => {
            if (!document.fullscreenElement && projector) {
                projector = false;
                app.classList.remove("is-projector");
                $("projector-toggle").textContent = t("projector");
            }
        });
    }

    function bindSdkEvents() {
        if (!ba || typeof ba.on !== "function") {
            return;
        }
        ba.on("pause", () => {
            timerPaused = true;
        });
        ba.on("resume", () => {
            timerPaused = false;
        });
        ba.on("session", (nextContext) => {
            context = nextContext || context;
            if (settings && locale && game) {
                toast(t("session_expired"));
                startGame();
            }
        });
        ba.on("error", (error) => {
            toast(error && error.message ? error.message : t("error_generic"));
        });
    }

    function showBootError(messageKey) {
        showScreen("boot");
        setText("boot-message", t(messageKey || "error_sdk"));
        const loader = document.querySelector(".loader");
        if (loader) {
            loader.hidden = true;
        }
    }

    async function boot() {
        if (!C) {
            showBootError("error_sdk");
            return;
        }
        try {
            locale = await fetchLocale("en");
            language = "en";
            applyStaticI18n();
            if (!SDK) {
                throw new Error("SDK missing");
            }
            ba = await SDK.init({ timeoutMs: 5000 });
            context = ba.context;
            const preferred = context && context.language;
            if (preferred && preferred !== "en" && SUPPORTED_LANGUAGES.includes(preferred)) {
                try {
                    locale = await fetchLocale(preferred);
                    language = preferred;
                } catch (error) {
                    language = "en";
                }
            }
            applyStaticI18n();
            await hydrateSettings();
            sound = settings.sound;
            bindEvents();
            bindSdkEvents();
            updateSoundButton();
            renderSetup();
            ba.ready();
        } catch (error) {
            showBootError("error_sdk");
        }
    }

    void boot();
})();

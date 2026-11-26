/* Who's Undercover? Live — SDK 1.2 room client.
 *
 * The server owns the room and every game rule. This file only renders the
 * viewer-scoped snapshot and sends intents; it never trusts client state.
 */

const SDK = globalThis.BreaktimeArcade;
const STORAGE_KEY = "whos_undercover.live.room";
const ROOM_POLL_MS = 1200;

const STRINGS = {
    en: {
        connection_offline: "offline",
        connection_connecting: "connecting",
        connection_online: "live",
        entry_lede: "Play with friends on their own screens. Create a room or join with a code.",
        create_warning: "Choose more civilians or fewer infiltrators for this table size.",
        need_civilians: "Add more players: civilians must outnumber the infiltrators.",
        create_title: "Create a room",
        join_title: "Join a room",
        name: "Your name",
        players: "Players",
        undercover: "Undercover",
        mrwhite: "Mr. White",
        mrwhite_hint: "No word. One guess can steal the game.",
        create: "Create room",
        join: "Join room",
        code: "Room code",
        copy: "Copy",
        lobby_title: "The table is gathering",
        ready: "I'm ready",
        not_ready: "Not ready",
        start: "Start game",
        claim: "Claim host",
        waiting_host: "Waiting for the host to start.",
        waiting_table: "Waiting for the table.",
        your_role: "Your secret role",
        your_word: "Your word",
        reveal_hint_undercover: "Blend in. Your word is close, but not the same.",
        reveal_hint_mrwhite: "You have no word. Listen carefully and steal one.",
        reveal_hint_civilian: "Give a clue that only a civilian would understand.",
        seen: "I've seen my card",
        waiting_reveal: "Waiting for the other players to reveal.",
        clues_title: "Give a clue",
        speaker: "Speaking now",
        clue_prompt: "One short clue. Do not say your word.",
        next_clue: "Next speaker",
        alive_players: "Still in the game",
        vote_title: "Who is undercover?",
        vote_prompt: "Choose one player. Your vote is secret.",
        vote_cast: "Vote cast",
        vote_waiting: "Waiting for the other votes.",
        vote_result: "The table has voted",
        tie: "Tie — nobody leaves this round.",
        eliminated: "Eliminated",
        continue: "Continue",
        mrwhite_phase: "Mr. White was caught",
        mrwhite_title: "One guess",
        mrwhite_prompt: "Mr. White, name the civilian word to steal the game.",
        your_guess: "Your guess",
        guess: "Guess",
        waiting_mrwhite: "Waiting for Mr. White's guess.",
        game_over: "Game over",
        win_civilians: "Civilians win",
        win_undercover: "Undercover wins",
        win_mrwhite: "Mr. White wins",
        reason_all_infiltrators_out: "Every infiltrator is out.",
        reason_infiltrators_equal: "The infiltrators reached parity.",
        reason_mr_white_guessed: "Mr. White guessed the word.",
        word_civilian: "Civilian word",
        word_undercover: "Undercover word",
        final_roles: "Final roles",
        restart: "Play again",
        stale: "The table moved on. Refreshing the room.",
        closed: "This room is closed.",
        error: "The room request failed.",
        leave: "Leave room",
        host: "Host",
        ready_short: "ready",
        not_ready_short: "waiting",
        you: "you",
        role_civilian: "Civilian",
        role_undercover: "Undercover",
        role_mr_white: "Mr. White",
        fallback_language: "English fallback",
        players_count: "{count} players",
        copy_done: "Copied",
        copy_failed: "Copy failed",
    },
    ru: {
        connection_offline: "нет связи",
        connection_connecting: "подключение",
        connection_online: "в эфире",
        entry_lede: "Играйте с друзьями на их экранах. Создайте комнату или войдите по коду.",
        create_warning: "Выберите больше мирных или меньше нарушителей для этого размера стола.",
        need_civilians: "Нужно больше игроков: мирных должно быть больше, чем нарушителей.",
        create_title: "Создать комнату",
        join_title: "Войти в комнату",
        name: "Ваше имя",
        players: "Игроки",
        undercover: "Под прикрытием",
        mrwhite: "Мистер Белый",
        mrwhite_hint: "Без слова. Одна догадка может украсть игру.",
        create: "Создать комнату",
        join: "Войти",
        code: "Код комнаты",
        copy: "Копировать",
        lobby_title: "Стол собирается",
        ready: "Я готов",
        not_ready: "Не готов",
        start: "Начать игру",
        claim: "Забрать роль ведущего",
        waiting_host: "Ждём, когда ведущий начнёт.",
        waiting_table: "Ждём остальных.",
        your_role: "Ваша секретная роль",
        your_word: "Ваше слово",
        reveal_hint_undercover: "Не выделяйтесь. Ваше слово похоже, но не совпадает.",
        reveal_hint_mrwhite: "У вас нет слова. Слушайте внимательно и украдите его.",
        reveal_hint_civilian: "Дайте подсказку, которую поймёт только мирный.",
        seen: "Я увидел карту",
        waiting_reveal: "Ждём, пока остальные откроют карты.",
        clues_title: "Дайте подсказку",
        speaker: "Сейчас говорит",
        clue_prompt: "Одна короткая подсказка. Не называйте своё слово.",
        next_clue: "Следующий игрок",
        alive_players: "Ещё в игре",
        vote_title: "Кто под прикрытием?",
        vote_prompt: "Выберите одного игрока. Голос тайный.",
        vote_cast: "Голос отдан",
        vote_waiting: "Ждём остальные голоса.",
        vote_result: "Стол проголосовал",
        tie: "Ничья — никто не выбывает.",
        eliminated: "Выбыл",
        continue: "Продолжить",
        mrwhite_phase: "Мистера Белого поймали",
        mrwhite_title: "Одна догадка",
        mrwhite_prompt: "Мистер Белый, назовите слово мирных, чтобы украсть игру.",
        your_guess: "Ваша догадка",
        guess: "Ответить",
        waiting_mrwhite: "Ждём догадку Мистера Белого.",
        game_over: "Игра окончена",
        win_civilians: "Победа мирных",
        win_undercover: "Победа под прикрытием",
        win_mrwhite: "Победа Мистера Белого",
        reason_all_infiltrators_out: "Все чужие выбыли.",
        reason_infiltrators_equal: "Чужие сравнялись с мирными.",
        reason_mr_white_guessed: "Мистер Белый угадал слово.",
        word_civilian: "Слово мирных",
        word_undercover: "Слово под прикрытием",
        final_roles: "Финальные роли",
        restart: "Играть снова",
        stale: "Стол изменился. Обновляем комнату.",
        closed: "Комната закрыта.",
        error: "Не удалось выполнить запрос комнаты.",
        leave: "Выйти",
        host: "Ведущий",
        ready_short: "готов",
        not_ready_short: "ждёт",
        you: "вы",
        role_civilian: "Мирный",
        role_undercover: "Под прикрытием",
        role_mr_white: "Мистер Белый",
        fallback_language: "Английский fallback",
        players_count: "{count} игроков",
        copy_done: "Скопировано",
        copy_failed: "Не удалось скопировать",
    },
};

const state = {
    sdk: null,
    snapshot: null,
    roomId: "",
    busy: false,
    polling: false,
    lang: "en",
    phase: "",
    createRequestId: "",
    errorTimer: 0,
};

const $ = (id) => document.getElementById(id);

function t(key, params = {}) {
    const table = STRINGS[state.lang] || STRINGS.en;
    let text = table[key] || STRINGS.en[key] || key;
    for (const [name, value] of Object.entries(params)) {
        text = text.split(`{${name}}`).join(String(value));
    }
    return text;
}

function fillPlayerOptions() {
    const select = $("create-max");
    const current = select.value || "8";
    select.textContent = "";
    for (let count = 4; count <= 12; count += 1) {
        const option = document.createElement("option");
        option.value = String(count);
        option.textContent = t("players_count", { count });
        select.append(option);
    }
    select.value = current;
}

function applyLanguage() {
    for (const node of document.querySelectorAll("[data-i18n]")) {
        node.textContent = t(node.dataset.i18n);
    }
    $("create-title").textContent = t("create_title");
    $("join-title").textContent = t("join_title");
    $("entry-lede").textContent = t("entry_lede");
    $("leave-room").textContent = t("leave");
    fillPlayerOptions();
    validateCreate();
    const connection = $("live-connection");
    connection.textContent = t(`connection_${connection.dataset.state}`);
    const badge = $("live-language");
    if (state.lang === "en") {
        badge.hidden = true;
    } else {
        badge.hidden = false;
        badge.textContent = state.lang === "ru" ? "RU" : t("fallback_language");
    }
    if (state.snapshot) {
        render();
    }
}

function showScreen(name) {
    for (const screen of document.querySelectorAll(".screen")) {
        screen.hidden = screen.id !== `${name}-screen`;
    }
}

function setConnection(value) {
    const node = $("live-connection");
    node.dataset.state = value;
    node.textContent = t(`connection_${value}`);
}

function showError(message) {
    const node = $("live-error");
    node.textContent = message;
    node.hidden = false;
    globalThis.clearTimeout(state.errorTimer);
    state.errorTimer = globalThis.setTimeout(() => {
        node.hidden = true;
    }, 6000);
}

function clearError() {
    $("live-error").hidden = true;
}

function roleLabel(role) {
    return role ? t(`role_${role}`) : "";
}

function playerById(id) {
    return (state.snapshot?.players || []).find((player) => player.id === id) || null;
}

function playerName(id) {
    return playerById(id)?.name || "—";
}

function appendPlayerRow(list, player, extra = "") {
    const item = document.createElement("li");
    if (player.id === state.snapshot?.you?.memberId) {
        item.classList.add("is-you");
    }
    const name = document.createElement("span");
    name.className = "player-name";
    name.textContent = player.name + (extra ? ` · ${extra}` : "");
    const meta = document.createElement("span");
    meta.className = "player-meta";
    meta.textContent = player.isHost ? t("host") : "";
    item.append(name, meta);
    list.append(item);
    return item;
}

function renderEntry() {
    showScreen("entry");
    $("leave-room").hidden = true;
    $("claim-host").hidden = true;
}

function renderLobby(snapshot) {
    showScreen("lobby");
    $("leave-room").hidden = false;
    const room = snapshot.room;
    const you = snapshot.you;
    $("lobby-code").textContent = room.code;
    $("lobby-count").textContent = t("players_count", { count: snapshot.players.length });
    const list = $("lobby-players");
    list.textContent = "";
    for (const player of snapshot.players) {
        appendPlayerRow(list, player, player.ready ? t("ready_short") : t("not_ready_short"));
    }
    $("lobby-ready").hidden = you.isHost;
    $("lobby-ready").textContent = you.ready ? t("not_ready") : t("ready");
    $("lobby-start").hidden = !you.isHost;
    const unready = snapshot.players.filter((player) => !player.isHost && !player.ready).length;
    const undercover = Number(snapshot.setup?.undercoverCount || 1);
    const infiltrators = undercover + (snapshot.setup?.mrWhite ? 1 : 0);
    const balanced = snapshot.players.length - infiltrators > infiltrators;
    $("lobby-start").disabled = snapshot.players.length < 4 || unready > 0 || !balanced;
    $("lobby-hint").textContent = !you.isHost
        ? t("waiting_host")
        : !balanced
          ? t("need_civilians")
          : unready
            ? t("waiting_table")
            : t("lobby_title");
}

function renderReveal(snapshot) {
    showScreen("reveal");
    $("leave-room").hidden = false;
    const you = snapshot.you;
    $("reveal-role").textContent = roleLabel(you.role);
    $("reveal-word").textContent = you.word || "—";
    $("reveal-hint").textContent =
        you.role === "undercover"
            ? t("reveal_hint_undercover")
            : you.role === "mr_white"
              ? t("reveal_hint_mrwhite")
              : t("reveal_hint_civilian");
    $("reveal-ack").disabled = Boolean(you.revealed);
    $("reveal-ack").textContent = you.revealed ? t("waiting_reveal") : t("seen");
}

function renderClues(snapshot) {
    showScreen("clues");
    $("leave-room").hidden = false;
    const game = snapshot.game;
    const you = snapshot.you;
    $("clues-round").textContent = `Round ${game.round}`;
    $("clues-alive").textContent = `${game.aliveCount} ${t("alive_players").toLowerCase()}`;
    $("clues-speaker").textContent = playerName(game.speakerId);
    $("clues-next").hidden = !you.isHost;
    const list = $("clues-players");
    list.textContent = "";
    for (const player of snapshot.players.filter((item) => item.alive)) {
        appendPlayerRow(list, player, player.id === you.memberId ? t("you") : "");
    }
}

function renderVote(snapshot) {
    showScreen("vote");
    $("leave-room").hidden = false;
    const game = snapshot.game;
    const you = snapshot.you;
    $("vote-round").textContent = `Round ${game.round}`;
    $("vote-progress").textContent = `${game.votesCast}/${game.aliveCount}`;
    const list = $("vote-targets");
    list.textContent = "";
    const votedFor = you.voteTargetId;
    const targets = snapshot.players.filter(
        (player) => player.alive && player.id !== you.memberId,
    );
    for (const player of targets) {
        const item = document.createElement("li");
        const button = document.createElement("button");
        button.type = "button";
        button.className = "btn btn-ghost";
        button.textContent = player.name;
        button.disabled = Boolean(votedFor);
        button.addEventListener("click", () => {
            void command("vote", { targetId: player.id });
        });
        item.append(button);
        list.append(item);
    }
    $("vote-self").hidden = !votedFor;
    if (votedFor) {
        $("vote-self").textContent = `${t("vote_cast")}: ${playerName(votedFor)}`;
    }
}

function renderResult(snapshot) {
    showScreen("result");
    $("leave-room").hidden = false;
    const vote = snapshot.game.lastVote;
    const you = snapshot.you;
    $("result-title").textContent = vote?.tie ? t("tie") : t("vote_result");
    const list = $("result-counts");
    list.textContent = "";
    if (vote) {
        for (const [targetId, count] of Object.entries(vote.counts)) {
            const player = playerById(targetId);
            const item = document.createElement("li");
            const name = document.createElement("span");
            name.textContent = player?.name || "—";
            const meta = document.createElement("span");
            meta.className = "player-meta";
            meta.textContent = String(count);
            item.append(name, meta);
            list.append(item);
        }
    }
    $("result-detail").textContent = vote?.eliminatedId
        ? `${t("eliminated")}: ${playerName(vote.eliminatedId)}`
        : t("tie");
    $("result-next").hidden = !you.isHost;
}

function renderMrWhite(snapshot, phaseChanged) {
    showScreen("mrwhite");
    $("leave-room").hidden = false;
    const you = snapshot.you;
    const isMrWhite = you.role === "mr_white";
    $("mrwhite-form").hidden = !isMrWhite;
    $("mrwhite-wait").hidden = isMrWhite;
    if (isMrWhite && phaseChanged) {
        $("mrwhite-guess").value = "";
    }
}

function renderOver(snapshot) {
    showScreen("over");
    $("leave-room").hidden = false;
    const game = snapshot.game;
    const you = snapshot.you;
    const title =
        game.winner === "civilians"
            ? t("win_civilians")
            : game.winner === "undercover"
              ? t("win_undercover")
              : game.winner === "mr_white"
                ? t("win_mrwhite")
                : t("closed");
    $("over-title").textContent = title;
    const reasonKey = `reason_${game.reason || "closed"}`;
    $("over-reason").textContent = STRINGS[state.lang]?.[reasonKey] ||
        STRINGS.en[reasonKey] ||
        "";
    $("over-civilian").textContent = game.civilianWord || "—";
    $("over-undercover").textContent = game.undercoverWord || "—";
    const list = $("over-players");
    list.textContent = "";
    for (const player of snapshot.players) {
        appendPlayerRow(
            list,
            player,
            [roleLabel(player.role), player.word || ""].filter(Boolean).join(" · "),
        );
    }
    $("over-restart").hidden = !(you.isHost && snapshot.room.status === "finished");
}

function render() {
    if (!state.snapshot) {
        renderEntry();
        return;
    }
    const snapshot = state.snapshot;
    const phaseChanged = state.phase !== snapshot.game.phase;
    state.phase = snapshot.game.phase;
    $("leave-room").hidden = snapshot.room.status === "finished";
    $("claim-host").hidden = !(
        !snapshot.you.isHost && ["lobby", "active"].includes(snapshot.room.status)
    );
    if (snapshot.room.status === "lobby") {
        renderLobby(snapshot);
        return;
    }
    if (snapshot.room.status === "finished" || snapshot.game.phase === "game_over") {
        renderOver(snapshot);
        return;
    }
    if (["abandoned", "expired"].includes(snapshot.room.status)) {
        state.snapshot = null;
        void state.sdk?.storage.remove(STORAGE_KEY);
        renderEntry();
        showError(t("closed"));
        return;
    }
    switch (snapshot.game.phase) {
        case "reveal":
            renderReveal(snapshot);
            break;
        case "clues":
            renderClues(snapshot);
            break;
        case "vote":
            renderVote(snapshot);
            break;
        case "vote_result":
            renderResult(snapshot);
            break;
        case "mr_white":
            renderMrWhite(snapshot, phaseChanged);
            break;
        default:
            renderOver(snapshot);
    }
}

function rememberRoom(snapshot) {
    state.roomId = snapshot.room.id;
    state.snapshot = snapshot;
    void state.sdk?.storage.set(STORAGE_KEY, state.roomId);
    setConnection("online");
    render();
}

function forgetRoom() {
    stopPolling();
    state.roomId = "";
    state.snapshot = null;
    state.phase = "";
    void state.sdk?.storage.remove(STORAGE_KEY);
    setConnection("offline");
    renderEntry();
}

function roomErrorCode(error) {
    return error?.code || "E_INTERNAL";
}

function handleRoomError(error) {
    const code = roomErrorCode(error);
    if (code === "E_ROOM_STALE" || code === "E_PHASE" || code === "E_ALREADY_VOTED") {
        showError(t("stale"));
        // The command's finally block clears state.busy after this handler;
        // defer the refresh so it is not dropped by the busy guard.
        globalThis.setTimeout(() => {
            void refresh();
        }, 0);
        return;
    }
    if (
        code === "E_NOT_MEMBER" ||
        code === "E_ROOM_NOT_FOUND" ||
        code === "E_ROOM_CLOSED"
    ) {
        forgetRoom();
        showError(t("closed"));
        return;
    }
    setConnection("offline");
    showError(error?.message || t("error"));
}

async function refresh() {
    if (!state.roomId || !state.sdk || state.busy || document.visibilityState === "hidden") {
        return;
    }
    if (state.polling) {
        return;
    }
    state.polling = true;
    const roomId = state.roomId;
    setConnection("connecting");
    try {
        const snapshot = await state.sdk.room.state(roomId);
        if (state.roomId !== roomId) {
            return;
        }
        state.snapshot = snapshot;
        setConnection("online");
        render();
    } catch (error) {
        if (state.roomId === roomId) {
            handleRoomError(error);
        }
    } finally {
        state.polling = false;
    }
}

async function command(name, payload = {}) {
    if (!state.roomId || !state.snapshot || state.busy) {
        return;
    }
    const roomId = state.roomId;
    const requestId = globalThis.crypto.randomUUID();
    let staleRetries = 0;
    state.busy = true;
    try {
        for (;;) {
            setConnection("connecting");
            try {
                const snapshot = await state.sdk.room.command(
                    roomId,
                    name,
                    payload,
                    state.snapshot.room.version,
                    requestId,
                );
                if (state.roomId !== roomId) {
                    return;
                }
                state.snapshot = snapshot;
                setConnection("online");
                render();
                return;
            } catch (error) {
                if (staleRetries < 3 && roomErrorCode(error) === "E_ROOM_STALE") {
                    staleRetries += 1;
                    try {
                        const refreshed = await state.sdk.room.state(roomId);
                        if (state.roomId !== roomId) {
                            return;
                        }
                        state.snapshot = refreshed;
                        setConnection("online");
                        render();
                        continue;
                    } catch (refreshError) {
                        if (state.roomId === roomId) {
                            handleRoomError(refreshError);
                        }
                        return;
                    }
                }
                if (state.roomId === roomId) {
                    handleRoomError(error);
                }
                return;
            }
        }
    } finally {
        state.busy = false;
    }
}

function resetCreateIntent() {
    state.createRequestId = "";
}

function validateCreate() {
    const max = Number($("create-max").value);
    const undercover = Number($("create-undercover").value);
    const mrWhite = $("create-mrwhite").checked;
    const infiltrators = undercover + (mrWhite ? 1 : 0);
    const valid = max >= 4 && max <= 12 && max - infiltrators > infiltrators;
    $("create-warning").hidden = valid;
    if (!valid) {
        $("create-warning").textContent = t("create_warning");
    }
    $("create-room").disabled = !valid;
    return { max, undercover, mrWhite, valid };
}

async function createRoom() {
    if (state.busy) {
        return;
    }
    const settings = validateCreate();
    if (!settings.valid) {
        return;
    }
    clearError();
    state.busy = true;
    $("create-room").disabled = true;
    if (!state.createRequestId) {
        state.createRequestId = globalThis.crypto.randomUUID();
    }
    try {
        const snapshot = await state.sdk.room.create({
            gameId: state.sdk.context.gameId,
            requestId: state.createRequestId,
            name: $("create-name").value.trim() || undefined,
            maxPlayers: settings.max,
            undercoverCount: settings.undercover,
            mrWhite: settings.mrWhite,
        });
        state.createRequestId = "";
        rememberRoom(snapshot);
        startPolling();
    } catch (error) {
        const code = roomErrorCode(error);
        if (
            code === "E_IDEMPOTENCY_CONFLICT" ||
            code === "E_IDEMPOTENCY_EXPIRED" ||
            code === "E_IDEMPOTENCY_GONE"
        ) {
            state.createRequestId = "";
        }
        handleRoomError(error);
    } finally {
        state.busy = false;
        validateCreate();
    }
}

async function joinRoom() {
    if (state.busy) {
        return;
    }
    const code = $("join-code").value.trim().toUpperCase();
    if (code.length < 4) {
        showError(t("code"));
        return;
    }
    clearError();
    state.busy = true;
    $("join-room").disabled = true;
    try {
        const snapshot = await state.sdk.room.join(
            code,
            $("join-name").value.trim() || undefined,
        );
        rememberRoom(snapshot);
        startPolling();
    } catch (error) {
        handleRoomError(error);
    } finally {
        state.busy = false;
        $("join-room").disabled = false;
    }
}

async function leaveRoom() {
    if (!state.roomId) {
        return;
    }
    const room = state.roomId;
    stopPolling();
    state.roomId = "";
    state.snapshot = null;
    state.phase = "";
    state.createRequestId = "";
    void state.sdk?.storage.remove(STORAGE_KEY);
    try {
        await state.sdk.room.leave(room);
    } catch {
        /* leaving is best-effort */
    }
    setConnection("offline");
    renderEntry();
}

function startPolling() {
    globalThis.clearInterval(startPolling.timer);
    startPolling.timer = globalThis.setInterval(() => {
        void refresh();
    }, ROOM_POLL_MS);
}

function stopPolling() {
    globalThis.clearInterval(startPolling.timer);
    startPolling.timer = undefined;
}

async function boot() {
    if (!SDK || typeof SDK.init !== "function") {
        showError("BA SDK is unavailable.");
        return;
    }
    try {
        state.sdk = await SDK.init({ timeoutMs: 5000 });
        const language = String(state.sdk.context?.language || "en").slice(0, 2).toLowerCase();
        state.lang = ["en", "ru"].includes(language) ? language : "en";
        applyLanguage();
        if (state.lang !== language) {
            $("live-language").hidden = false;
            $("live-language").textContent = t("fallback_language");
        }
        const stored = await state.sdk.storage.get(STORAGE_KEY);
        if (stored) {
            state.roomId = String(stored);
            setConnection("connecting");
            try {
                state.snapshot = await state.sdk.room.state(stored);
                setConnection("online");
                render();
                startPolling();
            } catch (error) {
                if (["E_NOT_MEMBER", "E_ROOM_NOT_FOUND", "E_ROOM_CLOSED"].includes(roomErrorCode(error))) {
                    forgetRoom();
                } else {
                    showError(error?.message || t("error"));
                    renderEntry();
                }
            }
        } else {
            renderEntry();
        }
    } catch (error) {
        showError(error?.message || "Could not start the game.");
    }
}

function wire() {
    $("create-warning").hidden = true;
    $("create-name").addEventListener("input", resetCreateIntent);
    $("create-max").addEventListener("change", () => {
        resetCreateIntent();
        validateCreate();
    });
    $("create-undercover").addEventListener("change", () => {
        resetCreateIntent();
        validateCreate();
    });
    $("create-mrwhite").addEventListener("change", () => {
        resetCreateIntent();
        validateCreate();
    });
    $("create-room").addEventListener("click", () => void createRoom());
    $("join-room").addEventListener("click", () => void joinRoom());
    $("lobby-ready").addEventListener("click", () => {
        void command("ready", { ready: !state.snapshot?.you?.ready });
    });
    $("lobby-start").addEventListener("click", () => void command("start"));
    $("claim-host").addEventListener("click", () => void command("claim_host"));
    $("reveal-ack").addEventListener("click", () => void command("reveal_ack"));
    $("clues-next").addEventListener("click", () => void command("advance_clue"));
    $("result-next").addEventListener("click", () => void command("advance"));
    $("mrwhite-submit").addEventListener("click", () => {
        const guess = $("mrwhite-guess").value.trim();
        if (guess) {
            void command("mrwhite_guess", { guess });
        }
    });
    $("over-restart").addEventListener("click", () => void command("restart"));
    $("leave-room").addEventListener("click", () => void leaveRoom());
    document.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "visible") {
            void refresh();
        }
    });
}

wire();
state.lang = "en";
applyLanguage();
void boot();

/* Who's Undercover? — pure, deterministic game rules.
 *
 * Exposed as WhosUndercoverCore in the browser and module.exports in Node.
 * No DOM, storage, timers or unseeded randomness lives here.
 */
(function (root, factory) {
    "use strict";
    const api = factory();
    if (typeof module === "object" && module.exports) {
        module.exports = api;
    }
    root.WhosUndercoverCore = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
    "use strict";

    const VERSION = "1.0.0";
    const MIN_PLAYERS = 4;
    const MAX_PLAYERS = 12;
    const MIN_UNDERCOVER = 1;
    const MAX_UNDERCOVER = 3;
    const MAX_NAME_LENGTH = 24;

    const ROLE_CIVILIAN = "civilian";
    const ROLE_UNDERCOVER = "undercover";
    const ROLE_MR_WHITE = "mr_white";

    const PHASE_REVEAL = "reveal";
    const PHASE_CLUES = "clues";
    const PHASE_VOTE = "vote";
    const PHASE_VOTE_RESULT = "vote_result";
    const PHASE_MR_WHITE = "mr_white";
    const PHASE_GAME_OVER = "game_over";

    const WIN_CIVILIANS = "civilians";
    const WIN_UNDERCOVER = "undercover";
    const WIN_MR_WHITE = "mr_white";

    function normalizeName(value) {
        return String(value === undefined || value === null ? "" : value)
            .trim()
            .replace(/\s+/g, " ");
    }

    function normalizeAnswer(value) {
        return normalizeName(value)
            .toLocaleLowerCase()
            .replace(/[.!?,;:]+$/g, "");
    }

    function recommendedUndercover(playerCount) {
        if (playerCount <= 5) {
            return 1;
        }
        if (playerCount <= 8) {
            return 2;
        }
        return 3;
    }

    function validateSetup(setup) {
        const source = setup && typeof setup === "object" ? setup : {};
        const rawNames = Array.isArray(source.names) ? source.names : [];
        const names = rawNames.map(normalizeName);
        if (names.length < MIN_PLAYERS || names.length > MAX_PLAYERS) {
            return { ok: false, code: "E_PLAYERS", field: "names" };
        }
        if (names.some((name) => !name || name.length > MAX_NAME_LENGTH)) {
            return { ok: false, code: "E_NAME", field: "names" };
        }
        const seen = new Set();
        for (const name of names) {
            const key = name.toLocaleLowerCase();
            if (seen.has(key)) {
                return { ok: false, code: "E_DUPLICATE_NAME", field: "names" };
            }
            seen.add(key);
        }
        const undercoverCount = Number(source.undercoverCount);
        if (
            !Number.isInteger(undercoverCount) ||
            undercoverCount < MIN_UNDERCOVER ||
            undercoverCount > MAX_UNDERCOVER
        ) {
            return { ok: false, code: "E_UNDERCOVER", field: "undercoverCount" };
        }
        const mrWhite = Boolean(source.mrWhite);
        const infiltrators = undercoverCount + (mrWhite ? 1 : 0);
        const civilians = names.length - infiltrators;
        if (civilians <= infiltrators) {
            return { ok: false, code: "E_BALANCE", field: "undercoverCount" };
        }
        return { ok: true, names, undercoverCount, mrWhite };
    }

    function normalizePack(pack, categoryId) {
        if (!Array.isArray(pack)) {
            return [];
        }
        const categories = pack
            .filter((category) => category && typeof category === "object")
            .map((category) => ({
                id: String(category.id || ""),
                name: category.name,
                pairs: Array.isArray(category.pairs)
                    ? category.pairs.filter(
                          (pair) =>
                              Array.isArray(pair) &&
                              pair.length >= 2 &&
                              typeof pair[0] === "string" &&
                              typeof pair[1] === "string" &&
                              pair[0] &&
                              pair[1],
                      )
                    : [],
            }))
            .filter((category) => category.id && category.pairs.length > 0);
        if (!categoryId) {
            return categories;
        }
        return categories.filter((category) => category.id === categoryId);
    }

    function createGame(options) {
        const source = options && typeof options === "object" ? options : {};
        const setup = validateSetup(source);
        if (!setup.ok) {
            return setup;
        }
        const Rng = source.rng || (typeof globalThis !== "undefined" ? globalThis.WhosUndercoverRng : null);
        if (!Rng || typeof Rng.create !== "function") {
            return { ok: false, code: "E_RNG", field: "seed" };
        }
        const categories = normalizePack(source.pack, source.categoryId);
        if (categories.length === 0) {
            return { ok: false, code: "E_PACK", field: "categoryId" };
        }
        const rng = Rng.create(source.seed === undefined ? "undercover" : source.seed);
        const category = rng.pick(categories);
        const pair = rng.pick(category.pairs);
        const civilianWord = pair[0];
        const undercoverWord = pair[1];
        const roles = [];
        for (let index = 0; index < setup.undercoverCount; index += 1) {
            roles.push(ROLE_UNDERCOVER);
        }
        if (setup.mrWhite) {
            roles.push(ROLE_MR_WHITE);
        }
        while (roles.length < setup.names.length) {
            roles.push(ROLE_CIVILIAN);
        }
        const shuffledRoles = rng.shuffled(roles);
        const players = setup.names.map((name, index) => {
            const role = shuffledRoles[index];
            return {
                id: `p${index + 1}`,
                name,
                role,
                word:
                    role === ROLE_CIVILIAN
                        ? civilianWord
                        : role === ROLE_UNDERCOVER
                          ? undercoverWord
                          : null,
                alive: true,
                eliminatedRound: null,
                revealedRole: null,
            };
        });
        return {
            ok: true,
            state: {
                version: VERSION,
                phase: PHASE_REVEAL,
                round: 1,
                players,
                aliveOrder: players.map((player) => player.id),
                categoryId: category.id,
                categoryName: category.name,
                civilianWord,
                undercoverWord,
                undercoverCount: setup.undercoverCount,
                mrWhite: setup.mrWhite,
                revealIndex: 0,
                speakerIndex: 0,
                spokenCount: 0,
                votes: {},
                lastVote: null,
                mrWhiteGuess: null,
                winner: null,
                reasonKey: null,
                history: [],
                seed: rng.seed,
            },
        };
    }

    function alivePlayers(state) {
        return state.players.filter((player) => player.alive);
    }

    function findPlayer(state, playerId) {
        return state.players.find((player) => player.id === playerId) || null;
    }

    function currentRevealPlayer(state) {
        if (state.phase !== PHASE_REVEAL) {
            return null;
        }
        return state.players[state.revealIndex] || null;
    }

    function secretFor(state, playerId) {
        const player = findPlayer(state, playerId);
        if (!player) {
            return null;
        }
        if (state.phase === PHASE_GAME_OVER) {
            return { role: player.role, word: player.word };
        }
        if (state.phase !== PHASE_REVEAL || currentRevealPlayer(state)?.id !== playerId) {
            return null;
        }
        return { role: player.role, word: player.word };
    }

    function advanceReveal(state) {
        if (state.phase !== PHASE_REVEAL) {
            return state;
        }
        if (state.revealIndex < state.players.length - 1) {
            state.revealIndex += 1;
        } else {
            state.phase = PHASE_CLUES;
            state.spokenCount = 0;
            state.speakerIndex = (state.round - 1) % Math.max(1, alivePlayers(state).length);
        }
        return state;
    }

    function currentSpeaker(state) {
        if (state.phase !== PHASE_CLUES) {
            return null;
        }
        const alive = alivePlayers(state);
        return alive[state.speakerIndex % alive.length] || null;
    }

    function advanceSpeaker(state) {
        if (state.phase !== PHASE_CLUES) {
            return state;
        }
        const alive = alivePlayers(state);
        state.spokenCount += 1;
        if (state.spokenCount >= alive.length) {
            state.phase = PHASE_VOTE;
            state.votes = {};
            state.spokenCount = 0;
        } else {
            state.speakerIndex = (state.speakerIndex + 1) % alive.length;
        }
        return state;
    }

    function castVote(state, voterId, targetId) {
        if (state.phase !== PHASE_VOTE) {
            return { ok: false, code: "E_PHASE" };
        }
        const voter = findPlayer(state, voterId);
        const target = findPlayer(state, targetId);
        if (!voter || !voter.alive || !target || !target.alive) {
            return { ok: false, code: "E_TARGET" };
        }
        if (voter.id === target.id) {
            return { ok: false, code: "E_SELF_VOTE" };
        }
        if (Object.prototype.hasOwnProperty.call(state.votes, voterId)) {
            return { ok: false, code: "E_ALREADY_VOTED" };
        }
        state.votes[voterId] = targetId;
        const alive = alivePlayers(state);
        if (Object.keys(state.votes).length >= alive.length) {
            resolveVote(state);
        }
        return { ok: true, state };
    }

    function resolveVote(state) {
        if (state.phase !== PHASE_VOTE) {
            return state;
        }
        const counts = {};
        for (const targetId of Object.values(state.votes)) {
            counts[targetId] = (counts[targetId] || 0) + 1;
        }
        let best = 0;
        let leaders = [];
        for (const [targetId, count] of Object.entries(counts)) {
            if (count > best) {
                best = count;
                leaders = [targetId];
            } else if (count === best) {
                leaders.push(targetId);
            }
        }
        const tie = leaders.length !== 1;
        const eliminatedId = tie ? null : leaders[0];
        let eliminated = null;
        if (eliminatedId) {
            eliminated = findPlayer(state, eliminatedId);
            eliminated.alive = false;
            eliminated.eliminatedRound = state.round;
            eliminated.revealedRole = eliminated.role;
            state.aliveOrder = alivePlayers(state).map((player) => player.id);
        }
        state.lastVote = {
            counts,
            eliminatedId,
            tie,
            eliminatedRole: eliminated ? eliminated.role : null,
            round: state.round,
        };
        state.history.push({
            type: "vote",
            round: state.round,
            counts,
            eliminatedId,
            tie,
        });
        state.votes = {};
        if (eliminated && eliminated.role === ROLE_MR_WHITE) {
            state.phase = PHASE_MR_WHITE;
            return state;
        }
        state.phase = PHASE_VOTE_RESULT;
        evaluateWinner(state);
        return state;
    }

    function evaluateWinner(state) {
        if (state.winner) {
            state.phase = PHASE_GAME_OVER;
            return state;
        }
        const alive = alivePlayers(state);
        const undercover = alive.filter((player) => player.role === ROLE_UNDERCOVER).length;
        const mrWhite = alive.filter((player) => player.role === ROLE_MR_WHITE).length;
        const civilians = alive.filter((player) => player.role === ROLE_CIVILIAN).length;
        if (undercover + mrWhite === 0) {
            state.winner = WIN_CIVILIANS;
            state.reasonKey = "all_infiltrators_out";
            state.phase = PHASE_GAME_OVER;
        } else if (undercover + mrWhite >= civilians) {
            state.winner = WIN_UNDERCOVER;
            state.reasonKey = "infiltrators_equal";
            state.phase = PHASE_GAME_OVER;
        }
        return state;
    }

    function guessMrWhite(state, guess) {
        if (state.phase !== PHASE_MR_WHITE) {
            return { ok: false, code: "E_PHASE" };
        }
        const answer = normalizeAnswer(guess);
        const correct = answer.length > 0 && answer === normalizeAnswer(state.civilianWord);
        state.mrWhiteGuess = { guess: normalizeName(guess), correct };
        state.history.push({ type: "mr_white_guess", round: state.round, correct });
        if (correct) {
            state.winner = WIN_MR_WHITE;
            state.reasonKey = "mr_white_guessed";
            state.phase = PHASE_GAME_OVER;
        } else {
            state.phase = PHASE_VOTE_RESULT;
            evaluateWinner(state);
        }
        return { ok: true, correct, state };
    }

    function continueAfterVote(state) {
        if (state.phase === PHASE_GAME_OVER) {
            return state;
        }
        if (state.phase === PHASE_MR_WHITE) {
            return state;
        }
        if (state.phase !== PHASE_VOTE_RESULT) {
            return state;
        }
        state.round += 1;
        state.phase = PHASE_CLUES;
        state.spokenCount = 0;
        state.speakerIndex = (state.round - 1) % Math.max(1, alivePlayers(state).length);
        state.lastVote = null;
        return state;
    }

    function publicSnapshot(state) {
        const gameOver = state.phase === PHASE_GAME_OVER;
        const alive = alivePlayers(state);
        const speaker = currentSpeaker(state);
        return {
            phase: state.phase,
            round: state.round,
            categoryId: state.categoryId,
            categoryName: state.categoryName,
            civilianWord: gameOver ? state.civilianWord : null,
            undercoverWord: gameOver ? state.undercoverWord : null,
            winner: state.winner,
            reasonKey: state.reasonKey,
            speakerId: speaker ? speaker.id : null,
            spokenCount: state.spokenCount,
            aliveCount: alive.length,
            votesCast: Object.keys(state.votes).length,
            revealIndex: state.revealIndex,
            players: state.players.map((player) => ({
                id: player.id,
                name: player.name,
                alive: player.alive,
                eliminatedRound: player.eliminatedRound,
                role: gameOver || !player.alive ? player.revealedRole || player.role : null,
                word: gameOver ? player.word : null,
            })),
            lastVote: state.lastVote,
            mrWhiteGuess: state.mrWhiteGuess,
            history: state.history.slice(),
        };
    }

    return Object.freeze({
        VERSION,
        MIN_PLAYERS,
        MAX_PLAYERS,
        MIN_UNDERCOVER,
        MAX_UNDERCOVER,
        MAX_NAME_LENGTH,
        ROLE_CIVILIAN,
        ROLE_UNDERCOVER,
        ROLE_MR_WHITE,
        PHASE_REVEAL,
        PHASE_CLUES,
        PHASE_VOTE,
        PHASE_VOTE_RESULT,
        PHASE_MR_WHITE,
        PHASE_GAME_OVER,
        WIN_CIVILIANS,
        WIN_UNDERCOVER,
        WIN_MR_WHITE,
        normalizeName,
        normalizeAnswer,
        recommendedUndercover,
        validateSetup,
        createGame,
        alivePlayers,
        findPlayer,
        currentRevealPlayer,
        secretFor,
        advanceReveal,
        currentSpeaker,
        advanceSpeaker,
        castVote,
        resolveVote,
        guessMrWhite,
        continueAfterVote,
        publicSnapshot,
    });
});

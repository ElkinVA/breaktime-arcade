import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "../..");
vm.runInThisContext(readFileSync(resolve(root, "games-src/whos_undercover/js/rng.js"), "utf8"));
vm.runInThisContext(readFileSync(resolve(root, "games-src/whos_undercover/js/core.js"), "utf8"));
const C = globalThis.WhosUndercoverCore;
const en = JSON.parse(readFileSync(resolve(root, "games-src/whos_undercover/locales/en.json"), "utf8"));

function gameWith(names, options = {}) {
    const result = C.createGame({
        names,
        undercoverCount: options.undercoverCount ?? 1,
        mrWhite: options.mrWhite ?? false,
        pack: en.words,
        seed: options.seed ?? "test-seed",
        categoryId: options.categoryId,
    });
    assert.equal(result.ok, true, JSON.stringify(result));
    return result.state;
}

function finishReveal(state) {
    while (state.phase === C.PHASE_REVEAL) {
        C.advanceReveal(state);
    }
}

function finishClues(state) {
    while (state.phase === C.PHASE_CLUES) {
        C.advanceSpeaker(state);
    }
}

function voteAll(state, targetId) {
    const voters = C.alivePlayers(state).map((player) => player.id);
    for (const voterId of voters) {
        const chosen = voterId === targetId
            ? C.alivePlayers(state).find((player) => player.id !== voterId).id
            : targetId;
        const result = C.castVote(state, voterId, chosen);
        assert.equal(result.ok, true, JSON.stringify(result));
    }
}

function roles(state) {
    return state.players.map((player) => player.role);
}

let passed = 0;
function test(name, fn) {
    fn();
    passed += 1;
    console.log(`ok ${passed} - ${name}`);
}

test("setup requires 4-12 unique names and a balanced table", () => {
    const base = ["A", "B", "C", "D"];
    assert.equal(C.validateSetup({ names: base, undercoverCount: 1 }).ok, true);
    assert.equal(C.validateSetup({ names: ["A", "B", "C"], undercoverCount: 1 }).code, "E_PLAYERS");
    assert.equal(
        C.validateSetup({ names: ["A", "A", "B", "C"], undercoverCount: 1 }).code,
        "E_DUPLICATE_NAME",
    );
    assert.equal(C.validateSetup({ names: base, undercoverCount: 2 }).code, "E_BALANCE");
    assert.equal(
        C.validateSetup({ names: ["A", "B", "C", "D", "E"], undercoverCount: 1, mrWhite: true })
            .ok,
        true,
    );
    assert.equal(
        C.validateSetup({ names: base, undercoverCount: 1, mrWhite: true }).code,
        "E_BALANCE",
    );
    assert.equal(C.validateSetup({ names: base, undercoverCount: 0 }).code, "E_UNDERCOVER");
    assert.equal(C.recommendedUndercover(4), 1);
    assert.equal(C.recommendedUndercover(7), 2);
    assert.equal(C.recommendedUndercover(10), 3);
});

test("role assignment is deterministic and exact", () => {
    const names = ["A", "B", "C", "D", "E", "F"];
    const a = gameWith(names, { undercoverCount: 1, seed: "same" });
    const b = gameWith(names, { undercoverCount: 1, seed: "same" });
    assert.deepEqual(roles(a), roles(b));
    assert.deepEqual(a.players.map((p) => p.word), b.players.map((p) => p.word));
    assert.equal(roles(a).filter((role) => role === C.ROLE_UNDERCOVER).length, 1);
    assert.equal(roles(a).filter((role) => role === C.ROLE_CIVILIAN).length, 5);
    assert.equal(new Set(a.players.map((p) => p.name)).size, names.length);
    assert.notEqual(a.civilianWord, a.undercoverWord);
});

test("Mr. White has no word and is assigned once", () => {
    const state = gameWith(["A", "B", "C", "D", "E"], { undercoverCount: 1, mrWhite: true });
    const white = state.players.filter((player) => player.role === C.ROLE_MR_WHITE);
    assert.equal(white.length, 1);
    assert.equal(white[0].word, null);
    assert.equal(
        state.players.filter((player) => player.role === C.ROLE_UNDERCOVER).length,
        1,
    );
});

test("snapshot hides secrets until the game is over", () => {
    const state = gameWith(["A", "B", "C", "D"]);
    const snapshot = C.publicSnapshot(state);
    assert.equal(snapshot.civilianWord, null);
    assert.equal(snapshot.undercoverWord, null);
    assert.ok(snapshot.players.every((player) => player.role === null && player.word === null));
    finishReveal(state);
    finishClues(state);
    voteAll(state, state.players.find((player) => player.role === C.ROLE_UNDERCOVER).id);
    assert.equal(state.phase, C.PHASE_GAME_OVER);
    const final = C.publicSnapshot(state);
    assert.equal(final.civilianWord, state.civilianWord);
    assert.equal(final.undercoverWord, state.undercoverWord);
    assert.ok(final.players.every((player) => typeof player.role === "string"));
});

test("a table can vote out the undercover and civilians win", () => {
    const state = gameWith(["A", "B", "C", "D", "E"]);
    finishReveal(state);
    finishClues(state);
    const undercover = state.players.find((player) => player.role === C.ROLE_UNDERCOVER);
    voteAll(state, undercover.id);
    assert.equal(state.phase, C.PHASE_GAME_OVER);
    assert.equal(state.winner, C.WIN_CIVILIANS);
    assert.equal(state.reasonKey, "all_infiltrators_out");
});

test("undercover wins when it matches the civilians", () => {
    const state = gameWith(["A", "B", "C", "D", "E"], { undercoverCount: 2 });
    finishReveal(state);
    finishClues(state);
    const civilian = state.players.find((player) => player.role === C.ROLE_CIVILIAN);
    voteAll(state, civilian.id);
    assert.equal(state.phase, C.PHASE_GAME_OVER);
    assert.equal(state.winner, C.WIN_UNDERCOVER);
    assert.equal(state.reasonKey, "infiltrators_equal");
});


test("a tied vote eliminates nobody and continues", () => {
    const state = gameWith(["A", "B", "C", "D"]);
    finishReveal(state);
    finishClues(state);
    const [a, b, c, d] = C.alivePlayers(state);
    assert.equal(C.castVote(state, a.id, b.id).ok, true);
    assert.equal(C.castVote(state, b.id, a.id).ok, true);
    assert.equal(C.castVote(state, c.id, a.id).ok, true);
    assert.equal(C.castVote(state, d.id, b.id).ok, true);
    assert.equal(state.phase, C.PHASE_VOTE_RESULT);
    assert.equal(state.lastVote.tie, true);
    assert.equal(C.alivePlayers(state).length, 4);
    C.continueAfterVote(state);
    assert.equal(state.phase, C.PHASE_CLUES);
    assert.equal(state.round, 2);
});

test("votes reject self, dead and duplicate voters", () => {
    const state = gameWith(["A", "B", "C", "D"]);
    finishReveal(state);
    finishClues(state);
    const [a, b] = C.alivePlayers(state);
    assert.equal(C.castVote(state, a.id, a.id).code, "E_SELF_VOTE");
    assert.equal(C.castVote(state, a.id, b.id).ok, true);
    assert.equal(C.castVote(state, a.id, b.id).code, "E_ALREADY_VOTED");
    assert.equal(C.castVote(state, "nope", b.id).code, "E_TARGET");
});

test("Mr. White can steal the game with the right guess", () => {
    const state = gameWith(["A", "B", "C", "D", "E"], { undercoverCount: 1, mrWhite: true });
    finishReveal(state);
    finishClues(state);
    const white = state.players.find((player) => player.role === C.ROLE_MR_WHITE);
    voteAll(state, white.id);
    assert.equal(state.phase, C.PHASE_MR_WHITE);
    const result = C.guessMrWhite(state, ` ${state.civilianWord.toUpperCase()}! `);
    assert.equal(result.correct, true);
    assert.equal(state.winner, C.WIN_MR_WHITE);
    assert.equal(state.phase, C.PHASE_GAME_OVER);
});

test("a wrong Mr. White guess continues when undercover remains", () => {
    const state = gameWith(["A", "B", "C", "D", "E"], { undercoverCount: 1, mrWhite: true });
    finishReveal(state);
    finishClues(state);
    const white = state.players.find((player) => player.role === C.ROLE_MR_WHITE);
    voteAll(state, white.id);
    const result = C.guessMrWhite(state, "definitely-not-the-word");
    assert.equal(result.correct, false);
    assert.equal(state.phase, C.PHASE_VOTE_RESULT);
    assert.equal(state.winner, null);
    C.continueAfterVote(state);
    assert.equal(state.phase, C.PHASE_CLUES);
    assert.equal(state.round, 2);
});

test("reveal is one player at a time and secretFor is scoped", () => {
    const state = gameWith(["A", "B", "C", "D"]);
    const first = C.currentRevealPlayer(state);
    assert.equal(state.players[0].id, first.id);
    assert.ok(C.secretFor(state, first.id));
    assert.equal(C.secretFor(state, state.players[1].id), null);
    C.advanceReveal(state);
    assert.equal(C.secretFor(state, first.id), null);
    assert.ok(C.secretFor(state, state.players[1].id));
});

test("word decks are complete and bilingual", () => {
    const ru = JSON.parse(
        readFileSync(resolve(root, "games-src/whos_undercover/locales/ru.json"), "utf8"),
    );
    assert.equal(en.words.length, 10);
    assert.equal(ru.words.length, en.words.length);
    for (let index = 0; index < en.words.length; index += 1) {
        assert.equal(en.words[index].id, ru.words[index].id);
        assert.equal(en.words[index].pairs.length, ru.words[index].pairs.length);
        assert.ok(en.words[index].pairs.length >= 10);
    }
});

console.log(`${passed} Who's Undercover? core tests passed`);

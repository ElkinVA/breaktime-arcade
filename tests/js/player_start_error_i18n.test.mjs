import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const ORIGIN = "https://game.test";
const START_ERROR = "Could not start the game";

const listeners = new Map();
const frame = {
    dataset: {
        gameId: "archer",
        csrf: "csrf-token",
        src: `${ORIGIN}/v/hash/index.html#p=https%3A%2F%2Fportal.test%3A8443`,
        startError: START_ERROR,
    },
    contentWindow: { postMessage() {} },
    addEventListener() {},
};
const status = { hidden: true, textContent: "" };

globalThis.document = {
    getElementById(id) {
        if (id === "game-frame") {
            return frame;
        }
        if (id === "player-status") {
            return status;
        }
        return null;
    },
    addEventListener() {},
    visibilityState: "visible",
};
globalThis.window = {
    addEventListener(type, callback) {
        listeners.set(type, callback);
    },
    removeEventListener(type) {
        listeners.delete(type);
    },
};
globalThis.setInterval = () => 0;

// An error without a message must surface the page-injected localized value.
globalThis.fetch = async () => {
    throw new Error("");
};

await import("../../static/src/js/player.js");

test("start failure falls back to the localized data-start-error value", async () => {
    for (let attempt = 0; attempt < 300 && status.hidden; attempt += 1) {
        await new Promise((resolve) => setTimeout(resolve, 10));
    }
    assert.equal(status.hidden, false, "player status is visible");
    assert.equal(status.textContent, START_ERROR);
    assert.equal(frame.src, undefined);
    assert.equal(listeners.has("message"), false, "no bridge is created without a session");
});

test("player.js keeps no hardcoded Russian fallback", async () => {
    const source = await readFile(
        new URL("../../static/src/js/player.js", import.meta.url),
        "utf8",
    );
    assert.equal(source.includes("Не удалось начать игру"), false);
});

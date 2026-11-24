import assert from "node:assert/strict";
import test from "node:test";

const ORIGIN = "https://game.test";
const SESSION = "018f6c2e-6f5a-7c31-9a44-4f1b6e9a0c12";

const listeners = new Map();
const frame = {
    dataset: {
        gameId: "archer",
        csrf: "csrf-token",
        src: `${ORIGIN}/v/hash/index.html#p=https%3A%2F%2Fportal.test%3A8443`,
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

globalThis.fetch = async () => ({
    status: 429,
    ok: false,
    headers: { get: () => null },
    json: async () => ({ code: "E_RATE_LIMIT", message: "Too many active sessions" }),
});

await import("../../static/src/js/player.js");

test("create failure is shown to the player and no iframe src is set", async () => {
    for (let attempt = 0; attempt < 50 && status.hidden; attempt += 1) {
        await new Promise((resolve) => setTimeout(resolve, 0));
    }
    assert.equal(status.hidden, false, "player status is visible");
    assert.match(status.textContent, /Too many active sessions/);
    assert.equal(frame.src, undefined);
    assert.equal(listeners.has("message"), false, "no bridge is created without a session");
});

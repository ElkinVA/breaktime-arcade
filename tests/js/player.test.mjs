import assert from "node:assert/strict";
import test from "node:test";

const OLD_SESSION = "018f6c2e-6f5a-7c31-9a44-4f1b6e9a0c12";
const NEW_SESSION = "018f6c2e-6f5a-7c31-9a44-4f1b6e9a0c13";
const ORIGIN = "https://game.test";

const listeners = new Map();
const fetchCalls = [];
const posted = [];
const frame = {
    dataset: {
        context: JSON.stringify({ sessionId: OLD_SESSION, seed: "old-seed", mode: "guest" }),
        gameId: "archer",
        csrf: "csrf-token",
        src: `${ORIGIN}/v/hash/index.html`,
        sessionId: OLD_SESSION,
    },
    contentWindow: {
        postMessage(data) {
            posted.push(data);
        },
    },
    addEventListener() {},
};

globalThis.document = {
    getElementById() {
        return frame;
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

globalThis.fetch = async (url, options = {}) => {
    fetchCalls.push({ url, method: options.method || "GET" });
    const response = (status, payload, headers = {}) => ({
        status,
        ok: status >= 200 && status < 300,
        headers: { get: (name) => headers[name] ?? null },
        json: async () => payload,
    });
    if (url.endsWith(`/sessions/${OLD_SESSION}/close`)) {
        return response(204, null);
    }
    if (url.endsWith("/api/v1/sessions")) {
        return response(201, {
            sessionId: NEW_SESSION,
            ticket: "ticket-value",
            expires_at: "2026-11-23T00:00:00Z",
        });
    }
    if (url.includes(`/sessions/${NEW_SESSION}/activate`)) {
        return response(200, {
            context: { sessionId: NEW_SESSION, seed: "new-seed", mode: "guest" },
        });
    }
    throw new Error(`unexpected fetch: ${url}`);
};

await import("../../static/src/js/player.js");

const messageHandler = listeners.get("message");
assert.equal(typeof messageHandler, "function");

function envelope(type, sessionId, requestId, payload = {}) {
    return {
        source: "ba-sdk",
        protocol: 1,
        type,
        requestId,
        sessionId,
        payload,
    };
}

await messageHandler({
    source: frame.contentWindow,
    origin: ORIGIN,
    data: envelope("ba:hello", OLD_SESSION, crypto.randomUUID()),
});
await new Promise((resolve) => setTimeout(resolve, 0));

test("newSession closes the old session before creating the next one", async () => {
    await messageHandler({
        source: frame.contentWindow,
        origin: ORIGIN,
        data: envelope("ba:newSession", OLD_SESSION, crypto.randomUUID()),
    });
    await new Promise((resolve) => setTimeout(resolve, 20));

    const closeIndex = fetchCalls.findIndex((call) => call.url.endsWith("/close"));
    const createIndex = fetchCalls.findIndex(
        (call) => call.url.endsWith("/api/v1/sessions") && call.method === "POST",
    );
    assert.ok(closeIndex >= 0, "old session close was requested");
    assert.ok(createIndex > closeIndex, "new session is created after close");

    const sessionMessage = posted.findLast((data) => data.type === "ba:session");
    assert.ok(sessionMessage, "host sends the new session");
    assert.equal(sessionMessage.sessionId, NEW_SESSION);
});

import assert from "node:assert/strict";
import test from "node:test";

const OLD_SESSION = "018f6c2e-6f5a-7c31-9a44-4f1b6e9a0c12";
const NEW_SESSION = "018f6c2e-6f5a-7c31-9a44-4f1b6e9a0c13";
const ORIGIN = "https://game.test";

const listeners = new Map();
const fetchCalls = [];
const posted = [];
let heartbeatMode = "ok";
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
    if (url.endsWith(`/sessions/${NEW_SESSION}/heartbeat`)) {
        if (heartbeatMode === "transient") {
            return response(500, { code: "E_INTERNAL", message: "temporary" });
        }
        if (heartbeatMode === "expired") {
            return response(410, { code: "E_SESSION_EXPIRED", message: "expired" });
        }
        return response(204, null);
    }
    if (url.endsWith(`/sessions/${NEW_SESSION}/result`)) {
        return response(200, {
            status: "saved",
            rank: 1,
            is_personal_best: true,
            is_record: true,
            trust_level: "client_reported",
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

async function switchToNewSession() {
    await messageHandler({
        source: frame.contentWindow,
        origin: ORIGIN,
        data: envelope("ba:newSession", NEW_SESSION, crypto.randomUUID()),
    });
    await new Promise((resolve) => setTimeout(resolve, 20));
}

async function submit(value = 10) {
    await messageHandler({
        source: frame.contentWindow,
        origin: ORIGIN,
        data: envelope("ba:submit", NEW_SESSION, crypto.randomUUID(), {
            value,
            durationMs: 30000,
            seed: "new-seed",
            eventLog: { v: 1, seed: "new-seed", events: [] },
        }),
    });
}

test("submit sends a final heartbeat before the result", async () => {
    heartbeatMode = "ok";
    await switchToNewSession();
    const before = fetchCalls.length;

    await submit();
    await new Promise((resolve) => setTimeout(resolve, 20));

    const heartbeatIndex = fetchCalls.findIndex(
        (call, index) =>
            index >= before && call.url.endsWith(`/sessions/${NEW_SESSION}/heartbeat`),
    );
    const resultIndex = fetchCalls.findIndex(
        (call, index) => index >= before && call.url.endsWith(`/sessions/${NEW_SESSION}/result`),
    );
    assert.ok(heartbeatIndex >= 0, "final heartbeat was sent");
    assert.ok(resultIndex > heartbeatIndex, "result is sent after the final heartbeat");
});

test("a transient final heartbeat failure still attempts the result", async () => {
    heartbeatMode = "transient";
    await switchToNewSession();
    const before = fetchCalls.length;

    await submit();
    await new Promise((resolve) => setTimeout(resolve, 1200));

    const resultIndex = fetchCalls.findIndex(
        (call, index) => index >= before && call.url.endsWith(`/sessions/${NEW_SESSION}/result`),
    );
    assert.ok(resultIndex >= 0, "result is attempted after a transient heartbeat failure");
    heartbeatMode = "ok";
});

test("an expired final heartbeat skips the result", async () => {
    heartbeatMode = "expired";
    await switchToNewSession();
    const before = fetchCalls.length;

    await submit();
    await new Promise((resolve) => setTimeout(resolve, 20));

    const resultIndex = fetchCalls.findIndex(
        (call, index) => index >= before && call.url.endsWith(`/sessions/${NEW_SESSION}/result`),
    );
    assert.equal(resultIndex, -1, "result is not sent after an expired heartbeat");
    const error = posted.findLast((data) => data.type === "ba:error");
    assert.ok(error, JSON.stringify(posted.slice(-4)));
    assert.equal(error.payload.code, "E_SESSION_EXPIRED");
    heartbeatMode = "ok";
});

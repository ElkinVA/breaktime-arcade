import assert from "node:assert/strict";
import test from "node:test";

const OLD_SESSION = "018f6c2e-6f5a-7c31-9a44-4f1b6e9a0c12";
const NEW_SESSION = "018f6c2e-6f5a-7c31-9a44-4f1b6e9a0c13";
const ORIGIN = "https://game.test";

const listeners = new Map();
const fetchCalls = [];
const posted = [];
const oldSubmits = [];
const oldLeaderboards = [];
const oldStorages = [];
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

function response(status, payload, headers = {}) {
    return {
        status,
        ok: status >= 200 && status < 300,
        headers: { get: (name) => headers[name] ?? null },
        json: async () => payload,
    };
}

function deferred() {
    let resolve;
    let reject;
    const promise = new Promise((onResolve, onReject) => {
        resolve = onResolve;
        reject = onReject;
    });
    return { promise, resolve, reject };
}

globalThis.fetch = async (url, options = {}) => {
    fetchCalls.push({
        url,
        method: options.method || "GET",
        headers: options.headers || {},
        body: options.body,
    });
    if (url.endsWith(`/sessions/${OLD_SESSION}/result`)) {
        const pending = deferred();
        oldSubmits.push(pending);
        return pending.promise;
    }
    if (url.endsWith("/api/v1/games/archer/leaderboard?limit=10")) {
        const pending = deferred();
        oldLeaderboards.push(pending);
        return pending.promise;
    }
    if (url.endsWith("/api/v1/games/archer/storage")) {
        const pending = deferred();
        oldStorages.push(pending);
        return pending.promise;
    }
    if (
        url.endsWith(`/sessions/${OLD_SESSION}/heartbeat`) ||
        url.endsWith(`/sessions/${NEW_SESSION}/heartbeat`)
    ) {
        return response(204, null);
    }
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
    return { source: "ba-sdk", protocol: 1, type, requestId, sessionId, payload };
}

const submitPayload = { value: 5, durationMs: 1000, eventLog: { v: 1, seed: "seed", events: [] }, seed: "seed" };

await messageHandler({
    source: frame.contentWindow,
    origin: ORIGIN,
    data: envelope("ba:hello", OLD_SESSION, crypto.randomUUID()),
});
await new Promise((resolve) => setTimeout(resolve, 0));

test("stale submit responses and retries never cross a session boundary", async () => {
    const firstRequest = crypto.randomUUID();
    const secondRequest = crypto.randomUUID();
    const leaderboardRequest = crypto.randomUUID();
    const storageRequest = crypto.randomUUID();
    const newSessionRequest = crypto.randomUUID();
    const newSubmitRequest = crypto.randomUUID();

    await messageHandler({
        source: frame.contentWindow,
        origin: ORIGIN,
        data: envelope("ba:submit", OLD_SESSION, firstRequest, submitPayload),
    });
    await messageHandler({
        source: frame.contentWindow,
        origin: ORIGIN,
        data: envelope("ba:submit", OLD_SESSION, secondRequest, submitPayload),
    });
    await messageHandler({
        source: frame.contentWindow,
        origin: ORIGIN,
        data: envelope("ba:leaderboard", OLD_SESSION, leaderboardRequest, { limit: 10 }),
    });
    await messageHandler({
        source: frame.contentWindow,
        origin: ORIGIN,
        data: envelope("ba:storage", OLD_SESSION, storageRequest, { op: "get", key: "k" }),
    });
    await new Promise((resolve) => setTimeout(resolve, 0));

    const oldCalls = fetchCalls.filter((call) =>
        call.url.endsWith(`/sessions/${OLD_SESSION}/result`),
    );
    assert.equal(oldCalls.length, 2);
    const firstKey = oldCalls[0].headers["Idempotency-Key"];
    const secondKey = oldCalls[1].headers["Idempotency-Key"];
    assert.ok(firstKey, "submit carries an idempotency key");
    assert.equal(firstKey, secondKey, "retries within one session reuse the key");

    await messageHandler({
        source: frame.contentWindow,
        origin: ORIGIN,
        data: envelope("ba:newSession", OLD_SESSION, newSessionRequest),
    });
    await new Promise((resolve) => setTimeout(resolve, 20));

    assert.ok(
        posted.some((data) => data.type === "ba:session" && data.sessionId === NEW_SESSION),
        "the new session reached the iframe",
    );

    oldSubmits[0].resolve(
        response(200, {
            status: "saved",
            rank: 2,
            is_personal_best: true,
            is_record: false,
            trust_level: "client_reported",
        }),
    );
    const staleError = new Error("old session expired");
    staleError.status = 400;
    staleError.code = "E_SESSION_EXPIRED";
    oldSubmits[1].reject(staleError);
    oldLeaderboards[0].resolve(response(200, { entries: [], me: null }));
    oldStorages[0].resolve(response(200, { data: {}, revision: 0 }));
    await new Promise((resolve) => setTimeout(resolve, 20));

    assert.equal(
        posted.filter(
            (data) =>
                (data.type === "ba:result" || data.type === "ba:error") &&
                (data.requestId === firstRequest || data.requestId === secondRequest),
        ).length,
        0,
        "stale success/error must not be posted to the new round",
    );
    assert.equal(
        posted.filter(
            (data) =>
                (data.type === "ba:leaderboard:data" || data.type === "ba:error") &&
                data.requestId === leaderboardRequest,
        ).length,
        0,
        "stale leaderboard data must not be posted",
    );
    assert.equal(
        posted.filter(
            (data) =>
                (data.type === "ba:storage:data" || data.type === "ba:error") &&
                data.requestId === storageRequest,
        ).length,
        0,
        "stale storage data must not be posted",
    );

    await messageHandler({
        source: frame.contentWindow,
        origin: ORIGIN,
        data: envelope("ba:submit", NEW_SESSION, newSubmitRequest, submitPayload),
    });
    await new Promise((resolve) => setTimeout(resolve, 20));

    const newCall = fetchCalls.find((call) =>
        call.url.endsWith(`/sessions/${NEW_SESSION}/result`),
    );
    assert.ok(newCall, "new session submit was sent");
    assert.ok(newCall.headers["Idempotency-Key"], "new submit carries an idempotency key");
    assert.notEqual(
        newCall.headers["Idempotency-Key"],
        firstKey,
        "a new session uses a fresh idempotency key",
    );
    assert.ok(
        posted.some((data) => data.type === "ba:result" && data.requestId === newSubmitRequest),
        "the new session result is posted",
    );
});

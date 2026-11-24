import assert from "node:assert/strict";
import test from "node:test";

const SESSION = "018f6c2e-6f5a-7c31-9a44-4f1b6e9a0c12";
const ORIGIN = "https://game.test";

const listeners = new Map();
const posted = [];
let bestResponse = { value: null, achieved_at: null, rank: null };

const frame = {
    dataset: {
        context: JSON.stringify({ sessionId: SESSION, seed: "seed", mode: "guest" }),
        gameId: "archer",
        csrf: "csrf-token",
        src: `${ORIGIN}/v/hash/index.html`,
        sessionId: SESSION,
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

function response(status, payload) {
    return {
        status,
        ok: status >= 200 && status < 300,
        headers: { get: () => null },
        json: async () => payload,
    };
}

globalThis.fetch = async (url) => {
    if (url.endsWith("/api/v1/sessions")) {
        return response(201, {
            sessionId: SESSION,
            ticket: "ticket-value",
            expires_at: "2026-11-23T00:00:00Z",
        });
    }
    if (url.includes(`/sessions/${SESSION}/activate`)) {
        return response(200, {
            context: { sessionId: SESSION, seed: "seed", mode: "guest" },
        });
    }
    if (url.endsWith(`/sessions/${SESSION}/heartbeat`)) {
        return response(204, null);
    }
    if (url.endsWith("/api/v1/games/archer/me/best")) {
        return response(200, bestResponse);
    }
    throw new Error(`unexpected fetch: ${url}`);
};

await import("../../static/src/js/player.js");

async function waitForMessageHandler() {
    for (let attempt = 0; attempt < 50; attempt += 1) {
        const handler = listeners.get("message");
        if (typeof handler === "function") {
            return handler;
        }
        await new Promise((resolve) => setTimeout(resolve, 0));
    }
    throw new Error("player message handler did not start");
}

const messageHandler = await waitForMessageHandler();

function envelope(type, payload, requestId = crypto.randomUUID()) {
    return { source: "ba-sdk", protocol: 1, type, requestId, sessionId: SESSION, payload };
}

async function requestBest() {
    const requestId = crypto.randomUUID();
    await messageHandler({
        source: frame.contentWindow,
        origin: ORIGIN,
        data: envelope("ba:leaderboard", { limit: 10, bestOnly: true }, requestId),
    });
    await new Promise((resolve) => setTimeout(resolve, 20));
    return posted.find((data) => data.requestId === requestId);
}

await messageHandler({
    source: frame.contentWindow,
    origin: ORIGIN,
    data: envelope("ba:hello", {}),
});
await new Promise((resolve) => setTimeout(resolve, 0));

test("host bestOnly returns empty entries and null myRank when there is no best", async () => {
    bestResponse = { value: null, achieved_at: null, rank: null };
    const message = await requestBest();
    assert.equal(message.type, "ba:leaderboard:data");
    assert.deepEqual(message.payload, { entries: [], myRank: null });
});

test("host bestOnly returns the personal best as a single schema entry", async () => {
    bestResponse = { value: 42, achieved_at: "2026-11-23T10:00:00+00:00", rank: 3 };
    const message = await requestBest();
    assert.equal(message.type, "ba:leaderboard:data");
    assert.deepEqual(message.payload, {
        entries: [
            {
                rank: 3,
                nickname: null,
                value: 42,
                achievedAt: "2026-11-23T10:00:00+00:00",
            },
        ],
        myRank: 3,
    });
});

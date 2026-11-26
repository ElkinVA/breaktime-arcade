import assert from "node:assert/strict";
import test from "node:test";

const OLD_SESSION = "018f6c2e-6f5a-7c31-9a44-4f1b6e9a0c12";
const SECOND_SESSION = "018f6c2e-6f5a-7c31-9a44-4f1b6e9a0c13";
const THIRD_SESSION = "018f6c2e-6f5a-7c31-9a44-4f1b6e9a0c14";
const FOURTH_SESSION = "018f6c2e-6f5a-7c31-9a44-4f1b6e9a0c15";
const SESSIONS = [OLD_SESSION, SECOND_SESSION, THIRD_SESSION, FOURTH_SESSION];
const ORIGIN = "https://game.test";

const listeners = new Map();
const fetchCalls = [];
const posted = [];
const closeGates = new Map();
const resultGates = new Map();
let createCount = 0;

const frame = {
    dataset: {
        context: JSON.stringify({ sessionId: OLD_SESSION, seed: "seed-old", mode: "guest" }),
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

function deferred() {
    let resolve;
    let reject;
    const promise = new Promise((onResolve, onReject) => {
        resolve = onResolve;
        reject = onReject;
    });
    return { promise, resolve, reject };
}

function response(status, payload) {
    return {
        status,
        ok: status >= 200 && status < 300,
        headers: { get: () => null },
        json: async () => payload,
    };
}

globalThis.fetch = async (url, options = {}) => {
    fetchCalls.push({
        url,
        method: options.method || "GET",
        headers: options.headers || {},
        body: options.body,
    });
    if (url.endsWith("/api/v1/sessions")) {
        const sessionId = SESSIONS[createCount];
        createCount += 1;
        return response(201, {
            sessionId,
            ticket: "ticket-value",
            expires_at: "2026-11-23T00:00:00Z",
        });
    }
    const match = url.match(/\/sessions\/([0-9a-f-]+)\/(activate|close|heartbeat|result)$/);
    if (!match) {
        throw new Error(`unexpected fetch: ${url}`);
    }
    const [, sessionId, operation] = match;
    if (operation === "activate") {
        return response(200, {
            context: { sessionId, seed: `seed-${sessionId.slice(-4)}`, mode: "guest" },
        });
    }
    if (operation === "heartbeat") {
        return response(204, null);
    }
    if (operation === "close") {
        const gate = closeGates.get(sessionId);
        if (gate) {
            closeGates.delete(sessionId);
            return gate.promise;
        }
        return response(204, null);
    }
    const gate = resultGates.get(sessionId);
    if (gate) {
        resultGates.delete(sessionId);
        return gate.promise;
    }
    return response(200, {
        status: "saved",
        rank: 1,
        is_personal_best: true,
        is_record: true,
        trust_level: "client_reported",
    });
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

function envelope(type, sessionId, requestId, payload = {}) {
    return { source: "ba-sdk", protocol: 1, type, requestId, sessionId, payload };
}

async function send(type, sessionId, requestId, payload = {}) {
    await messageHandler({
        source: frame.contentWindow,
        origin: ORIGIN,
        data: envelope(type, sessionId, requestId, payload),
    });
    await new Promise((resolve) => setTimeout(resolve, 0));
}

const tick = (ms = 20) => new Promise((resolve) => setTimeout(resolve, ms));

await send("ba:hello", OLD_SESSION, crypto.randomUUID());

test("two quick restarts are serialized and close each previous session once", async () => {
    const oldClose = deferred();
    closeGates.set(OLD_SESSION, oldClose);
    const firstRestart = crypto.randomUUID();
    const secondRestart = crypto.randomUUID();

    await send("ba:newSession", OLD_SESSION, firstRestart);
    await send("ba:newSession", OLD_SESSION, secondRestart);
    await tick();
    assert.equal(createCount, 1, "the second restart waits for the first close");

    oldClose.resolve(response(204, null));
    await tick(40);

    const closeOrder = fetchCalls
        .filter((call) => call.url.endsWith("/close"))
        .map((call) => call.url.match(/\/sessions\/([0-9a-f-]+)\/close$/)[1]);
    assert.deepEqual(closeOrder, [OLD_SESSION, SECOND_SESSION]);
    assert.equal(createCount, 3, "initial session plus two replacements");
    assert.deepEqual(
        posted.filter((data) => data.type === "ba:session").map((data) => data.sessionId),
        [SECOND_SESSION, THIRD_SESSION],
        "both restart responses carry their own replacement session",
    );
});

test("a submit that crosses the close boundary is surfaced as a closed-session error", async () => {
    const fourthClose = deferred();
    closeGates.set(THIRD_SESSION, fourthClose);
    const restart = crypto.randomUUID();
    const lateSubmit = crypto.randomUUID();
    const lateResult = deferred();
    resultGates.set(THIRD_SESSION, lateResult);

    await send("ba:newSession", THIRD_SESSION, restart);
    await send("ba:submit", THIRD_SESSION, lateSubmit, {
        value: 7,
        durationMs: 1000,
        seed: "seed-0c14",
        eventLog: { v: 1, seed: "seed-0c14", events: [] },
    });
    assert.equal(createCount, 3, "the replacement is still blocked on close");

    fourthClose.resolve(response(204, null));
    await tick(40);
    assert.equal(createCount, 4);
    assert.ok(
        posted.some((data) => data.type === "ba:session" && data.sessionId === FOURTH_SESSION),
        "the replacement session is announced",
    );

    lateResult.resolve(
        response(200, {
            status: "saved",
            rank: 1,
            is_personal_best: true,
            is_record: true,
            trust_level: "client_reported",
        }),
    );
    await tick(40);

    assert.equal(
        posted.filter((data) => data.type === "ba:result" && data.requestId === lateSubmit).length,
        0,
        "a stale result must not be delivered as the new round's result",
    );
    const lateError = posted.find(
        (data) => data.type === "ba:error" && data.requestId === lateSubmit,
    );
    assert.ok(lateError, "the dropped boundary submit is surfaced");
    assert.equal(lateError.payload.code, "E_SESSION_FINISHED");
});

test("exit during a pending restart cancels the replacement and closes the bridge", async () => {
    const submitResult = deferred();
    resultGates.set(FOURTH_SESSION, submitResult);
    const submitRequest = crypto.randomUUID();
    const restart = crypto.randomUUID();

    await send("ba:submit", FOURTH_SESSION, submitRequest, {
        value: 9,
        durationMs: 1000,
        seed: "seed-0c15",
        eventLog: { v: 1, seed: "seed-0c15", events: [] },
    });
    await send("ba:newSession", FOURTH_SESSION, restart);
    await send("ba:exit", FOURTH_SESSION, crypto.randomUUID());

    submitResult.resolve(
        response(200, {
            status: "saved",
            rank: 1,
            is_personal_best: true,
            is_record: true,
            trust_level: "client_reported",
        }),
    );
    await tick(60);

    assert.equal(createCount, 4, "exit cancels the queued replacement");
    assert.equal(
        fetchCalls.filter((call) => call.url.endsWith(`/sessions/${FOURTH_SESSION}/close`)).length,
        1,
        "the active session is closed exactly once",
    );
    assert.ok(
        !posted.some((data) => data.type === "ba:session" && data.sessionId === SESSIONS[4]),
        "no fifth session is announced",
    );
    const restartError = posted.find(
        (data) => data.type === "ba:error" && data.requestId === restart,
    );
    assert.ok(restartError, "the cancelled restart gets a structured error");
    assert.equal(restartError.payload.code, "E_SESSION_FINISHED");

    const afterExit = crypto.randomUUID();
    await send("ba:hello", FOURTH_SESSION, afterExit);
    const exitError = posted.find(
        (data) => data.type === "ba:error" && data.requestId === afterExit,
    );
    assert.ok(exitError, "the bridge rejects messages after exit");
    assert.equal(exitError.payload.code, "E_SESSION_FINISHED");
});

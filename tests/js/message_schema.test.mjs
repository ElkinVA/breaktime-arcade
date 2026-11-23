import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "../..");

const SESSION = "018f6c2e-6f5a-7c31-9a44-4f1b6e9a0c12";
const OTHER_SESSION = "018f6c2e-6f5a-7c31-9a44-4f1b6e9a0c13";
const ORIGIN = "https://probe.games.test:8443";
const PORTAL = "https://portal.test";

const listeners = new Map();
globalThis.window = {
    addEventListener(type, callback) {
        listeners.set(type, callback);
    },
    removeEventListener(type) {
        listeners.delete(type);
    },
};

const { HostBridge, validateMessage, validatePayload } = await import(
    "../../static/src/js/host_protocol.js"
);

/* ------------------------------------------------------------------ host -- */

function hostSetup() {
    const sent = [];
    const calls = [];
    const contentWindow = {
        postMessage(data, targetOrigin) {
            sent.push({ data, targetOrigin });
        },
    };
    const bridge = new HostBridge({
        iframe: { contentWindow },
        iframeOrigin: ORIGIN,
        sessionId: SESSION,
        onMessage: (...args) => calls.push(args),
    });
    return { bridge, sent, calls };
}

function hostMessage(overrides = {}) {
    return {
        source: "ba-sdk",
        protocol: 1,
        type: "ba:hello",
        requestId: crypto.randomUUID(),
        sessionId: SESSION,
        payload: {},
        ...overrides,
    };
}

function hostSend(bridge, data, { source, origin } = {}) {
    bridge.onWindowMessage({
        source: source ?? bridge.iframe.contentWindow,
        origin: origin ?? ORIGIN,
        data,
    });
}

function assertWireInvalid(sent, { field } = {}) {
    const message = sent.at(-1);
    assert.equal(message.data.type, "ba:error");
    assert.equal(message.data.payload.code, "E_MESSAGE_INVALID");
    if (field) {
        assert.equal(message.data.payload.field, field);
    }
    return message.data;
}

test("host schema rejects missing, mistyped and unknown envelope fields", () => {
    const valid = hostMessage();
    const cases = [
        ["missing payload", { ...valid, payload: undefined }, "payload"],
        ["wrong protocol type", { ...valid, protocol: "1" }, "protocol"],
        ["wrong type field", { ...valid, type: 7 }, "type"],
        ["wrong payload type", { ...valid, payload: [] }, "payload"],
        ["wrong source", { ...valid, source: "ba-host" }, "source"],
        ["bad requestId", { ...valid, requestId: "not-a-uuid" }, "requestId"],
        ["bad sessionId", { ...valid, sessionId: "not-a-uuid" }, "sessionId"],
        ["unknown message type", { ...valid, type: "ba:unknown" }, "type"],
        ["unknown envelope field", { ...valid, extra: true }, "extra"],
    ];
    for (const [name, value, field] of cases) {
        const error = validateMessage(value, "ba-sdk");
        assert.ok(error, name);
        assert.equal(error.code, "E_MESSAGE_INVALID", name);
        assert.equal(error.field, field, name);
    }
});

test("host payload schemas reject missing fields, wrong types and long strings", () => {
    const errorLog = { v: 1, seed: "s", events: [] };
    const cases = [
        ["submit missing value", "ba:submit", { durationMs: 1, eventLog: errorLog, seed: "s" }, "payload.value"],
        ["submit non-integer duration", "ba:submit", { value: 1, durationMs: 1.5, eventLog: errorLog, seed: "s" }, "payload.durationMs"],
        ["submit bad eventLog", "ba:submit", { value: 1, durationMs: 1, eventLog: [], seed: "s" }, "payload.eventLog"],
        ["submit eventLog missing v", "ba:submit", { value: 1, durationMs: 1, eventLog: { seed: "s", events: [] }, seed: "s" }, "payload.eventLog.v"],
        ["submit huge event kind", "ba:submit", { value: 1, durationMs: 1, eventLog: { v: 1, seed: "s", events: [{ t: 0, k: "x".repeat(65), d: {} }] }, seed: "s" }, "payload.eventLog.events[0].k"],
        ["storage bad op", "ba:storage", { op: "delete", key: "k" }, "payload.op"],
        ["storage missing key", "ba:storage", { op: "get" }, "payload.key"],
        ["storage oversized key", "ba:storage", { op: "get", key: "x".repeat(129) }, "payload.key"],
        ["storage unknown field", "ba:storage", { op: "get", key: "k", extra: 1 }, "payload.extra"],
        ["leaderboard unsupported limit", "ba:leaderboard", { limit: 5 }, "payload.limit"],
        ["leaderboard wrong bestOnly", "ba:leaderboard", { bestOnly: "yes" }, "payload.bestOnly"],
        ["error missing code", "ba:error", { message: "x" }, "payload.code"],
        ["error oversized code", "ba:error", { code: "E".repeat(129) }, "payload.code"],
    ];
    for (const [name, type, payload, field] of cases) {
        const error = validatePayload(type, payload);
        assert.ok(error, name);
        assert.equal(error.code, "E_MESSAGE_INVALID", name);
        assert.equal(error.field, field, name);
    }
    assert.equal(validatePayload("ba:hello", {}), null);
    assert.equal(validatePayload("ba:newSession", {}), null);
});

test("host bridge relays schema violations as structured E_MESSAGE_INVALID", () => {
    const { bridge, sent, calls } = hostSetup();
    hostSend(bridge, hostMessage());
    assert.equal(calls.length, 1);
    sent.length = 0;

    const missingPayload = hostMessage();
    delete missingPayload.payload;
    hostSend(bridge, missingPayload);
    assertWireInvalid(sent, { field: "payload" });
    assert.equal(calls.length, 1);

    const request = hostMessage({
        type: "ba:storage",
        payload: { op: "get", key: "x".repeat(129) },
    });
    hostSend(bridge, request);
    const wire = assertWireInvalid(sent, { field: "payload.key" });
    assert.equal(wire.requestId, request.requestId);

    hostSend(bridge, hostMessage({ type: "ba:unknown" }));
    assertWireInvalid(sent, { field: "type" });

    hostSend(bridge, hostMessage({ requestId: "bad-request-id" }));
    assertWireInvalid(sent, { field: "requestId" });

    hostSend(bridge, hostMessage({ sessionId: OTHER_SESSION }));
    assertWireInvalid(sent, { field: "sessionId" });

    assert.equal(calls.length, 1);
});

test("host bridge silently ignores untrusted source windows and origins", () => {
    const { bridge, sent, calls } = hostSetup();
    hostSend(bridge, hostMessage(), { source: {} });
    hostSend(bridge, hostMessage(), { origin: "https://evil.test" });
    assert.equal(calls.length, 0);
    assert.equal(sent.length, 0);
});

test("host bridge does not redispatch a replayed requestId", () => {
    const { bridge, sent, calls } = hostSetup();
    hostSend(bridge, hostMessage());
    const replay = hostMessage();
    hostSend(bridge, replay);
    hostSend(bridge, replay);
    assert.equal(calls.length, 2);
    assert.equal(sent.filter((item) => item.data.type === "ba:error").length, 0);
});

/* ------------------------------------------------------------------- sdk -- */

const sdkSource = readFileSync(resolve(root, "sdk/1.1.0/ba-sdk.js"), "utf8");

function createSdkEnv() {
    const sdkListeners = new Map();
    const posted = [];
    const parent = {
        postMessage(data, targetOrigin) {
            posted.push({ data, targetOrigin });
        },
    };
    const sandbox = {
        crypto: globalThis.crypto,
        URL,
        URLSearchParams,
        TextEncoder,
        console,
        setTimeout,
        clearTimeout,
        location: { hash: `#p=${encodeURIComponent(PORTAL)}&s=${SESSION}` },
        parent,
        document: {
            querySelector() {
                return null;
            },
            addEventListener() {},
            visibilityState: "visible",
        },
        addEventListener(type, callback) {
            sdkListeners.set(type, callback);
        },
        removeEventListener(type) {
            sdkListeners.delete(type);
        },
    };
    sandbox.window = sandbox;
    vm.createContext(sandbox);
    vm.runInContext(sdkSource, sandbox);
    return { api: sandbox.BreaktimeArcade, sdkListeners, posted, parent };
}

function validContext() {
    return {
        sessionId: SESSION,
        gameId: "archer",
        gameVersion: "1.0.0",
        mode: "guest",
        nickname: null,
        language: "en",
        fallbackLanguage: "en",
        strings: {},
        score: {},
        limits: {},
        trustLevel: "client_reported",
        seed: "seed",
    };
}

function sdkEnvelope(type, sessionId, payload, requestId = crypto.randomUUID()) {
    return { source: "ba-host", protocol: 1, type, requestId, sessionId, payload };
}

function sdkSend(env, data, { source, origin } = {}) {
    const listener = env.sdkListeners.get("message");
    assert.equal(typeof listener, "function");
    listener({ source: source ?? env.parent, origin: origin ?? PORTAL, data });
}

async function startSdk() {
    const env = createSdkEnv();
    const pending = env.api.init({ timeoutMs: 500 });
    sdkSend(env, sdkEnvelope("ba:context", SESSION, validContext()));
    const sdk = await pending;
    return { ...env, sdk };
}

test("SDK rejects malformed context envelopes during init", async () => {
    const cases = [
        [
            "missing seed",
            (payload) => {
                delete payload.seed;
                return sdkEnvelope("ba:context", SESSION, payload);
            },
            "payload.seed",
        ],
        [
            "wrong gameId type",
            (payload) => {
                payload.gameId = 42;
                return sdkEnvelope("ba:context", SESSION, payload);
            },
            "payload.gameId",
        ],
        [
            "oversized gameId",
            (payload) => {
                payload.gameId = "g".repeat(41);
                return sdkEnvelope("ba:context", SESSION, payload);
            },
            "payload.gameId",
        ],
        [
            "oversized nickname",
            (payload) => {
                payload.nickname = "n".repeat(21);
                return sdkEnvelope("ba:context", SESSION, payload);
            },
            "payload.nickname",
        ],
        [
            "bad requestId",
            () => sdkEnvelope("ba:context", SESSION, validContext(), "not-a-uuid"),
            "requestId",
        ],
        [
            "bad sessionId",
            () => sdkEnvelope("ba:context", "not-a-uuid", validContext()),
            "sessionId",
        ],
        [
            "wrong source",
            () => ({ ...sdkEnvelope("ba:context", SESSION, validContext()), source: "ba-sdk" }),
            "source",
        ],
        [
            "unknown type",
            () => sdkEnvelope("ba:unknown", SESSION, {}),
            "type",
        ],
    ];
    for (const [name, mutate, field] of cases) {
        const env = createSdkEnv();
        const pending = env.api.init({ timeoutMs: 500 });
        sdkSend(env, mutate(validContext()));
        await assert.rejects(pending, (error) => {
            assert.equal(error.code, "E_MESSAGE_INVALID", name);
            assert.equal(error.field, field, name);
            return true;
        });
    }
});

test("SDK ignores messages from a foreign source window or origin", async () => {
    const env = createSdkEnv();
    const pending = env.api.init({ timeoutMs: 500 });
    sdkSend(env, sdkEnvelope("ba:context", SESSION, {}), { source: {} });
    sdkSend(env, sdkEnvelope("ba:context", SESSION, {}), { origin: "https://evil.test" });
    sdkSend(env, sdkEnvelope("ba:context", SESSION, validContext()));
    const sdk = await pending;
    assert.equal(sdk.context.gameId, "archer");
});

test("SDK rejects bad payloads for a pending request with a structured error", async () => {
    const env = await startSdk();
    const pending = env.sdk.leaderboard.top(10);
    const requestId = env.posted.at(-1).data.requestId;
    sdkSend(
        env,
        sdkEnvelope("ba:leaderboard:data", SESSION, { entries: "nope", myRank: null }, requestId),
    );
    await assert.rejects(pending, (error) => {
        assert.equal(error.code, "E_MESSAGE_INVALID");
        assert.equal(error.field, "payload.entries");
        return true;
    });
});

test("SDK rejects oversized leaderboard nicknames", async () => {
    const env = await startSdk();
    const pending = env.sdk.leaderboard.top(10);
    const requestId = env.posted.at(-1).data.requestId;
    sdkSend(
        env,
        sdkEnvelope(
            "ba:leaderboard:data",
            SESSION,
            {
                entries: [{ rank: 1, nickname: "n".repeat(21), value: 10 }],
                myRank: 1,
            },
            requestId,
        ),
    );
    await assert.rejects(pending, (error) => {
        assert.equal(error.code, "E_MESSAGE_INVALID");
        assert.equal(error.field, "payload.entries[0].nickname");
        return true;
    });
});

test("SDK rejects a response bound to a different session", async () => {
    const env = await startSdk();
    const pending = env.sdk.leaderboard.top(10);
    const requestId = env.posted.at(-1).data.requestId;
    sdkSend(
        env,
        sdkEnvelope(
            "ba:leaderboard:data",
            OTHER_SESSION,
            { entries: [], myRank: null },
            requestId,
        ),
    );
    await assert.rejects(pending, (error) => {
        assert.equal(error.code, "E_MESSAGE_INVALID");
        assert.equal(error.field, "sessionId");
        return true;
    });
});

test("SDK leaves a pending request open for a bad requestId or foreign origin", async () => {
    const env = await startSdk();
    const pending = env.sdk.leaderboard.top(10);
    const requestId = env.posted.at(-1).data.requestId;
    let outcome = "pending";
    pending.then(
        () => {
            outcome = "resolved";
        },
        () => {
            outcome = "rejected";
        },
    );
    sdkSend(
        env,
        sdkEnvelope("ba:leaderboard:data", SESSION, { entries: [], myRank: null }, "bad-id"),
    );
    sdkSend(
        env,
        sdkEnvelope("ba:leaderboard:data", SESSION, { entries: [], myRank: null }, requestId),
        { origin: "https://evil.test" },
    );
    await new Promise((resolve) => setTimeout(resolve, 10));
    assert.equal(outcome, "pending");
    sdkSend(
        env,
        sdkEnvelope("ba:leaderboard:data", SESSION, { entries: [], myRank: null }, requestId),
    );
    const payload = await pending;
    assert.deepEqual(payload, { entries: [], myRank: null });
});

test("SDK myBest returns null when the host reports no personal best", async () => {
    const env = await startSdk();
    const pending = env.sdk.leaderboard.myBest();
    const request = env.posted.at(-1).data;
    assert.equal(request.type, "ba:leaderboard");
    assert.equal(request.payload.limit, 10);
    assert.equal(request.payload.bestOnly, true);
    sdkSend(
        env,
        sdkEnvelope(
            "ba:leaderboard:data",
            SESSION,
            { entries: [], myRank: null },
            request.requestId,
        ),
    );
    assert.equal(await pending, null);
});

test("SDK myBest extracts value and achievedAt from the single entry", async () => {
    const env = await startSdk();
    const pending = env.sdk.leaderboard.myBest();
    const requestId = env.posted.at(-1).data.requestId;
    const achievedAt = "2026-11-23T10:00:00+00:00";
    sdkSend(
        env,
        sdkEnvelope(
            "ba:leaderboard:data",
            SESSION,
            {
                entries: [{ rank: 2, nickname: null, value: 42, achievedAt }],
                myRank: 2,
            },
            requestId,
        ),
    );
    const result = await pending;
    assert.equal(result.value, 42);
    assert.equal(result.achievedAt, achievedAt);
});

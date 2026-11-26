import assert from "node:assert/strict";
import test from "node:test";

const listeners = new Map();
globalThis.window = {
    addEventListener(type, callback) {
        listeners.set(type, callback);
    },
    removeEventListener(type) {
        listeners.delete(type);
    },
};

const { HostBridge } = await import("../../static/src/js/host_protocol.js");

const SESSION = "018f6c2e-6f5a-7c31-9a44-4f1b6e9a0c12";
const OTHER_SESSION = "018f6c2e-6f5a-7c31-9a44-4f1b6e9a0c13";
const ORIGIN = "https://probe.games.test:8443";

function setup() {
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
    return { bridge, sent, calls, contentWindow };
}

function message(overrides = {}) {
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

test("host bridge accepts a valid hello and replies only to exact origin", () => {
    const { bridge, sent, calls } = setup();
    bridge.onWindowMessage({
        source: bridge.iframe.contentWindow,
        origin: ORIGIN,
        data: message(),
    });
    assert.equal(calls.length, 1);
    assert.equal(calls[0][0], "ba:hello");

    bridge.sendPause({});
    assert.equal(sent.at(-1).targetOrigin, ORIGIN);
    assert.equal(sent.at(-1).data.source, "ba-host");
});

test("host bridge rejects wrong source window, origin, session and replay", () => {
    const { bridge, calls } = setup();
    bridge.onWindowMessage({
        source: {},
        origin: ORIGIN,
        data: message(),
    });
    bridge.onWindowMessage({
        source: bridge.iframe.contentWindow,
        origin: "https://evil.test",
        data: message(),
    });
    bridge.onWindowMessage({
        source: bridge.iframe.contentWindow,
        origin: ORIGIN,
        data: message({ sessionId: OTHER_SESSION }),
    });
    const request = message();
    bridge.onWindowMessage({
        source: bridge.iframe.contentWindow,
        origin: ORIGIN,
        data: request,
    });
    bridge.onWindowMessage({
        source: bridge.iframe.contentWindow,
        origin: ORIGIN,
        data: request,
    });
    assert.equal(calls.length, 1);
});

test("host bridge emits protocol error for invalid payload", () => {
    const { bridge, sent, calls } = setup();
    bridge.onWindowMessage({
        source: bridge.iframe.contentWindow,
        origin: ORIGIN,
        data: message({
            type: "ba:storage",
            payload: { op: "delete", key: "x" },
        }),
    });
    assert.equal(calls.length, 0);
    assert.equal(sent.at(-1).data.type, "ba:error");
    assert.equal(sent.at(-1).data.payload.code, "E_MESSAGE_INVALID");
});

test("host bridge rejects non-integer scores and unsupported leaderboard limits", () => {
    const { bridge, sent, calls } = setup();
    const submit = message({
        type: "ba:submit",
        payload: {
            value: Number.NaN,
            durationMs: 1000,
            eventLog: { v: 1, seed: "s", events: [] },
            seed: "s",
        },
    });
    bridge.onWindowMessage({
        source: bridge.iframe.contentWindow,
        origin: ORIGIN,
        data: submit,
    });
    for (const limit of [5, 50, 1000]) {
        bridge.onWindowMessage({
            source: bridge.iframe.contentWindow,
            origin: ORIGIN,
            data: message({
                type: "ba:leaderboard",
                payload: { limit },
            }),
        });
    }
    for (const payload of [
        { value: 1, durationMs: 1.5, eventLog: {}, seed: "s" },
        { value: 1, durationMs: 1000, eventLog: [], seed: "s" },
        { value: 1, durationMs: 1000, eventLog: null, seed: "s" },
        { value: 1, durationMs: 1000, eventLog: {}, seed: 7 },
    ]) {
        bridge.onWindowMessage({
            source: bridge.iframe.contentWindow,
            origin: ORIGIN,
            data: message({ type: "ba:submit", payload }),
        });
    }
    assert.equal(calls.length, 0);
    assert.equal(sent.at(-1).data.payload.code, "E_MESSAGE_INVALID");
});

test("host bridge enforces 60 messages per minute", () => {
    const { bridge, sent, calls } = setup();
    for (let index = 0; index < 61; index += 1) {
        bridge.onWindowMessage({
            source: bridge.iframe.contentWindow,
            origin: ORIGIN,
            data: message(),
        });
    }
    assert.equal(calls.length, 60);
    assert.equal(sent.at(-1).data.type, "ba:error");
    assert.equal(sent.at(-1).data.payload.code, "E_RATE_LIMIT");
});

test("host bridge rejects all messages after exit, including hello", () => {
    const { bridge, sent, calls } = setup();
    bridge.markExited();
    for (const type of ["ba:hello", "ba:leaderboard", "ba:newSession"]) {
        bridge.onWindowMessage({
            source: bridge.iframe.contentWindow,
            origin: ORIGIN,
            data: message({ type, payload: type === "ba:leaderboard" ? { limit: 10 } : {} }),
        });
    }
    assert.equal(calls.length, 0);
    assert.equal(sent.length, 3);
    assert.equal(sent.at(-1).data.type, "ba:error");
    assert.equal(sent.at(-1).data.payload.code, "E_SESSION_FINISHED");
});

test("exited state is not reopened by a late result or session", () => {
    const { bridge, sent, calls } = setup();
    bridge.markExited();

    bridge.sendResult(crypto.randomUUID(), { status: "saved" });
    assert.equal(bridge.state, "exited");
    assert.equal(calls.length, 0);
    assert.equal(sent.at(-1).data.type, "ba:error");
    assert.equal(sent.at(-1).data.payload.code, "E_SESSION_FINISHED");

    bridge.sendSession(crypto.randomUUID(), { sessionId: OTHER_SESSION, seed: "s" });
    assert.equal(bridge.state, "exited");
    assert.equal(calls.length, 0);
    assert.equal(sent.at(-1).data.type, "ba:error");
    assert.equal(sent.at(-1).data.payload.code, "E_SESSION_FINISHED");
});

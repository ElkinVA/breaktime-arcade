import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "../..");

const SESSION = "018f6c2e-6f5a-7c31-9a44-4f1b6e9a0c12";
const NEW_SESSION = "018f6c2e-6f5a-7c31-9a44-4f1b6e9a0c13";
const PORTAL = "https://portal.test";

const sdkSource = readFileSync(resolve(root, "sdk/1.1.0/ba-sdk.js"), "utf8");

/* Deterministic timers: pending requests never reach their timeout inside
 * these tests, so any settlement must come from explicit cancellation.
 */
function createSdkEnv() {
    const sdkListeners = new Map();
    const posted = [];
    const timers = new Map();
    const cleared = [];
    let nextTimer = 1;
    let lastTimer = null;
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
        setTimeout(callback, ms) {
            const id = nextTimer;
            nextTimer += 1;
            lastTimer = id;
            timers.set(id, { callback, ms });
            return id;
        },
        clearTimeout(id) {
            cleared.push(id);
            timers.delete(id);
        },
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
    return {
        api: sandbox.BreaktimeArcade,
        sdkListeners,
        posted,
        parent,
        timers,
        cleared,
        lastTimerId() {
            return lastTimer;
        },
    };
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

function sdkSend(env, data) {
    const listener = env.sdkListeners.get("message");
    assert.equal(typeof listener, "function");
    listener({ source: env.parent, origin: PORTAL, data });
}

async function startSdk() {
    const env = createSdkEnv();
    const pending = env.api.init({ timeoutMs: 500 });
    sdkSend(env, sdkEnvelope("ba:context", SESSION, validContext()));
    const sdk = await pending;
    assert.equal(env.timers.size, 0, "init timer is cleared once the context arrives");
    return { env, sdk };
}

/* Wait for settlement but fail fast if the promise only ever settles through
 * a real request timeout (those are deliberately never fired here).
 */
async function settlement(promise) {
    let timer;
    try {
        return await Promise.race([
            promise.then(
                () => ({ status: "resolved" }),
                (error) => ({ status: "rejected", error }),
            ),
            new Promise((resolve) => {
                timer = setTimeout(() => resolve({ status: "pending" }), 500);
            }),
        ]);
    } finally {
        clearTimeout(timer);
    }
}

function assertCancelled(outcome) {
    assert.equal(outcome.status, "rejected", "request must settle instead of hanging");
    assert.equal(outcome.error.code, "E_TIMEOUT");
    assert.match(outcome.error.message, /CANCEL|ABORT|TIMEOUT/);
}

test("newSession settles pending old-session requests and clears their timers", async () => {
    const { env, sdk } = await startSdk();

    const stale = sdk.leaderboard.top(10);
    const staleRequestId = env.posted.at(-1).data.requestId;
    const staleTimer = env.lastTimerId();
    assert.ok(env.timers.has(staleTimer), "pending request owns a timer");

    const nextSession = sdk.newSession();
    const newSessionRequest = env.posted.at(-1).data;
    assert.equal(newSessionRequest.type, "ba:newSession");
    const newSessionTimer = env.lastTimerId();
    assert.notEqual(newSessionTimer, staleTimer);

    assertCancelled(await settlement(stale));
    assert.ok(env.cleared.includes(staleTimer), "stale request timer is cleared");
    assert.equal(env.timers.has(staleTimer), false, "stale timer is gone from the pending map");
    assert.ok(env.timers.has(newSessionTimer), "the newSession request itself stays pending");

    sdkSend(
        env,
        sdkEnvelope(
            "ba:session",
            NEW_SESSION,
            { sessionId: NEW_SESSION, seed: "new-seed" },
            newSessionRequest.requestId,
        ),
    );
    const context = await nextSession;
    assert.equal(context.sessionId, NEW_SESSION);
    assert.ok(env.cleared.includes(newSessionTimer), "newSession timer is cleared on response");
    assert.equal(env.timers.size, 0);

    // A late response for the cancelled request is ignored, not re-correlated.
    sdkSend(
        env,
        sdkEnvelope("ba:leaderboard:data", SESSION, { entries: [], myRank: null }, staleRequestId),
    );
    await new Promise((resolve) => setTimeout(resolve, 10));
    assert.equal(env.timers.size, 0);
});

test("exit settles pending requests immediately", async () => {
    const { env, sdk } = await startSdk();

    const pending = sdk.storage.get("slot");
    const timer = env.lastTimerId();
    assert.ok(env.timers.has(timer));

    sdk.exit();

    assertCancelled(await settlement(pending));
    assert.ok(env.cleared.includes(timer), "request timer is cleared on close");
    assert.equal(env.timers.size, 0);
    assert.equal(env.posted.at(-1).data.type, "ba:exit");
});

test("ba:session settles requests started while newSession is in flight", async () => {
    const { env, sdk } = await startSdk();

    const nextSession = sdk.newSession();
    const request = env.posted.at(-1).data;
    assert.equal(request.type, "ba:newSession");

    // A concurrent request still carries the superseded session id.
    const straggler = sdk.leaderboard.top(10);
    const stragglerTimer = env.lastTimerId();
    assert.equal(env.posted.at(-1).data.sessionId, SESSION);

    sdkSend(
        env,
        sdkEnvelope(
            "ba:session",
            NEW_SESSION,
            { sessionId: NEW_SESSION, seed: "new-seed" },
            request.requestId,
        ),
    );

    const context = await nextSession;
    assert.equal(context.sessionId, NEW_SESSION);
    assertCancelled(await settlement(straggler));
    assert.ok(env.cleared.includes(stragglerTimer));
    assert.equal(env.timers.size, 0);
});

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "../..");
const SESSION = "018f6c2e-6f5a-7c31-9a44-4f1b6e9a0c12";
const ROOM = "018f6c2e-6f5a-7c31-9a44-4f1b6e9a0c13";
const CREATE = "018f6c2e-6f5a-7c31-9a44-4f1b6e9a0c15";
const PORTAL = "https://portal.test";
const source = readFileSync(resolve(root, "sdk/1.2.0/ba-sdk.js"), "utf8");

function setup() {
    const posted = [];
    const listeners = new Map();
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
            listeners.set(type, callback);
        },
        removeEventListener(type) {
            listeners.delete(type);
        },
    };
    sandbox.window = sandbox;
    vm.createContext(sandbox);
    vm.runInContext(source, sandbox);
    return { api: sandbox.BreaktimeArcade, posted, listeners, sandbox };
}

function hostMessage(type, requestId, payload) {
    return {
        source: "ba-host",
        protocol: 1,
        type,
        requestId,
        sessionId: SESSION,
        payload,
    };
}

function context() {
    return {
        sessionId: SESSION,
        gameId: "whos_undercover",
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

function deliver(env, data) {
    const listener = env.listeners.get("message");
    assert.ok(listener);
    listener({ source: env.sandbox.parent, origin: PORTAL, data });
}

async function init(env) {
    const promise = env.api.init({ timeoutMs: 1000 });
    const hello = env.posted.find((item) => item.data.type === "ba:hello");
    assert.ok(hello);
    deliver(env, hostMessage("ba:context", hello.data.requestId, context()));
    return promise;
}

function roomRequest(env) {
    return env.posted.filter((item) => item.data.type === "ba:room").at(-1).data;
}

const snapshot = { room: {}, you: {}, players: [], game: {}, setup: {} };

test("SDK 1.2 state resolves a sanitized room snapshot", async () => {
    const env = setup();
    const sdk = await init(env);
    const promise = sdk.room.state(ROOM);
    const request = roomRequest(env);
    assert.equal(request.payload.op, "state");
    assert.equal(request.payload.roomId, ROOM);
    deliver(env, hostMessage("ba:room:data", request.requestId, snapshot));
    assert.deepEqual(await promise, snapshot);
});

test("SDK 1.2 command carries expectedVersion and a stable requestId", async () => {
    const env = setup();
    const sdk = await init(env);
    const commandId = crypto.randomUUID();
    const promise = sdk.room.command(ROOM, "vote", { targetId: "p1" }, 7, commandId);
    const request = roomRequest(env);
    assert.equal(request.payload.command, "vote");
    assert.equal(request.payload.expectedVersion, 7);
    assert.equal(request.payload.requestId, commandId);
    assert.equal(request.payload.commandPayload.targetId, "p1");
    deliver(env, hostMessage("ba:room:data", request.requestId, snapshot));
    await promise;
});

test("SDK 1.2 rejects invalid room ids and creates with camelCase options", async () => {
    const env = setup();
    const sdk = await init(env);
    await assert.rejects(() => sdk.room.state("bad"), /BA_SDK_INVALID_ROOM/);
    const promise = sdk.room.create({
        gameId: "whos_undercover",
        requestId: CREATE,
        maxPlayers: 8,
        undercoverCount: 2,
        mrWhite: true,
    });
    const request = roomRequest(env);
    assert.equal(request.payload.op, "create");
    assert.equal(request.payload.requestId, CREATE);
    assert.equal(request.payload.maxPlayers, 8);
    assert.equal(request.payload.undercoverCount, 2);
    assert.equal(request.payload.mrWhite, true);
    deliver(env, hostMessage("ba:room:data", request.requestId, snapshot));
    await promise;
});

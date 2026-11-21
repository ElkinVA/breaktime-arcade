/* BA-SDK 1.1.0 — official platform SDK.
 *
 * This file is replaced by the platform at publish time. Game code must use
 * only the public API below; direct postMessage to the portal is forbidden.
 * Implementation follows docs/contracts/BA-SDK-1.1_v1.1.0.md (submitted,
 * not yet owner-approved) and schemas/messages/*.json.
 */
(function (global) {
    "use strict";

    const PROTOCOL = 1;
    const SDK_VERSION = "1.1.0";
    const DEFAULT_INIT_TIMEOUT = 5000;
    const DEFAULT_REQUEST_TIMEOUT = 5000;
    const SUBMIT_TIMEOUT = 10000;
    const MAX_MESSAGES_PER_MINUTE = 60;
    const SEEN_LIMIT = 512;
    const HOST_TYPES = new Set([
        "ba:context",
        "ba:result",
        "ba:leaderboard:data",
        "ba:storage:data",
        "ba:session",
        "ba:pause",
        "ba:resume",
        "ba:error",
    ]);
    const SDK_TYPES = new Set([
        "ba:hello",
        "ba:submit",
        "ba:leaderboard",
        "ba:storage",
        "ba:newSession",
        "ba:exit",
        "ba:error",
    ]);
    const GUEST_CODE = "E_GUEST_FORBIDDEN";

    function isUuid(value) {
        return (
            typeof value === "string" &&
            /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(
                value,
            )
        );
    }

    function newRequestId() {
        if (global.crypto && typeof global.crypto.randomUUID === "function") {
            return global.crypto.randomUUID();
        }
        throw new Error("BA_SDK_NO_CRYPTO");
    }

    function pinnedPortalOrigin() {
        if (typeof global.BA_PORTAL_ORIGIN !== "string" || !global.BA_PORTAL_ORIGIN) {
            return null;
        }
        try {
            return new URL(global.BA_PORTAL_ORIGIN).origin;
        } catch {
            return null;
        }
    }

    function parseFragment() {
        if (!global.location || typeof global.location.hash !== "string") {
            return null;
        }
        const params = new URLSearchParams(global.location.hash.replace(/^#/, ""));
        const portal = params.get("p");
        const sessionId = params.get("s");
        if (!portal || !sessionId || !isUuid(sessionId)) {
            return null;
        }
        let origin;
        try {
            const parsed = new URL(portal);
            if (parsed.protocol !== "https:" || parsed.pathname !== "/" ||
                parsed.search || parsed.hash) {
                return null;
            }
            origin = parsed.origin;
        } catch {
            return null;
        }
        const pinned = pinnedPortalOrigin();
        if (pinned !== null && origin !== pinned) {
            return null;
        }
        return { parentOrigin: origin, sessionId };
    }

    function isEnvelope(value) {
        return (
            value !== null &&
            typeof value === "object" &&
            typeof value.source === "string" &&
            value.protocol === PROTOCOL &&
            typeof value.type === "string" &&
            isUuid(value.requestId) &&
            isUuid(value.sessionId) &&
            value.payload !== null &&
            typeof value.payload === "object"
        );
    }

    function isObject(value) {
        return value !== null && typeof value === "object" && !Array.isArray(value);
    }

    function validHostPayload(type, payload) {
        if (!isObject(payload)) {
            return false;
        }
        if (type === "ba:context") {
            return (
                isUuid(payload.sessionId) &&
                typeof payload.gameId === "string" &&
                typeof payload.gameVersion === "string" &&
                typeof payload.mode === "string" &&
                (payload.nickname === null || typeof payload.nickname === "string") &&
                typeof payload.language === "string" &&
                typeof payload.fallbackLanguage === "string" &&
                isObject(payload.strings) &&
                isObject(payload.score) &&
                isObject(payload.limits) &&
                typeof payload.trustLevel === "string" &&
                typeof payload.seed === "string"
            );
        }
        if (type === "ba:result") {
            return (
                typeof payload.status === "string" &&
                (payload.rank === null || Number.isInteger(payload.rank)) &&
                typeof payload.isPersonalBest === "boolean" &&
                typeof payload.isRecord === "boolean" &&
                typeof payload.trustLevel === "string"
            );
        }
        if (type === "ba:leaderboard:data") {
            return (
                Array.isArray(payload.entries) &&
                (payload.myRank === null || Number.isInteger(payload.myRank)) &&
                payload.entries.every(
                    (entry) =>
                        isObject(entry) &&
                        Number.isInteger(entry.rank) &&
                        (entry.nickname === null || typeof entry.nickname === "string") &&
                        typeof entry.value === "number",
                )
            );
        }
        if (type === "ba:storage:data") {
            return Object.prototype.hasOwnProperty.call(payload, "value");
        }
        if (type === "ba:session") {
            return (
                isUuid(payload.sessionId) &&
                typeof payload.seed === "string" &&
                (payload.context === undefined || isObject(payload.context))
            );
        }
        if (type === "ba:error") {
            return typeof payload.code === "string" && payload.code.length > 0;
        }
        return type === "ba:pause" || type === "ba:resume";
    }

    class BreaktimeArcadeSDK {
        constructor(fragment) {
            this.parentOrigin = fragment.parentOrigin;
            this.sessionId = fragment.sessionId;
            this.session = null;
            this.context = null;
            this.contextPromise = null;
            this.resolveContext = null;
            this.rejectContext = null;
            this.pending = new Map();
            this.seen = new Set();
            this.seenOrder = [];
            this.listeners = new Map();
            this.messageTimes = [];
            this.state = "init";
            this.onMessage = this.onMessage.bind(this);
            this.onVisibility = this.onVisibility.bind(this);
        }

        async init(options) {
            const timeoutMs = Number(options?.timeoutMs) || DEFAULT_INIT_TIMEOUT;
            if (global.parent === global) {
                throw new Error("BA_SDK_NOT_IFRAME");
            }
            global.addEventListener("message", this.onMessage);
            global.document?.addEventListener("visibilitychange", this.onVisibility);
            this.contextPromise = new Promise((resolve, reject) => {
                this.resolveContext = resolve;
                this.rejectContext = reject;
            });
            const timer = global.setTimeout(() => {
                if (this.state === "init") {
                    this.rejectContext?.(new Error("BA_SDK_INIT_TIMEOUT"));
                }
            }, timeoutMs);
            this.send("ba:hello", {});
            try {
                const context = await this.contextPromise;
                global.clearTimeout(timer);
                this.context = context;
                this.state = "active";
                return this;
            } catch (error) {
                global.clearTimeout(timer);
                this.state = "failed";
                throw error;
            }
        }

        ready() {
            if (this.state === "init" || this.state === "active") {
                this.send("ba:hello", {});
            }
        }

        t(key, params) {
            const strings = this.context?.strings;
            let text = strings && typeof strings === "object" ? strings[key] : undefined;
            if (typeof text !== "string" || text.length === 0) {
                text = key;
            }
            if (params && typeof params === "object") {
                for (const [name, value] of Object.entries(params)) {
                    text = text.split(`{${name}}`).join(String(value));
                }
            }
            return text;
        }

        on(event, callback) {
            if (typeof event !== "string" || typeof callback !== "function") {
                throw new Error("BA_SDK_INVALID_LISTENER");
            }
            const bucket = this.listeners.get(event) ?? [];
            bucket.push(callback);
            this.listeners.set(event, bucket);
            return () => {
                const current = this.listeners.get(event) ?? [];
                this.listeners.set(event, current.filter((item) => item !== callback));
            };
        }

        emit(event, payload) {
            for (const callback of this.listeners.get(event) ?? []) {
                try {
                    callback(payload);
                } catch {
                    /* game callback errors must not break the protocol */
                }
            }
        }

        async submitResult(data) {
            if (!data || typeof data.value !== "number" ||
                !Number.isInteger(data.durationMs) || data.durationMs < 0 ||
                typeof data.seed !== "string" ||
                data.eventLog === null || typeof data.eventLog !== "object") {
                throw new Error("BA_SDK_INVALID_RESULT");
            }
            try {
                const payload = await this.request(
                    "ba:submit",
                    {
                        value: data.value,
                        durationMs: data.durationMs,
                        eventLog: data.eventLog,
                        seed: data.seed,
                        ...(data.clientMeta ? { clientMeta: data.clientMeta } : {}),
                    },
                    SUBMIT_TIMEOUT,
                );
                this.state = "finished";
                return payload;
            } catch (error) {
                if (error?.code === GUEST_CODE) {
                    this.state = "finished";
                    return {
                        status: "guest",
                        code: GUEST_CODE,
                        rank: null,
                        isPersonalBest: false,
                        isRecord: false,
                        trustLevel: "client_reported",
                    };
                }
                throw error;
            }
        }

        leaderboard = {
            top: async (limit = 10) => {
                if (limit !== 10 && limit !== 100) {
                    throw new Error("BA_SDK_INVALID_LIMIT");
                }
                return this.request("ba:leaderboard", { limit }, DEFAULT_REQUEST_TIMEOUT);
            },
            myBest: async () => {
                const payload = await this.request(
                    "ba:leaderboard",
                    { limit: 10, bestOnly: true },
                    DEFAULT_REQUEST_TIMEOUT,
                );
                return payload?.value === null || payload?.value === undefined
                    ? null
                    : { value: payload.value, achievedAt: payload.achievedAt };
            },
        };

        storage = {
            get: async (key) => {
                const payload = await this.request(
                    "ba:storage",
                    { op: "get", key },
                    DEFAULT_REQUEST_TIMEOUT,
                );
                return payload?.value ?? null;
            },
            set: async (key, value) => {
                return this.request(
                    "ba:storage",
                    { op: "set", key, value },
                    DEFAULT_REQUEST_TIMEOUT,
                );
            },
            remove: async (key) => {
                return this.request(
                    "ba:storage",
                    { op: "remove", key },
                    DEFAULT_REQUEST_TIMEOUT,
                );
            },
        };

        async newSession() {
            const payload = await this.request("ba:newSession", {}, DEFAULT_REQUEST_TIMEOUT);
            if (!isUuid(payload?.sessionId) || typeof payload?.seed !== "string") {
                throw new Error("BA_SDK_INVALID_SESSION");
            }
            this.sessionId = payload.sessionId;
            this.session = payload;
            this.seen.clear();
            this.seenOrder = [];
            this.context = payload.context && typeof payload.context === "object"
                ? payload.context
                : { ...(this.context ?? {}), ...payload };
            this.state = "active";
            this.emit("session", this.context);
            return this.context;
        }

        exit() {
            if (this.state === "active" || this.state === "init" || this.state === "finished") {
                this.send("ba:exit", {});
            }
            this.state = "exited";
        }

        fail(code, message) {
            this.send("ba:error", {
                code: typeof code === "string" && code ? code : "E_INTERNAL",
                message: typeof message === "string" ? message : "",
            });
            this.state = "failed";
        }

        send(type, payload) {
            if (!SDK_TYPES.has(type)) {
                throw new Error("BA_SDK_INVALID_TYPE");
            }
            this.checkRate();
            global.parent.postMessage(
                {
                    source: "ba-sdk",
                    protocol: PROTOCOL,
                    type,
                    requestId: newRequestId(),
                    sessionId: this.sessionId,
                    payload,
                },
                this.parentOrigin,
            );
        }

        request(type, payload, timeoutMs) {
            this.checkRate();
            const requestId = newRequestId();
            return new Promise((resolve, reject) => {
                const timer = global.setTimeout(() => {
                    this.pending.delete(requestId);
                    const error = new Error("BA_SDK_TIMEOUT");
                    error.code = "E_TIMEOUT";
                    reject(error);
                }, timeoutMs);
                this.pending.set(requestId, { resolve, reject, timer });
                global.parent.postMessage(
                    {
                        source: "ba-sdk",
                        protocol: PROTOCOL,
                        type,
                        requestId,
                        sessionId: this.sessionId,
                        payload,
                    },
                    this.parentOrigin,
                );
            });
        }

        checkRate() {
            const now = Date.now();
            this.messageTimes = this.messageTimes.filter((time) => now - time < 60000);
            if (this.messageTimes.length >= MAX_MESSAGES_PER_MINUTE) {
                throw new Error("BA_SDK_RATE_LIMIT");
            }
            this.messageTimes.push(now);
        }

        onMessage(event) {
            if (event.source !== global.parent) {
                return;
            }
            if (event.origin !== this.parentOrigin) {
                return;
            }
            const data = event.data;
            if (!isEnvelope(data) || data.source !== "ba-host" || !HOST_TYPES.has(data.type)) {
                return;
            }
            if (data.type !== "ba:session" && data.sessionId !== this.sessionId) {
                return;
            }
            if (this.seen.has(data.requestId)) {
                return;
            }
            this.seen.add(data.requestId);
            this.seenOrder.push(data.requestId);
            if (this.seenOrder.length > SEEN_LIMIT) {
                this.seen.delete(this.seenOrder.shift());
            }
            if (!validHostPayload(data.type, data.payload)) {
                return;
            }

            if (data.type === "ba:context") {
                this.context = data.payload;
                this.state = "active";
                this.resolveContext?.(data.payload);
                this.resolveContext = null;
                this.rejectContext = null;
                return;
            }
            if (data.type === "ba:pause" || data.type === "ba:resume") {
                this.emit(data.type.slice(3), data.payload);
                return;
            }
            if (data.type === "ba:error") {
                const pending = this.pending.get(data.requestId);
                if (pending) {
                    global.clearTimeout(pending.timer);
                    this.pending.delete(data.requestId);
                    const error = new Error(data.payload.message || "BA_SDK_ERROR");
                    error.code = data.payload.code;
                    pending.reject(error);
                }
                return;
            }
            const pending = this.pending.get(data.requestId);
            if (!pending) {
                return;
            }
            global.clearTimeout(pending.timer);
            this.pending.delete(data.requestId);
            if (data.type === "ba:session") {
                if (isUuid(data.payload.sessionId)) {
                    this.sessionId = data.payload.sessionId;
                    this.session = data.payload;
                }
                pending.resolve(data.payload);
                return;
            }
            pending.resolve(data.payload);
        }

        onVisibility() {
            this.emit("visibility", {
                visible: global.document?.visibilityState === "visible",
            });
        }
    }

    async function init(options) {
        const fragment = parseFragment();
        if (!fragment) {
            throw new Error("BA_SDK_BAD_FRAGMENT");
        }
        const sdk = new BreaktimeArcadeSDK(fragment);
        await sdk.init(options);
        return sdk;
    }

    global.BreaktimeArcade = Object.freeze({
        version: SDK_VERSION,
        protocol: PROTOCOL,
        init,
    });
})(typeof window !== "undefined" ? window : globalThis);

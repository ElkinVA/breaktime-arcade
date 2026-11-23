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
    const MAX_MESSAGE_BYTES = 64 * 1024;
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
        let value = global.BA_PORTAL_ORIGIN;
        if ((typeof value !== "string" || !value) && global.document?.querySelector) {
            value = global.document
                .querySelector('meta[name="ba-portal-origin"]')
                ?.getAttribute("content");
        }
        if (typeof value !== "string" || !value) {
            return null;
        }
        try {
            return new URL(value).origin;
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

    /* Explicit per-message schemas for the host -> game direction. They mirror
     * schemas/messages/*.json; violations produce a structured
     * {code: "E_MESSAGE_INVALID", field, reason} object.
     */
    const MAX_TYPE_LENGTH = 64;
    const MAX_GAME_ID_LENGTH = 40;
    const MAX_GAME_VERSION_LENGTH = 32;
    const MAX_LANGUAGE_LENGTH = 35;
    const MAX_NICKNAME_LENGTH = 20;
    const MAX_TRUST_LEVEL_LENGTH = 32;
    const MAX_SEED_LENGTH = 128;
    const MAX_ERROR_CODE_LENGTH = 128;
    const MAX_LEADERBOARD_ENTRIES = 100;
    const MAX_STATUS_LENGTH = 32;

    function invalid(field, reason) {
        return Object.freeze({ code: "E_MESSAGE_INVALID", field, reason });
    }

    function tooLarge(field) {
        return Object.freeze({ code: "E_PAYLOAD_TOO_LARGE", field, reason: "payload too large" });
    }

    function isObject(value) {
        return value !== null && typeof value === "object" && !Array.isArray(value);
    }

    function matchesType(value, type) {
        if (Array.isArray(type)) {
            return type.some((item) => matchesType(value, item));
        }
        switch (type) {
            case "object":
                return isObject(value);
            case "array":
                return Array.isArray(value);
            case "string":
                return typeof value === "string";
            case "integer":
                return typeof value === "number" && Number.isInteger(value);
            case "number":
                return typeof value === "number" && Number.isFinite(value);
            case "boolean":
                return typeof value === "boolean";
            case "null":
                return value === null;
            default:
                return false;
        }
    }

    function joinPath(path, field) {
        return path ? `${path}.${field}` : field;
    }

    /* JSON-Schema-subset validator shared by every message schema below.
     * Supported keywords: type (including nullable type arrays), const, enum,
     * required, properties, additionalProperties, minLength, maxLength, format
     * ("uuid"), minimum, maximum, items, maxItems.
     */
    function validateSchema(value, schema, path = "") {
        if (!schema) {
            return null;
        }
        if (schema.type && !matchesType(value, schema.type)) {
            return invalid(path, `expected ${[].concat(schema.type).join("|")}`);
        }
        if (Object.prototype.hasOwnProperty.call(schema, "const") && value !== schema.const) {
            return invalid(path, "unexpected constant");
        }
        if (schema.enum && !schema.enum.includes(value)) {
            return invalid(path, "value is not in enum");
        }
        if (typeof value === "string") {
            if (schema.minLength !== undefined && value.length < schema.minLength) {
                return invalid(path, `shorter than ${schema.minLength}`);
            }
            if (schema.maxLength !== undefined && value.length > schema.maxLength) {
                return invalid(path, `longer than ${schema.maxLength}`);
            }
            if (schema.format === "uuid" && !isUuid(value)) {
                return invalid(path, "expected uuid");
            }
        }
        if (typeof value === "number") {
            if (schema.minimum !== undefined && value < schema.minimum) {
                return invalid(path, `less than ${schema.minimum}`);
            }
            if (schema.maximum !== undefined && value > schema.maximum) {
                return invalid(path, `greater than ${schema.maximum}`);
            }
        }
        if (Array.isArray(value)) {
            if (schema.maxItems !== undefined && value.length > schema.maxItems) {
                return invalid(path, `more than ${schema.maxItems} items`);
            }
            if (schema.items) {
                for (let index = 0; index < value.length; index += 1) {
                    const error = validateSchema(value[index], schema.items, `${path}[${index}]`);
                    if (error) {
                        return error;
                    }
                }
            }
        }
        if (isObject(value)) {
            if (schema.required) {
                for (const field of schema.required) {
                    if (!Object.prototype.hasOwnProperty.call(value, field)) {
                        return invalid(joinPath(path, field), "required field missing");
                    }
                }
            }
            const properties = schema.properties ?? {};
            if (schema.properties) {
                for (const [field, propertySchema] of Object.entries(schema.properties)) {
                    if (Object.prototype.hasOwnProperty.call(value, field)) {
                        const error = validateSchema(
                            value[field],
                            propertySchema,
                            joinPath(path, field),
                        );
                        if (error) {
                            return error;
                        }
                    }
                }
            }
            if (schema.additionalProperties === false) {
                for (const field of Object.keys(value)) {
                    if (!Object.prototype.hasOwnProperty.call(properties, field)) {
                        return invalid(joinPath(path, field), "unknown field");
                    }
                }
            }
        }
        return null;
    }

    const UUID_SCHEMA = { type: "string", format: "uuid" };

    const ENVELOPE_SCHEMA = {
        type: "object",
        additionalProperties: false,
        required: ["source", "protocol", "type", "requestId", "sessionId", "payload"],
        properties: {
            source: { type: "string", enum: ["ba-sdk", "ba-host"] },
            protocol: { const: PROTOCOL },
            type: { type: "string", minLength: 1, maxLength: MAX_TYPE_LENGTH },
            requestId: UUID_SCHEMA,
            sessionId: UUID_SCHEMA,
            payload: { type: "object" },
        },
    };

    const HOST_MESSAGE_SCHEMAS = Object.freeze({
        "ba:context": Object.freeze({
            type: "object",
            additionalProperties: true,
            required: [
                "sessionId",
                "gameId",
                "gameVersion",
                "mode",
                "nickname",
                "language",
                "fallbackLanguage",
                "strings",
                "score",
                "limits",
                "trustLevel",
                "seed",
            ],
            properties: {
                sessionId: UUID_SCHEMA,
                gameId: { type: "string", minLength: 1, maxLength: MAX_GAME_ID_LENGTH },
                gameVersion: {
                    type: "string",
                    minLength: 1,
                    maxLength: MAX_GAME_VERSION_LENGTH,
                },
                mode: { type: "string", enum: ["guest", "user", "autotest", "preview"] },
                nickname: { type: ["string", "null"], maxLength: MAX_NICKNAME_LENGTH },
                language: { type: "string", minLength: 2, maxLength: MAX_LANGUAGE_LENGTH },
                fallbackLanguage: {
                    type: "string",
                    minLength: 2,
                    maxLength: MAX_LANGUAGE_LENGTH,
                },
                strings: { type: "object" },
                score: { type: "object" },
                limits: { type: "object" },
                trustLevel: {
                    type: "string",
                    minLength: 1,
                    maxLength: MAX_TRUST_LEVEL_LENGTH,
                },
                seed: { type: "string", minLength: 1, maxLength: MAX_SEED_LENGTH },
            },
        }),
        "ba:result": Object.freeze({
            type: "object",
            additionalProperties: true,
            required: ["status", "rank", "isPersonalBest", "isRecord", "trustLevel"],
            properties: {
                status: { type: "string", minLength: 1, maxLength: MAX_STATUS_LENGTH },
                rank: { type: ["integer", "null"] },
                isPersonalBest: { type: "boolean" },
                isRecord: { type: "boolean" },
                trustLevel: {
                    type: "string",
                    minLength: 1,
                    maxLength: MAX_TRUST_LEVEL_LENGTH,
                },
                code: { type: ["string", "null"], maxLength: MAX_ERROR_CODE_LENGTH },
            },
        }),
        "ba:leaderboard:data": Object.freeze({
            type: "object",
            additionalProperties: true,
            required: ["entries", "myRank"],
            properties: {
                entries: {
                    type: "array",
                    maxItems: MAX_LEADERBOARD_ENTRIES,
                    items: {
                        type: "object",
                        additionalProperties: true,
                        required: ["rank", "nickname", "value"],
                        properties: {
                            rank: { type: "integer", minimum: 1 },
                            nickname: {
                                type: ["string", "null"],
                                maxLength: MAX_NICKNAME_LENGTH,
                            },
                            value: { type: "number" },
                        },
                    },
                },
                myRank: { type: ["integer", "null"] },
            },
        }),
        "ba:storage:data": Object.freeze({
            type: "object",
            additionalProperties: true,
            required: ["value"],
            properties: {
                value: {},
                revision: { type: ["integer", "string", "null"] },
            },
        }),
        "ba:session": Object.freeze({
            type: "object",
            additionalProperties: true,
            required: ["sessionId", "seed"],
            properties: {
                sessionId: UUID_SCHEMA,
                seed: { type: "string", minLength: 1, maxLength: MAX_SEED_LENGTH },
                context: { type: "object" },
            },
        }),
        "ba:pause": Object.freeze({ type: "object", additionalProperties: false }),
        "ba:resume": Object.freeze({ type: "object", additionalProperties: false }),
        "ba:error": Object.freeze({
            type: "object",
            additionalProperties: true,
            required: ["code"],
            properties: {
                code: { type: "string", minLength: 1, maxLength: MAX_ERROR_CODE_LENGTH },
                message: { type: "string" },
            },
        }),
    });

    function payloadBytes(payload) {
        try {
            return new TextEncoder().encode(JSON.stringify(payload)).length;
        } catch {
            return Number.POSITIVE_INFINITY;
        }
    }

    function validateHostMessage(value) {
        const envelopeError = validateSchema(value, ENVELOPE_SCHEMA);
        if (envelopeError) {
            return envelopeError;
        }
        if (value.source !== "ba-host") {
            return invalid("source", "expected source ba-host");
        }
        if (!Object.prototype.hasOwnProperty.call(HOST_MESSAGE_SCHEMAS, value.type)) {
            return invalid("type", "unsupported message type");
        }
        if (payloadBytes(value.payload) > MAX_MESSAGE_BYTES) {
            return tooLarge("payload");
        }
        return validateSchema(value.payload, HOST_MESSAGE_SCHEMAS[value.type], "payload");
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
                const entry = payload?.entries?.[0];
                return entry ? { value: entry.value, achievedAt: entry.achievedAt ?? null } : null;
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

        rejectInvalid(data, error) {
            const failure = new Error(error.reason || "Invalid message");
            failure.code = error.code;
            if (error.field) {
                failure.field = error.field;
            }
            const requestId = isUuid(data?.requestId) ? data.requestId : null;
            if (requestId) {
                const pending = this.pending.get(requestId);
                if (pending) {
                    global.clearTimeout(pending.timer);
                    this.pending.delete(requestId);
                    pending.reject(failure);
                    return;
                }
            }
            if (this.state === "init") {
                this.rejectContext?.(failure);
                this.rejectContext = null;
                this.resolveContext = null;
                this.state = "failed";
            }
        }

        onMessage(event) {
            if (event.source !== global.parent) {
                return;
            }
            if (event.origin !== this.parentOrigin) {
                return;
            }
            const data = event.data;
            const schemaError = validateHostMessage(data);
            if (schemaError) {
                this.rejectInvalid(data, schemaError);
                return;
            }
            if (data.type !== "ba:session" && data.sessionId !== this.sessionId) {
                this.rejectInvalid(
                    data,
                    invalid("sessionId", "does not match the active session"),
                );
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

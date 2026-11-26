/* Host side of the BA postMessage protocol (BA-SDK 1.1).
 *
 * The host owns the launch ticket and calls the portal API; the iframe only
 * receives the session fragment and public context. This module performs the
 * validation order required by BA-PLAT §2.12.4 before dispatching a message.
 *
 * Message envelopes and payloads are validated against the schema registry
 * generated from schemas/messages/*.json (game -> host direction). That
 * registry is committed as host_schemas.generated.js; regenerate it with
 * `python3 scripts/generate_host_schemas.py` after editing a schema. A schema
 * violation produces a structured {code: "E_MESSAGE_INVALID", field, reason}
 * object, which the bridge relays to the trusted iframe as a ba:error message.
 */

import {
    ENVELOPE_SCHEMA,
    PROTOCOL,
    SDK_MESSAGE_SCHEMAS,
    SDK_MESSAGE_TYPES,
} from "./host_schemas.generated.js";

export { SDK_MESSAGE_SCHEMAS };

const MAX_MESSAGES_PER_MINUTE = 60;
const MAX_ROOM_MESSAGES_PER_MINUTE = 120;
const SEEN_LIMIT = 512;
const MAX_MESSAGE_BYTES = 64 * 1024;
const MAX_SUBMIT_BYTES = 2 * 1024 * 1024 + 64 * 1024;
const SDK_TYPES = new Set(SDK_MESSAGE_TYPES);
const ACTIVE_TYPES = new Set([...SDK_TYPES]);
const FINISHED_TYPES = new Set([
    "ba:leaderboard",
    "ba:storage",
    "ba:newSession",
    "ba:exit",
    "ba:error",
]);

export function isUuid(value) {
    return (
        typeof value === "string" &&
        /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(
            value,
        )
    );
}

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

/* JSON-Schema-subset validator shared by the generated schema registry.
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

function payloadBytes(payload) {
    try {
        return new TextEncoder().encode(JSON.stringify(payload)).length;
    } catch {
        return Number.POSITIVE_INFINITY;
    }
}

export function validateEnvelope(value, expectedSource = "ba-sdk") {
    const error = validateSchema(value, ENVELOPE_SCHEMA);
    if (error) {
        return error;
    }
    if (expectedSource && value.source !== expectedSource) {
        return invalid("source", `expected source ${expectedSource}`);
    }
    if (!Object.prototype.hasOwnProperty.call(SDK_MESSAGE_SCHEMAS, value.type)) {
        return invalid("type", "unsupported message type");
    }
    return null;
}

export function validatePayload(type, payload) {
    if (!Object.prototype.hasOwnProperty.call(SDK_MESSAGE_SCHEMAS, type)) {
        return invalid("type", "unsupported message type");
    }
    if (payloadBytes(payload) > (type === "ba:submit" ? MAX_SUBMIT_BYTES : MAX_MESSAGE_BYTES)) {
        return tooLarge("payload");
    }
    return validateSchema(payload, SDK_MESSAGE_SCHEMAS[type], "payload");
}

export function validateMessage(value, expectedSource = "ba-sdk") {
    const envelopeError = validateEnvelope(value, expectedSource);
    if (envelopeError) {
        return envelopeError;
    }
    return validatePayload(value.type, value.payload);
}

export class HostBridge {
    constructor({ iframe, iframeOrigin, sessionId, onMessage }) {
        if (!iframe || !iframeOrigin || !isUuid(sessionId)) {
            throw new Error("BA_HOST_INVALID_CONFIG");
        }
        this.iframe = iframe;
        this.iframeOrigin = iframeOrigin;
        this.sessionId = sessionId;
        this.onMessage = onMessage;
        this.state = "init";
        this.seen = new Set();
        this.seenOrder = [];
        this.messageTimes = [];
        this.roomMessageTimes = [];
        this.onWindowMessage = this.onWindowMessage.bind(this);
        window.addEventListener("message", this.onWindowMessage);
    }

    destroy() {
        window.removeEventListener("message", this.onWindowMessage);
    }

    setSession(sessionId) {
        if (!isUuid(sessionId)) {
            throw new Error("BA_HOST_INVALID_SESSION");
        }
        this.sessionId = sessionId;
        this.seen.clear();
        this.seenOrder = [];
    }

    send(type, requestId, payload = {}) {
        this.iframe.contentWindow?.postMessage(
            {
                source: "ba-host",
                protocol: PROTOCOL,
                type,
                requestId: requestId ?? crypto.randomUUID(),
                sessionId: this.sessionId,
                payload,
            },
            this.iframeOrigin,
        );
    }

    sendContext(context, requestId) {
        this.send("ba:context", requestId, context);
    }

    sendResult(requestId, payload) {
        this.state = "finished";
        this.send("ba:result", requestId, payload);
    }

    sendLeaderboardData(requestId, payload) {
        this.send("ba:leaderboard:data", requestId, payload);
    }

    sendStorageData(requestId, payload) {
        this.send("ba:storage:data", requestId, payload);
    }

    sendRoomData(requestId, payload) {
        this.send("ba:room:data", requestId, payload);
    }

    sendSession(requestId, payload) {
        this.setSession(payload.sessionId);
        this.state = "active";
        this.send("ba:session", requestId, payload);
    }

    sendPause(payload = {}) {
        this.send("ba:pause", null, payload);
    }

    sendResume(payload = {}) {
        this.send("ba:resume", null, payload);
    }

    sendError(requestId, code, message = "", field = null) {
        const payload = { code, message };
        if (typeof field === "string" && field && field.length <= 64) {
            payload.field = field;
        }
        this.send("ba:error", requestId, payload);
    }

    checkRate(requestId, type) {
        const now = Date.now();
        if (type === "ba:room") {
            this.roomMessageTimes = this.roomMessageTimes.filter((time) => now - time < 60000);
            if (this.roomMessageTimes.length >= MAX_ROOM_MESSAGES_PER_MINUTE) {
                this.sendError(requestId, "E_RATE_LIMIT", "Too many room messages");
                return false;
            }
            this.roomMessageTimes.push(now);
            return true;
        }
        this.messageTimes = this.messageTimes.filter((time) => now - time < 60000);
        if (this.messageTimes.length >= MAX_MESSAGES_PER_MINUTE) {
            this.sendError(requestId, "E_RATE_LIMIT", "Too many messages");
            return false;
        }
        this.messageTimes.push(now);
        return true;
    }

    onWindowMessage(event) {
        if (event.source !== this.iframe.contentWindow) {
            return;
        }
        if (event.origin !== this.iframeOrigin) {
            return;
        }
        const data = event.data;
        const requestId = isUuid(data?.requestId) ? data.requestId : null;
        if (!this.checkRate(requestId, data?.type)) {
            return;
        }
        const schemaError = validateMessage(data, "ba-sdk");
        if (schemaError) {
            this.sendError(requestId, schemaError.code, schemaError.reason, schemaError.field);
            return;
        }
        if (data.sessionId !== this.sessionId) {
            this.sendError(
                data.requestId,
                "E_MESSAGE_INVALID",
                "sessionId does not match the active session",
                "sessionId",
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
        if (data.type === "ba:hello") {
            if (this.state === "init") {
                this.state = "active";
            }
        } else if (this.state === "init") {
            this.sendError(data.requestId, "E_MESSAGE_INVALID", "Hello is required");
            return;
        } else if (this.state === "finished" && !FINISHED_TYPES.has(data.type)) {
            this.sendError(data.requestId, "E_SESSION_FINISHED", "Session is finished");
            return;
        } else if (this.state === "exited") {
            this.sendError(data.requestId, "E_SESSION_FINISHED", "Session is closed");
            return;
        }
        this.onMessage?.(data.type, data.payload, data.requestId);
    }
}

export { ACTIVE_TYPES, PROTOCOL };

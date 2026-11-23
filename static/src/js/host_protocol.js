/* Host side of the BA postMessage protocol (BA-SDK 1.1).
 *
 * The host owns the launch ticket and calls the portal API; the iframe only
 * receives the session fragment and public context. This module performs the
 * validation order required by BA-PLAT §2.12.4 before dispatching a message.
 */

const PROTOCOL = 1;
const MAX_MESSAGES_PER_MINUTE = 60;
const SEEN_LIMIT = 512;
const MAX_MESSAGE_BYTES = 64 * 1024;
const MAX_SUBMIT_BYTES = 2 * 1024 * 1024 + 64 * 1024;
const SDK_TYPES = new Set([
    "ba:hello",
    "ba:submit",
    "ba:leaderboard",
    "ba:storage",
    "ba:newSession",
    "ba:exit",
    "ba:error",
]);
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

function envelope(value) {
    return (
        value !== null &&
        typeof value === "object" &&
        value.source === "ba-sdk" &&
        value.protocol === PROTOCOL &&
        typeof value.type === "string" &&
        isUuid(value.requestId) &&
        isUuid(value.sessionId) &&
        value.payload !== null &&
        typeof value.payload === "object"
    );
}

function payloadBytes(payload) {
    try {
        return new TextEncoder().encode(JSON.stringify(payload)).length;
    } catch {
        return Number.POSITIVE_INFINITY;
    }
}

export function validatePayload(type, payload) {
    if (payloadBytes(payload) > (type === "ba:submit" ? MAX_SUBMIT_BYTES : MAX_MESSAGE_BYTES)) {
        return "E_PAYLOAD_TOO_LARGE";
    }
    if (payload === null || typeof payload !== "object" || Array.isArray(payload)) {
        return "E_MESSAGE_INVALID";
    }
    switch (type) {
        case "ba:submit":
            if (!Number.isSafeInteger(payload.value) ||
                !Number.isSafeInteger(payload.durationMs) || payload.durationMs < 0 ||
                payload.eventLog === null || Array.isArray(payload.eventLog) ||
                typeof payload.eventLog !== "object" || typeof payload.seed !== "string") {
                return "E_MESSAGE_INVALID";
            }
            return null;
        case "ba:storage":
            if (!["get", "set", "remove"].includes(payload.op) ||
                typeof payload.key !== "string" ||
                payload.key.length < 1 || payload.key.length > 128) {
                return "E_MESSAGE_INVALID";
            }
            return null;
        case "ba:leaderboard":
            if (payload.limit !== undefined && payload.limit !== 10 && payload.limit !== 100) {
                return "E_MESSAGE_INVALID";
            }
            if (payload.bestOnly !== undefined && typeof payload.bestOnly !== "boolean") {
                return "E_MESSAGE_INVALID";
            }
            return null;
        case "ba:hello":
        case "ba:newSession":
        case "ba:exit":
        case "ba:error":
            return null;
        default:
            return "E_MESSAGE_INVALID";
    }
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

    sendError(requestId, code, message = "") {
        this.send("ba:error", requestId, { code, message });
    }

    onWindowMessage(event) {
        if (event.source !== this.iframe.contentWindow) {
            return;
        }
        if (event.origin !== this.iframeOrigin) {
            return;
        }
        const data = event.data;
        if (!envelope(data) || !SDK_TYPES.has(data.type)) {
            return;
        }
        if (data.sessionId !== this.sessionId) {
            return;
        }
        if (this.seen.has(data.requestId)) {
            return;
        }
        const now = Date.now();
        this.messageTimes = this.messageTimes.filter((time) => now - time < 60000);
        if (this.messageTimes.length >= MAX_MESSAGES_PER_MINUTE) {
            this.sendError(data.requestId, "E_RATE_LIMIT", "Too many messages");
            return;
        }
        this.messageTimes.push(now);
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
        const error = validatePayload(data.type, data.payload);
        if (error) {
            this.sendError(data.requestId, error, "Invalid message");
            return;
        }
        this.onMessage?.(data.type, data.payload, data.requestId);
    }
}

export { ACTIVE_TYPES, PROTOCOL };

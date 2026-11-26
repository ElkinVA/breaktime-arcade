/* Pure mapping from the SDK 1.2 ba:room payload to the portal room API.
 * Kept outside player.js so the camelCase -> snake_case contract is testable.
 */

import { isUuid } from "./host_protocol.js";

const ROOM_BASE = "/api/v1/rooms";

function invalid(message) {
    const error = new Error(message);
    error.code = "E_INVALID_REQUEST";
    return error;
}

function roomPath(roomId) {
    return `${ROOM_BASE}/${encodeURIComponent(roomId)}`;
}

export function roomApiRequest(payload, envelopeRequestId) {
    const op = payload?.op;
    if (op === "create") {
        if (typeof payload.gameId !== "string" || !payload.gameId) {
            throw invalid("gameId is required");
        }
        if (payload.requestId !== undefined && !isUuid(payload.requestId)) {
            throw invalid("requestId is invalid");
        }
        return {
            method: "POST",
            path: ROOM_BASE,
            retry: false,
            body: {
                game_id: payload.gameId,
                ...(payload.requestId !== undefined ? { request_id: payload.requestId } : {}),
                ...(payload.name !== undefined ? { name: payload.name } : {}),
                ...(payload.maxPlayers !== undefined
                    ? { max_players: payload.maxPlayers }
                    : {}),
                ...(payload.undercoverCount !== undefined
                    ? { undercover_count: payload.undercoverCount }
                    : {}),
                ...(payload.mrWhite !== undefined ? { mr_white: payload.mrWhite } : {}),
                ...(payload.categoryId !== undefined
                    ? { category_id: payload.categoryId }
                    : {}),
            },
        };
    }
    if (op === "join") {
        return {
            method: "POST",
            path: `${ROOM_BASE}/join`,
            retry: false,
            body: {
                code: payload.code,
                ...(payload.name !== undefined ? { name: payload.name } : {}),
            },
        };
    }
    if (!isUuid(payload.roomId)) {
        throw invalid("roomId is required");
    }
    if (op === "state") {
        return {
            method: "GET",
            path: roomPath(payload.roomId),
            retry: true,
            body: null,
        };
    }
    if (op === "command") {
        if (
            typeof payload.command !== "string" ||
            !payload.command ||
            !Number.isInteger(payload.expectedVersion)
        ) {
            throw invalid("invalid room command");
        }
        return {
            method: "POST",
            path: `${roomPath(payload.roomId)}/commands`,
            retry: false,
            body: {
                command: payload.command,
                payload: payload.commandPayload ?? {},
                requestId: isUuid(payload.requestId) ? payload.requestId : envelopeRequestId,
                expectedVersion: payload.expectedVersion,
            },
        };
    }
    if (op === "leave") {
        return {
            method: "POST",
            path: `${roomPath(payload.roomId)}/leave`,
            retry: false,
            body: {},
        };
    }
    throw invalid("unsupported room operation");
}

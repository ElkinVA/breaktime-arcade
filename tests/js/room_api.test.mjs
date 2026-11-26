import assert from "node:assert/strict";
import test from "node:test";

const { roomApiRequest } = await import("../../static/src/js/room_api.js");

const ROOM = "018f6c2e-6f5a-7c31-9a44-4f1b6e9a0c13";
const ENVELOPE = "018f6c2e-6f5a-7c31-9a44-4f1b6e9a0c14";
const CREATE = "018f6c2e-6f5a-7c31-9a44-4f1b6e9a0c15";

test("room API maps create camelCase options to the serializer fields", () => {
    const request = roomApiRequest(
        {
            op: "create",
            gameId: "whos_undercover",
            requestId: CREATE,
            name: "Maya",
            maxPlayers: 8,
            undercoverCount: 2,
            mrWhite: true,
            categoryId: "food",
        },
        ENVELOPE,
    );
    assert.equal(request.method, "POST");
    assert.equal(request.path, "/api/v1/rooms");
    assert.equal(request.retry, false);
    assert.equal(request.body.game_id, "whos_undercover");
    assert.equal(request.body.request_id, CREATE);
    assert.equal(request.body.name, "Maya");
    assert.equal(request.body.max_players, 8);
    assert.equal(request.body.undercover_count, 2);
    assert.equal(request.body.mr_white, true);
    assert.equal(request.body.category_id, "food");
});

test("room API maps command with stable requestId and state fields", () => {
    const command = roomApiRequest(
        {
            op: "command",
            roomId: ROOM,
            command: "vote",
            commandPayload: { targetId: "p1" },
            expectedVersion: 4,
            requestId: ENVELOPE,
        },
        "018f6c2e-6f5a-7c31-9a44-4f1b6e9a0c99",
    );
    assert.equal(command.path, `/api/v1/rooms/${ROOM}/commands`);
    assert.equal(command.body.requestId, ENVELOPE);
    assert.equal(command.body.expectedVersion, 4);
    assert.equal(command.body.payload.targetId, "p1");
    assert.equal(command.retry, false);

    const fallback = roomApiRequest(
        { op: "command", roomId: ROOM, command: "advance", expectedVersion: 1 },
        ENVELOPE,
    );
    assert.equal(fallback.body.requestId, ENVELOPE);
});

test("room API maps join, state and leave", () => {
    const join = roomApiRequest({ op: "join", code: "ABC234", name: "Maya" }, ENVELOPE);
    assert.equal(join.path, "/api/v1/rooms/join");
    assert.equal(join.body.code, "ABC234");

    const state = roomApiRequest({ op: "state", roomId: ROOM }, ENVELOPE);
    assert.equal(state.method, "GET");
    assert.equal(state.path, `/api/v1/rooms/${ROOM}`);
    assert.equal(state.body, null);
    assert.equal(state.retry, true);

    const leave = roomApiRequest({ op: "leave", roomId: ROOM }, ENVELOPE);
    assert.equal(leave.path, `/api/v1/rooms/${ROOM}/leave`);
    assert.equal(leave.method, "POST");
});

test("room API rejects invalid ids and commands", () => {
    assert.throws(
        () => roomApiRequest({ op: "state", roomId: "bad" }, ENVELOPE),
        (error) => error.code === "E_INVALID_REQUEST",
    );
    assert.throws(
        () => roomApiRequest({ op: "create", gameId: "whos_undercover", requestId: "bad" }, ENVELOPE),
        (error) => error.code === "E_INVALID_REQUEST",
    );
    assert.throws(
        () => roomApiRequest({ op: "command", roomId: ROOM, command: "", expectedVersion: 1 }, ENVELOPE),
        (error) => error.code === "E_INVALID_REQUEST",
    );
    assert.throws(
        () => roomApiRequest({ op: "delete" }, ENVELOPE),
        (error) => error.code === "E_INVALID_REQUEST",
    );
});

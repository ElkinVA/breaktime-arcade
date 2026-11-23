/* GENERATED FILE - DO NOT EDIT.
 * Source of truth: schemas/messages/*.json (with $ref to schemas/eventlog.json).
 * Regenerate with: python3 scripts/generate_host_schemas.py
 */

export const PROTOCOL = 1;

export const SDK_MESSAGE_TYPES = Object.freeze([
    "ba:error",
    "ba:exit",
    "ba:hello",
    "ba:leaderboard",
    "ba:newSession",
    "ba:storage",
    "ba:submit",
]);

export const ENVELOPE_SCHEMA = Object.freeze({
    "type": "object",
    "additionalProperties": false,
    "required": [
        "source",
        "protocol",
        "type",
        "requestId",
        "sessionId",
        "payload"
    ],
    "properties": {
        "source": {
            "type": "string",
            "enum": [
                "ba-sdk",
                "ba-host"
            ]
        },
        "protocol": {
            "const": 1
        },
        "type": {
            "type": "string",
            "minLength": 1,
            "maxLength": 64
        },
        "requestId": {
            "type": "string",
            "format": "uuid"
        },
        "sessionId": {
            "type": "string",
            "format": "uuid"
        },
        "payload": {
            "type": "object"
        }
    }
});

export const SDK_MESSAGE_SCHEMAS = Object.freeze({
    "ba:error": Object.freeze({
        "type": "object",
        "additionalProperties": true,
        "properties": {
            "code": {
                "type": "string",
                "minLength": 1,
                "maxLength": 128
            },
            "message": {
                "type": "string"
            }
        },
        "required": [
            "code"
        ]
    }),
    "ba:exit": Object.freeze({
        "type": "object",
        "additionalProperties": false
    }),
    "ba:hello": Object.freeze({
        "type": "object",
        "additionalProperties": true
    }),
    "ba:leaderboard": Object.freeze({
        "type": "object",
        "additionalProperties": true,
        "properties": {
            "limit": {
                "type": "integer",
                "enum": [
                    10,
                    100
                ]
            },
            "bestOnly": {
                "type": "boolean"
            }
        },
        "required": []
    }),
    "ba:newSession": Object.freeze({
        "type": "object",
        "additionalProperties": false
    }),
    "ba:storage": Object.freeze({
        "type": "object",
        "additionalProperties": false,
        "properties": {
            "op": {
                "type": "string",
                "enum": [
                    "get",
                    "set",
                    "remove"
                ]
            },
            "key": {
                "type": "string",
                "minLength": 1,
                "maxLength": 128
            },
            "value": {}
        },
        "required": [
            "op",
            "key"
        ]
    }),
    "ba:submit": Object.freeze({
        "type": "object",
        "additionalProperties": true,
        "properties": {
            "value": {
                "type": "number"
            },
            "durationMs": {
                "type": "integer",
                "minimum": 0
            },
            "eventLog": {
                "type": "object",
                "additionalProperties": false,
                "required": [
                    "v",
                    "seed",
                    "events"
                ],
                "properties": {
                    "v": {
                        "const": 1
                    },
                    "seed": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 128
                    },
                    "events": {
                        "type": "array",
                        "maxItems": 20000,
                        "items": {
                            "type": "object",
                            "additionalProperties": false,
                            "required": [
                                "t",
                                "k",
                                "d"
                            ],
                            "properties": {
                                "t": {
                                    "type": "integer",
                                    "minimum": 0
                                },
                                "k": {
                                    "type": "string",
                                    "minLength": 1,
                                    "maxLength": 64
                                },
                                "d": {
                                    "type": "object"
                                }
                            }
                        }
                    }
                }
            },
            "seed": {
                "type": "string"
            },
            "clientMeta": {
                "type": "object"
            }
        },
        "required": [
            "value",
            "durationMs",
            "eventLog",
            "seed"
        ]
    }),
})

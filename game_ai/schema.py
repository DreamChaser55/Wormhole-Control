"""Strict JSON Schema for an agent's complete turn response."""

from .contracts import SUPPORTED_COMMANDS


NULLABLE_STRING = {"type": ["string", "null"]}
NULLABLE_INTEGER = {"type": ["integer", "null"]}
NULLABLE_NUMBER = {"type": ["number", "null"]}
NULLABLE_HEX = {
    "anyOf": [
        {"type": "array", "items": {"type": "integer"}, "minItems": 2, "maxItems": 2},
        {"type": "null"},
    ]
}
NULLABLE_POSITION = {
    "anyOf": [
        {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2},
        {"type": "null"},
    ]
}

COMMAND_PROPERTIES = {
    "type": {"type": "string", "enum": sorted(SUPPORTED_COMMANDS)},
    "unit_ids": {"type": "array", "items": {"type": "integer"}, "maxItems": 12},
    "target_id": NULLABLE_INTEGER,
    "system_name": NULLABLE_STRING,
    "hex_coord": NULLABLE_HEX,
    "position": NULLABLE_POSITION,
    "template_name": NULLABLE_STRING,
    "amount": NULLABLE_NUMBER,
    "stance": NULLABLE_STRING,
    "queue": {"type": "boolean"},
    "ability": NULLABLE_STRING,
    "minefield_type": NULLABLE_STRING,
    "target_component": NULLABLE_STRING,
}

TURN_PLAN_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "plan": {
            "type": "array",
            "items": {"type": "string", "maxLength": 500},
            "maxItems": 12,
        },
        "commands": {
            "type": "array",
            "maxItems": 40,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": COMMAND_PROPERTIES,
                "required": list(COMMAND_PROPERTIES),
            },
        },
        "memory_patch": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "strategy": {"type": ["string", "null"], "maxLength": 3000},
                "objectives": {
                    "type": ["array", "null"],
                    "items": {"type": "string", "maxLength": 500},
                    "maxItems": 12,
                },
                "commitments": {
                    "type": ["array", "null"],
                    "items": {"type": "string", "maxLength": 500},
                    "maxItems": 12,
                },
                "beliefs": {
                    "type": ["array", "null"],
                    "items": {"type": "string", "maxLength": 500},
                    "maxItems": 16,
                },
                "lessons": {
                    "type": ["array", "null"],
                    "items": {"type": "string", "maxLength": 500},
                    "maxItems": 16,
                },
            },
            "required": ["strategy", "objectives", "commitments", "beliefs", "lessons"],
        },
        "end_turn": {"type": "boolean", "const": True},
    },
    "required": ["plan", "commands", "memory_patch", "end_turn"],
}


def responses_text_config() -> dict:
    return {
        "format": {
            "type": "json_schema",
            "name": "wormhole_control_turn_v1",
            "strict": True,
            "schema": TURN_PLAN_SCHEMA,
        },
        "verbosity": "low",
    }

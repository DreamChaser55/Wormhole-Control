"""Strict JSON Schema for an agent's complete turn response."""

from .command_spec import COMMAND_PROPERTIES


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
                "misc": {
                    "type": ["array", "null"],
                    "items": {"type": "string", "maxLength": 500},
                    "maxItems": 16,
                },
            },
            "required": [
                "strategy",
                "objectives",
                "commitments",
                "beliefs",
                "lessons",
                "misc",
            ],
        },
        "end_turn": {"type": "boolean", "const": True},
    },
    "required": ["plan", "commands", "memory_patch", "end_turn"],
}


def responses_text_config() -> dict:
    return {
        "format": {
            "type": "json_schema",
            "name": "wormhole_control_turn_v2",
            "strict": True,
            "schema": TURN_PLAN_SCHEMA,
        },
        "verbosity": "low",
    }

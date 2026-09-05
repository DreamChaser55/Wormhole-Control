"""Small, explicit JSON value codec shared by component and ability schemas."""
from enum import Enum
import math
from geometry import Vector, Position


def encode(value):
    if isinstance(value, Enum):
        return {"$enum": type(value).__name__, "name": value.name}
    if isinstance(value, Vector):
        return {"$position": [value.x, value.y]}
    if isinstance(value, tuple):
        return {"$tuple": [encode(v) for v in value]}
    if isinstance(value, set):
        return {"$set": [encode(v) for v in sorted(value)]}
    if isinstance(value, list):
        return [encode(v) for v in value]
    if isinstance(value, dict):
        if not all(isinstance(k, str) for k in value):
            raise ValueError("State dictionaries must have string keys")
        return {k: encode(v) for k, v in value.items()}
    if value is None or type(value) in (str, bool, int, float):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("Non-finite state number")
        return value
    raise ValueError(f"Unsupported state value: {type(value).__name__}")


def decode(value):
    if isinstance(value, list):
        return [decode(v) for v in value]
    if not isinstance(value, dict):
        return value
    if "$position" in value:
        fields(value, ("$position",), "position")
        xy = value["$position"]
        if not isinstance(xy, list) or len(xy) != 2:
            raise ValueError("Invalid position")
        for v in xy:
            number(v, "position")
        return Position(*xy)
    if "$enum" in value:
        fields(value, ("$enum", "name"), "enum")
        from unit_components import enums
        import constants
        cls = getattr(enums, value["$enum"], None) or getattr(constants, value["$enum"], None)
        if not isinstance(cls, type) or not issubclass(cls, Enum):
            raise ValueError(f"Unknown enum {value['$enum']}")
        return cls[value["name"]]
    if "$tuple" in value:
        fields(value, ("$tuple",), "tuple")
        if not isinstance(value["$tuple"], list):
            raise ValueError("Invalid tuple")
        return tuple(decode(v) for v in value["$tuple"])
    if "$set" in value:
        fields(value, ("$set",), "set")
        if not isinstance(value["$set"], list):
            raise ValueError("Invalid set")
        return set(decode(v) for v in value["$set"])
    if any(k.startswith("$") for k in value):
        raise ValueError("Unknown state tag")
    return {k: decode(v) for k, v in value.items()}


def number(value, path, minimum=None, integer=False):
    if type(value) not in ((int,) if integer else (int, float)) or not math.isfinite(value):
        raise ValueError(f"{path}: expected a finite {'integer' if integer else 'number'}")
    if minimum is not None and value < minimum:
        raise ValueError(f"{path}: must be >= {minimum}")
    return value


def fields(data, required, path):
    required = tuple(required)
    if not isinstance(data, dict) or set(data) != set(required):
        raise ValueError(f"{path}: expected fields {sorted(required)}")

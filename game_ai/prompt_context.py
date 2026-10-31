"""Lossless planning-only catalogue references and payload-free size metrics."""
from copy import deepcopy
from collections import Counter
import json


CONTEXT_INSTRUCTIONS = (
    "Catalogs in the preceding developer message are shared definitions for this observation. "
    "construction_templates and wing_templates are indexed by name. Their current availability "
    "is in action_catalogs.*_availability. Constructor price_exceptions override the shared "
    "resource_cost by template_name; omitted shortfalls are zero. buildable_template_names "
    "still restrict each constructor's hardware and construct.template_names lists issuable builds. "
    "Preserve useful current/queued orders; compare replacement commands with those roots and "
    "update objectives/commitments to match the orders you actually issue. Lessons are merged "
    "into durable memory; other memory sections replace their prior values."
    " Each JSON message may contain shared_values. An object with only $shared names an "
    "exact JSON value in that same message's shared_values; follow references "
    "recursively. These references deduplicate data, including command options and rules; "
    "they do not change command fields, visibility, availability, or order semantics."
)


def serialized(value):
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False, sort_keys=True)


def share_repeated_values(data):
    """Factor repeated large JSON values only when their complete encoding shrinks."""
    counts, values = Counter(), {}

    def count(value):
        if isinstance(value, (dict, list, str)):
            key = serialized(value)
            if len(key) >= 64:
                counts[key] += 1
                values[key] = value
            if not isinstance(value, str):
                for child in value.values() if isinstance(value, dict) else value:
                    count(child)

    count(data)
    keys = sorted((key for key, count in counts.items() if count > 1), key=lambda key: (-len(key), key))
    names = {key: f'd{index}' for index, key in enumerate(keys)}

    def encode(value, defining=None):
        if not isinstance(value, (dict, list, str)):
            return value
        key = serialized(value)
        if key in names and key != defining:
            return {'$shared': names[key]}
        if isinstance(value, str):
            return value
        return ({name: encode(child) for name, child in value.items()} if isinstance(value, dict)
                else [encode(child) for child in value])

    encoded = encode(data)
    definitions = {names[key]: encode(values[key], defining=key) for key in keys}

    def references(value):
        if isinstance(value, dict):
            if set(value) == {'$shared'}:
                yield value['$shared']
            else:
                for child in value.values():
                    yield from references(child)
        elif isinstance(value, list):
            for child in value:
                yield from references(child)

    def inline(value, removed):
        if isinstance(value, dict):
            if set(value) == {'$shared'} and value['$shared'] in removed:
                return inline(removed[value['$shared']], removed)
            return {name: inline(child, removed) for name, child in value.items()}
        if isinstance(value, list):
            return [inline(child, removed) for child in value]
        return value

    while definitions:
        reachable, pending = set(), list(references(encoded))
        while pending:
            name = pending.pop()
            if name not in reachable:
                reachable.add(name)
                pending.extend(references(definitions[name]))
        definitions = {name: value for name, value in definitions.items() if name in reachable}
        uses = Counter(references(encoded))
        for value in definitions.values():
            uses.update(references(value))
        removed = {name: value for name, value in definitions.items() if uses[name] <= 1}
        if not removed:
            break
        encoded = inline(encoded, removed)
        definitions = {name: inline(value, removed) for name, value in definitions.items() if name not in removed}
    compact = dict(encoded, shared_values=definitions) if definitions else encoded
    return compact if len(serialized(compact)) < len(serialized(data)) else data


def expand_shared_values(data):
    """Expand one planning message for offline inspection and semantic comparison."""
    definitions = data.get('shared_values', {})

    def expand(value, stack=()):
        if isinstance(value, dict):
            if set(value) == {'$shared'}:
                name = value['$shared']
                if name in stack or name not in definitions:
                    raise ValueError('Invalid shared planning reference')
                return expand(definitions[name], (*stack, name))
            return {name: expand(child, stack) for name, child in value.items()}
        return [expand(child, stack) for child in value] if isinstance(value, list) else value

    return expand({name: value for name, value in data.items() if name != 'shared_values'})


def planning_context(request, *, compact=True):
    """Return stable prefix, changing state and character counts, never mutate input.

    Only already-public observation data is moved. The socket observation and
    provider-neutral PlanningRequest retain their complete original contracts.
    """
    original = request.to_dict()
    data = deepcopy(original)
    observation = data["observation"]
    catalogs = {}
    for key in ("command_catalog", "ability_catalog"):
        if key in observation:
            catalogs[key] = observation.pop(key)
    actions = observation.get("action_catalogs", {})
    prices = {}
    for key in ("construction_templates", "wing_templates"):
        if key not in actions:
            continue
        definitions, availability = [], []
        for entry in actions.pop(key):
            dynamic = {name: entry.pop(name) for name in ("resource_shortfall", "replacement_blocker", "queued_blocker") if name in entry}
            definitions.append(entry)
            if dynamic:
                availability.append({"name": entry["name"], **dynamic})
            if key == "construction_templates":
                prices[entry["name"]] = entry.get("resource_cost")
        catalogs[key] = sorted(definitions, key=lambda entry: entry["name"])
        actions[key.removesuffix("s") + "_availability"] = availability
    for unit in observation.get("units", []):
        construct = unit.get("command_options", {}).get("construct", {})
        if "prices" not in construct:
            continue
        exceptions = []
        for quote in construct.pop("prices"):
            name = quote["template_name"]
            entry = {"template_name": name}
            if name not in prices or quote["resource_cost"] != prices[name]:
                entry["resource_cost"] = quote["resource_cost"]
            for key in ("replacement_shortfall", "queued_shortfall"):
                if any(quote.get(key, {}).values()):
                    entry[key] = quote[key]
            if len(entry) > 1:
                exceptions.append(entry)
        construct["price_exceptions"] = exceptions
    unfactored_chars = len(serialized(catalogs)) + len(serialized(data))
    if compact:
        catalogs = share_repeated_values(catalogs)
        data = share_repeated_values(data)
    stable = serialized(catalogs)
    dynamic = serialized(data)
    metrics = {
        "original_request_chars": len(serialized(original)),
        "stable_catalog_chars": len(stable),
        "dynamic_request_chars": len(dynamic),
        "shared_value_savings_chars": unfactored_chars - len(stable) - len(dynamic),
        "observation_sections_chars": {key: len(serialized(value)) for key, value in original["observation"].items()},
        "compact_sections_chars": {key: len(serialized(value)) for key, value in data['observation'].items()},
        "dynamic_shared_values_chars": len(serialized(data.get('shared_values', {}))),
    }
    messages = [{"role": "developer", "content": CONTEXT_INSTRUCTIONS + "\n" + stable},
                {"role": "user", "content": dynamic}]
    metrics["serialized_input_chars"] = len(serialized(messages))
    metrics["content_input_chars"] = sum(len(message["content"]) for message in messages)
    metrics["original_serialized_input_chars"] = len(serialized(serialized(original)))
    return messages, metrics

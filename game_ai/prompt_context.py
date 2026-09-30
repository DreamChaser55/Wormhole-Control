"""Lossless planning-only catalogue references and payload-free size metrics."""
from copy import deepcopy
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
)


def serialized(value):
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False, sort_keys=True)


def planning_context(request):
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
    stable = serialized(catalogs)
    dynamic = serialized(data)
    metrics = {
        "original_request_chars": len(serialized(original)),
        "stable_catalog_chars": len(stable),
        "dynamic_request_chars": len(dynamic),
        "observation_sections_chars": {key: len(serialized(value)) for key, value in original["observation"].items()},
        "compact_sections_chars": {key: len(serialized(value)) for key, value in observation.items()},
    }
    messages = [{"role": "developer", "content": CONTEXT_INSTRUCTIONS + "\n" + stable},
                {"role": "user", "content": dynamic}]
    metrics["serialized_input_chars"] = len(serialized(messages))
    metrics["content_input_chars"] = sum(len(message["content"]) for message in messages)
    metrics["original_serialized_input_chars"] = len(serialized(serialized(original)))
    return messages, metrics

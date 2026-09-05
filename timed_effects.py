"""Idempotent, source-owned contributions to hull-level ability status."""


def refresh(unit):
    effects = getattr(unit, "_ability_effects", {})
    unit.damage_reduction = sum(amount for kind, amount in effects.values() if kind == "reduction")
    unit.damage_amplification = sum(amount for kind, amount in effects.values() if kind == "amplification")
    unit.disabled_by_unit_ids = {source for (source, _), (kind, _) in effects.items() if kind == "disable"}
    unit.is_disabled = bool(unit.disabled_by_unit_ids)


def add(unit, source_id, ability_type, kind, amount=0):
    if not hasattr(unit, "_ability_effects"):
        unit._ability_effects = {}
    unit._ability_effects[(source_id, ability_type.value)] = (kind, amount)
    refresh(unit)


def remove(unit, source_id, ability_type):
    getattr(unit, "_ability_effects", {}).pop((source_id, ability_type.value), None)
    refresh(unit)

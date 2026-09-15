"""Read-only help content assembled from equipment and ability definitions."""

from html import escape

import constants as rules
from custom_unit_templates import (
    ADVANCED_CLOAKING_MIN_HULL, ADVANCED_HYPERDRIVE_MIN_HULL, HULL_RESTRICTIONS,
)
from tactical_balance import SPECS
from unit_components.abilities import ABILITY_DEFINITIONS
from unit_components.enums import AbilityType
from unit_components.intelligence import (
    COUNTER_INTELLIGENCE_HULL_COST, DEFAULT_INFILTRATION_RANGE,
    INTELLIGENCE_BASE_HULL_COST, INTELLIGENCE_EXTRA_AGENT_HULL_COST,
)

from .catalog import COMPONENT_DESCRIPTIONS, COMPONENT_ROWS


DYNAMIC_COST_BASIS = {
    "has_engine": "speed and hull size",
    "has_antimatter_storage": "fuel capacity",
    "has_hyperdrive": "drive type, jump range and hull size",
    "has_weapon_bays": "turret count, damage, range and cooldown",
    "has_defenses": "Armor, Shields and Point Defense values",
    "has_repair_component": "repair rate",
    "has_mining_component": "mining rate and cargo capacity",
    "has_hangar": "hangar slots",
    "has_strikecraft_bay": "wing slots",
    "has_inhibitor": "field radius",
    "has_ability_component": "number of equipped abilities",
    "has_sensors": "short-range radius and long-range hex coverage",
    "has_marines_component": "marine count",
    "has_cloaking_device": "cloak type and Advanced area radius",
    "has_intelligence_component": "agent capacity and the Counter-Intelligence upgrade",
}


def _body(description: str, facts: list[tuple[str, str]]) -> str:
    return escape(description) + "<br><br><b>Key rules</b><br>" + "<br><br>".join(
        f"<b>{escape(label)}:</b> {escape(value)}" for label, value in facts
    )


def component_description(key: str) -> tuple[str, str]:
    """Return a component title and HTML without reading or editing a design."""
    is_ci = key == "has_counter_intelligence"
    row_key = "has_intelligence_component" if is_ci else key
    row = next(row for row in COMPONENT_ROWS if row["key"] == row_key)
    title = "Counter-Intelligence" if is_ci else row["label"]
    hulls = ", ".join(hull.name.replace("_", " ").title() for hull in rules.HullSize
                      if row_key not in HULL_RESTRICTIONS.get(hull, set()))
    facts = [("Supported hulls", hulls)]
    if is_ci:
        facts.extend([
            ("Requires", "Intelligence"),
            ("Additional hull cost", f"{COUNTER_INTELLIGENCE_HULL_COST:g}"),
            ("CI Sweep", f"{rules.CI_SWEEP_CREDIT_COST:g} credits and "
             f"{rules.CI_SWEEP_ANTIMATTER_COST:g} AM; "
             f"{rules.CI_SWEEP_COOLDOWN_TURNS} turns cooldown; range {rules.CI_SWEEP_RANGE:g}"),
        ])
    elif row["is_dynamic"]:
        facts.append(("Hull cost", f"Scales with {DYNAMIC_COST_BASIS[key]}."))
    else:
        facts.append(("Hull cost", f"{row['default_cost']:g}"))

    if key == "has_antimatter_storage":
        facts.append(("Minimum capacity when equipped", "; ".join(
            f"{hull.name.replace('_', ' ').title()}: {rules.get_min_antimatter_capacity(hull):g} AM"
            for hull in rules.HullSize)))
    elif key == "has_antimatter_harvester":
        facts.append(("Harvesting", f"Within {rules.ANTIMATTER_HARVEST_RANGE:g} units of the source center; "
                      f"base yield {rules.DEFAULT_ANTIMATTER_HARVEST_RATE:g} AM/turn, modified by source."))
    elif key == "has_hyperdrive":
        facts.append(("Advanced variant", f"Requires {ADVANCED_HYPERDRIVE_MIN_HULL.name.title()} or larger."))
    elif key == "has_civilian_habitat_component":
        facts.append(("Colony support", f"Each populated colony supports max(1, floor(population / "
                      f"{rules.POPULATION_PER_HABITAT:g})) habitats of its owner."))
    elif key == "has_orbital_defense_component":
        facts.extend([
            ("Aura", f"Radius {rules.DEFAULT_ORBITAL_DEFENSE_RADIUS:g}; "
             f"+{rules.DEFAULT_ORBITAL_DEFENSE_ATTACK_BONUS:.0%} weapon damage and "
             f"+{rules.DEFAULT_ORBITAL_DEFENSE_DEFENSE_BONUS:.0%} defense mitigation."),
            ("Colony support", f"Requires an allied or owned populated colony and a free support slot. "
             f"Each colony supports max(1, floor(population / {rules.POPULATION_PER_ORBITAL_DEFENSE:g})) modules."),
        ])
    elif key == "has_trade_component":
        facts.append(("Requires", "Engines"))
    elif key == "has_inhibitor":
        facts.append(("Radius costs", f"Hull: radius / {rules.INHIBITOR_RADIUS_PER_HULL_POINT:g}. "
                      f"Active fuel: {rules.INHIBITOR_ANTIMATTER_COST_PER_50_RADIUS:g} AM per 50 radius per turn."))
    elif key == "has_sensors":
        facts.append(("Strikecraft wings", "Long-range hex coverage must be zero."))
    elif key == "has_cloaking_device":
        facts.extend([
            ("Basic", f"{rules.CLOAKING_BASIC_HULL_COST:g} hull; "
             f"{rules.CLOAKING_BASIC_ANTIMATTER_COST_PER_TURN:g} AM/turn."),
            ("Advanced", f"Requires {ADVANCED_CLOAKING_MIN_HULL.name.title()} or larger. "
             f"Hull: radius / {rules.CLOAKING_ADVANCED_RADIUS_PER_HULL_POINT:g}; "
             f"fuel: radius × {rules.CLOAKING_ADVANCED_ANTIMATTER_COST_PER_RADIUS:g} AM/turn."),
        ])
    elif key == "has_intelligence_component":
        facts.extend([
            ("Agent capacity", f"{INTELLIGENCE_BASE_HULL_COST:g} hull for the first agent, "
             f"{INTELLIGENCE_EXTRA_AGENT_HULL_COST:g} per additional agent."),
            ("Infiltration range", f"{DEFAULT_INFILTRATION_RANGE:g} units; approaches automatically."),
        ])
    return title, _body(COMPONENT_DESCRIPTIONS[key], facts)


def ability_description(name: str) -> tuple[str, str]:
    """Return registered ability prose and current base rules, not live unit stats."""
    definition = ABILITY_DEFINITIONS[AbilityType(name)]
    labels = {row["key"]: row["label"] for row in COMPONENT_ROWS}
    required = [labels[key] for key in definition.required_components]
    if name in ("tracking_lock", "flak_barrage"):
        required.append("an Anti-Strikecraft turret")
    persistent = name in ("ghost_fleet",)
    duration = ("Persistent deployment (no expiry)" if persistent else
                f"{definition.duration} turns" if definition.duration else "Instant / one-shot")
    range_text = ("Any legal position in the same sector" if name == "microjump" else
                  f"{definition.range:g} logical units" if definition.range else "Self")
    targets = {"self": "Self", "unit": "Unit", "position": "Position",
               "celestial_position": "Nebula and position inside it"}
    facts = [
        ("Requires", ", ".join(["Abilities", *required])),
        ("Activation cost", f"{definition.antimatter_cost:g} AM"),
        ("Cooldown", f"{definition.cooldown} turns"),
        ("Duration", duration),
        ("Range", range_text),
        ("Target", targets[definition.target_kind]),
    ]
    spec = SPECS.get(name)
    if spec and spec.cap:
        facts.append(("Deployment limit", f"{spec.cap} per deploying ship across the galaxy."))
    if name == "microjump":
        facts.append(("Placement", "Origin and destination must be outside inhibition fields; "
                      "the destination must respect collision and hull-specific field restrictions."))
    facts.append(("Activation", "Required equipment must be operational, the cooldown ready, "
                  "and enough antimatter available. Turns advance at the caster owner's turn start."))
    return definition.name, _body(definition.description, facts)

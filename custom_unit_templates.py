"""
custom_unit_templates.py

Manages player-created unit designs at runtime.  A design is stored as a
CustomUnitTemplate dataclass, converted into the same dict format used by
data/unit_templates.json, and inserted into the global UNIT_TEMPLATES dict
so that create_unit_from_template() works without modification.

Designs are persisted to data/custom_unit_templates.json so they survive
game restarts.
"""

import json
import logging
import os
import dataclasses
from typing import Dict, List, Optional, Any

from constants import HullSize, HULL_CAPACITIES, HIT_POINTS

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Hull-size restrictions
# --------------------------------------------------------------------------

# Components that are FORBIDDEN for a given hull size.
# Keys are HullSize enum values; values are sets of component key strings.
HULL_RESTRICTIONS: Dict[HullSize, set] = {
    HullSize.TINY: {
        "has_inhibitor",
        "has_hangar",
        "has_constructor_component",
        "has_repair_component",
        "has_colony_component",
        "has_metal_refinery_component",
        "has_crystal_refinery_component",
        "has_ability_component",
    },
    HullSize.SMALL: {
        "has_hangar",
        "has_inhibitor",
    },
    HullSize.MEDIUM: {
        "has_hangar",
    },
    HullSize.LARGE: set(),
    HullSize.HUGE: set(),
}

# Advanced hyperdrive is unavailable on TINY hulls (existing game rule).
ADVANCED_HYPERDRIVE_MIN_HULL = HullSize.SMALL

# --------------------------------------------------------------------------
# Hull-size cost multipliers (used in build cost calculation)
# --------------------------------------------------------------------------
HULL_BASE_COST: Dict[HullSize, int] = {
    HullSize.TINY: 100,
    HullSize.SMALL: 250,
    HullSize.MEDIUM: 500,
    HullSize.LARGE: 1000,
    HullSize.HUGE: 2000,
}

HULL_BASE_BUILD_TIME: Dict[HullSize, int] = {
    HullSize.TINY: 3,
    HullSize.SMALL: 6,
    HullSize.MEDIUM: 10,
    HullSize.LARGE: 15,
    HullSize.HUGE: 20,
}

COMPONENT_COST_PER_HULL_POINT = 30  # credits per hull capacity point used


# --------------------------------------------------------------------------
# Turret definition
# --------------------------------------------------------------------------
@dataclasses.dataclass
class TurretConfig:
    turret_type: str      # "MASS_DRIVER", "BEAM", or "MISSILE"
    damage: float
    range: float
    cooldown: int


# --------------------------------------------------------------------------
# Component configuration dataclass
# --------------------------------------------------------------------------
@dataclasses.dataclass
class ComponentConfig:
    """Configuration for every component type that can appear in a design."""
    # Engines
    has_engine: bool = False
    engine_speed: float = 100.0
    engine_hull_cost: int = 5

    # Hyperdrive
    has_hyperdrive: bool = False
    hyperdrive_type: str = "BASIC"      # "BASIC" or "ADVANCED"
    hyperdrive_hull_cost: int = 5

    # Weapons
    has_weapon_bays: bool = False
    weapon_bays_hull_cost: int = 10
    turrets: List[TurretConfig] = dataclasses.field(default_factory=list)

    # Constructor
    has_constructor_component: bool = False
    constructor_hull_cost: int = 15
    buildable_units: List[str] = dataclasses.field(default_factory=list)

    # Repair
    has_repair_component: bool = False
    repair_rate: float = 10.0
    repair_range: float = 200.0
    credit_cost_per_hp: float = 1.0
    repair_hull_cost: int = 15

    # Colony
    has_colony_component: bool = False
    colony_hull_cost: int = 10

    # Mining
    has_mining_component: bool = False
    mining_rate: float = 10.0
    mining_range: float = 200.0
    max_mining_cargo: float = 100.0
    mining_hull_cost: int = 10

    # Metal refinery
    has_metal_refinery_component: bool = False
    metal_refinery_hull_cost: int = 20

    # Crystal refinery
    has_crystal_refinery_component: bool = False
    crystal_refinery_hull_cost: int = 20

    # Hangar
    has_hangar: bool = False
    hangar_slots: int = 2
    hangar_hull_cost: int = 20

    # Hyperspace inhibitor
    has_inhibitor: bool = False
    inhibitor_radius: float = 100.0
    inhibitor_hull_cost: int = 20

    # Abilities
    has_ability_component: bool = False
    ability_hull_cost: int = 10
    abilities: List[str] = dataclasses.field(default_factory=list)

    def __post_init__(self):
        if self.hyperdrive_type == "BASIC":
            self.hyperdrive_hull_cost = 5
        elif self.hyperdrive_type == "ADVANCED":
            self.hyperdrive_hull_cost = 10


# --------------------------------------------------------------------------
# Custom unit template dataclass
# --------------------------------------------------------------------------
@dataclasses.dataclass
class CustomUnitTemplate:
    """A player-designed unit template."""
    design_name: str          # Template key (unique, used as UNIT_TEMPLATES key)
    display_name: str         # Human-readable name shown in-game
    hull_size: HullSize
    components: ComponentConfig = dataclasses.field(default_factory=ComponentConfig)

    @property
    def hull_capacity(self) -> int:
        return HULL_CAPACITIES[self.hull_size]

    @property
    def total_hull_cost(self) -> int:
        """Sum of hull costs for all enabled components."""
        c = self.components
        total = 0
        if c.has_engine:            total += c.engine_hull_cost
        if c.has_hyperdrive:        total += c.hyperdrive_hull_cost
        if c.has_weapon_bays:       total += c.weapon_bays_hull_cost
        if c.has_constructor_component: total += c.constructor_hull_cost
        if c.has_repair_component:  total += c.repair_hull_cost
        if c.has_colony_component:  total += c.colony_hull_cost
        if c.has_mining_component:  total += c.mining_hull_cost
        if c.has_metal_refinery_component: total += c.metal_refinery_hull_cost
        if c.has_crystal_refinery_component: total += c.crystal_refinery_hull_cost
        if c.has_hangar:            total += c.hangar_hull_cost
        if c.has_inhibitor:         total += c.inhibitor_hull_cost
        if c.has_ability_component: total += c.ability_hull_cost
        return total

    @property
    def is_over_capacity(self) -> bool:
        return self.total_hull_cost > self.hull_capacity

    @property
    def build_cost(self) -> int:
        """Calculated credit cost: base hull cost + component hull-point cost."""
        return HULL_BASE_COST[self.hull_size] + self.total_hull_cost * COMPONENT_COST_PER_HULL_POINT

    @property
    def build_time(self) -> int:
        """Calculated build time proportional to hull size + component load."""
        base = HULL_BASE_BUILD_TIME[self.hull_size]
        capacity = max(1, self.hull_capacity)
        extra = max(0, round((self.total_hull_cost / capacity) * base))
        return base + extra

    def validate(self) -> List[str]:
        """
        Returns a list of validation error strings.
        An empty list means the design is valid.
        """
        errors: List[str] = []
        if not self.design_name or not self.design_name.strip():
            errors.append("Design name cannot be empty.")
        if not self.display_name or not self.display_name.strip():
            errors.append("Display name cannot be empty.")
        if self.is_over_capacity:
            errors.append(
                f"Hull over capacity: {self.total_hull_cost} / {self.hull_capacity} used."
            )
        # Check hull-size restrictions
        restricted = HULL_RESTRICTIONS.get(self.hull_size, set())
        c = self.components
        comp_flags = {
            "has_hyperdrive": c.has_hyperdrive,
            "has_inhibitor": c.has_inhibitor,
            "has_hangar": c.has_hangar,
            "has_constructor_component": c.has_constructor_component,
            "has_repair_component": c.has_repair_component,
            "has_colony_component": c.has_colony_component,
            "has_metal_refinery_component": c.has_metal_refinery_component,
            "has_crystal_refinery_component": c.has_crystal_refinery_component,
            "has_ability_component": c.has_ability_component,
        }
        for flag, enabled in comp_flags.items():
            if enabled and flag in restricted:
                errors.append(
                    f"Component '{flag}' is not allowed on {self.hull_size.name} hull."
                )
        # Advanced hyperdrive restriction
        hull_sizes = list(HullSize)
        min_idx = hull_sizes.index(ADVANCED_HYPERDRIVE_MIN_HULL)
        if c.has_hyperdrive and c.hyperdrive_type == "ADVANCED":
            if hull_sizes.index(self.hull_size) < min_idx:
                errors.append(
                    f"ADVANCED hyperdrive requires at least {ADVANCED_HYPERDRIVE_MIN_HULL.name} hull."
                )
        # At least one meaningful component
        any_component = any([
            c.has_engine, c.has_hyperdrive, c.has_weapon_bays,
            c.has_constructor_component, c.has_repair_component,
            c.has_colony_component, c.has_mining_component,
            c.has_metal_refinery_component, c.has_crystal_refinery_component,
            c.has_hangar, c.has_inhibitor, c.has_ability_component,
        ])
        if not any_component:
            errors.append("At least one component must be enabled.")
        return errors


# --------------------------------------------------------------------------
# CustomTemplateManager
# --------------------------------------------------------------------------
_DATA_FILE = os.path.join(os.path.dirname(__file__), "data", "custom_unit_templates.json")


class CustomTemplateManager:
    """
    Manages player-created unit designs.

    Designs are stored in self.designs (keyed by design_name).
    When saved, designs are:
      1. Inserted into the global UNIT_TEMPLATES dict so that
         create_unit_from_template() works unchanged.
      2. Written to data/custom_unit_templates.json for persistence.
    """

    def __init__(self):
        self.designs: Dict[str, CustomUnitTemplate] = {}

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def load_from_file(self) -> None:
        """Load persisted designs from disk and register them."""
        if not os.path.exists(_DATA_FILE):
            return
        try:
            with open(_DATA_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"[CustomTemplateManager] Could not load custom templates: {e}")
            return

        for key, d in raw.items():
            try:
                template = self._dict_to_template(key, d)
                self.designs[key] = template
                self._register_in_global(template)
                logger.debug(f"[CustomTemplateManager] Loaded design '{key}'")
            except Exception as e:
                logger.warning(f"[CustomTemplateManager] Failed to load design '{key}': {e}")

    def save_to_file(self) -> None:
        """Persist all current designs to disk."""
        raw: Dict[str, Any] = {}
        for key, template in self.designs.items():
            d = self._template_to_dict(template)
            # Ensure hull_size is stored as a string (JSON-serializable)
            if hasattr(d.get("hull_size"), "name"):
                d["hull_size"] = d["hull_size"].name
            raw[key] = d
        try:
            with open(_DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(raw, f, indent=2)
            logger.debug(f"[CustomTemplateManager] Saved {len(self.designs)} design(s) to {_DATA_FILE}")
        except OSError as e:
            logger.error(f"[CustomTemplateManager] Could not save custom templates: {e}")

    # ------------------------------------------------------------------
    # Design management
    # ------------------------------------------------------------------

    def save_design(self, template: CustomUnitTemplate) -> List[str]:
        """
        Validate and save a design.

        Returns a list of validation error strings. An empty list means
        success — the design has been stored and registered.
        """
        errors = template.validate()
        if errors:
            return errors
        # Use uppercase, whitespace-stripped key
        key = template.design_name.strip().upper().replace(" ", "_")
        template.design_name = key
        self.designs[key] = template
        self._register_in_global(template)
        self.save_to_file()
        logger.debug(f"[CustomTemplateManager] Design '{key}' saved.")
        return []

    def delete_design(self, design_name: str) -> bool:
        """Remove a design. Returns True if it existed."""
        key = design_name.strip().upper().replace(" ", "_")
        if key not in self.designs:
            return False
        del self.designs[key]
        self._unregister_from_global(key)
        self.save_to_file()
        logger.debug(f"[CustomTemplateManager] Design '{key}' deleted.")
        return True

    def get_design(self, design_name: str) -> Optional[CustomUnitTemplate]:
        key = design_name.strip().upper().replace(" ", "_")
        return self.designs.get(key)

    def list_design_names(self) -> List[str]:
        return list(self.designs.keys())

    # ------------------------------------------------------------------
    # Constructor integration
    # ------------------------------------------------------------------

    def refresh_shipyard_buildables(self, units_iter) -> int:
        """
        Append custom designs to every SHIPYARD_MK1 constructor's buildable list.

        ``units_iter`` should be an iterable of all Unit objects in the galaxy.
        Returns the number of constructors updated.
        """
        from unit_components import Constructor, BuildableUnit
        from unit_templates import UNIT_TEMPLATES

        count = 0
        for unit in units_iter:
            constructor: Optional[Constructor] = getattr(unit, "constructor_component", None)
            if constructor is None:
                continue
            # Only refresh SHIPYARD_MK1-equivalent constructors (those that can already
            # build BATTLESHIP_MEDIUM, a hallmark of shipyard capability).
            existing_names = {bu.unit_template_name for bu in constructor.buildable_units}
            if "BATTLESHIP_MEDIUM" not in existing_names:
                continue
            added = False
            for key, template in self.designs.items():
                if key not in existing_names:
                    t = UNIT_TEMPLATES.get(key, {})
                    new_bu = BuildableUnit(
                        unit_template_name=key,
                        time_to_build=t.get("build_time", template.build_time),
                        cost_credits=t.get("build_cost", template.build_cost),
                    )
                    constructor.buildable_units.append(new_bu)
                    added = True
                    logger.debug(
                        f"[CustomTemplateManager] Added '{key}' to constructor on '{unit.name}'."
                    )
            if added:
                count += 1
        return count

    # ------------------------------------------------------------------
    # Conversion helpers
    # ------------------------------------------------------------------

    def _register_in_global(self, template: CustomUnitTemplate) -> None:
        from unit_templates import UNIT_TEMPLATES
        UNIT_TEMPLATES[template.design_name] = self._template_to_dict(template)

    def _unregister_from_global(self, key: str) -> None:
        from unit_templates import UNIT_TEMPLATES
        UNIT_TEMPLATES.pop(key, None)

    def _template_to_dict(self, template: CustomUnitTemplate) -> Dict[str, Any]:
        """Convert a CustomUnitTemplate to the unit_templates.json dict format."""
        c = template.components
        d: Dict[str, Any] = {
            "name": template.display_name,
            "hull_size": template.hull_size,   # kept as HullSize enum (matches how JSON loader converts)
            "hull_points": HIT_POINTS[template.hull_size],
            "build_time": template.build_time,
            "build_cost": template.build_cost,

            "has_engine": c.has_engine,
            "engine_speed": c.engine_speed,
            "engine_hull_cost": c.engine_hull_cost,

            "has_hyperdrive": c.has_hyperdrive,
            "hyperdrive_type": c.hyperdrive_type,
            "hyperdrive_hull_cost": c.hyperdrive_hull_cost,

            "has_weapon_bays": c.has_weapon_bays,
            "weapon_bays_hull_cost": c.weapon_bays_hull_cost,
            "turrets": [
                {
                    "type": t.turret_type,
                    "damage": t.damage,
                    "range": t.range,
                    "cooldown": t.cooldown,
                }
                for t in c.turrets
            ],

            "has_constructor_component": c.has_constructor_component,
            "constructor_hull_cost": c.constructor_hull_cost,
            "buildable_units": c.buildable_units,

            "has_repair_component": c.has_repair_component,
            "repair_rate": c.repair_rate,
            "repair_range": c.repair_range,
            "credit_cost_per_hp": c.credit_cost_per_hp,
            "repair_hull_cost": c.repair_hull_cost,

            "has_colony_component": c.has_colony_component,
            "colony_hull_cost": c.colony_hull_cost,

            "has_mining_component": c.has_mining_component,
            "mining_rate": c.mining_rate,
            "mining_range": c.mining_range,
            "max_mining_cargo": c.max_mining_cargo,
            "mining_hull_cost": c.mining_hull_cost,

            "has_metal_refinery_component": c.has_metal_refinery_component,
            "metal_refinery_hull_cost": c.metal_refinery_hull_cost,
            "unload_range": 300.0,

            "has_crystal_refinery_component": c.has_crystal_refinery_component,
            "crystal_refinery_hull_cost": c.crystal_refinery_hull_cost,

            "has_hangar": c.has_hangar,
            "hangar_slots": c.hangar_slots,
            "hangar_hull_cost": c.hangar_hull_cost,

            "has_inhibitor": c.has_inhibitor,
            "inhibitor_radius": c.inhibitor_radius,
            "inhibitor_hull_cost": c.inhibitor_hull_cost,

            "has_ability_component": c.has_ability_component,
            "ability_hull_cost": c.ability_hull_cost,
            "abilities": c.abilities,

            "is_custom": True,  # marker so we know it's player-designed
        }
        return d

    def _dict_to_template(self, key: str, d: Dict[str, Any]) -> CustomUnitTemplate:
        """Reconstruct a CustomUnitTemplate from its persisted dict form."""
        # hull_size stored as string in JSON
        hull_size_raw = d.get("hull_size", "MEDIUM")
        if isinstance(hull_size_raw, str):
            hull_size = HullSize[hull_size_raw.upper()]
        else:
            hull_size = hull_size_raw

        turrets = [
            TurretConfig(
                turret_type=t["type"],
                damage=t["damage"],
                range=t["range"],
                cooldown=t["cooldown"],
            )
            for t in d.get("turrets", [])
        ]

        comp = ComponentConfig(
            has_engine=d.get("has_engine", False),
            engine_speed=d.get("engine_speed", 100.0),
            engine_hull_cost=d.get("engine_hull_cost", 5),

            has_hyperdrive=d.get("has_hyperdrive", False),
            hyperdrive_type=d.get("hyperdrive_type", "BASIC"),
            hyperdrive_hull_cost=d.get("hyperdrive_hull_cost", 10),

            has_weapon_bays=d.get("has_weapon_bays", False),
            weapon_bays_hull_cost=d.get("weapon_bays_hull_cost", 10),
            turrets=turrets,

            has_constructor_component=d.get("has_constructor_component", False),
            constructor_hull_cost=d.get("constructor_hull_cost", 15),
            buildable_units=d.get("buildable_units", []),

            has_repair_component=d.get("has_repair_component", False),
            repair_rate=d.get("repair_rate", 10.0),
            repair_range=d.get("repair_range", 200.0),
            credit_cost_per_hp=d.get("credit_cost_per_hp", 1.0),
            repair_hull_cost=d.get("repair_hull_cost", 15),

            has_colony_component=d.get("has_colony_component", False),
            colony_hull_cost=d.get("colony_hull_cost", 10),

            has_mining_component=d.get("has_mining_component", False),
            mining_rate=d.get("mining_rate", 10.0),
            mining_range=d.get("mining_range", 200.0),
            max_mining_cargo=d.get("max_mining_cargo", 100.0),
            mining_hull_cost=d.get("mining_hull_cost", 10),

            has_metal_refinery_component=d.get("has_metal_refinery_component", False),
            metal_refinery_hull_cost=d.get("metal_refinery_hull_cost", 20),

            has_crystal_refinery_component=d.get("has_crystal_refinery_component", False),
            crystal_refinery_hull_cost=d.get("crystal_refinery_hull_cost", 20),

            has_hangar=d.get("has_hangar", False),
            hangar_slots=d.get("hangar_slots", 2),
            hangar_hull_cost=d.get("hangar_hull_cost", 20),

            has_inhibitor=d.get("has_inhibitor", False),
            inhibitor_radius=d.get("inhibitor_radius", 100.0),
            inhibitor_hull_cost=d.get("inhibitor_hull_cost", 20),

            has_ability_component=d.get("has_ability_component", False),
            ability_hull_cost=d.get("ability_hull_cost", 10),
            abilities=d.get("abilities", []),
        )

        return CustomUnitTemplate(
            design_name=key,
            display_name=d.get("name", key),
            hull_size=hull_size,
            components=comp,
        )

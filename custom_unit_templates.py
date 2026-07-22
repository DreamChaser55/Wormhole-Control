"""
custom_unit_templates.py

Manages player-created unit designs at runtime.  A design is stored as a
CustomUnitTemplate dataclass, converted into the same dict format used by
data/unit_templates.json, and inserted into the global UNIT_TEMPLATES dict
so that create_unit_from_template() works without modification.

Designs are persisted to data/custom_unit_templates.json so they survive
game restarts.

Component hull costs for Engines, Weapons, Defenses, and Hyperdrive are
**computed dynamically** from their performance parameters using the
calc_*_hull_cost() functions in this module.  All other components retain
fixed hull costs.
"""

import json
import logging
import math
import os
import dataclasses
from typing import Dict, List, Optional, Any

from constants import HullSize, HULL_CAPACITIES, HIT_POINTS, ANTIMATTER_CAPACITY_PER_HULL_POINT

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Hull-size restrictions
# --------------------------------------------------------------------------

# Components that are FORBIDDEN for a given hull size.
# Keys are HullSize enum values; values are sets of component key strings.
HULL_RESTRICTIONS: Dict[HullSize, set] = {
    HullSize.STRIKECRAFT_WING: {
        "has_inhibitor",
        "has_hangar",
        "has_constructor_component",
        "has_repair_component",
        "has_colony_component",
        "has_metal_refinery_component",
        "has_crystal_refinery_component",
        "has_ability_component",
        "has_hyperdrive",
        "has_strikecraft_bay",
    },
    HullSize.TINY: {
        "has_inhibitor",
        "has_hangar",
        "has_constructor_component",
        "has_repair_component",
        "has_colony_component",
        "has_metal_refinery_component",
        "has_crystal_refinery_component",
        "has_ability_component",
        "has_strikecraft_bay",
    },
    HullSize.SMALL: {
        "has_hangar",
        "has_inhibitor",
        "has_strikecraft_bay",
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
    HullSize.STRIKECRAFT_WING: 50,
    HullSize.TINY: 100,
    HullSize.SMALL: 250,
    HullSize.MEDIUM: 500,
    HullSize.LARGE: 1000,
    HullSize.HUGE: 2000,
}

HULL_BASE_BUILD_TIME: Dict[HullSize, int] = {
    HullSize.STRIKECRAFT_WING: 1,
    HullSize.TINY: 3,
    HullSize.SMALL: 6,
    HullSize.MEDIUM: 10,
    HullSize.LARGE: 15,
    HullSize.HUGE: 20,
}

COMPONENT_COST_PER_HULL_POINT = 30  # credits per hull capacity point used


# --------------------------------------------------------------------------
# Dynamic hull-cost tuning constants
# --------------------------------------------------------------------------

# Engines: 1 hull point per SPEED_PER_HULL_POINT units of speed.
# Speed 100 → hull cost 5.
SPEED_PER_HULL_POINT: float = 20.0

# Weapons: per-turret formula components
BASE_TURRET_COST: float = 1.0          # flat per turret
DMG_PER_POINT: float = 5.0             # hull points per unit of damage
RANGE_PER_POINT: float = 100.0         # hull points per unit of range
COOLDOWN_BONUS: float = 2.0            # hull points granted by short cooldown

# Defenses: 1 hull point per DEFENSE_PER_HULL_POINT total defense rating.
# armor=5 + shields=5 + pd=5 → hull cost 5.
DEFENSE_PER_HULL_POINT: float = 3.0

# Hyperdrive: base costs per drive type + cost per jump range unit.
HYPERDRIVE_BASE_COST: Dict[str, int] = {
    "BASIC": 3,
    "ADVANCED": 7,
}
HYPERDRIVE_RANGE_PER_POINT: float = 5.0   # jump range units per hull point

# Abilities: base cost + cost per selected ability
ABILITY_BASE_COST: int = 10
ABILITY_COST_PER_ABILITY: int = 5


# --------------------------------------------------------------------------
# Dynamic hull-cost calculation functions
# --------------------------------------------------------------------------

def calc_engine_hull_cost(speed: float) -> int:
    """Compute the hull cost of an Engines component from its speed.

    Formula: ceil(speed / SPEED_PER_HULL_POINT), minimum 1.

    Examples:
        speed=100 → 5
        speed=200 → 10
        speed=50  → 3
    """
    if speed <= 0:
        return 0
    return max(1, math.ceil(speed / SPEED_PER_HULL_POINT))


def calc_antimatter_hull_cost(capacity: float) -> int:
    """Compute the hull cost of an Antimatter Storage component from its capacity.

    Formula: ceil(capacity / ANTIMATTER_CAPACITY_PER_HULL_POINT), minimum 1.

    Examples:
        capacity=100 → 5
        capacity=200 → 10
        capacity=50  → 3
    """
    if capacity <= 0:
        return 0
    return max(1, math.ceil(capacity / ANTIMATTER_CAPACITY_PER_HULL_POINT))


def calc_turret_hull_cost(turret: 'TurretConfig') -> int:
    """Compute the hull cost of a single turret based on its stats.

    Formula:
        BASE_TURRET_COST
        + damage / DMG_PER_POINT
        + range / RANGE_PER_POINT
        + COOLDOWN_BONUS / max(1, cooldown)

    Note: Long-Range turrets already triple their effective range and cooldown
    in Turret.__post_init__, so the stored config values are pre-variant.
    We apply the variant multiplier here to price LONG_RANGE accordingly.
    """
    effective_range = turret.range
    effective_cooldown = max(1, turret.cooldown)

    if turret.variant.upper() == "LONG_RANGE":
        effective_range *= 3.0
        effective_cooldown *= 3

    cost = (
        BASE_TURRET_COST
        + turret.damage / DMG_PER_POINT
        + effective_range / RANGE_PER_POINT
        + COOLDOWN_BONUS / effective_cooldown
    )
    return max(1, math.ceil(cost))


def calc_weapons_hull_cost(turrets: List['TurretConfig']) -> int:
    """Compute the total hull cost of a Weapons component from its turrets.

    Returns 0 if no turrets are configured (0 hull used, but component still
    may be toggled on — the UI should enforce at least 1 turret if weapons
    are enabled).
    """
    if not turrets:
        return 0
    return sum(calc_turret_hull_cost(t) for t in turrets)


def calc_defenses_hull_cost(armor: int, shields: int, point_defense: int) -> int:
    """Compute the hull cost of a Defenses component from its stats.

    Formula: ceil((armor + shields + point_defense) / DEFENSE_PER_HULL_POINT),
    minimum 1.

    Examples:
        armor=5, shields=5, pd=5 → 5
        armor=10, shields=10, pd=10 → 10
        all zeros → 0 (not enabled)
    """
    total = armor + shields + point_defense
    if total <= 0:
        return 0
    return max(1, math.ceil(total / DEFENSE_PER_HULL_POINT))


def calc_hyperdrive_hull_cost(drive_type: str, jump_range: int) -> int:
    """Compute the hull cost of a Hyperdrive component.

    Formula: HYPERDRIVE_BASE_COST[drive_type] + ceil(jump_range / RANGE_PER_POINT),
    minimum 1.

    Examples:
        BASIC,    range=5  → 3 + 1 = 4
        ADVANCED, range=5  → 7 + 1 = 8
        BASIC,    range=10 → 3 + 2 = 5
    """
    base = HYPERDRIVE_BASE_COST.get(drive_type.upper(), HYPERDRIVE_BASE_COST["BASIC"])
    range_cost = math.ceil(max(0, jump_range) / HYPERDRIVE_RANGE_PER_POINT)
    return max(1, base + range_cost)


def calc_ability_hull_cost(abilities: List[str]) -> int:
    """Compute the hull cost of an Ability component from its list of selected abilities.

    Formula: ABILITY_BASE_COST + len(abilities) * ABILITY_COST_PER_ABILITY
    """
    return ABILITY_BASE_COST + len(abilities) * ABILITY_COST_PER_ABILITY


# --------------------------------------------------------------------------
# Turret definition
# --------------------------------------------------------------------------
@dataclasses.dataclass
class TurretConfig:
    turret_type: str      # "MASS_DRIVER", "BEAM", or "MISSILE"
    damage: float
    range: float
    cooldown: int
    variant: str = "STANDARD"


# --------------------------------------------------------------------------
# Component configuration dataclass
# --------------------------------------------------------------------------
@dataclasses.dataclass
class ComponentConfig:
    """Configuration for every component type that can appear in a design.

    Hull costs for Engines, Weapons, Defenses, and Hyperdrive are computed
    dynamically from their performance parameters.  All other components
    use fixed hull costs stored as plain fields.
    """
    # Engines
    has_engine: bool = False
    engine_speed: float = 100.0
    # hull cost is computed: see engine_hull_cost property

    # Antimatter Storage
    has_antimatter_storage: bool = False
    antimatter_capacity: float = 100.0
    # hull cost is computed: see antimatter_hull_cost property

    # Hyperdrive
    has_hyperdrive: bool = False
    hyperdrive_type: str = "BASIC"      # "BASIC" or "ADVANCED"
    hyperdrive_jump_range: int = 5      # in hexes
    # hull cost is computed: see hyperdrive_hull_cost property

    # Weapons
    has_weapon_bays: bool = False
    turrets: List[TurretConfig] = dataclasses.field(default_factory=list)
    # hull cost is computed: see weapon_bays_hull_cost property

    # Defenses
    has_defenses: bool = False
    armor: int = 0
    shields: int = 0
    point_defense: int = 0
    # hull cost is computed: see defenses_hull_cost property

    # Constructor
    has_constructor_component: bool = False
    constructor_hull_cost: int = 15

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

    # Strikecraft Bay
    has_strikecraft_bay: bool = False
    strikecraft_bay_slots: int = 2
    strikecraft_bay_hull_cost: int = 15

    # Wing Type (Fighter vs Bomber) - only for Strikecraft hulls
    wing_type: str = "FIGHTER"

    # Hyperspace inhibitor
    has_inhibitor: bool = False
    inhibitor_radius: float = 100.0
    inhibitor_hull_cost: int = 20

    # Abilities
    has_ability_component: bool = False
    abilities: List[str] = dataclasses.field(default_factory=list)

    # ------------------------------------------------------------------
    # Computed hull-cost properties for dynamic components
    # ------------------------------------------------------------------

    @property
    def engine_hull_cost(self) -> int:
        """Hull cost of Engines, computed from engine_speed."""
        if not self.has_engine:
            return 0
        return calc_engine_hull_cost(self.engine_speed)

    @property
    def antimatter_hull_cost(self) -> int:
        """Hull cost of Antimatter Storage, computed from antimatter_capacity."""
        if not self.has_antimatter_storage:
            return 0
        return calc_antimatter_hull_cost(self.antimatter_capacity)

    @property
    def weapon_bays_hull_cost(self) -> int:
        """Hull cost of Weapons, computed from turret list."""
        if not self.has_weapon_bays:
            return 0
        return calc_weapons_hull_cost(self.turrets)

    @property
    def defenses_hull_cost(self) -> int:
        """Hull cost of Defenses, computed from armor/shields/point_defense."""
        if not self.has_defenses:
            return 0
        return calc_defenses_hull_cost(self.armor, self.shields, self.point_defense)

    @property
    def hyperdrive_hull_cost(self) -> int:
        """Hull cost of Hyperdrive, computed from type and jump_range."""
        if not self.has_hyperdrive:
            return 0
        return calc_hyperdrive_hull_cost(self.hyperdrive_type, self.hyperdrive_jump_range)

    @property
    def ability_hull_cost(self) -> int:
        """Hull cost of Abilities, computed from the number of abilities."""
        if not self.has_ability_component:
            return 0
        return calc_ability_hull_cost(self.abilities)


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
        """Sum of hull costs for all enabled components.

        Dynamic components (Engines, Weapons, Defenses, Hyperdrive) use
        their computed properties; fixed components use their stored values.
        """
        c = self.components
        total = 0
        if c.has_engine:                        total += c.engine_hull_cost
        if c.has_antimatter_storage:            total += c.antimatter_hull_cost
        if c.has_hyperdrive:                    total += c.hyperdrive_hull_cost
        if c.has_weapon_bays:                   total += c.weapon_bays_hull_cost
        if c.has_defenses:                      total += c.defenses_hull_cost
        if c.has_constructor_component:         total += c.constructor_hull_cost
        if c.has_repair_component:              total += c.repair_hull_cost
        if c.has_colony_component:              total += c.colony_hull_cost
        if c.has_mining_component:              total += c.mining_hull_cost
        if c.has_metal_refinery_component:      total += c.metal_refinery_hull_cost
        if c.has_crystal_refinery_component:    total += c.crystal_refinery_hull_cost
        if c.has_hangar:                        total += c.hangar_hull_cost
        if c.has_strikecraft_bay:               total += c.strikecraft_bay_hull_cost
        if c.has_inhibitor:                     total += c.inhibitor_hull_cost
        if c.has_ability_component:             total += c.ability_hull_cost
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
            "has_hangar": c.has_hangar,
            "has_strikecraft_bay": c.has_strikecraft_bay,
            "has_inhibitor": c.has_inhibitor,
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

        # Validate Strikecraft Wing wing_type and turret variants
        if self.hull_size == HullSize.STRIKECRAFT_WING:
            wing_type_upper = c.wing_type.upper() if hasattr(c, "wing_type") else "FIGHTER"
            if wing_type_upper not in ("FIGHTER", "BOMBER"):
                errors.append(f"Invalid strikecraft wing role: {c.wing_type}. Must be FIGHTER or BOMBER.")
            else:
                for idx, turret in enumerate(c.turrets):
                    variant_upper = turret.variant.upper()
                    if wing_type_upper == "FIGHTER":
                        if variant_upper != "ANTI_STRIKECRAFT":
                            errors.append(f"Fighter Wing turret {idx + 1} must be ANTI_STRIKECRAFT (got {variant_upper}).")
                    elif wing_type_upper == "BOMBER":
                        if variant_upper == "ANTI_STRIKECRAFT":
                            errors.append(f"Bomber Wing turret {idx + 1} cannot be ANTI_STRIKECRAFT.")
        # Advanced hyperdrive restriction
        hull_sizes = list(HullSize)
        min_idx = hull_sizes.index(ADVANCED_HYPERDRIVE_MIN_HULL)
        if c.has_hyperdrive and c.hyperdrive_type == "ADVANCED":
            if hull_sizes.index(self.hull_size) < min_idx:
                errors.append(
                    f"ADVANCED hyperdrive requires at least {ADVANCED_HYPERDRIVE_MIN_HULL.name} hull."
                )
        # Jump range must be positive
        if c.has_hyperdrive and c.hyperdrive_jump_range < 1:
            errors.append("Hyperdrive jump range must be at least 1.")
        # Antimatter capacity must be positive
        if c.has_antimatter_storage and c.antimatter_capacity <= 0:
            errors.append("Antimatter storage capacity must be positive.")
        # At least one meaningful component
        any_component = any([
            c.has_engine, c.has_antimatter_storage, c.has_hyperdrive, c.has_weapon_bays,
            c.has_defenses,
            c.has_constructor_component, c.has_repair_component,
            c.has_colony_component, c.has_mining_component,
            c.has_metal_refinery_component, c.has_crystal_refinery_component,
            c.has_hangar, c.has_strikecraft_bay, c.has_inhibitor, c.has_ability_component,
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
        Append custom designs to every SHIPYARD_MK1 constructor's buildable list. (Deprecated/No-op)
        """
        return 0

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
        """Convert a CustomUnitTemplate to the unit_templates.json dict format.

        Dynamic hull costs (Engines, Weapons, Defenses, Hyperdrive) are stored
        as computed values so that create_unit_from_template() picks them up
        correctly.  Performance parameters are also stored so the design can
        be reconstructed faithfully on load.
        """
        c = template.components
        d: Dict[str, Any] = {
            "name": template.display_name,
            "hull_size": template.hull_size,   # kept as HullSize enum (matches how JSON loader converts)
            "hull_points": HIT_POINTS[template.hull_size],
            "build_time": template.build_time,
            "build_cost": template.build_cost,

            # --- Engines ---
            "has_engine": c.has_engine,
            "engine_speed": c.engine_speed,
            "engine_hull_cost": c.engine_hull_cost,  # computed

            # --- Antimatter Storage ---
            "has_antimatter_storage": c.has_antimatter_storage,
            "antimatter_capacity": c.antimatter_capacity,
            "antimatter_hull_cost": c.antimatter_hull_cost,  # computed

            # --- Hyperdrive ---
            "has_hyperdrive": c.has_hyperdrive,
            "hyperdrive_type": c.hyperdrive_type,
            "hyperdrive_jump_range": c.hyperdrive_jump_range,
            "hyperdrive_hull_cost": c.hyperdrive_hull_cost,  # computed

            # --- Weapons ---
            "has_weapon_bays": c.has_weapon_bays,
            "weapon_bays_hull_cost": c.weapon_bays_hull_cost,  # computed
            "turrets": [
                {
                    "type": t.turret_type,
                    "damage": t.damage,
                    "range": t.range,
                    "cooldown": t.cooldown,
                    "variant": t.variant,
                }
                for t in c.turrets
            ],

            # --- Defenses ---
            "has_defenses": c.has_defenses,
            "defenses_hull_cost": c.defenses_hull_cost,  # computed
            "armor": c.armor,
            "shields": c.shields,
            "point_defense": c.point_defense,

            # --- Fixed-cost components ---
            "has_constructor_component": c.has_constructor_component,
            "constructor_hull_cost": c.constructor_hull_cost,

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

            "has_strikecraft_bay": c.has_strikecraft_bay,
            "strikecraft_bay_slots": c.strikecraft_bay_slots,
            "strikecraft_bay_hull_cost": c.strikecraft_bay_hull_cost,
            "wing_type": c.wing_type,

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
        """Reconstruct a CustomUnitTemplate from its persisted dict form.

        Performance parameters are loaded from the dict.  Hull costs for
        dynamic components are NOT read from the dict — they are recomputed
        from the performance parameters to ensure correctness.
        """
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
                variant=t.get("variant", "STANDARD"),
            )
            for t in d.get("turrets", [])
        ]

        comp = ComponentConfig(
            # --- Dynamic components: load performance params only ---
            has_engine=d.get("has_engine", False),
            engine_speed=d.get("engine_speed", 100.0),

            has_antimatter_storage=d.get("has_antimatter_storage", True),
            antimatter_capacity=float(d.get("antimatter_capacity", 100.0)),

            has_hyperdrive=d.get("has_hyperdrive", False),
            hyperdrive_type=d.get("hyperdrive_type", "BASIC"),
            hyperdrive_jump_range=d.get("hyperdrive_jump_range", 5),

            has_weapon_bays=d.get("has_weapon_bays", False),
            turrets=turrets,

            has_defenses=d.get("has_defenses", False),
            armor=d.get("armor", 0),
            shields=d.get("shields", 0),
            point_defense=d.get("point_defense", 0),

            # --- Fixed-cost components ---
            has_constructor_component=d.get("has_constructor_component", False),
            constructor_hull_cost=d.get("constructor_hull_cost", 15),

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

            has_strikecraft_bay=d.get("has_strikecraft_bay", False) or d.get("has_fighter_bay", False),
            strikecraft_bay_slots=d.get("strikecraft_bay_slots", d.get("fighter_bay_slots", 2)),
            strikecraft_bay_hull_cost=d.get("strikecraft_bay_hull_cost", d.get("fighter_bay_hull_cost", 15)),
            wing_type=d.get("wing_type", "FIGHTER"),

            has_inhibitor=d.get("has_inhibitor", False),
            inhibitor_radius=d.get("inhibitor_radius", 100.0),
            inhibitor_hull_cost=d.get("inhibitor_hull_cost", 20),

            has_ability_component=d.get("has_ability_component", False),
            abilities=d.get("abilities", []),
        )

        return CustomUnitTemplate(
            design_name=key,
            display_name=d.get("name", key),
            hull_size=hull_size,
            components=comp,
        )

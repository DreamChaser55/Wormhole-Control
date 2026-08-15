import logging

logger = logging.getLogger(__name__)

import typing
from typing import Dict, Optional, Any, Tuple, TYPE_CHECKING
from utils import HexCoord
from geometry import Position, distance, Vector
from constants import (
    WHITE, YELLOW, GREEN, PURPLE, HULL_CAPACITIES, HullSize, HIT_POINTS,
    StarType, PlanetType, NebulaType, StormType, NEBULA_COLORS, STORM_COLORS,
    MAX_UNIT_XP, XP_WEAPON_DAMAGE_BONUS, XP_DEFENSE_BONUS, XP_SPEED_BONUS,
    XP_JUMP_RANGE_BONUS, DEFAULT_SENSOR_SHORT_RANGE, STAR_HARVEST_MULTIPLIERS,
    MINEFIELD_DEFAULT_DAMAGE, MINEFIELD_DEFAULT_MINES, MINEFIELD_DETONATION_RADIUS,
    POPULATION_PER_HABITAT, BASE_HABITAT_CAPACITY
)
import uuid
import dataclasses
from enum import Enum, auto
from collections import deque
from unit_orders import (
    Order, OrderStatus, OrderType,
    MoveOrder, ReachWaypointOrder, AttackOrder, ColonizeOrder,
    LoadColonistsOrder, ConstructOrder, ToggleInhibitorOrder, PatrolOrder,
    RepairOrder, MineOrder, UnloadResourcesOrder, DockOrder, DeployUnitOrder,
    UseAbilityOrder, ProtectOrder, ContinuousMineOrder, TransferAntimatterOrder,
    ContinuousResupplyOrder
)
from unit_components import (
    UnitComponent,
    AntimatterStorage,
    AntimatterHarvester,
    Engines,
    Hyperdrive, HyperdriveType,
    Commander,
    HyperspaceInhibitionFieldEmitter,
    Weapons,
    Defenses,
    TurretType,
    ColonyComponent,
    CivilianHabitatComponent,
    Constructor,
    RepairComponent,
    MiningComponent,
    MetalRefineryComponent,
    CrystalRefineryComponent,
    HangarComponent,
    AbilityComponent,
    AbilityType,
    StrikecraftBayComponent,
    StrikecraftWingComponent,
    Sensors,
    MinefieldType,
    MarinesComponent,
)
from unit_components.cloaking import CloakingDevice


if TYPE_CHECKING:
    from galaxy import Galaxy
    from game import Game

# --- Player Class ---
class Player:
    """Represents a player in the game (human or AI)."""
    player_counter = 0

    def __init__(self, name: str, color: tuple, is_human: bool = True):
        self.id = Player.player_counter
        Player.player_counter += 1
        self.name = name if name else f"Player {self.id}"
        self.color = color
        self.is_human = is_human
        self.credits = 20000
        self.metal = 10000
        self.crystal = 10000
        self.sector_intel: Dict[Tuple[str, HexCoord], int] = {}

    def record_sector_intel(self, system_name: str, hex_coord: HexCoord, turn: int) -> None:
        """Records or updates the last turn a sector was in long-range sensor range."""
        self.sector_intel[(system_name, hex_coord)] = turn

    def get_sector_last_intel_turn(self, system_name: str, hex_coord: HexCoord) -> Optional[int]:
        """Returns the turn number when intel was last updated for a sector, or None."""
        return self.sector_intel.get((system_name, hex_coord))

    def __repr__(self):
        return f"Player({self.name}, ID:{self.id}, Color:{self.color})"

# --- Game Object Base Class ---
class GameObject:
    """Base class for all objects that can exist in a sector."""
    object_counter = 0

    def __init__(self, position: Position, in_hex: HexCoord, in_system: str):
        self.id = GameObject.object_counter
        GameObject.object_counter += 1
        self.position = position
        self.in_hex = in_hex
        self.in_system = in_system

    def __repr__(self):
        return f"{self.__class__.__name__}(ID:{self.id}, Pos:{self.position}, Hex:{self.in_hex}, System:{self.in_system})"

# --- GameObject-derived Class: CelestialBody ---

class CelestialBody(GameObject):
    """Base class for fixed celestial objects like planets, stars."""
    def __init__(self, position: Position, in_hex: HexCoord, in_system: str, inhibition_field_radius: float = 0.0):
        super().__init__(position, in_hex, in_system)
        self.inhibition_field_radius = inhibition_field_radius

    def get_supported_habitat_capacity(self) -> int:
        """Returns the maximum number of civilian habitat modules this body can support based on population."""
        if not getattr(self, 'owner', None) or getattr(self, 'population', 0.0) <= 0:
            return 0
        return max(BASE_HABITAT_CAPACITY, int(self.population // POPULATION_PER_HABITAT))

# --- CelestialBody-derived Classes ---

class Wormhole(CelestialBody):
    """Represents a wormhole connecting two systems."""
    def __init__(self, in_hex: HexCoord, in_system: str, exit_system_name: str, stability: int = 100, diameter: HullSize = HullSize.HUGE):
        super().__init__(position=Position(0.0, 0.0), in_hex=in_hex, in_system=in_system, inhibition_field_radius=1500.0)
        self.exit_system_name = exit_system_name
        self.exit_wormhole_id: typing.Optional[int] = None
        self.stability = stability
        self.diameter = diameter
        self.name = f"Wormhole {self.id}"

class Star(CelestialBody):
    """Represents the central star of a system."""
    def __init__(self, in_system: str, star_type: StarType):
        super().__init__(position=Position(0.0, 0.0), in_hex=(0, 0), in_system=in_system, inhibition_field_radius=2700.0)
        self.star_type = star_type
        self.name = f"Star {self.id}"

    @property
    def harvest_multiplier(self) -> float:
        """Returns the antimatter harvest rate multiplier based on star type."""
        return STAR_HARVEST_MULTIPLIERS.get(self.star_type, 1.0)

class Planet(CelestialBody):
    """Represents a planet within a system."""
    def __init__(self, in_hex: HexCoord, in_system: str, planet_type: PlanetType):
        super().__init__(position=Position(0.0, 0.0), in_hex=in_hex, in_system=in_system, inhibition_field_radius=2400.0)
        self.name = f"Planet {self.id}"
        self.owner: Optional[Player] = None
        self.population: float = 0
        self.max_population: float = 100.0
        self.population_growth_rate: float = 0.02
        self.planet_type = planet_type

    def update_population(self):
        if self.owner and self.population < self.max_population:
            self.population += self.population * self.population_growth_rate
            if self.population > self.max_population:
                self.population = self.max_population


class Moon(CelestialBody):
    """Represents a moon, which is colonisable."""
    def __init__(self, in_hex: HexCoord, in_system: str):
        super().__init__(position=Position(0.0, 0.0), in_hex=in_hex, in_system=in_system, inhibition_field_radius=1800.0)
        self.name = f"Moon {self.id}"
        self.owner: Optional[Player] = None
        self.population: float = 0
        self.max_population: float = 50.0
        self.population_growth_rate: float = 0.01

    def update_population(self):
        if self.owner and self.population < self.max_population:
            self.population += self.population * self.population_growth_rate
            if self.population > self.max_population:
                self.population = self.max_population


class ColonizableAsteroid(CelestialBody):
    """Represents a colonisable asteroid with population growth."""
    def __init__(self, in_hex: HexCoord, in_system: str):
        super().__init__(position=Position(0.0, 0.0), in_hex=in_hex, in_system=in_system, inhibition_field_radius=1200.0)
        self.name = f"Colonizable Asteroid {self.id}"
        self.owner: Optional[Player] = None
        self.population: float = 0
        self.max_population: float = 20.0
        self.population_growth_rate: float = 0.005

    def update_population(self):
        if self.owner and self.population < self.max_population:
            self.population += self.population * self.population_growth_rate
            if self.population > self.max_population:
                self.population = self.max_population

class MetalAsteroid(CelestialBody):
    """Represents a metal asteroid, which is a source of Metal."""
    def __init__(self, in_hex: HexCoord, in_system: str):
        super().__init__(position=Position(0.0, 0.0), in_hex=in_hex, in_system=in_system, inhibition_field_radius=1200.0)
        self.name = f"Metal Asteroid {self.id}"
        self.metal_yield: float = 10.0


class DebrisField(CelestialBody):
    """Represents a field of debris."""
    def __init__(self, in_hex: HexCoord, in_system: str):
        super().__init__(position=Position(0.0, 0.0), in_hex=in_hex, in_system=in_system)
        self.name = f"Debris Field {self.id}"

class AsteroidField(CelestialBody):
    """Represents a field of asteroids."""
    def __init__(self, in_hex: HexCoord, in_system: str):
        super().__init__(position=Position(0.0, 0.0), in_hex=in_hex, in_system=in_system, inhibition_field_radius=900.0)
        self.name = f"Asteroid Field {self.id}"
        self.asteroid_count = 100 # Example value

class IceField(CelestialBody):
    """Represents a field of ice particles."""
    def __init__(self, in_hex: HexCoord, in_system: str):
        super().__init__(position=Position(0.0, 0.0), in_hex=in_hex, in_system=in_system, inhibition_field_radius=600.0)
        self.name = f"Ice Field {self.id}"

class Nebula(CelestialBody):
    """Represents a nebula."""
    def __init__(self, in_hex: HexCoord, in_system: str, nebula_type: NebulaType):
        super().__init__(position=Position(0.0, 0.0), in_hex=in_hex, in_system=in_system, inhibition_field_radius=0.0)
        self.name = f"Nebula {self.id}"
        self.nebula_type = nebula_type

class Storm(CelestialBody):
    """Represents a storm."""
    def __init__(self, in_hex: HexCoord, in_system: str, storm_type: StormType):
        super().__init__(position=Position(0.0, 0.0), in_hex=in_hex, in_system=in_system, inhibition_field_radius=0.0)
        self.name = f"Storm {self.id}"
        self.storm_type = storm_type

class Comet(CelestialBody):
    """Represents a comet, which is a source of Crystal."""
    def __init__(self, in_hex: HexCoord, in_system: str):
        super().__init__(position=Position(0.0, 0.0), in_hex=in_hex, in_system=in_system, inhibition_field_radius=600.0)
        self.name = f"Comet {self.id}"
        self.crystal_yield: float = 10.0


# --- GameObject-derived Class: Minefield ---

class Minefield(GameObject):
    """Represents a deployed minefield hazard in a hex."""
    def __init__(self, owner: Player, position: Position, in_hex: HexCoord, in_system: str,
                 mines_remaining: int = int(MINEFIELD_DEFAULT_MINES),
                 mine_damage: float = MINEFIELD_DEFAULT_DAMAGE,
                 detonation_radius: float = MINEFIELD_DETONATION_RADIUS,
                 minefield_type: typing.Union[MinefieldType, str] = MinefieldType.ANTI_SHIP):
        super().__init__(position, in_hex, in_system)
        self.owner = owner
        if isinstance(minefield_type, str):
            try:
                self.minefield_type = MinefieldType(minefield_type)
            except ValueError:
                self.minefield_type = MinefieldType.ANTI_SHIP
        else:
            self.minefield_type = minefield_type
        self.name = f"{self.minefield_type.display_name} Minefield {self.id}"
        self.mines_remaining = mines_remaining
        self.mine_damage = mine_damage
        self.detonation_radius = detonation_radius
        self.revealed_to_player_ids: typing.Set[int] = set()

    def reveal_to(self, player: typing.Optional[Player]) -> None:
        """Permanently marks this minefield as revealed to the given player."""
        if player is not None:
            self.revealed_to_player_ids.add(player.id)

    def is_revealed_to(self, player: typing.Optional[Player]) -> bool:
        """Return True if this minefield has been revealed to the given player."""
        if player is None:
            return False
        return player.id in self.revealed_to_player_ids

    def can_target(self, unit: 'Unit') -> bool:
        """Return True if unit is a valid target for this minefield type."""
        if self.owner and unit.owner == self.owner:
            return False
        if unit.current_hit_points <= 0:
            return False
        if self.minefield_type == MinefieldType.ANTI_SHIP:
            return unit.hull_size != HullSize.STRIKECRAFT_WING
        elif self.minefield_type == MinefieldType.ANTI_STRIKECRAFT:
            return unit.hull_size == HullSize.STRIKECRAFT_WING
        return True

    def detonate_against(self, unit: 'Unit') -> float:
        """Detonates a mine against an enemy unit, applying net damage and reducing mine count."""
        if self.mines_remaining <= 0:
            return 0.0

        defenses = unit.get_component(Defenses)
        armor = defenses.armor if defenses else 0
        shields = defenses.shields if defenses else 0

        mitigation = (armor * 0.5) + (shields * 0.25)
        effective_damage = max(10.0, self.mine_damage - mitigation)

        if getattr(unit, 'damage_reduction', 0) > 0:
            effective_damage *= (1.0 - min(0.9, unit.damage_reduction))
        if getattr(unit, 'damage_amplification', 0) > 0:
            effective_damage *= (1.0 + unit.damage_amplification)

        damage_int = int(round(effective_damage))
        unit.current_hit_points = max(0, unit.current_hit_points - damage_int)
        self.mines_remaining -= 1

        logger.debug(f"{self.name} (Owner: {self.owner.name}) detonated against {unit.name}! Dealt {damage_int} damage. Mines remaining: {self.mines_remaining}")
        if unit.current_hit_points <= 0:
            unit.destroy()
        return damage_int


# --- GameObject-derived Class: Unit ---


class Unit(GameObject):
    """Represents a generic unit in the game, composed of various components."""
    def __init__(self, owner: Player, position: Position, in_hex: HexCoord, in_system: str, name: str,
                 hull_size: HullSize,
                 game: "Game",
                 template_name: typing.Optional[str] = None):
        super().__init__(position, in_hex, in_system)
        self.owner = owner
        self.name: str = name
        self.game = game
        self.in_galaxy: Optional['Galaxy'] = game.galaxy if game else None

        self.hull_size: HullSize = hull_size
        self.hull_capacity: float = HULL_CAPACITIES[self.hull_size] # consumed by components with hull_cost
        self.current_hull_usage: float = 0.0

        self.max_hit_points: int = HIT_POINTS[self.hull_size]
        self.current_hit_points: int = self.max_hit_points

        self.components: typing.Dict[type, UnitComponent] = {}

        # --- Status effects applied by abilities ---
        # Damage reduction (0.0 = none, 0.75 = 75% reduction). Stacks additively.
        self.damage_reduction: float = 0.0
        # Extra damage taken multiplier from Designate Target. Stacks additively.
        self.damage_amplification: float = 0.0
        # Ion Bolt disable: unit cannot move or attack while True.
        self.is_disabled: bool = False
        # Set of unit IDs that have applied a disable. Disable lifts when the set is empty.
        self.disabled_by_unit_ids: typing.Set[int] = set()
        # Lifetime in turns (None = permanent). Used by temporary units (Missile Platforms).
        self.lifetime: typing.Optional[int] = None
        # Flag to distinguish spawned temporary units from regular units.
        self.is_temporary: bool = False

        # Experience points earned through combat (0 – MAX_UNIT_XP).
        self.experience_points: int = 0

        self.template_name: typing.Optional[str] = template_name

        # Every unit has a commander component by default
        self.add_component(Commander(unit=self))
        # Every unit has an antimatter storage component by default
        self.add_component(AntimatterStorage(unit=self))
        # Every unit has baseline sensors by default (0 hull cost)
        self.add_component(Sensors(unit=self, short_range_radius=DEFAULT_SENSOR_SHORT_RANGE, long_range_hexes=0, hull_cost=0))

    def add_component(self, component: UnitComponent) -> None:
        self.components[type(component)] = component
        self._update_hull_usage()

    def get_component(self, component_type: type) -> typing.Optional[UnitComponent]:
        return self.components.get(component_type)
        
    def remove_component(self, component_type: type) -> None:
        if component_type in self.components:
            del self.components[component_type]
            self._update_hull_usage()

    @property
    def sensors_component(self) -> typing.Optional[Sensors]:
        return self.get_component(Sensors)

    @property
    def antimatter_component(self) -> typing.Optional[AntimatterStorage]:
        return self.get_component(AntimatterStorage)


    @property
    def harvester_component(self) -> typing.Optional[AntimatterHarvester]:
        return self.get_component(AntimatterHarvester)

    @property
    def engines_component(self) -> typing.Optional[Engines]:
        return self.get_component(Engines)


    @property
    def hyperdrive_component(self) -> typing.Optional[Hyperdrive]:
        return self.get_component(Hyperdrive)

    @property
    def inhibitor_component(self) -> typing.Optional[HyperspaceInhibitionFieldEmitter]:
        return self.get_component(HyperspaceInhibitionFieldEmitter)

    @property
    def weapons_component(self) -> typing.Optional[Weapons]:
        return self.get_component(Weapons)

    @property
    def colony_component(self) -> typing.Optional[ColonyComponent]:
        return self.get_component(ColonyComponent)

    @property
    def civilian_habitat_component(self) -> typing.Optional[CivilianHabitatComponent]:
        return self.get_component(CivilianHabitatComponent)

    @property
    def constructor_component(self) -> typing.Optional[Constructor]:
        return self.get_component(Constructor)

    @property
    def repair_component(self) -> typing.Optional[RepairComponent]:
        return self.get_component(RepairComponent)

    @property
    def mining_component(self) -> typing.Optional[MiningComponent]:
        return self.get_component(MiningComponent)

    @property
    def metal_refinery_component(self) -> typing.Optional[MetalRefineryComponent]:
        return self.get_component(MetalRefineryComponent)

    @property
    def crystal_refinery_component(self) -> typing.Optional[CrystalRefineryComponent]:
        return self.get_component(CrystalRefineryComponent)

    @property
    def hangar_component(self) -> typing.Optional[HangarComponent]:
        return self.get_component(HangarComponent)

    @property
    def strikecraft_bay_component(self) -> typing.Optional[StrikecraftBayComponent]:
        return self.get_component(StrikecraftBayComponent)

    @property
    def strikecraft_wing_component(self) -> typing.Optional[StrikecraftWingComponent]:
        return self.get_component(StrikecraftWingComponent)

    @property
    def ability_component(self) -> typing.Optional[AbilityComponent]:
        return self.get_component(AbilityComponent)

    @property
    def marines_component(self) -> typing.Optional[MarinesComponent]:
        return self.get_component(MarinesComponent)

    @property
    def cloaking_component(self) -> typing.Optional[CloakingDevice]:
        return self.get_component(CloakingDevice)

    @property
    def commander_component(self) -> Commander:
        return self.get_component(Commander)

    def gain_experience(self, amount: int) -> None:
        """Awards experience points to the unit, capped at MAX_UNIT_XP."""
        if self.experience_points >= MAX_UNIT_XP:
            return
        self.experience_points = min(MAX_UNIT_XP, self.experience_points + max(0, amount))

    def xp_multiplier(self, max_bonus: float) -> float:
        """Returns a linear scaling multiplier (1.0 at 0 XP, 1.0 + max_bonus at MAX_UNIT_XP)."""
        return 1.0 + max_bonus * (self.experience_points / MAX_UNIT_XP)

    def take_damage(self, amount: int, damage_type: Optional[TurretType] = None) -> None:
        """Reduces the unit's current hit points by the given amount, applying any active damage reduction and defenses mitigation."""
        if damage_type:
            defenses = self.get_component(Defenses)
            if defenses:
                mitigation = defenses.calculate_mitigation(amount, damage_type)
                amount = max(0, amount - mitigation)
                logger.debug(f"Unit '{self.name}' defenses mitigated {mitigation} damage. Remaining damage: {amount}")

        if self.damage_reduction > 0.0:
            amount = max(1, int(amount * (1.0 - self.damage_reduction)))
        self.current_hit_points -= amount
        if self.current_hit_points < 0:
            self.current_hit_points = 0
        logger.debug(f"Unit '{self.name}' takes {amount} damage. Current HP: {self.current_hit_points}/{self.max_hit_points}")

        if self.current_hit_points <= 0:
            self.current_hit_points = 0
            self.destroy()

    def take_component_damage(self, component_type: type, amount: int, damage_type: Optional[TurretType] = None) -> int:
        """
        Applies damage to a specific component. 
        Returns any excess damage (spillover) if the component is destroyed.
        """
        if damage_type:
            defenses = self.get_component(Defenses)
            if defenses:
                mitigation = defenses.calculate_mitigation(amount, damage_type)
                amount = max(0, amount - mitigation)
                logger.debug(f"Unit '{self.name}' defenses mitigated {mitigation} component damage. Remaining damage: {amount}")

        component = self.get_component(component_type)
        if not component or component.is_destroyed:
            return amount  # All damage spills over if component is missing or already destroyed

        logger.debug(f"Unit '{self.name}' component {component_type.__name__} takes {amount} damage.")
        component.current_hit_points -= amount
        spillover = 0
        
        if component.current_hit_points <= 0:
            spillover = abs(component.current_hit_points)
            component.current_hit_points = 0
            component.on_destroyed()
            logger.debug(f"Unit '{self.name}' component {component_type.__name__} has been destroyed!")

        return spillover

    def heal_hull(self, amount: int) -> int:
        """Heals the unit's hull by the given amount. Returns actual amount healed."""
        if self.current_hit_points >= self.max_hit_points:
            return 0
        healed = min(amount, self.max_hit_points - self.current_hit_points)
        self.current_hit_points += healed
        logger.debug(f"Unit '{self.name}' hull healed by {healed}. HP: {self.current_hit_points}/{self.max_hit_points}")
        return healed

    def heal_components(self, amount: int) -> int:
        """Heals damaged components by the given amount. Returns actual amount healed."""
        healed_total = 0
        for component in self.components.values():
            if amount <= 0:
                break
            if component.current_hit_points < component.max_hit_points:
                needed = component.max_hit_points - component.current_hit_points
                healed = min(amount, needed)
                component.current_hit_points += healed
                healed_total += healed
                amount -= healed
                logger.debug(f"Unit '{self.name}' component {type(component).__name__} healed by {healed}. HP: {component.current_hit_points}/{component.max_hit_points}")
        return healed_total

    def destroy(self) -> None:
        """Handles the destruction of the unit."""
        logger.debug(f"Unit '{self.name}' has been destroyed.")
        if self.hangar_component:
            for docked_unit in list(self.hangar_component.docked_units):
                docked_unit.destroy()
        if self.strikecraft_bay_component:
            for docked_unit in list(self.strikecraft_bay_component.docked_units):
                docked_unit.destroy()
        galaxy = self.in_galaxy or (self.game.galaxy if self.game else None)
        if galaxy:
            galaxy.remove_unit(self)
        if self.game:
            self.game.deselect_object(self)
            if getattr(self.game, 'sector_view_mouse_hover_object', None) == self:
                self.game.sector_view_mouse_hover_object = None
            if getattr(self.game, 'hovered_object', None) == self:
                self.game.hovered_object = None

    def _update_hull_usage(self) -> None:
        """Recalculates and updates the current hull usage based on installed components."""
        usage = sum(c.hull_cost for c in self.components.values())
        self.current_hull_usage = usage
        
        if hasattr(self, 'hull_capacity') and self.current_hull_usage > self.hull_capacity:
            logger.debug(f"Warning: Unit '{self.name}' created exceeding hull capacity! "
                  f"Usage: {self.current_hull_usage}, Capacity: {self.hull_capacity}")
        
    def update(self) -> None:
        """Update the unit's state, including updating its components (processing orders etc.).
        
        This method should be called on each turn processing cycle.
        """
        # Antimatter is no longer regenerated automatically for all units.
        # Only units with an AntimatterHarvester component can replenish their
        # own antimatter, and only while positioned near a star. All other
        # units must receive antimatter via TransferAntimatterOrder from
        # another unit's existing storage.
        if self.harvester_component and self.in_galaxy:
            self.harvester_component.update(self.in_galaxy)

        # --- Lifetime check for temporary units (e.g. Missile Platforms) ---

        if self.lifetime is not None:
            self.lifetime -= 1
            if self.lifetime <= 0:
                self.destroy()
                return

        # Update hyperdrive recharge status if applicable
        if self.hyperdrive_component:
            self.hyperdrive_component.update_recharge()

        # Tick the inhibitor field: consume antimatter, auto-deactivate if empty.
        if self.inhibitor_component:
            self.inhibitor_component.update()

        # Tick the cloaking device: consume antimatter, auto-deactivate if empty.
        if self.cloaking_component:
            self.cloaking_component.update()

        # Skip weapons updates for disabled units (Ion Bolt)
        if not self.is_disabled:
            if self.weapons_component and self.in_galaxy:
                self.weapons_component.update(self.in_galaxy)

        if self.constructor_component and self.in_galaxy:
            self.constructor_component.update(self.in_galaxy)

        if self.repair_component and self.in_galaxy:
            self.repair_component.update(self.in_galaxy)

        if self.mining_component and self.in_galaxy:
            self.mining_component.update(self.in_galaxy)

        # Tick ability cooldowns and apply ongoing ability effects
        if self.ability_component and self.in_galaxy:
            self.ability_component.update(self.in_galaxy)
            
        if self.strikecraft_bay_component and self.in_galaxy:
            self.strikecraft_bay_component.update(self.in_galaxy)
            
        if self.commander_component:
            self.commander_component.update()

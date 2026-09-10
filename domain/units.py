"""Units domain objects and ownership rules."""
from __future__ import annotations

import typing
from typing import TYPE_CHECKING, Any, Optional

from constants import (
    CELESTIAL_FIELD_RADIUS,
    DEBRIS_FIELD_DEFENSE_BONUS,
    DEFAULT_SENSOR_SHORT_RANGE,
    HIT_POINTS,
    HULL_CAPACITIES,
    ICE_FIELD_BEAM_DEFENSE_BONUS,
    MAX_UNIT_XP,
    HullSize,
)
from domain.celestials import (
    DebrisField,
    IceField,
    _normalize_sabotage_type,
    is_position_blocked_by_celestial_field,
    is_position_in_magnetic_storm,
)
from domain.coordinates import HexCoord
from domain.identity import GameObject
from domain.players import Player
from geometry import Position, distance
from unit_components.abilities import AbilityComponent
from unit_components.antimatter import AntimatterHarvester, AntimatterStorage
from unit_components.base import UnitComponent
from unit_components.civilian_habitat import CivilianHabitatComponent
from unit_components.cloaking import CloakingDevice
from unit_components.colony import ColonyComponent
from unit_components.commander import Commander
from unit_components.constructor import Constructor
from unit_components.defenses import Defenses
from unit_components.enums import SabotageType, TurretType
from unit_components.hangar import HangarComponent
from unit_components.inhibitor import HyperspaceInhibitionFieldEmitter
from unit_components.intelligence import Agent, IntelligenceComponent
from unit_components.marines import MarinesComponent
from unit_components.mining import (
    CrystalRefineryComponent,
    MetalRefineryComponent,
    MiningComponent,
)
from unit_components.movement import Engines, Hyperdrive
from unit_components.orbital_defense import OrbitalDefenseComponent
from unit_components.repair import RepairComponent
from unit_components.sensors import Sensors
from unit_components.strikecraft import (
    StrikecraftBayComponent,
    StrikecraftWingComponent,
)
from unit_components.trade import TradeComponent
from unit_components.weapons import Weapons

if TYPE_CHECKING:
    from galaxy import Galaxy
    from game import Game

import logging

logger = logging.getLogger(__name__)

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
        self.infiltrating_agents: typing.List[Agent] = []

        self.is_hidden_in_gas_giant: bool = False
        self.hidden_in_gas_giant_id: typing.Optional[int] = None

        # Every unit has a commander component by default
        self.add_component(Commander(unit=self))
        # Every unit has an antimatter storage component by default
        self.add_component(AntimatterStorage(unit=self))
        # Every unit has baseline sensors by default (0 hull cost)
        self.add_component(Sensors(unit=self, short_range_radius=DEFAULT_SENSOR_SHORT_RANGE, long_range_hexes=0, hull_cost=0))

    def add_component(self, component: UnitComponent) -> None:
        """Install the already-bound component under its exact concrete type.

        A different prior instance receives on_destroyed before replacement so its
        effects/jobs can release ownership. Hull usage is recalculated, but this
        primitive does not validate a design budget or charge construction costs.
        Cleanup failures propagate; there is no transactional rollback here.
        """
        existing = self.components.get(type(component))
        if existing is not None and existing is not component:
            existing.on_destroyed()
        self.components[type(component)] = component
        self._update_hull_usage()

    def get_component(self, component_type: type) -> typing.Optional[UnitComponent]:
        return self.components.get(component_type)
        
    def remove_component(self, component_type: type) -> None:
        """Release and remove an exact component type, or do nothing if absent.

        The component owns effect/job cleanup through on_destroyed. A cleanup
        exception propagates before removal; refit orders own costs and timing.
        """
        if component_type in self.components:
            self.components[component_type].on_destroyed()
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
    def orbital_defense_component(self) -> typing.Optional[OrbitalDefenseComponent]:
        return self.get_component(OrbitalDefenseComponent)

    @property
    def trade_component(self) -> typing.Optional[TradeComponent]:
        return self.get_component(TradeComponent)

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
    def intelligence_component(self) -> typing.Optional[IntelligenceComponent]:
        return self.get_component(IntelligenceComponent)

    @property
    def commander_component(self) -> Commander:
        return self.get_component(Commander)

    def has_infiltrating_agent_from(self, player: Optional['Player']) -> bool:
        """Returns True if this unit has an active agent belonging to the player."""
        if not player or not hasattr(self, 'infiltrating_agents'):
            return False
        return any(a.owner == player for a in self.infiltrating_agents)

    def get_infiltrating_agents_for_viewer(self, viewer: Optional['Player']) -> typing.List[Agent]:
        """Returns infiltrating agents visible to the viewer."""
        if not viewer or not hasattr(self, 'infiltrating_agents'):
            return []
        return [a for a in self.infiltrating_agents if a.owner == viewer or (a.is_discovered and self.owner == viewer)]

    def is_sabotaged(self, sabotage_type: typing.Union[str, SabotageType]) -> bool:
        """Returns True if this unit currently suffers from the specified sabotage."""
        if not hasattr(self, 'infiltrating_agents'):
            return False
        target_type = _normalize_sabotage_type(sabotage_type)
        return any(a.active_sabotage == target_type for a in self.infiltrating_agents)

    def apply_sabotage(self, agent: Agent, sabotage_type: typing.Union[str, SabotageType]) -> bool:
        """Apply sabotage through an attached agent, returning False if unattached.

        Callers enforce ownership and visibility before invoking this primitive.
        Unknown sabotage names raise ValueError. Antimatter drains immediately and
        hyperdrive sabotage starts recharge; other modifiers derive from agent state.
        """
        target_type = _normalize_sabotage_type(sabotage_type)
        if agent in getattr(self, 'infiltrating_agents', []):
            agent.active_sabotage = target_type
            logger.debug(f"Applied sabotage {target_type.name} to {self.name} via Agent {agent.id}.")
            if target_type == SabotageType.ANTIMATTER:
                am_comp = self.antimatter_component
                if am_comp and am_comp.current_amount > 0:
                    drained = am_comp.current_amount * 0.5
                    am_comp.consume(drained)
                    logger.debug(f"Antimatter sabotage drained {drained:.1f} AM from {self.name}.")
            elif target_type == SabotageType.HYPERDRIVE:
                hd = self.hyperdrive_component
                if hd:
                    from unit_components.enums import JumpStatus
                    hd.jump_status = JumpStatus.CHARGING
                    hd.recharge_time_remaining = max(hd.recharge_time_remaining, 3)
            return True
        return False

    def remove_agent(self, agent: Agent) -> bool:
        """Removes an agent from this unit."""
        if hasattr(self, 'infiltrating_agents') and agent in self.infiltrating_agents:
            self.infiltrating_agents.remove(agent)
            return True
        return False

    def gain_experience(self, amount: int) -> None:
        """Awards experience points to the unit, capped at MAX_UNIT_XP."""
        if self.experience_points >= MAX_UNIT_XP:
            return
        self.experience_points = min(MAX_UNIT_XP, self.experience_points + max(0, amount))

    def xp_multiplier(self, max_bonus: float) -> float:
        """Returns a linear scaling multiplier (1.0 at 0 XP, 1.0 + max_bonus at MAX_UNIT_XP)."""
        return 1.0 + max_bonus * (self.experience_points / MAX_UNIT_XP)

    def get_orbital_defense_buffs(self, galaxy: typing.Optional['Galaxy'] = None) -> typing.Tuple[float, float]:
        """Calculates the total additive attack and defense percentage bonuses granted to this
        unit by friendly active Orbital Defense units within effective radius in the current sector.

        Returns:
            (total_attack_bonus, total_defense_bonus): e.g. (0.40, 0.40) for two +20% auras.
        """
        if not self.owner or self.current_hit_points <= 0 or not self.in_system or self.in_hex is None or not self.position:
            return (0.0, 0.0)

        g = galaxy or self.in_galaxy
        if not g and self.game:
            g = getattr(self.game, 'galaxy', None)

        if not g:
            return (0.0, 0.0)

        system = g.systems.get(self.in_system)
        if not system:
            return (0.0, 0.0)

        hex_obj = system.hexes.get(self.in_hex)
        if not hex_obj:
            return (0.0, 0.0)

        total_atk = 0.0
        total_def = 0.0
        from geometry import distance

        for u in hex_obj.units:
            if (u.owner == self.owner or (self.owner and self.owner.is_allied_with(u.owner))) and u.current_hit_points > 0 and u.position:
                od_comp = getattr(u, 'orbital_defense_component', None)
                if od_comp and not od_comp.is_destroyed and od_comp.is_active(g):
                    if distance(self.position, u.position) <= od_comp.radius:
                        total_atk += od_comp.attack_bonus
                        total_def += od_comp.defense_bonus

        return (total_atk, total_def)

    def get_environmental_cover_bonus(self, damage_type: Optional[TurretType]) -> float:
        """Returns extra percentage damage reduction from environmental cover (e.g. IceField, DebrisField)."""
        if not damage_type or not self.in_system or self.in_hex is None or not self.position:
            return 0.0

        g = getattr(self, 'in_galaxy', None)
        if not g and getattr(self, 'game', None):
            g = getattr(self.game, 'galaxy', None)
        if not g:
            return 0.0

        system = g.systems.get(self.in_system)
        if not system:
            return 0.0

        hex_obj = system.hexes.get(self.in_hex)
        if not hex_obj:
            return 0.0

        cover_bonus = 0.0
        for body in hex_obj.celestial_bodies:
            radius = getattr(body, 'radius', CELESTIAL_FIELD_RADIUS)
            if distance(self.position, body.position) <= radius:
                is_beam = damage_type == TurretType.BEAM or (isinstance(damage_type, str) and damage_type.lower() == "beam")
                is_kinetic_missile = damage_type in (TurretType.MASS_DRIVER, TurretType.MISSILE) or (isinstance(damage_type, str) and damage_type.lower() in ("mass_driver", "missile", "kinetic"))
                if isinstance(body, IceField) and is_beam:
                    cover_bonus = max(cover_bonus, getattr(body, 'beam_defense_bonus', ICE_FIELD_BEAM_DEFENSE_BONUS))
                elif isinstance(body, DebrisField) and is_kinetic_missile:
                    cover_bonus = max(cover_bonus, getattr(body, 'defense_bonus', DEBRIS_FIELD_DEFENSE_BONUS))

        return cover_bonus

    @property
    def is_strikecraft_wing(self) -> bool:
        """Returns True if this unit has STRIKECRAFT_WING hull size."""
        return self.hull_size == HullSize.STRIKECRAFT_WING

    def is_in_magnetic_storm(self, position: Optional[Position] = None, galaxy_ref: Any = None) -> bool:
        """Returns True if this unit (or given position) is inside a magnetic storm."""
        g = galaxy_ref or getattr(self, "in_galaxy", None) or (getattr(self.game, "galaxy", None) if getattr(self, "game", None) else None)
        pos = position if position is not None else self.position
        return is_position_in_magnetic_storm(g, self.in_system, self.in_hex, pos)

    def is_in_dense_field(self, position: Optional[Position] = None, galaxy_ref: Any = None) -> bool:
        """Returns True if this unit (or given position) is inside a celestial field too dense for its hull."""
        g = galaxy_ref or getattr(self, "in_galaxy", None) or (getattr(self.game, "galaxy", None) if getattr(self, "game", None) else None)
        pos = position if position is not None else self.position
        return is_position_blocked_by_celestial_field(g, self.in_system, self.in_hex, pos, self)

    def take_damage(self, amount: int, damage_type: Optional[TurretType] = None, *, is_splash: bool = False) -> None:
        """Reduces the unit's current hit points by the given amount, applying any active damage reduction, environmental cover, and defenses mitigation."""
        if amount <= 0:
            return
        if is_splash:
            from environmental_effects import splash_damage
            amount = splash_damage(amount, self)
        if damage_type:
            cover = self.get_environmental_cover_bonus(damage_type)
            if cover > 0.0:
                cover_mitigation = amount * cover
                amount = max(0, int(round(amount - cover_mitigation)))
            defenses = self.get_component(Defenses)
            if defenses:
                mitigation = defenses.calculate_mitigation(amount, damage_type)
                if self.is_sabotaged(SabotageType.DEFENSES):
                    mitigation *= 0.5
                amount = max(0, int(round(amount - mitigation)))
                logger.debug(f"Unit '{self.name}' defenses mitigated {mitigation} damage. Remaining damage: {amount}")

        reduction = max(0.0, min(1.0, self.damage_reduction))
        if reduction > 0.0:
            amount = max(0, int(amount * (1.0 - reduction)))
        if amount <= 0:
            return
        self.current_hit_points -= amount
        if self.current_hit_points < 0:
            self.current_hit_points = 0
        logger.debug(f"Unit '{self.name}' takes {amount} damage. Current HP: {self.current_hit_points}/{self.max_hit_points}")

        if self.current_hit_points <= 0:
            self.current_hit_points = 0
            self.destroy()

    def take_component_damage(self, component_type: type, amount: int, damage_type: Optional[TurretType] = None, *, apply_reduction: bool = False) -> int:
        """
        Applies damage to a specific component. 
        Returns any excess damage (spillover) if the component is destroyed.
        """
        if damage_type:
            cover = self.get_environmental_cover_bonus(damage_type)
            if cover > 0.0:
                cover_mitigation = amount * cover
                amount = max(0, int(round(amount - cover_mitigation)))
            defenses = self.get_component(Defenses)
            if defenses:
                mitigation = defenses.calculate_mitigation(amount, damage_type)
                if self.is_sabotaged(SabotageType.DEFENSES):
                    mitigation *= 0.5
                amount = max(0, int(round(amount - mitigation)))
                logger.debug(f"Unit '{self.name}' defenses mitigated {mitigation} component damage. Remaining damage: {amount}")

        if apply_reduction:
            amount = int(amount * (1 - max(0.0, min(1.0, self.damage_reduction))))

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
        """Permanently detach this unit and destroy its stored craft, once.

        Releases component effects, interrupts orders, severs carrier/target links,
        updates galaxy membership and clears application selection references.
        Repeated calls are no-ops; programming failures propagate without rollback.
        """
        if getattr(self, "_destroyed", False):
            return
        self._destroyed = True
        from campaign_graph import detach_unit, iter_units
        galaxy = self.in_galaxy or getattr(self.game, "galaxy", None)
        for component in list(self.components.values()):
            component.on_destroyed()
        if galaxy:
            for source, _ in list(iter_units(galaxy)):
                wing = source.strikecraft_wing_component
                if wing and wing.mother_carrier is self:
                    wing.mother_carrier = None
                abilities = source.ability_component
                if abilities:
                    for atype, effect in abilities.abilities.items():
                        if effect.target_unit_id == self.id:
                            abilities._expire_ability(atype, galaxy)
                        if self.id in effect.spawned_unit_ids:
                            effect.spawned_unit_ids.remove(self.id)
        from order_history import interrupt_unit_orders
        interrupt_unit_orders(self, "unit_destroyed")
        logger.debug(f"Unit '{self.name}' has been destroyed.")
        if self.hangar_component:
            for docked_unit in list(self.hangar_component.docked_units):
                docked_unit.destroy()
        if self.strikecraft_bay_component:
            for docked_unit in list(self.strikecraft_bay_component.docked_units):
                docked_unit.destroy()
        if getattr(self, 'is_hidden_in_gas_giant', False) or getattr(self, 'hidden_in_gas_giant_id', None) is not None:
            galaxy = self.in_galaxy or (self.game.galaxy if self.game else None)
            if galaxy and self.hidden_in_gas_giant_id is not None:
                gas_giant = galaxy.get_celestial_body_by_id(self.hidden_in_gas_giant_id)
                if gas_giant and hasattr(gas_giant, 'hidden_units') and self in gas_giant.hidden_units:
                    gas_giant.hidden_units.remove(self)
        galaxy = self.in_galaxy or (self.game.galaxy if self.game else None)
        if galaxy:
            detach_unit(self, galaxy)
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
        if getattr(self, 'is_hidden_in_gas_giant', False):
            # Units hidden in a gas giant cannot harvest from stars, tick external fields, or attack
            if self.commander_component:
                self.commander_component.update()
            return
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
            
        if self.intelligence_component:
            self.intelligence_component.update()

        if self.commander_component:
            self.commander_component.update()

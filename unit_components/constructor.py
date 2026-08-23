import logging
import typing
from typing import Optional, TYPE_CHECKING
import dataclasses

from .base import UnitComponent
from .antimatter import AntimatterStorage, AntimatterHarvester
from .movement import Engines, Hyperdrive
from .weapons import Weapons, Turret
from .defenses import Defenses
from .inhibitor import HyperspaceInhibitionFieldEmitter
from .repair import RepairComponent
from .colony import ColonyComponent
from .civilian_habitat import CivilianHabitatComponent
from .orbital_defense import OrbitalDefenseComponent
from .trade import TradeComponent
from .mining import MiningComponent, MetalRefineryComponent, CrystalRefineryComponent
from .hangar import HangarComponent
from .strikecraft import StrikecraftWingComponent, StrikecraftBayComponent
from .abilities import AbilityComponent
from .sensors import Sensors
from .minelayer import MinelayerComponent
from .marines import MarinesComponent
from .cloaking import CloakingDevice
from .intelligence import IntelligenceComponent
from .enums import (
    HyperdriveType, UnitStance, TurretType, TurretVariant,
    WingType, AbilityType, CloakingType
)

from utils import HexCoord
from geometry import Position
from constants import (
    DEFAULT_ANTIMATTER_CAPACITY, DEFAULT_ANTIMATTER_HARVEST_RATE,
    ANTIMATTER_HARVESTER_HULL_COST, MINELAYER_HULL_COST,
    DEFAULT_JUMP_RANGE, HullSize, DEFAULT_SENSOR_SHORT_RANGE, REPAIR_CREDIT_COST_PER_HP
)


from unit_templates import UNIT_TEMPLATES

if TYPE_CHECKING:
    from entities import Unit, Player
    from galaxy import Galaxy
    from game import Game

logger = logging.getLogger(__name__)


def instantiate_unit_from_template(
    template_name: str,
    owner: 'Player',
    system_name: str,
    hex_coord: 'HexCoord',
    position: 'Position',
    galaxy: 'Galaxy',
    game: 'Game',
) -> None:
    """Module-level helper that builds a :class:`~entities.Unit` from a
    template entry in :data:`~unit_templates.UNIT_TEMPLATES` and adds it to
    *galaxy*.

    This is the canonical instantiation routine.  :meth:`Constructor.
    create_unit_from_template` is a thin wrapper around this function so that
    both the constructor component **and** :func:`~game.Game.spawn_units` can
    share the same logic without code duplication.
    """
    from entities import Unit  # avoid circular import

    template = UNIT_TEMPLATES.get(template_name)
    if not template:
        logger.debug(f"Error: Unit template '{template_name}' not found.")
        return

    system = galaxy.systems.get(system_name)
    if not system:
        logger.debug(f"Error: System '{system_name}' not found for unit creation.")
        return

    hull_size_val = template["hull_size"]
    if isinstance(hull_size_val, str):
        hull_size_val = HullSize[hull_size_val.upper()]

    new_unit = Unit(
        owner=owner,
        name=template["name"],
        hull_size=hull_size_val,
        game=game,
        in_system=system_name,
        in_hex=hex_coord,
        position=position,
        template_name=template.get("name", template_name)
    )

    if template.get("has_antimatter_storage", True):
        from custom_unit_templates import calc_antimatter_hull_cost
        cap = float(template.get("antimatter_capacity", DEFAULT_ANTIMATTER_CAPACITY))
        cost = template.get("antimatter_hull_cost")
        if cost is None:
            cost = calc_antimatter_hull_cost(cap)
        new_unit.add_component(AntimatterStorage(new_unit, max_capacity=cap, hull_cost=cost))
    elif template.get("has_antimatter_storage") is False:
        new_unit.remove_component(AntimatterStorage)

    if template.get("has_antimatter_harvester"):
        new_unit.add_component(AntimatterHarvester(
            new_unit,
            harvest_rate=template.get("antimatter_harvest_rate", DEFAULT_ANTIMATTER_HARVEST_RATE),
            hull_cost=template.get("antimatter_harvester_hull_cost", ANTIMATTER_HARVESTER_HULL_COST)
        ))

    if template.get("has_engine"):
        speed = template.get("engine_speed", 0)
        new_unit.add_component(Engines(new_unit, speed=speed, hull_cost=template.get("engine_hull_cost", 0)))

    if template.get("has_hyperdrive"):
        htype_raw = template.get("hyperdrive_type", HyperdriveType.BASIC)
        if isinstance(htype_raw, str):
            raw_upper = htype_raw.upper()
            if raw_upper == "ADVANCED":
                htype = HyperdriveType.ADVANCED
            elif raw_upper == "BASIC":
                htype = HyperdriveType.BASIC
            else:
                try:
                    htype = HyperdriveType(htype_raw.lower())
                except ValueError:
                    htype = HyperdriveType.BASIC
        else:
            htype = htype_raw

        hull_size = new_unit.hull_size
        if hull_size == HullSize.TINY and htype == HyperdriveType.ADVANCED:
            logger.warning(f"Warning: Attempted to add ADVANCED hyperdrive to TINY unit template '{template_name}'. Downgrading to BASIC.")
            htype = HyperdriveType.BASIC

        cost = template.get("hyperdrive_hull_cost")
        if cost is None or cost == 0:
            cost = 5.0 if htype == HyperdriveType.BASIC else 10.0
        jump_range = template.get("hyperdrive_jump_range", DEFAULT_JUMP_RANGE)
        new_unit.add_component(Hyperdrive(new_unit, drive_type=htype, hull_cost=cost, jump_range=jump_range))

    if template.get("has_weapon_bays"):
        weapons_comp = Weapons(new_unit, hull_cost=template.get("weapon_bays_hull_cost", 0))
        for turret_def in template.get("turrets", []):
            variant_str = turret_def.get("variant", "STANDARD")
            try:
                variant = TurretVariant[variant_str.upper()]
            except (KeyError, ValueError, AttributeError):
                variant = TurretVariant.STANDARD

            turret = Turret(
                turret_type=TurretType[turret_def["type"]],
                damage=turret_def["damage"],
                range=turret_def["range"],
                cooldown=turret_def["cooldown"],
                parent_unit=new_unit,
                variant=variant
            )
            weapons_comp.add_turret(turret)
        new_unit.add_component(weapons_comp)

    if template.get("has_defenses"):
        new_unit.add_component(Defenses(
            new_unit,
            armor=template.get("armor", 0),
            shields=template.get("shields", 0),
            point_defense=template.get("point_defense", 0),
            hull_cost=template.get("defenses_hull_cost", 0)
        ))

    if template.get("has_constructor_component"):
        new_unit.add_component(Constructor(new_unit, hull_cost=template.get("constructor_hull_cost", 0)))

    if template.get("has_repair_component"):
        r_rate = template.get("repair_rate", 10.0)
        r_cost = template.get("repair_hull_cost")
        if r_cost is None:
            from custom_unit_templates import calc_repair_hull_cost
            r_cost = calc_repair_hull_cost(r_rate)
        new_unit.add_component(RepairComponent(
            new_unit,
            repair_rate=r_rate,
            repair_range=template.get("repair_range", 200.0),
            credit_cost_per_hp=template.get("credit_cost_per_hp", REPAIR_CREDIT_COST_PER_HP),
            hull_cost=r_cost
        ))

    if template.get("has_mining_component"):
        m_rate = template.get("mining_rate", 10.0)
        m_cargo = template.get("max_mining_cargo", 100.0)
        m_cost = template.get("mining_hull_cost")
        if m_cost is None:
            from custom_unit_templates import calc_mining_hull_cost
            m_cost = calc_mining_hull_cost(m_rate, m_cargo)
        new_unit.add_component(MiningComponent(
            new_unit,
            mining_rate=m_rate,
            mining_range=template.get("mining_range", 200.0),
            max_cargo=m_cargo,
            hull_cost=m_cost
        ))

    if template.get("has_metal_refinery_component"):
        new_unit.add_component(MetalRefineryComponent(
            new_unit,
            unload_range=template.get("unload_range", 300.0),
            hull_cost=template.get("metal_refinery_hull_cost", 20.0)
        ))

    if template.get("has_crystal_refinery_component"):
        new_unit.add_component(CrystalRefineryComponent(
            new_unit,
            unload_range=template.get("unload_range", 300.0),
            hull_cost=template.get("crystal_refinery_hull_cost", 20.0)
        ))

    if template.get("has_hangar"):
        hull_size = new_unit.hull_size
        if hull_size in (HullSize.TINY, HullSize.SMALL, HullSize.MEDIUM):
            logger.warning(f"Warning: Attempted to add hangar to forbidden hull size {hull_size.name} in template '{template_name}'. Skipping.")
        else:
            h_slots = template.get("hangar_slots", 0)
            h_cost = template.get("hangar_hull_cost")
            if h_cost is None:
                from custom_unit_templates import calc_hangar_hull_cost
                h_cost = calc_hangar_hull_cost(h_slots)
            new_unit.add_component(HangarComponent(
                new_unit,
                max_slots=h_slots,
                hull_cost=h_cost
            ))

    if template.get("has_strikecraft_bay"):
        hull_size = new_unit.hull_size
        if hull_size in (HullSize.STRIKECRAFT_WING, HullSize.TINY, HullSize.SMALL):
            logger.warning(f"Warning: Attempted to add strikecraft bay to forbidden hull size {hull_size.name} in template '{template_name}'. Skipping.")
        else:
            sb_slots = template.get("strikecraft_bay_slots", 0)
            sb_cost = template.get("strikecraft_bay_hull_cost")
            if sb_cost is None:
                from custom_unit_templates import calc_strikecraft_bay_hull_cost
                sb_cost = calc_strikecraft_bay_hull_cost(sb_slots)
            new_unit.add_component(StrikecraftBayComponent(
                new_unit,
                max_slots=sb_slots,
                hull_cost=sb_cost
            ))

    if new_unit.hull_size == HullSize.STRIKECRAFT_WING:
        wing_type_str = template.get("wing_type", "FIGHTER")
        try:
            wing_type = WingType[wing_type_str.upper()]
        except (KeyError, ValueError, AttributeError):
            wing_type = WingType.FIGHTER
        new_unit.add_component(StrikecraftWingComponent(new_unit, wing_type=wing_type))

    if template.get("has_colony_component"):
        new_unit.add_component(ColonyComponent(
            new_unit,
            hull_cost=template.get("colony_hull_cost", 10.0)
        ))

    if template.get("has_civilian_habitat_component"):
        bonus = float(template.get("civilian_habitat_bonus", 50.0))
        cost = template.get("civilian_habitat_hull_cost")
        if cost is None:
            from custom_unit_templates import calc_civilian_habitat_hull_cost
            cost = calc_civilian_habitat_hull_cost(bonus)
        new_unit.add_component(CivilianHabitatComponent(
            new_unit,
            economic_bonus=bonus,
            hull_cost=cost
        ))

    if template.get("has_orbital_defense_component"):
        cost = template.get("orbital_defense_hull_cost", 20.0)
        radius = float(template.get("orbital_defense_radius", 500.0))
        atk_bonus = float(template.get("orbital_defense_attack_bonus", 0.20))
        def_bonus = float(template.get("orbital_defense_defense_bonus", 0.20))
        new_unit.add_component(OrbitalDefenseComponent(
            new_unit,
            radius=radius,
            attack_bonus=atk_bonus,
            defense_bonus=def_bonus,
            hull_cost=float(cost)
        ))

    if template.get("has_trade_component"):
        cost = template.get("trade_hull_cost", 10.0)
        mult = template.get("trade_revenue_multiplier", 1.0)
        new_unit.add_component(TradeComponent(
            new_unit,
            hull_cost=float(cost),
            trade_revenue_multiplier=float(mult)
        ))

    if template.get("has_inhibitor"):
        inh_radius = template.get("inhibitor_radius", 100.0)
        inh_cost = template.get("inhibitor_hull_cost")
        if inh_cost is None:
            from custom_unit_templates import calc_inhibitor_hull_cost
            inh_cost = calc_inhibitor_hull_cost(inh_radius)
        new_unit.add_component(HyperspaceInhibitionFieldEmitter(
            new_unit,
            radius=inh_radius,
            hull_cost=inh_cost
        ))

    if template.get("has_ability_component"):
        raw_ability_names = template.get("abilities", [])
        ability_types = []
        for aname in raw_ability_names:
            try:
                ability_types.append(AbilityType(aname))
            except ValueError:
                logger.warning(f"[instantiate_unit_from_template] Unknown ability '{aname}' in template '{template_name}'. Skipping.")
        if ability_types:
            new_unit.add_component(AbilityComponent(
                new_unit,
                ability_types=ability_types,
                hull_cost=template.get("ability_hull_cost", 10.0)
            ))

    # Sensors: prefer explicit new flags; fall back to legacy has_scanner.
    has_sensors = template.get("has_sensors", template.get("has_scanner", False))
    if has_sensors:
        short_range = template.get("sensor_short_range", DEFAULT_SENSOR_SHORT_RANGE)
        long_range_hexes = template.get("sensor_long_range_hexes", 0)
        hull_cost = template.get(
            "sensors_hull_cost",
            template.get("scanner_hull_cost", 0),
        )
        new_unit.remove_component(Sensors)
        new_unit.add_component(Sensors(
            new_unit,
            short_range_radius=short_range,
            long_range_hexes=long_range_hexes,
            hull_cost=hull_cost,
        ))

    if template.get("has_minelayer_component"):
        new_unit.add_component(MinelayerComponent(
            new_unit,
            hull_cost=template.get("minelayer_hull_cost", MINELAYER_HULL_COST)
        ))

    if template.get("has_marines_component"):
        m_count = template.get("marines_count", 10)
        m_cost = template.get("marines_hull_cost")
        if m_cost is None:
            from custom_unit_templates import calc_marines_hull_cost
            m_cost = calc_marines_hull_cost(m_count)
        new_unit.add_component(MarinesComponent(
            new_unit,
            marines_count=m_count,
            hull_cost=m_cost
        ))

    if template.get("has_cloaking_device"):
        from unit_components.cloaking import CloakingDevice
        from unit_components.enums import CloakingType
        from constants import CLOAKING_BASIC_HULL_COST, DEFAULT_ADVANCED_CLOAKING_RADIUS
        c_type_raw = template.get("cloaking_type", "BASIC")
        c_type = CloakingType.ADVANCED if str(c_type_raw).upper() == "ADVANCED" else CloakingType.BASIC
        c_radius = float(template.get("cloaking_radius", DEFAULT_ADVANCED_CLOAKING_RADIUS)) if c_type == CloakingType.ADVANCED else 0.0
        c_cost = float(template.get("cloaking_hull_cost", CloakingDevice.calc_hull_cost(c_type, c_radius)))
        new_unit.add_component(CloakingDevice(new_unit, device_type=c_type, area_radius=c_radius, hull_cost=c_cost))

    if template.get("has_intelligence_component"):
        i_count = template.get("intelligence_agents_count", 1)
        i_ci = template.get("has_counter_intelligence", False)
        i_cost = template.get("intelligence_hull_cost")
        if i_cost is None:
            i_cost = IntelligenceComponent.calc_hull_cost(i_count, i_ci)
        new_unit.add_component(IntelligenceComponent(
            new_unit,
            agents_count=i_count,
            agents_capacity=i_count,
            has_counter_intelligence=i_ci,
            hull_cost=i_cost
        ))

    system.add_unit(new_unit)

    logger.debug(f"Created unit {new_unit.name} ({new_unit.id}) for player {owner.id} in {system_name} at {hex_coord}")


@dataclasses.dataclass
class BuildableUnit:
    unit_template_name: str
    time_to_build: int
    cost_credits: int


class Constructor(UnitComponent):
    """A component that allows a unit to construct other units (stations) and refit friendly units."""
    DISPLAY_NAME: str = "Constructor"
    SIDEBAR_ORDER: int = 5
    build_range: float = 500.0
    
    # Construction state
    current_construction_target: Optional[tuple[str, Position]] = None # (unit_template_name, position)
    construction_progress: int = 0
    time_to_build: int = 0

    # Refit state
    current_refit_target: Optional[dict] = None
    refit_progress: int = 0
    refit_time: int = 0

    def __init__(self, unit: 'Unit', hull_cost: float = 15.0, buildable_unit_names: typing.Optional[list[str]] = None):
        super().__init__(unit, hull_cost)
        self.current_construction_target = None
        self.construction_progress = 0
        self.time_to_build = 0
        self.current_refit_target = None
        self.refit_progress = 0
        self.refit_time = 0

    def get_sidebar_data(self, game_state: 'Game') -> list[dict]:
        data = super().get_sidebar_data(game_state)
        if self.current_construction_target:
            target_name = self.current_construction_target[0]
            progress = self.construction_progress
            total = self.time_to_build
            data.append({'type': 'label', 'text': f"Constructing: {target_name}", 'object_id': '#sidebar_info_label', 'height': 25})
            data.append({
                'type': 'progress_bar',
                'progress': progress,
                'total': total,
                'height': 25
            })
        elif self.current_refit_target:
            tgt_id = self.current_refit_target.get("target_unit_id")
            action = self.current_refit_target.get("action", "REFIT")
            comp_name = self.current_refit_target.get("component_type", "Component")
            tgt_unit = game_state.galaxy.get_unit_by_id(tgt_id) if (game_state and game_state.galaxy) else None
            tgt_name = tgt_unit.name if tgt_unit else f"Unit #{tgt_id}"
            action_desc = f"+{comp_name}" if action.upper() == "ADD" else f"-{comp_name}"
            data.append({'type': 'label', 'text': f"Refitting {tgt_name}: {action_desc}", 'object_id': '#sidebar_info_label', 'height': 25})
            data.append({
                'type': 'progress_bar',
                'progress': self.refit_progress,
                'total': self.refit_time,
                'height': 25
            })
        else:
            data.append({'type': 'label', 'text': "Status: Idle", 'object_id': '#sidebar_info_label', 'height': 20})
        return data

    def get_basic_sidebar_data(self, game_state: 'Game') -> list[dict]:
        data = super().get_basic_sidebar_data(game_state)
        if self.is_destroyed:
            return data
        if self.current_construction_target:
            target_name = self.current_construction_target[0]
            pct = int((self.construction_progress / self.time_to_build) * 100) if self.time_to_build > 0 else 100
            status_str = f"Constructing {target_name} ({pct}%)"
            obj_id = '#sidebar_status_active_label'
        elif self.current_refit_target:
            tgt_id = self.current_refit_target.get("target_unit_id")
            action = self.current_refit_target.get("action", "REFIT")
            comp_name = self.current_refit_target.get("component_type", "Component")
            pct = int((self.refit_progress / self.refit_time) * 100) if self.refit_time > 0 else 100
            action_desc = f"+{comp_name}" if action.upper() == "ADD" else f"-{comp_name}"
            status_str = f"Refitting #{tgt_id} ({action_desc}) ({pct}%)"
            obj_id = '#sidebar_status_active_label'
        else:
            status_str = "Idle"
            obj_id = '#sidebar_status_idle_label'
        data.append({
            'type': 'label',
            'text': f"• Construction: {status_str}",
            'object_id': obj_id,
            'height': 18,
            'indent_level': 1
        })
        return data

    @property
    def buildable_units(self) -> list[BuildableUnit]:
        """Dynamically retrieve all buildable units based on UNIT_TEMPLATES."""
        buildables = []
        for name, template in UNIT_TEMPLATES.items():
            buildables.append(BuildableUnit(
                unit_template_name=name,
                time_to_build=template.get("build_time", 10),
                cost_credits=template.get("build_cost", 500)
            ))
        return buildables

    def can_build(self, unit_template_name: str) -> Optional[BuildableUnit]:
        """Check if this constructor can build a specific unit type."""
        template = UNIT_TEMPLATES.get(unit_template_name)
        if template:
            return BuildableUnit(
                unit_template_name=unit_template_name,
                time_to_build=template.get("build_time", 10),
                cost_credits=template.get("build_cost", 500)
            )
        return None

    def refresh_buildable_units(self, additional_names: typing.List[str]) -> None:
        """Append template names to buildable_units if not already present. (Deprecated/No-op)"""
        pass

    def start_construction(self, unit_template_name: str, position: Position, galaxy: 'Galaxy') -> bool:
        """Starts the construction of a new unit."""
        if self.is_destroyed:
            return False

        buildable = self.can_build(unit_template_name)
        if not buildable:
            logger.debug(f"Error: {self.unit.name} cannot build {unit_template_name}.")
            return False

        owner = self.unit.owner
        if owner.credits < buildable.cost_credits:
            logger.debug(f"Error: Not enough credits to build {unit_template_name}.")
            return False
        owner.credits -= buildable.cost_credits

        self.current_construction_target = (unit_template_name, position)
        self.time_to_build = buildable.time_to_build
        self.construction_progress = 0
        logger.debug(f"{self.unit.name} started constructing {unit_template_name} at {position}. Cost: {buildable.cost_credits}")
        return True

    def cancel_construction(self):
        """Cancels the current construction project."""
        if self.current_construction_target:
            logger.debug(f"Construction of {self.current_construction_target[0]} cancelled.")
            # NOTE: Resource refund should be handled by the Order
            self.current_construction_target = None
            self.construction_progress = 0
            self.time_to_build = 0

    def start_refit(self, target_unit: 'Unit', action: str, component_type: str, component_config: Optional[dict] = None, cost_credits: Optional[int] = 0, time_to_build: Optional[int] = 1) -> bool:
        """Starts a refit operation on a target unit."""
        if self.is_destroyed:
            return False

        cost_credits = int(cost_credits or 0)
        time_to_build = int(time_to_build or 1)

        owner = self.unit.owner
        if cost_credits > 0:
            if owner.credits < cost_credits:
                logger.debug(f"Error: Not enough credits to refit {target_unit.name}.")
                return False
            owner.credits -= cost_credits

        self.current_refit_target = {
            "target_unit_id": target_unit.id,
            "action": action,
            "component_type": component_type,
            "component_config": component_config or {},
            "cost_credits": cost_credits,
            "time_to_build": time_to_build,
        }
        self.refit_time = max(1, time_to_build)
        self.refit_progress = 0
        logger.debug(f"{self.unit.name} started refit ({action} {component_type}) on {target_unit.name}. Cost: {cost_credits}, Time: {self.refit_time}")
        return True

    def cancel_refit(self):
        """Cancels the current refit operation."""
        if self.current_refit_target:
            logger.debug(f"Refit on unit {self.current_refit_target.get('target_unit_id')} cancelled.")
            self.current_refit_target = None
            self.refit_progress = 0
            self.refit_time = 0

    def update(self, galaxy: 'Galaxy'):
        """Updates the construction or refit progress. Called each turn."""
        if self.is_destroyed:
            return
        if self.current_construction_target:
            self.construction_progress += 1
            if self.construction_progress >= self.time_to_build:
                self.finish_construction(galaxy)
        elif self.current_refit_target:
            self.refit_progress += 1
            if self.refit_progress >= self.refit_time:
                self.finish_refit(galaxy)

    def create_unit_from_template(self, galaxy: 'Galaxy', template_name: str, owner: 'Player', system_name: str, hex_coord: 'HexCoord', position: 'Position'):
        """Creates a new unit based on the template.

        Delegates to the module-level :func:`instantiate_unit_from_template`
        helper, passing ``self.unit.game`` as the game context.
        """
        instantiate_unit_from_template(
            template_name=template_name,
            owner=owner,
            system_name=system_name,
            hex_coord=hex_coord,
            position=position,
            galaxy=galaxy,
            game=self.unit.game,
        )

    def finish_construction(self, galaxy: 'Galaxy'):
        """Finalizes the construction and creates the new unit."""
        if not self.current_construction_target:
            return

        unit_template_name, position = self.current_construction_target
        logger.debug(f"Construction of {unit_template_name} finished by {self.unit.name}.")
        
        self.create_unit_from_template(
            galaxy=galaxy,
            template_name=unit_template_name,
            owner=self.unit.owner,
            system_name=self.unit.in_system,
            hex_coord=self.unit.in_hex,
            position=position
        )

        # Construction complete; reset building state variables.
        self.current_construction_target = None
        self.construction_progress = 0
        self.time_to_build = 0

    def finish_refit(self, galaxy: 'Galaxy'):
        """Finalizes the refit operation on the target unit."""
        if not self.current_refit_target:
            return

        target_unit_id = self.current_refit_target["target_unit_id"]
        action = self.current_refit_target["action"]
        component_type_name = self.current_refit_target["component_type"]
        config = self.current_refit_target.get("component_config", {})

        target_unit = galaxy.get_unit_by_id(target_unit_id)
        if target_unit and target_unit.current_hit_points > 0:
            if action.upper() == "ADD":
                comp = instantiate_component_for_unit(component_type_name, target_unit, config)
                if comp:
                    if target_unit.current_hull_usage + comp.hull_cost > target_unit.hull_capacity:
                        logger.warning(
                            f"Refit failed on completion: Exceeds hull capacity of {target_unit.name} "
                            f"({target_unit.current_hull_usage + comp.hull_cost:.1f}/{target_unit.hull_capacity:.1f})."
                        )
                    else:
                        target_unit.add_component(comp)
                        logger.debug(f"Successfully added {component_type_name} to {target_unit.name}.")
            elif action.upper() == "REMOVE":
                comp_cls = get_component_class_by_name(component_type_name)
                if comp_cls and comp_cls in target_unit.components:
                    comp = target_unit.components[comp_cls]
                    if hasattr(comp, 'is_active') and comp.is_active:
                        comp.is_active = False
                    target_unit.remove_component(comp_cls)
                    logger.debug(f"Successfully removed {component_type_name} from {target_unit.name}.")

        self.current_refit_target = None
        self.refit_progress = 0
        self.refit_time = 0


COMPONENT_NAME_MAP = {
    "Engines": Engines,
    "Hyperdrive": Hyperdrive,
    "Weapons": Weapons,
    "Defenses": Defenses,
    "AntimatterHarvester": AntimatterHarvester,
    "AntimatterStorage": AntimatterStorage,
    "Sensors": Sensors,
    "RepairComponent": RepairComponent,
    "MiningComponent": MiningComponent,
    "MetalRefineryComponent": MetalRefineryComponent,
    "CrystalRefineryComponent": CrystalRefineryComponent,
    "HangarComponent": HangarComponent,
    "StrikecraftBayComponent": StrikecraftBayComponent,
    "ColonyComponent": ColonyComponent,
    "CivilianHabitatComponent": CivilianHabitatComponent,
    "OrbitalDefenseComponent": OrbitalDefenseComponent,
    "OrbitalDefense": OrbitalDefenseComponent,
    "TradeComponent": TradeComponent,
    "Trade": TradeComponent,
    "HyperspaceInhibitionFieldEmitter": HyperspaceInhibitionFieldEmitter,
    "Inhibitor": HyperspaceInhibitionFieldEmitter,
    "AbilityComponent": AbilityComponent,
    "MinelayerComponent": MinelayerComponent,
    "MarinesComponent": MarinesComponent,
    "CloakingDevice": CloakingDevice,
    "IntelligenceComponent": IntelligenceComponent,
    "Intelligence": IntelligenceComponent,
    "Constructor": Constructor,
}


def get_component_class_by_name(name: str) -> Optional[type]:
    """Retrieve the UnitComponent class matching the provided component name string."""
    return COMPONENT_NAME_MAP.get(name)


def get_component_hull_cost(component_name: str, unit: 'Unit', config: Optional[dict] = None) -> float:
    """Calculate the hull cost for a given component configuration and target unit.

    If explicit 'hull_cost' is present in config, returns that value.
    Otherwise calculates the default or dynamic cost matching instantiate_component_for_unit.
    """
    config = config or {}
    if config.get("hull_cost") is not None:
        return float(config["hull_cost"])

    comp_cls = get_component_class_by_name(component_name)
    if not comp_cls:
        return 15.0

    if comp_cls == Engines:
        speed = float(config.get("speed", 100.0))
        return float(Engines.calc_hull_cost(speed, unit.hull_size))

    elif comp_cls == Hyperdrive:
        htype_raw = config.get("drive_type", HyperdriveType.BASIC)
        if isinstance(htype_raw, str):
            htype = HyperdriveType.ADVANCED if htype_raw.upper() == "ADVANCED" else HyperdriveType.BASIC
        else:
            htype = htype_raw
        jump_range = int(config.get("jump_range", DEFAULT_JUMP_RANGE))
        return float(Hyperdrive.calc_hull_cost(htype, jump_range, unit.hull_size))

    elif comp_cls == Weapons:
        turret_defs = config.get("turrets")
        if turret_defs:
            turrets = []
            for t_def in turret_defs:
                t_type_str = t_def.get("type", "MASS_DRIVER")
                t_var_str = t_def.get("variant", "STANDARD")
                try:
                    t_type = TurretType[t_type_str.upper()]
                except KeyError:
                    t_type = TurretType.MASS_DRIVER
                try:
                    t_var = TurretVariant[t_var_str.upper()]
                except KeyError:
                    t_var = TurretVariant.STANDARD
                turrets.append(Turret(
                    turret_type=t_type,
                    damage=float(t_def.get("damage", 10)),
                    range=float(t_def.get("range", 300)),
                    cooldown=int(t_def.get("cooldown", 1)),
                    parent_unit=unit,
                    variant=t_var
                ))
            return float(Weapons.calc_hull_cost(turrets))
        return 5.0

    elif comp_cls == Defenses:
        armor = int(config.get("armor", 50))
        shields = int(config.get("shields", 50))
        pd = int(config.get("point_defense", 0))
        return float(Defenses.calc_hull_cost(armor, shields, pd))

    elif comp_cls == AntimatterHarvester:
        return float(ANTIMATTER_HARVESTER_HULL_COST)

    elif comp_cls == AntimatterStorage:
        cap = float(config.get("max_capacity", DEFAULT_ANTIMATTER_CAPACITY))
        return float(AntimatterStorage.calc_hull_cost(cap))

    elif comp_cls == Sensors:
        s_range = float(config.get("short_range_radius", DEFAULT_SENSOR_SHORT_RANGE))
        l_hexes = int(config.get("long_range_hexes", 1))
        return float(Sensors.calc_hull_cost(s_range, l_hexes))

    elif comp_cls == RepairComponent:
        r_rate = float(config.get("repair_rate", 10.0))
        return float(RepairComponent.calc_hull_cost(r_rate))

    elif comp_cls == MiningComponent:
        m_rate = float(config.get("mining_rate", 10.0))
        m_cargo = float(config.get("max_cargo", 100.0))
        return float(MiningComponent.calc_hull_cost(m_rate, m_cargo))

    elif comp_cls == MetalRefineryComponent:
        return 20.0

    elif comp_cls == CrystalRefineryComponent:
        return 20.0

    elif comp_cls == HangarComponent:
        slots = int(config.get("max_slots", 2))
        return float(HangarComponent.calc_hull_cost(slots))

    elif comp_cls == StrikecraftBayComponent:
        slots = int(config.get("max_slots", 2))
        return float(StrikecraftBayComponent.calc_hull_cost(slots))

    elif comp_cls == ColonyComponent:
        return 10.0

    elif comp_cls == CivilianHabitatComponent:
        bonus = float(config.get("economic_bonus", 50.0))
        return float(CivilianHabitatComponent.calc_hull_cost(bonus))

    elif comp_cls == OrbitalDefenseComponent:
        return float(OrbitalDefenseComponent.calc_hull_cost())

    elif comp_cls == TradeComponent:
        mult = float(config.get("trade_revenue_multiplier", 1.0))
        return float(TradeComponent.calc_hull_cost(mult))

    elif comp_cls == HyperspaceInhibitionFieldEmitter:
        radius = float(config.get("radius", 100.0))
        return float(HyperspaceInhibitionFieldEmitter.calc_hull_cost(radius))

    elif comp_cls == AbilityComponent:
        raw_abilities = config.get("ability_types", [])
        ability_types = []
        for aname in raw_abilities:
            try:
                ability_types.append(AbilityType(aname) if isinstance(aname, str) else aname)
            except ValueError:
                pass
        return float(AbilityComponent.calc_hull_cost(ability_types))

    elif comp_cls == MinelayerComponent:
        return float(MINELAYER_HULL_COST)

    elif comp_cls == MarinesComponent:
        count = int(config.get("marines_count", 10))
        return float(MarinesComponent.calc_hull_cost(count))

    elif comp_cls == CloakingDevice:
        c_type_raw = config.get("device_type", "BASIC")
        if isinstance(c_type_raw, str):
            c_type = CloakingType.ADVANCED if c_type_raw.upper() == "ADVANCED" else CloakingType.BASIC
        else:
            c_type = c_type_raw
        radius = float(config.get("area_radius", 0.0)) if c_type == CloakingType.ADVANCED else 0.0
        return float(CloakingDevice.calc_hull_cost(c_type, radius))

    elif comp_cls == IntelligenceComponent:
        count = int(config.get("agents_count", config.get("agents_capacity", 1)))
        ci = bool(config.get("has_counter_intelligence", False))
        return float(IntelligenceComponent.calc_hull_cost(count, ci))

    elif comp_cls == Constructor:
        return 15.0

    return 15.0


def instantiate_component_for_unit(component_name: str, unit: 'Unit', config: Optional[dict] = None) -> Optional[UnitComponent]:
    """Instantiate a new UnitComponent for the given unit with specified or default config."""
    config = config or {}
    comp_cls = get_component_class_by_name(component_name)
    if not comp_cls:
        logger.warning(f"Unknown component name: {component_name}")
        return None

    cost = get_component_hull_cost(component_name, unit, config)

    if comp_cls == Engines:
        speed = float(config.get("speed", 100.0))
        return Engines(unit, speed=speed, hull_cost=cost)

    elif comp_cls == Hyperdrive:
        htype_raw = config.get("drive_type", HyperdriveType.BASIC)
        if isinstance(htype_raw, str):
            htype = HyperdriveType.ADVANCED if htype_raw.upper() == "ADVANCED" else HyperdriveType.BASIC
        else:
            htype = htype_raw
        jump_range = int(config.get("jump_range", DEFAULT_JUMP_RANGE))
        return Hyperdrive(unit, drive_type=htype, jump_range=jump_range, hull_cost=cost)

    elif comp_cls == Weapons:
        weapons_comp = Weapons(unit, hull_cost=cost)
        turret_defs = config.get("turrets")
        if turret_defs:
            for t_def in turret_defs:
                t_type_str = t_def.get("type", "MASS_DRIVER")
                t_var_str = t_def.get("variant", "STANDARD")
                try:
                    t_type = TurretType[t_type_str.upper()]
                except KeyError:
                    t_type = TurretType.MASS_DRIVER
                try:
                    t_var = TurretVariant[t_var_str.upper()]
                except KeyError:
                    t_var = TurretVariant.STANDARD
                turret = Turret(
                    turret_type=t_type,
                    damage=float(t_def.get("damage", 10)),
                    range=float(t_def.get("range", 300)),
                    cooldown=int(t_def.get("cooldown", 1)),
                    parent_unit=unit,
                    variant=t_var
                )
                weapons_comp.add_turret(turret)
        else:
            weapons_comp.add_turret(Turret(
                turret_type=TurretType.MASS_DRIVER,
                damage=10,
                range=300,
                cooldown=1,
                parent_unit=unit,
                variant=TurretVariant.STANDARD
            ))
        return weapons_comp

    elif comp_cls == Defenses:
        armor = int(config.get("armor", 50))
        shields = int(config.get("shields", 50))
        pd = int(config.get("point_defense", 0))
        return Defenses(unit, armor=armor, shields=shields, point_defense=pd, hull_cost=cost)

    elif comp_cls == AntimatterHarvester:
        rate = float(config.get("harvest_rate", DEFAULT_ANTIMATTER_HARVEST_RATE))
        return AntimatterHarvester(unit, harvest_rate=rate, hull_cost=cost)

    elif comp_cls == AntimatterStorage:
        cap = float(config.get("max_capacity", DEFAULT_ANTIMATTER_CAPACITY))
        return AntimatterStorage(unit, max_capacity=cap, hull_cost=cost)

    elif comp_cls == Sensors:
        s_range = float(config.get("short_range_radius", DEFAULT_SENSOR_SHORT_RANGE))
        l_hexes = int(config.get("long_range_hexes", 1))
        return Sensors(unit, short_range_radius=s_range, long_range_hexes=l_hexes, hull_cost=cost)

    elif comp_cls == RepairComponent:
        r_rate = float(config.get("repair_rate", 10.0))
        r_range = float(config.get("repair_range", 200.0))
        c_cost = float(config.get("credit_cost_per_hp", REPAIR_CREDIT_COST_PER_HP))
        return RepairComponent(unit, repair_rate=r_rate, repair_range=r_range, credit_cost_per_hp=c_cost, hull_cost=cost)

    elif comp_cls == MiningComponent:
        m_rate = float(config.get("mining_rate", 10.0))
        m_range = float(config.get("mining_range", 200.0))
        m_cargo = float(config.get("max_cargo", 100.0))
        return MiningComponent(unit, mining_rate=m_rate, mining_range=m_range, max_cargo=m_cargo, hull_cost=cost)

    elif comp_cls == MetalRefineryComponent:
        u_range = float(config.get("unload_range", 300.0))
        return MetalRefineryComponent(unit, unload_range=u_range, hull_cost=cost)

    elif comp_cls == CrystalRefineryComponent:
        u_range = float(config.get("unload_range", 300.0))
        return CrystalRefineryComponent(unit, unload_range=u_range, hull_cost=cost)

    elif comp_cls == HangarComponent:
        slots = int(config.get("max_slots", 2))
        return HangarComponent(unit, max_slots=slots, hull_cost=cost)

    elif comp_cls == StrikecraftBayComponent:
        slots = int(config.get("max_slots", 2))
        return StrikecraftBayComponent(unit, max_slots=slots, hull_cost=cost)

    elif comp_cls == ColonyComponent:
        return ColonyComponent(unit, hull_cost=cost)

    elif comp_cls == CivilianHabitatComponent:
        bonus = float(config.get("economic_bonus", 50.0))
        return CivilianHabitatComponent(unit, economic_bonus=bonus, hull_cost=cost)

    elif comp_cls == OrbitalDefenseComponent:
        radius = float(config.get("radius", 500.0))
        atk_bonus = float(config.get("attack_bonus", 0.20))
        def_bonus = float(config.get("defense_bonus", 0.20))
        return OrbitalDefenseComponent(unit, radius=radius, attack_bonus=atk_bonus, defense_bonus=def_bonus, hull_cost=cost)

    elif comp_cls == TradeComponent:
        mult = float(config.get("trade_revenue_multiplier", 1.0))
        return TradeComponent(unit, hull_cost=cost, trade_revenue_multiplier=mult)

    elif comp_cls == HyperspaceInhibitionFieldEmitter:
        radius = float(config.get("radius", 100.0))
        return HyperspaceInhibitionFieldEmitter(unit, radius=radius, hull_cost=cost)

    elif comp_cls == AbilityComponent:
        raw_abilities = config.get("ability_types", [])
        ability_types = []
        for aname in raw_abilities:
            try:
                ability_types.append(AbilityType(aname) if isinstance(aname, str) else aname)
            except ValueError:
                pass
        return AbilityComponent(unit, ability_types=ability_types, hull_cost=cost)

    elif comp_cls == MinelayerComponent:
        return MinelayerComponent(unit, hull_cost=cost)

    elif comp_cls == MarinesComponent:
        count = int(config.get("marines_count", 10))
        return MarinesComponent(unit, marines_count=count, hull_cost=cost)

    elif comp_cls == CloakingDevice:
        c_type_raw = config.get("device_type", "BASIC")
        if isinstance(c_type_raw, str):
            c_type = CloakingType.ADVANCED if c_type_raw.upper() == "ADVANCED" else CloakingType.BASIC
        else:
            c_type = c_type_raw
        radius = float(config.get("area_radius", 0.0)) if c_type == CloakingType.ADVANCED else 0.0
        return CloakingDevice(unit, device_type=c_type, area_radius=radius, hull_cost=cost)

    elif comp_cls == IntelligenceComponent:
        count = int(config.get("agents_count", config.get("agents_capacity", 1)))
        ci = bool(config.get("has_counter_intelligence", False))
        return IntelligenceComponent(unit, agents_count=count, agents_capacity=count, has_counter_intelligence=ci, hull_cost=cost)

    elif comp_cls == Constructor:
        return Constructor(unit, hull_cost=cost)

    return None



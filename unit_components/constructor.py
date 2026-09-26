import logging
from game_logging import format_unit_for_log
import typing
from typing import Optional, TYPE_CHECKING
import dataclasses

from .base import UnitComponent
from .wormhole_stabilizer import WormholeStabilizerComponent
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
from .planetary import TroopTransportComponent, SiegeBatteryComponent
from planetary_balance import TROOP_DEFAULT_CAPACITY
from .cloaking import CloakingDevice
from .intelligence import IntelligenceComponent
from .enums import (
    HyperdriveType, TurretType, TurretVariant,
    WingType, AbilityType, CloakingType
)

from domain.coordinates import HexCoord
from geometry import Position, distance
from constants import (
    DEFAULT_ANTIMATTER_CAPACITY, DEFAULT_ANTIMATTER_HARVEST_RATE,
    ANTIMATTER_HARVESTER_HULL_COST, MINELAYER_HULL_COST,
    DEFAULT_JUMP_RANGE, HullSize, DEFAULT_SENSOR_SHORT_RANGE, REPAIR_CREDIT_COST_PER_HP,
    CONSTRUCTOR_BUILD_RANGE,
)


from unit_templates import UNIT_TEMPLATES, get_all_templates_for_player
from construction_customization import customize_template, validate_template_overrides, validate_override_values, OVERRIDE_FIELDS
from resource_costs import ResourceCost, template_cost

if TYPE_CHECKING:
    from domain.units import Unit
    from domain.players import Player
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
    *,
    templates: Optional[dict] = None,
    turret_type_override: Optional[str] = None,
    defense_type_override: Optional[str] = None,
) -> Optional['Unit']:
    """Module-level helper that builds a :class:`~domain.units.Unit` from a
    template entry in :data:`~unit_templates.UNIT_TEMPLATES` (or private templates
    for human players) and adds it to *galaxy*.

    This is the canonical instantiation routine.  :meth:`Constructor.
    create_unit_from_template` is a thin wrapper around this function so that
    both the constructor component **and** :func:`~game.Game.spawn_units` can
    share the same logic without code duplication.
    """
    template_source = templates if templates is not None else get_all_templates_for_player(owner, base_templates=UNIT_TEMPLATES)
    template = template_source.get(template_name)
    if not template:
        logger.debug(f"Error: Unit template '{template_name}' not found.")
        return


    system = galaxy.systems.get(system_name)
    if not system:
        logger.debug(f"Error: System '{system_name}' not found for unit creation.")
        return

    template = customize_template(template, turret_type_override, defense_type_override)
    new_unit = assemble_unit_from_template(template_name, template, owner, system_name, hex_coord, position, game)
    system.add_unit(new_unit)
    return new_unit


def assemble_unit_from_template(template_name, template, owner, system_name, hex_coord, position, game):
    """Assemble a detached unit; callers decide whether to deploy or dock it."""
    from domain.units import Unit
    from unit_naming import initial_unit_name

    hull_size_val = template["hull_size"]
    if isinstance(hull_size_val, str):
        hull_size_val = HullSize[hull_size_val.upper()]

    new_unit = Unit(
        owner=owner,
        name=initial_unit_name(template),
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
            armor=float(template.get("armor", 0.0)),
            shields=float(template.get("shields", 0.0)),
            point_defense=float(template.get("point_defense", 0.0)),
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
        new_unit.add_component(HyperspaceInhibitionFieldEmitter(
            new_unit,
            radius=inh_radius
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

    has_sensors = template.get("has_sensors", False)
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

    if template.get("has_troop_transport_component"):
        new_unit.add_component(TroopTransportComponent(new_unit, template.get("troop_capacity", TROOP_DEFAULT_CAPACITY)))
    if template.get("has_wormhole_stabilizer_component"):
        new_unit.add_component(WormholeStabilizerComponent(new_unit))
    if template.get("has_siege_battery_component"):
        new_unit.add_component(SiegeBatteryComponent(new_unit))

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
        from constants import DEFAULT_ADVANCED_CLOAKING_RADIUS
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

    return new_unit


def _is_strikecraft_wing_template(template: dict) -> bool:
    """Return True if the template has STRIKECRAFT_WING hull size."""
    if not isinstance(template, dict):
        return False
    hull_size = template.get("hull_size")
    if isinstance(hull_size, str):
        try:
            hull_size = HullSize[hull_size.upper()]
        except KeyError:
            return hull_size.upper() == "STRIKECRAFT_WING"
    return hull_size == HullSize.STRIKECRAFT_WING


@dataclasses.dataclass
class BuildableUnit:
    unit_template_name: str
    time_to_build: int
    cost_credits: int
    cost_metal: float = 0
    cost_crystal: float = 0

    @property
    def resource_cost(self):
        return ResourceCost(self.cost_credits, self.cost_metal, self.cost_crystal)


class Constructor(UnitComponent):
    """A component that allows a unit to construct other units (stations) and refit friendly units."""
    SCHEMA_VERSION = 4
    STATE_CONFIG = ('build_range',)
    STATE_RUNTIME = ('current_construction_target', 'construction_progress', 'time_to_build', 'construction_order_id', 'current_refit_target', 'refit_progress', 'refit_time', 'refit_order_id')
    STATE_REFS = ()
    STATE_OPTIONAL_TYPES = {"current_construction_target": dict, "current_refit_target": dict,
                            "construction_order_id": str, "refit_order_id": str}

    def validate_state(self):
        target = self.current_construction_target
        if target is not None:
            from location_validation import location
            from state_codec import fields
            fields(target, ("template_name", "system_name", "hex_coord", "position", *OVERRIDE_FIELDS), "construction")
            validate_override_values(*(target[field] for field in OVERRIDE_FIELDS))
            if not isinstance(target["template_name"], str) or not target["template_name"]:
                raise ValueError("Invalid construction template")
            location(target["system_name"], target["hex_coord"], target["position"])

        if self.current_refit_target is not None:
            from state_codec import number, fields
            fields(self.current_refit_target, ("target_unit_id", "action", "component_type", "component_config", "cost_credits", "time_to_build", "payer_id", "salvage_due", "resource_cost", "resource_salvage"), "refit")
            cost = ResourceCost.from_dict(self.current_refit_target['resource_cost'])
            salvage = ResourceCost.from_dict(self.current_refit_target['resource_salvage'])
            if cost.credits != self.current_refit_target['cost_credits'] or salvage.credits != self.current_refit_target['salvage_due']:
                raise ValueError('Inconsistent refit accounting')
            if ((self.current_refit_target['action'] == 'ADD' and salvage != ResourceCost())
                    or (self.current_refit_target['action'] == 'REMOVE' and cost != ResourceCost())):
                raise ValueError('Invalid refit charge or salvage for action')
            number(self.current_refit_target.get("target_unit_id"), "refit.target_unit_id", 0, integer=True)
            if self.current_refit_target.get("action") not in ("ADD", "REMOVE"):
                raise ValueError("Invalid refit action")
            if not isinstance(self.current_refit_target["component_config"], dict) or get_component_class_by_name(self.current_refit_target["component_type"]) is None:
                raise ValueError("Invalid refit component/configuration")
            number(self.current_refit_target["payer_id"], "refit.payer_id", 0, integer=True)
            number(self.current_refit_target["salvage_due"], "refit.salvage_due", 0, integer=True)
            number(self.current_refit_target["cost_credits"], "refit.cost_credits", 0)
            number(self.current_refit_target["time_to_build"], "refit.time_to_build", 0, integer=True)

    DISPLAY_NAME: str = "Constructor"
    SIDEBAR_ORDER: int = 5
    build_range: float = CONSTRUCTOR_BUILD_RANGE
    
    # Construction state
    current_construction_target: Optional[dict] = None # Fixed template/system/hex/position job record
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
        self.construction_order_id = None
        self.refit_order_id = None
        self.current_refit_target = None
        self.refit_progress = 0
        self.refit_time = 0

    def get_sidebar_data(self, game_state: 'Game') -> list[dict]:
        data = super().get_sidebar_data(game_state)
        from component_visibility import unit_details_are_public_in_game
        if not unit_details_are_public_in_game(self.unit, game_state):
            return data
        if getattr(self.unit, '_dismantle_executor', None):
            data.append({'type': 'label', 'text': 'Constructor busy: dismantling',
                         'object_id': '#sidebar_info_label', 'height': 25})
        elif self.current_construction_target:
            target_name = self.current_construction_target["template_name"]
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
        from component_visibility import unit_details_are_public_in_game
        if not unit_details_are_public_in_game(self.unit, game_state):
            return data
        if self.is_destroyed:
            return data
        if getattr(self.unit, '_dismantle_executor', None):
            status_str = 'Dismantling'
            obj_id = '#sidebar_status_active_label'
        elif self.current_construction_target:
            target_name = self.current_construction_target["template_name"]
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
        """Dynamically retrieve all buildable units based on accessible templates, excluding strikecraft wings."""
        buildables = []
        owner = getattr(self.unit, "owner", None)
        templates = get_all_templates_for_player(owner, base_templates=UNIT_TEMPLATES)
        for name, template in templates.items():
            if _is_strikecraft_wing_template(template):
                continue
            cost = template_cost(template)
            buildables.append(BuildableUnit(
                unit_template_name=name,
                time_to_build=template.get("build_time", 10),
                cost_credits=template.get("build_cost", 500),
                cost_metal=cost.metal,
                cost_crystal=cost.crystal
            ))
        return buildables

    def can_build(self, unit_template_name: str) -> Optional[BuildableUnit]:
        """Check if this constructor can build a specific unit type."""
        owner = getattr(self.unit, "owner", None)
        templates = get_all_templates_for_player(owner, base_templates=UNIT_TEMPLATES)
        template = templates.get(unit_template_name)
        if template:
            if _is_strikecraft_wing_template(template):
                return None
            cost = template_cost(template)
            return BuildableUnit(
                unit_template_name=unit_template_name,
                time_to_build=template.get("build_time", 10),
                cost_credits=template.get("build_cost", 500),
                cost_metal=cost.metal,
                cost_crystal=cost.crystal
            )
        return None


    def start_construction(self, unit_template_name: str, position: Position, galaxy: 'Galaxy', *, system_name: str, hex_coord: HexCoord, order=None,
                           turret_type_override=None, defense_type_override=None) -> bool:
        """Starts the construction of a new unit."""
        if self.is_destroyed:
            return False

        from location_validation import location
        try:
            system_name, hex_coord, position = location(system_name, hex_coord, position, galaxy)
        except ValueError:
            return False
        from dismantling import offline
        if offline(self.unit) or getattr(self.unit, '_dismantle_executor', None) or self.current_construction_target or self.current_refit_target:
            return False
        if (self.unit.in_system != system_name or self.unit.in_hex != hex_coord
                or distance(self.unit.position, position) > self.build_range):
            logger.debug(f"Error: Construction target {position} is beyond build range ({self.build_range}).")
            return False

        buildable = self.can_build(unit_template_name)
        if not buildable:
            logger.debug(f"Error: {format_unit_for_log(self.unit)} cannot build {unit_template_name}.")
            return False

        template = get_all_templates_for_player(self.unit.owner, base_templates=UNIT_TEMPLATES).get(unit_template_name)
        try:
            validate_template_overrides(template, turret_type_override, defense_type_override)
        except ValueError:
            return False

        owner = self.unit.owner
        if not buildable.resource_cost.pay(owner):
            logger.debug(f"Error: Not enough resources to build {unit_template_name}.")
            return False

        self.current_construction_target = dict(template_name=unit_template_name, system_name=system_name, hex_coord=hex_coord, position=position,
                                                turret_type_override=turret_type_override, defense_type_override=defense_type_override)
        self.construction_order_id = order.public_id if order else None
        self._construction_order_ref = order
        if order is not None:
            order.record_charge(buildable.resource_cost, owner.id)
        self.time_to_build = buildable.time_to_build
        self.construction_progress = 0
        from location_validation import format_location
        logger.debug(f"{format_unit_for_log(self.unit)} started constructing {unit_template_name} at {format_location(system_name, hex_coord, position)}. Cost: {buildable.cost_credits}")
        return True

    def _owning_construction_order(self):
        def find(node):
            if node is None:
                return None
            if node.public_id == self.construction_order_id:
                return node
            return next((found for child in node.sub_orders if (found := find(child))), None)
        commander = self.unit.commander_component
        found = find(commander.current_order) if commander else None
        cached = getattr(self, "_construction_order_ref", None)
        return found or (cached if cached is not None and cached.public_id == self.construction_order_id else None)

    def _check_construction_site(self, galaxy):
        job = self.current_construction_target
        if job is None:
            return False
        from location_validation import location, format_location
        try:
            system, coord, position = location(job["system_name"], job["hex_coord"], job["position"], galaxy)
            valid = (self.unit.in_system == system and self.unit.in_hex == coord
                     and distance(self.unit.position, position) <= self.build_range)
        except ValueError:
            valid = False
        if valid:
            return True
        order = self._owning_construction_order()
        if order is not None:
            order.refund_charge()
        logger.debug("Construction site lost by %s: %s", format_unit_for_log(self.unit),
                     format_location(job["system_name"], job["hex_coord"], job["position"]))
        self.cancel_construction()
        if order is not None:
            order.fail("target_out_of_range")
        return False

    def cancel_construction(self):
        """Cancels the current construction project."""
        if self.current_construction_target:
            logger.debug(f"Construction of {self.current_construction_target['template_name']} cancelled.")
            # NOTE: Resource refund should be handled by the Order
            self.construction_order_id = None
            self._construction_order_ref = None
            self.current_construction_target = None
            self.construction_progress = 0
            self.time_to_build = 0

    def start_refit(self, target_unit: 'Unit', action: str, component_type: str,
                    component_config: Optional[dict] = None, cost_credits: Optional[int] = 0,
                    time_to_build: Optional[int] = 1, *, order=None) -> bool:
        """Validate and charge a refit; supplied cost/time values are preview hints."""
        from refit_validation import evaluate_refit
        from domain.players import are_allies
        from geometry import distance
        from dismantling import offline
        if (offline(self.unit) or offline(target_unit) or getattr(self.unit, '_dismantle_executor', None)
                or self.is_destroyed or self.current_refit_target or self.current_construction_target
                or target_unit.current_hit_points <= 0
                or not are_allies(self.unit.owner, target_unit.owner)
                or self.unit.in_system != target_unit.in_system or self.unit.in_hex != target_unit.in_hex
                or distance(self.unit.position, target_unit.position) > self.build_range):
            return False
        result = evaluate_refit(target_unit, action, component_type, component_config)
        if result.errors or not result.resource_cost.affordable(self.unit.owner):
            return False
        owner = self.unit.owner
        if not result.resource_cost.pay(owner):
            return False
        self.current_refit_target = {
            "target_unit_id": target_unit.id, "action": action,
            "component_type": result.component_name, "component_config": result.configuration,
            "cost_credits": result.cost_credits, "time_to_build": result.duration,
            "payer_id": owner.id, "salvage_due": result.salvage,
            "resource_cost": result.resource_cost.to_dict(), "resource_salvage": result.resource_salvage.to_dict(),
        }
        self.refit_order_id = order.public_id if order else None
        self._refit_order_ref = order
        if order:
            order.record_charge(result.resource_cost, owner.id)
        self.refit_time = result.duration
        self.refit_progress = 0
        return True

    def _owning_refit_order(self):
        cached = getattr(self, '_refit_order_ref', None)
        commander = self.unit.commander_component
        if commander:
            def find(node):
                if node is None:
                    return None
                if node.public_id == self.refit_order_id:
                    return node
                return next((found for child in node.sub_orders if (found := find(child))), None)
            found = find(commander.current_order)
            if found:
                return found
        return cached if cached is not None and cached.public_id == self.refit_order_id else None

    def _settle_refit(self, *, success=False, cancelled=False):
        """Settle only this job, to its original payer, exactly once."""
        job = self.current_refit_target
        if not job:
            return
        order = self._owning_refit_order()
        payer = next((p for p in getattr(self.unit.game, 'players', []) if p.id == job['payer_id']), None)
        if payer is None and self.unit.owner.id == job['payer_id']:
            payer = self.unit.owner
        if payer is not None:
            ResourceCost.from_dict(job['resource_salvage'] if success else job['resource_cost']).refund(payer)
        if order:
            order.clear_charge()
        self.current_refit_target = None
        self.refit_order_id = None
        self._refit_order_ref = None
        self.refit_progress = self.refit_time = 0
        if order:
            from unit_orders.base import OrderStatus
            if cancelled:
                order.status = OrderStatus.CANCELLED
            elif success:
                order.status = OrderStatus.COMPLETED
            else:
                order.fail("invalid_refit")

    def cancel_refit(self):
        """Cancel the active job without granting removal salvage."""
        self._settle_refit(cancelled=True)

    def update(self, galaxy: 'Galaxy'):
        """Updates the construction or refit progress. Called each turn."""
        if self.is_destroyed:
            return
        if self.current_construction_target:
            if not self._check_construction_site(galaxy):
                return
            self.construction_progress += 1
            if self.construction_progress >= self.time_to_build:
                self.finish_construction(galaxy)
        elif self.current_refit_target:
            self.refit_progress += 1
            if self.refit_progress >= self.refit_time:
                self.finish_refit(galaxy)

    def create_unit_from_template(self, galaxy: 'Galaxy', template_name: str, owner: 'Player', system_name: str, hex_coord: 'HexCoord', position: 'Position', *,
                                  turret_type_override=None, defense_type_override=None):
        """Creates a new unit based on the template.

        Delegates to the module-level :func:`instantiate_unit_from_template`
        helper, passing ``self.unit.game`` as the game context.
        """
        built = instantiate_unit_from_template(
            template_name=template_name,
            owner=owner,
            system_name=system_name,
            hex_coord=hex_coord,
            position=position,
            galaxy=galaxy,
            game=self.unit.game,
            turret_type_override=turret_type_override,
            defense_type_override=defense_type_override,
        )
        if built is not None:
            from turn_briefing import unit_event
            unit_event(built, "development", "Construction completed", private=True)
        return built

    def finish_construction(self, galaxy: 'Galaxy'):
        """Finalizes the construction and creates the new unit."""
        if not self.current_construction_target:
            return

        if not self._check_construction_site(galaxy):
            return
        job = self.current_construction_target
        unit_template_name, position = job["template_name"], job["position"]
        from location_validation import format_location
        logger.debug("Construction of %s finished by %s at %s", unit_template_name, format_unit_for_log(self.unit),
                     format_location(job["system_name"], job["hex_coord"], position))
        
        template = get_all_templates_for_player(self.unit.owner, base_templates=UNIT_TEMPLATES).get(unit_template_name)
        valid = template is not None
        try:
            validate_template_overrides(template, job["turret_type_override"], job["defense_type_override"])
        except ValueError:
            valid = False
        built = None
        if valid:
            built = self.create_unit_from_template(
                galaxy=galaxy,
                template_name=unit_template_name,
                owner=self.unit.owner,
                system_name=job["system_name"],
                hex_coord=job["hex_coord"],
                position=position,
                turret_type_override=job["turret_type_override"],
                defense_type_override=job["defense_type_override"],
            )
        if built is None:
            order = self._owning_construction_order()
            if order is not None:
                order.refund_charge()
                order.fail("construction_unavailable")
            self.cancel_construction()
            return

        # Construction complete; reset building state variables.
        order = self._owning_construction_order()
        if order is not None:
            order.clear_charge()
        self.construction_order_id = None
        self._construction_order_ref = None
        self.current_construction_target = None
        self.construction_progress = 0
        self.time_to_build = 0

    def finish_refit(self, galaxy: 'Galaxy'):
        """Revalidate the live target before committing or paying salvage."""
        from refit_validation import evaluate_refit
        from domain.players import are_allies
        job = self.current_refit_target
        if not job:
            return
        target = galaxy.get_unit_by_id(job['target_unit_id'])
        from dismantling import offline
        if (offline(self.unit) or (target is not None and offline(target))
                or self.is_destroyed or self.unit.owner.id != job['payer_id'] or not target
                or target.current_hit_points <= 0 or not are_allies(self.unit.owner, target.owner)):
            self._settle_refit()
            return
        result = evaluate_refit(target, job['action'], job['component_type'], job['component_config'])
        if result.errors:
            logger.warning("Refit completion rejected: %s", '; '.join(result.errors))
            self._settle_refit()
            return
        if job['action'] == 'ADD':
            component = instantiate_component_for_unit(result.component_name, target, result.configuration)
            if component is None:
                self._settle_refit()
                return
            target.add_component(component)
        else:
            target.remove_component(get_component_class_by_name(result.component_name))
        self._settle_refit(success=True)
        from turn_briefing import record
        record(self.unit.game, self.unit.owner, "development", "Refit completed", subject=target)


COMPONENT_NAME_MAP = {
    "WormholeStabilizerComponent": WormholeStabilizerComponent,
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
    "TroopTransportComponent": TroopTransportComponent,
    "SiegeBatteryComponent": SiegeBatteryComponent,
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
        from custom_unit_templates import TurretConfig
        turrets = [TurretConfig(t.get('type', 'MASS_DRIVER'), t.get('damage', 10),
                               t.get('range', 300), t.get('cooldown', 1), t.get('variant', 'STANDARD'))
                   for t in config.get('turrets', [])]
        return float(Weapons.calc_hull_cost(turrets))

    elif comp_cls == Defenses:
        armor = float(config.get("armor", 50.0))
        shields = float(config.get("shields", 50.0))
        pd = float(config.get("point_defense", 0.0))
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

    elif comp_cls == TroopTransportComponent:
        return TroopTransportComponent.calc_hull_cost(config.get("capacity", TROOP_DEFAULT_CAPACITY))
    elif comp_cls == WormholeStabilizerComponent:
        return WormholeStabilizerComponent.calc_hull_cost()
    elif comp_cls == SiegeBatteryComponent:
        return SiegeBatteryComponent.calc_hull_cost()
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
        count = int(config.get("agents_capacity", 1))
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
        return weapons_comp

    elif comp_cls == Defenses:
        armor = float(config.get("armor", 50.0))
        shields = float(config.get("shields", 50.0))
        pd = float(config.get("point_defense", 0.0))
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

    elif comp_cls == TroopTransportComponent:
        return TroopTransportComponent(unit, config.get("capacity", TROOP_DEFAULT_CAPACITY))
    elif comp_cls == WormholeStabilizerComponent:
        return WormholeStabilizerComponent(unit)
    elif comp_cls == SiegeBatteryComponent:
        return SiegeBatteryComponent(unit)
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
        component = CloakingDevice(unit, device_type=c_type, area_radius=radius, hull_cost=cost)
        # Explicit Designer zero radius must not become the runtime default radius.
        component.area_radius = radius
        return component

    elif comp_cls == IntelligenceComponent:
        count = int(config.get("agents_capacity", 1))
        ci = bool(config.get("has_counter_intelligence", False))
        return IntelligenceComponent(unit, agents_count=count, agents_capacity=count, has_counter_intelligence=ci, hull_cost=cost)

    elif comp_cls == Constructor:
        return Constructor(unit, hull_cost=cost)

    return None

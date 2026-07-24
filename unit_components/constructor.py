import logging
import typing
from typing import Optional, TYPE_CHECKING
import dataclasses

from .base import UnitComponent
from .enums import (
    HyperdriveType, UnitStance, TurretType, TurretVariant,
    WingType, AbilityType
)
from .antimatter import AntimatterStorage, AntimatterHarvester
from .movement import Engines, Hyperdrive
from .weapons import Weapons, Turret
from .defenses import Defenses
from .inhibitor import HyperspaceInhibitionFieldEmitter
from .repair import RepairComponent
from .colony import ColonyComponent
from .mining import MiningComponent, MetalRefineryComponent, CrystalRefineryComponent
from .hangar import HangarComponent
from .strikecraft import StrikecraftWingComponent, StrikecraftBayComponent
from .abilities import AbilityComponent
from .sensors import Sensors

from utils import HexCoord
from geometry import Position
from constants import (
    DEFAULT_ANTIMATTER_CAPACITY, DEFAULT_ANTIMATTER_HARVEST_RATE,
    DEFAULT_ANTIMATTER_HARVEST_RANGE, ANTIMATTER_HARVESTER_HULL_COST,
    DEFAULT_JUMP_RANGE, HullSize, DEFAULT_SENSOR_SHORT_RANGE
)

from unit_templates import UNIT_TEMPLATES

if TYPE_CHECKING:
    from entities import Unit, Player
    from galaxy import Galaxy
    from game import Game

logger = logging.getLogger(__name__)

@dataclasses.dataclass
class BuildableUnit:
    unit_template_name: str
    time_to_build: int
    cost_credits: int


class Constructor(UnitComponent):
    """A component that allows a unit to construct other units (stations)."""
    DISPLAY_NAME: str = "Constructor"
    SIDEBAR_ORDER: int = 5
    build_range: float = 500.0
    
    # Construction state
    current_construction_target: Optional[tuple[str, Position]] = None # (unit_template_name, position)
    construction_progress: int = 0
    time_to_build: int = 0

    def __init__(self, unit: 'Unit', hull_cost: int = 0, buildable_unit_names: typing.Optional[list[str]] = None):
        super().__init__(unit, hull_cost)
        self.current_construction_target = None
        self.construction_progress = 0
        self.time_to_build = 0

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
        else:
            data.append({'type': 'label', 'text': "Status: Idle", 'object_id': '#sidebar_info_label', 'height': 20})
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

    def update(self, galaxy: 'Galaxy'):
        """Updates the construction progress. Called each turn."""
        if self.is_destroyed:
            return
        if self.current_construction_target:
            self.construction_progress += 1
            if self.construction_progress >= self.time_to_build:
                self.finish_construction(galaxy)

    def create_unit_from_template(self, galaxy: 'Galaxy', template_name: str, owner: 'Player', system_name: str, hex_coord: 'HexCoord', position: 'Position'):
        """Creates a new unit based on the template."""
        from entities import Unit # Avoid circular import

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
            game=self.unit.game,
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
                harvest_range=template.get("antimatter_harvest_range", DEFAULT_ANTIMATTER_HARVEST_RANGE),
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
                cost = 5 if htype == HyperdriveType.BASIC else 10
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
            new_unit.add_component(RepairComponent(
                new_unit,
                repair_rate=template.get("repair_rate", 10.0),
                repair_range=template.get("repair_range", 200.0),
                credit_cost_per_hp=template.get("credit_cost_per_hp", 1.0),
                hull_cost=template.get("repair_hull_cost", 15)
            ))

        if template.get("has_mining_component"):
            new_unit.add_component(MiningComponent(
                new_unit,
                mining_rate=template.get("mining_rate", 10.0),
                mining_range=template.get("mining_range", 200.0),
                max_cargo=template.get("max_mining_cargo", 100.0),
                hull_cost=template.get("mining_hull_cost", 10)
            ))

        if template.get("has_metal_refinery_component"):
            new_unit.add_component(MetalRefineryComponent(
                new_unit,
                unload_range=template.get("unload_range", 300.0),
                hull_cost=template.get("metal_refinery_hull_cost", 20)
            ))

        if template.get("has_crystal_refinery_component"):
            new_unit.add_component(CrystalRefineryComponent(
                new_unit,
                unload_range=template.get("unload_range", 300.0),
                hull_cost=template.get("crystal_refinery_hull_cost", 20)
            ))

        if template.get("has_hangar"):
            hull_size = new_unit.hull_size
            if hull_size in (HullSize.TINY, HullSize.SMALL, HullSize.MEDIUM):
                logger.warning(f"Warning: Attempted to add hangar to forbidden hull size {hull_size.name} in template '{template_name}'. Skipping.")
            else:
                new_unit.add_component(HangarComponent(
                    new_unit,
                    max_slots=template.get("hangar_slots", 0),
                    hull_cost=template.get("hangar_hull_cost", 0)
                ))

        if template.get("has_strikecraft_bay"):
            hull_size = new_unit.hull_size
            if hull_size in (HullSize.STRIKECRAFT_WING, HullSize.TINY, HullSize.SMALL):
                logger.warning(f"Warning: Attempted to add strikecraft bay to forbidden hull size {hull_size.name} in template '{template_name}'. Skipping.")
            else:
                new_unit.add_component(StrikecraftBayComponent(
                    new_unit,
                    max_slots=template.get("strikecraft_bay_slots", 0),
                    hull_cost=template.get("strikecraft_bay_hull_cost", 0)
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
                hull_cost=template.get("colony_hull_cost", 10)
            ))

        if template.get("has_inhibitor"):
            new_unit.add_component(HyperspaceInhibitionFieldEmitter(
                new_unit,
                radius=template.get("inhibitor_radius", 100.0),
                hull_cost=template.get("inhibitor_hull_cost", 20)
            ))

        if template.get("has_ability_component"):
            raw_ability_names = template.get("abilities", [])
            ability_types = []
            for aname in raw_ability_names:
                try:
                    ability_types.append(AbilityType(aname))
                except ValueError:
                    logger.warning(f"[create_unit_from_template] Unknown ability '{aname}' in template '{template_name}'. Skipping.")
            if ability_types:
                new_unit.add_component(AbilityComponent(
                    new_unit,
                    ability_types=ability_types,
                    hull_cost=template.get("ability_hull_cost", 10)
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

        system.add_unit(new_unit)

        logger.debug(f"Created unit {new_unit.name} ({new_unit.id}) for player {owner.id} in {system_name} at {hex_coord}")

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

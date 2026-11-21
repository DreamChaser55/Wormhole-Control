from hp_format import format_hp
import logging
from game_logging import format_unit_for_log
import typing
from typing import TYPE_CHECKING
import dataclasses

from campaign_graph import sync_docked_sector
from .base import UnitComponent
from .enums import WingType
from geometry import Position
from constants import HullSize, STRIKECRAFT_BAY_HULL_COST_PER_SLOT
from deployment_placement import find_deployment_position
from resource_costs import template_cost

if TYPE_CHECKING:
    from domain.units import Unit
    from galaxy import Galaxy
    from game import Game

logger = logging.getLogger(__name__)

class StrikecraftWingComponent(UnitComponent):
    """Tracks a strikecraft wing's role, carrier association, and tactical state."""
    STATE_CONFIG = ('wing_type',)
    SCHEMA_VERSION = 2
    STATE_RUNTIME = ('recovery_ready_round', 'last_flak_round', 'last_flak_owner_id',
                     'turns_outside', 'last_endurance_round')
    STATE_REFS = ('mother_carrier',)
    DISPLAY_NAME: str = "Strikecraft Wing"
    SIDEBAR_ORDER: int = 13
    mother_carrier: typing.Optional['Unit'] = None

    def __init__(self, unit: 'Unit', wing_type: WingType = WingType.FIGHTER, hull_cost: float = 0.0):
        super().__init__(unit, hull_cost=hull_cost)
        self.mother_carrier = None
        self.wing_type: WingType = wing_type
        self.recovery_ready_round = 0
        self.last_flak_round = 0
        self.last_flak_owner_id = None
        self.turns_outside = 0
        self.last_endurance_round = 0

    def get_sidebar_data(self, game_state: 'Game') -> list[dict]:
        data = super().get_sidebar_data(game_state)
        role_str = "Fighter" if self.wing_type == WingType.FIGHTER else "Bomber"
        from titan_abilities import protected
        if protected(self.unit, 'carrier_supremacy'):
            data.extend({'type': 'label', 'text': text, 'object_id': '#sidebar_info_label', 'height': 20}
                        for text in ('Carrier Supremacy active', 'Weapon damage ×2; speed ×1.5', 'Incoming weapon damage ×0.5'))
        data.append({'type': 'label', 'text': f"Role: {role_str}", 'object_id': '#sidebar_info_label', 'height': 20})
        mother_name = self.mother_carrier.name if self.mother_carrier else "None"
        data.append({'type': 'label', 'text': f"Mother Carrier: {mother_name}", 'object_id': '#sidebar_info_label', 'height': 20})
        from strikecraft_service import sidebar_labels
        data.extend({'type': 'label', 'text': label, 'object_id': '#sidebar_info_label', 'height': 20}
                    for label in sidebar_labels(self.unit, game_state.galaxy))
        from strikecraft_abilities import wing_order, evasion, round_now
        root = wing_order(self.unit)
        if root:
            data.append({'type': 'label', 'text': f"{root.order_type.name.replace('_', ' ').title()}: {root.phase}", 'object_id': '#sidebar_info_label', 'height': 20})
        if evasion(self.unit):
            data.append({'type': 'label', 'text': 'Evasive: incoming damage 50%; outgoing 75%', 'object_id': '#sidebar_info_label', 'height': 20})
        if self.recovery_ready_round > round_now(game_state.galaxy):
            data.append({'type': 'label', 'text': 'Recovering: launch available next owner turn', 'object_id': '#sidebar_info_label', 'height': 20})
        return data

    def validate_state(self):
        from state_codec import number
        from constants import STRIKECRAFT_ENDURANCE_TURNS
        number(self.turns_outside, 'turns_outside', 0, integer=True)
        number(self.last_endurance_round, 'last_endurance_round', 0, integer=True)
        if self.turns_outside > STRIKECRAFT_ENDURANCE_TURNS:
            raise ValueError('Wing endurance counter exceeds limit')
        if self.last_flak_owner_id is not None:
            number(self.last_flak_owner_id, 'last_flak_owner_id', 0, integer=True)

    def get_basic_sidebar_data(self, game_state: 'Game') -> list[dict]:
        data = super().get_basic_sidebar_data(game_state)
        if self.is_destroyed:
            return data
        role_str = "Fighter" if self.wing_type == WingType.FIGHTER else "Bomber"
        data.append({
            'type': 'label',
            'text': f"Role: {role_str}",
            'object_id': '#sidebar_info_label',
            'height': 18,
            'indent_level': 1
        })
        return data


class StrikecraftBayComponent(UnitComponent):
    """A component that allows a unit to store, transport, and automatically construct/replenish strikecraft wings."""
    SCHEMA_VERSION = 5
    STATE_CONFIG = ('max_slots',)
    STATE_RUNTIME = ('construction_slot_index', 'construction_progress', 'replenish_progress',
                     'slots', 'production_enabled')
    STATE_OPTIONAL_TYPES = {'construction_slot_index': int}
    STATE_REFS = ('replenishing_unit',)
    STATE_CHILDREN = ("docked_units",)

    def on_destroyed(self) -> None:
        from campaign_graph import iter_units
        galaxy = self.unit.in_galaxy or getattr(self.unit.game, "galaxy", None)
        for unit, _ in iter_units(galaxy):
            wing = unit.strikecraft_wing_component
            if wing and wing.mother_carrier is self.unit and unit not in self.docked_units:
                self.release_wing(unit)
        self.launched_units.clear()

    DISPLAY_NAME: str = "Strikecraft Bay"
    SIDEBAR_ORDER: int = 12
    max_slots: int = 0
    docked_units: list['Unit'] = dataclasses.field(default_factory=list)
    launched_units: list['Unit'] = dataclasses.field(default_factory=list)
    
    # Auto-construction and replenishment state
    construction_progress: int = 0
    replenishing_unit: typing.Optional['Unit'] = None
    replenish_progress: int = 0

    def __init__(self, unit: 'Unit', max_slots: int = 0, hull_cost: float = 0.0):
        super().__init__(unit, hull_cost=hull_cost)
        self.max_slots = max_slots
        self.docked_units = []
        self.launched_units = []
        self.construction_slot_index: int | None = None
        self.construction_progress = 0
        self.replenishing_unit = None
        self.replenish_progress = 0
        self.slots = [dict(production_template_name=None, turret_type_override=None,
                           defense_type_override=None, wing_id=None) for _ in range(max_slots)]
        self.production_enabled = True

    @property
    def constructing(self):
        return self.construction_slot_index is not None

    def production_template(self, slot_index):
        from unit_templates import UNIT_TEMPLATES
        name = self.slots[slot_index]['production_template_name']
        return UNIT_TEMPLATES[name] if name is not None else None

    @staticmethod
    def validate_production(template_name, turret_type_override=None, defense_type_override=None):
        from unit_catalog import wing_template_names
        from unit_templates import UNIT_TEMPLATES
        from construction_customization import validate_template_overrides
        if template_name is None:
            if turret_type_override is not None or defense_type_override is not None:
                raise ValueError("Unselected strikecraft production cannot have overrides.")
            return
        if not isinstance(template_name, str) or template_name not in wing_template_names():
            raise ValueError("Choose a built-in strikecraft wing template.")
        validate_template_overrides(UNIT_TEMPLATES[template_name], turret_type_override, defense_type_override)

    def validate_state(self):
        from state_codec import fields, number
        number(self.max_slots, 'max_slots', 0, integer=True)
        if not isinstance(self.slots, list) or len(self.slots) != self.max_slots:
            raise ValueError("Strikecraft slot count must match bay capacity.")
        occupants = set()
        for slot in self.slots:
            fields(slot, ('production_template_name', 'turret_type_override', 'defense_type_override', 'wing_id'), 'slot')
            self.validate_production(slot['production_template_name'], slot['turret_type_override'], slot['defense_type_override'])
            if slot['wing_id'] is not None:
                number(slot['wing_id'], 'wing_id', 0, integer=True)
                if slot['wing_id'] in occupants:
                    raise ValueError("A wing cannot occupy multiple slots.")
                occupants.add(slot['wing_id'])
        number(self.construction_progress, 'construction_progress', 0, integer=True)
        if self.constructing:
            self.validate_slot_index(self.construction_slot_index)
            slot = self.slots[self.construction_slot_index]
            template = self.production_template(self.construction_slot_index)
            if (template is None or slot['wing_id'] is not None
                    or self.construction_progress >= template['build_time'] or self.replenishing_unit is not None):
                raise ValueError("Invalid strikecraft construction progress or concurrent replenishment.")
        elif self.construction_progress != 0:
            raise ValueError("Idle strikecraft construction must have zero progress.")

    def resolve_state(self, objects):
        replenishing_id = getattr(self, '_saved_refs', {}).get('replenishing_unit')
        if replenishing_id is not None and replenishing_id not in objects:
            raise ValueError("Missing replenishing wing reference.")
        super().resolve_state(objects)
        self.validate_state()

    def validate_slot_index(self, slot_index):
        if type(slot_index) is not int or not 0 <= slot_index < self.max_slots:
            raise ValueError("slot_index must identify an existing strikecraft bay slot.")

    def production_blocker(self, slot_index):
        from dismantling import offline
        self.validate_slot_index(slot_index)
        if self.is_destroyed or offline(self.unit):
            return 'bay_unavailable'
        if self.construction_slot_index == slot_index:
            return 'slot_constructing'
        return None

    def can_set_production(self, slot_index, template_name, turret_type_override=None, defense_type_override=None):
        try:
            if self.production_blocker(slot_index):
                return False
            self.validate_production(template_name, turret_type_override, defense_type_override)
        except ValueError:
            return False
        return True

    def set_production(self, slot_index, template_name, turret_type_override=None, defense_type_override=None):
        if not self.can_set_production(slot_index, template_name, turret_type_override, defense_type_override):
            return False
        self.slots[slot_index].update(production_template_name=template_name,
                                     turret_type_override=turret_type_override,
                                     defense_type_override=defense_type_override)
        return True

    def slot_for_wing(self, unit):
        return next((i for i, slot in enumerate(self.slots) if slot['wing_id'] == unit.id), None)

    def free_slot_indices(self):
        return [i for i, slot in enumerate(self.slots)
                if slot['wing_id'] is None and i != self.construction_slot_index]

    def assign_wing(self, unit, slot_index):
        """Associate a wing with one stable slot; containment is handled by the caller."""
        self.validate_slot_index(slot_index)
        if self.slots[slot_index]['wing_id'] not in (None, unit.id):
            raise ValueError("Strikecraft slot is occupied.")
        existing = self.slot_for_wing(unit)
        if existing is not None and existing != slot_index:
            raise ValueError("Wing already has a slot.")
        wing = unit.strikecraft_wing_component
        previous = wing.mother_carrier if wing else None
        if previous is not None and previous is not self.unit and previous.strikecraft_bay_component:
            previous.strikecraft_bay_component.release_wing(unit)
        self.slots[slot_index]['wing_id'] = unit.id
        if wing:
            wing.mother_carrier = self.unit

    def release_wing(self, unit):
        """Release occupancy, retaining the slot's future production settings."""
        index = self.slot_for_wing(unit)
        if index is not None:
            self.slots[index]['wing_id'] = None
        for collection in (self.docked_units, self.launched_units):
            if unit in collection:
                collection.remove(unit)
        if self.replenishing_unit is unit:
            self.replenishing_unit = None
            self.replenish_progress = 0
        wing = unit.strikecraft_wing_component
        if wing and wing.mother_carrier is self.unit:
            wing.mother_carrier = None

    def validate_assignments(self):
        """Check references after every component and carrier link has been restored."""
        self.validate_state()
        wings = self.docked_units + self.launched_units
        assigned = {slot['wing_id'] for slot in self.slots if slot['wing_id'] is not None}
        if len(wings) != len(assigned) or {wing.id for wing in wings} != assigned:
            raise ValueError("Strikecraft slot assignments do not match carrier wings.")
        for unit in wings:
            wing = unit.strikecraft_wing_component
            if (unit.hull_size != HullSize.STRIKECRAFT_WING or not wing
                    or wing.mother_carrier is not self.unit):
                raise ValueError("Invalid strikecraft slot occupant or carrier association.")
        if self.replenishing_unit is not None and self.replenishing_unit not in self.docked_units:
            raise ValueError("Replenishing wing must be docked in its bay.")

    def slot_views(self):
        wings = {wing.id: wing for wing in self.docked_units + self.launched_units}
        result = []
        for index, slot in enumerate(self.slots):
            template = self.production_template(index)
            cost = template_cost(template) if template else None
            wing = wings.get(slot['wing_id'])
            status = ('building' if index == self.construction_slot_index else
                      'docked' if wing in self.docked_units else 'launched' if wing is not None else 'empty')
            result.append(dict(slot_index=index, production_template=slot['production_template_name'],
                               turret_type_override=slot['turret_type_override'], defense_type_override=slot['defense_type_override'],
                               wing_id=slot['wing_id'], wing_name=wing.name if wing else None, status=status,
                               production_turns=template['build_time'] if template else None,
                               production_credit_cost=template['build_cost'] if template else None,
                               production_resource_cost=cost.to_dict() if cost else None,
                               production_shortfall=cost.shortfall(self.unit.owner).to_dict() if cost else None,
                               edit_blocker=self.production_blocker(index)))
        return result

    @staticmethod
    def calc_hull_cost(slots: int) -> float:
        """Compute the hull cost of a Strikecraft Bay component from strikecraft_bay_slots."""
        if slots <= 0:
            return 0.0
        return float(slots * STRIKECRAFT_BAY_HULL_COST_PER_SLOT)

    def get_sidebar_data(self, game_state: 'Game') -> list[dict]:
        from dismantling import evaluate, offline
        from domain.celestials import is_position_in_magnetic_storm
        from strikecraft_service import required, sidebar_labels
        from unit_templates import UNIT_TEMPLATES

        data = super().get_sidebar_data(game_state)
        is_owner = self.unit.owner == game_state.players[game_state.current_player_index]
        galaxy = getattr(getattr(self.unit, 'game', None), 'galaxy', None)
        wings = {wing.id: wing for wing in self.docked_units + self.launched_units}

        def label(text, object_id='#sidebar_info_label'):
            data.append({'type': 'label', 'text': text, 'object_id': object_id, 'height': 20})

        def button(text, action_id, target_data):
            data.append({'type': 'button', 'text': text, 'object_id': '#sidebar_expand_button',
                         'action_id': action_id, 'target_data': target_data, 'height': 25})

        label(f"{self.get_used_slots()}/{self.max_slots} slots · "
              f"{len(self.docked_units)} docked · {len(self.launched_units)} launched")
        label("New wing production enabled" if self.production_enabled else "New wing production paused")
        if self.replenishing_unit:
            label(f"Replenishing {self.replenishing_unit.name}", '#sidebar_status_active_label')
        if is_position_in_magnetic_storm(galaxy, self.unit.in_system, self.unit.in_hex, self.unit.position):
            label("Magnetic storm blocks launches", '#sidebar_status_charging_label')
        if is_owner and not self.is_destroyed and not offline(self.unit):
            if any(self.can_deploy(wing, galaxy) for wing in self.docked_units):
                button("Launch All Wings", 'launch_all_wings', self.unit.id)
            button("Pause new wings" if self.production_enabled else "Resume new wings",
                   'set_wing_production_enabled', (self.unit.id, not self.production_enabled))

        for slot in self.slot_views():
            index = slot['slot_index']
            status = slot['status']
            label(f"Slot {index + 1} · {status.capitalize()}", '#sidebar_section_header_label')
            key = slot['production_template']
            if key:
                label(f"Production · {UNIT_TEMPLATES[key]['name']}")
                for title, field in (('Turrets', 'turret_type_override'), ('Defenses', 'defense_type_override')):
                    if value := slot[field]:
                        label(f"{title}: {value.replace('_', ' ').title()}")
            if status == 'building':
                label(f"{self.construction_progress}/{slot['production_turns']} owner turns complete")
                from antimatter_logistics import work_fuel_blocker
                from constants import CONSTRUCTION_AM_PER_OWNER_TURN
                if work_fuel_blocker(self.unit, CONSTRUCTION_AM_PER_OWNER_TURN):
                    label("Waiting for antimatter", '#sidebar_status_charging_label')

            wing = wings.get(slot['wing_id'])
            if wing is not None:
                component = wing.strikecraft_wing_component
                role = component.wing_type.value.capitalize() if component else "Fighter"
                label(f"{wing.name} · {role} · {format_hp(wing.current_hit_points)}/{format_hp(wing.max_hit_points)} HP")
                if component:
                    for line in sidebar_labels(wing, galaxy):
                        label(line)
                actions = (self.unit.id, wing.id)
                if is_owner and status == 'docked':
                    if self.can_deploy(wing, galaxy):
                        button("Launch wing", 'deploy_ship', actions)
                    if evaluate(self.unit, wing, galaxy).blocker is None:
                        button("Dismantle wing…", 'dismantle_wing', actions)
                if is_owner and status == 'launched' and not required(wing):
                    button("Recall wing", 'recall_ship', actions)
            if is_owner and slot['edit_blocker'] is None:
                button(f"Slot {index + 1}: Select Production…", 'select_wing_production', (self.unit.id, index))
        return data

    def get_basic_sidebar_data(self, game_state: 'Game') -> list[dict]:
        data = super().get_basic_sidebar_data(game_state)
        if self.is_destroyed:
            return data
        used_slots = self.get_used_slots()
        docked_cnt = len(self.docked_units)
        launched_cnt = len(self.launched_units)
        data.append({
            'type': 'label',
            'text': f"Wings: {used_slots}/{self.max_slots} ({docked_cnt} docked, {launched_cnt} launched)",
            'object_id': '#sidebar_value_label',
            'height': 18,
            'indent_level': 1
        })
        return data


    def get_used_slots(self) -> int:
        return sum(slot['wing_id'] is not None for slot in self.slots)

    def can_dock(self, unit: 'Unit') -> bool:
        from dismantling import offline
        from strikecraft_service import required
        if required(unit) and unit.strikecraft_wing_component.mother_carrier is not self.unit:
            return False
        if self.is_destroyed or offline(self.unit) or offline(unit):
            return False
        if unit.hull_size != HullSize.STRIKECRAFT_WING:
            return False
        if unit in self.docked_units:
            return False
        if self.slot_for_wing(unit) is not None:
            return unit in self.launched_units
        return bool(self.free_slot_indices())

    def dock(self, unit: 'Unit', galaxy_ref: 'Galaxy', *, on_docked=None) -> bool:
        if not self.can_dock(unit):
            return False
        
        index = self.slot_for_wing(unit)
        if index is None:
            index = self.free_slot_indices()[0]
        self.assign_wing(unit, index)

        # Remove from system
        if unit.in_system and unit.in_hex is not None:
            system = galaxy_ref.systems.get(unit.in_system)
            if system:
                system.remove_unit(unit)
        
        unit.in_system = self.unit.in_system
        unit.in_hex = self.unit.in_hex
        unit.position = Position(self.unit.position.x, self.unit.position.y)
        sync_docked_sector(unit)
        
        if unit in self.launched_units:
            self.launched_units.remove(unit)
        
        # Orphaned wings are adopted
        if unit.strikecraft_wing_component:
            unit.strikecraft_wing_component.mother_carrier = self.unit
            from strikecraft_abilities import round_now
            unit.strikecraft_wing_component.turns_outside = 0
            unit.strikecraft_wing_component.recovery_ready_round = round_now(galaxy_ref) + 1
        
        self.docked_units.append(unit)
        from environmental_resistance import deactivate
        deactivate(unit)
        from wormhole_stabilization import interrupt
        interrupt(unit)
        if on_docked is not None:
            on_docked()
        if unit.commander_component:
            unit.commander_component.clear_explicit_orders()
            unit.commander_component.suspend_stance_activity("docked")
            
        logger.debug(f"Strikecraft wing {format_unit_for_log(unit)} docked into carrier {format_unit_for_log(self.unit)}.")
        return True

    def can_deploy(self, unit: 'Unit', galaxy_ref: 'Galaxy') -> bool:
        from dismantling import offline
        if self.is_destroyed or offline(self.unit) or offline(unit):
            return False
        if unit not in self.docked_units:
            return False
        from strikecraft_abilities import round_now
        wing = unit.strikecraft_wing_component
        if wing and wing.recovery_ready_round > round_now(galaxy_ref):
            return False
        from domain.celestials import is_position_in_magnetic_storm
        if is_position_in_magnetic_storm(galaxy_ref, self.unit.in_system, self.unit.in_hex, self.unit.position):
            return False
        return True

    def deploy(self, unit: 'Unit', galaxy_ref: 'Galaxy') -> bool:
        """Launch after finding a safe position, preserving slots on failure."""
        if not self.can_deploy(unit, galaxy_ref):
            return False
        position = find_deployment_position(self.unit, unit, galaxy_ref)
        if position is None:
            return False
        unit.in_system = self.unit.in_system
        unit.in_hex = self.unit.in_hex
        unit.position = position
        galaxy_ref.systems[unit.in_system].add_unit(unit)
            
        self.docked_units.remove(unit)
        self.launched_units.append(unit)
        logger.debug(f"Strikecraft wing {format_unit_for_log(unit)} deployed from carrier {format_unit_for_log(self.unit)}.")
        return True

    def finish_auto_construction(self, galaxy: 'Galaxy'):
        """Creates the new Strikecraft Wing and docks it."""
        from construction_customization import customize_template
        index = self.construction_slot_index
        self.validate_slot_index(index)
        slot = self.slots[index]
        template_name = slot['production_template_name']
        self.validate_production(template_name, slot['turret_type_override'], slot['defense_type_override'])
        template = customize_template(self.production_template(index), slot['turret_type_override'], slot['defense_type_override'])
 
        from .constructor import assemble_unit_from_template
        new_unit = assemble_unit_from_template(
            template_name, template, self.unit.owner, self.unit.in_system,
            self.unit.in_hex, Position(self.unit.position.x, self.unit.position.y), self.unit.game)

        self.assign_wing(new_unit, index)

        # Direct dock
        self.docked_units.append(new_unit)
        self.construction_slot_index = None
        self.construction_progress = 0
        from turn_briefing import unit_event
        unit_event(new_unit, "development", "Wing construction completed", private=True)
        logger.debug(f"Auto-constructed and docked new strikecraft wing {format_unit_for_log(new_unit)} for carrier {format_unit_for_log(self.unit)}.")

    def update(self, galaxy: 'Galaxy'):
        """Automatically constructs or replenishes wings. Called each turn."""
        from dismantling import offline
        if self.is_destroyed or offline(self.unit):
            return

        # Prune destroyed launched units
        for wing in list(self.launched_units):
            if wing.current_hit_points <= 0:
                self.release_wing(wing)

        owner = self.unit.owner
        if not owner:
            return

        from constants import CONSTRUCTION_AM_PER_OWNER_TURN, REPAIR_AM_PER_HP
        tank = self.unit.antimatter_component

        # 1. Update ongoing replenishment
        if self.replenishing_unit:
            # If the unit was deployed or destroyed in the meantime, cancel replenishment
            if self.replenishing_unit not in self.docked_units or self.replenishing_unit.current_hit_points <= 0:
                self.replenishing_unit = None
                self.replenish_progress = 0
            else:
                missing = self.replenishing_unit.max_hit_points - self.replenishing_unit.current_hit_points
                if missing > 0 and (tank is None or not tank.consume(min(10, missing) * REPAIR_AM_PER_HP)):
                    return
                self.replenish_progress += 1
                if self.replenish_progress >= 1: # 1 turn to restore up to 10 hull HP
                    self.replenishing_unit.heal_hull(10.0)
                    logger.debug(f"Strikecraft bay on {format_unit_for_log(self.unit)} restored hull HP to wing {format_unit_for_log(self.replenishing_unit)}. HP: {self.replenishing_unit.current_hit_points}/{self.replenishing_unit.max_hit_points}")
                    # If fully healed, clear. Otherwise keep replenishing on next turn
                    if self.replenishing_unit.current_hit_points >= self.replenishing_unit.max_hit_points:
                        self.replenishing_unit = None
                        self.replenish_progress = 0
                    elif not getattr(self, '_dismantle_job', None):
                        # Start next replenishment step immediately if we have credits
                        cost = 35
                        if owner.credits >= cost:
                            owner.credits -= cost
                            self.replenish_progress = 0
                        else:
                            self.replenishing_unit = None
                            self.replenish_progress = 0
                    else:
                        self.replenishing_unit = None
                        self.replenish_progress = 0
                return

        # 2. Update ongoing construction
        if self.constructing:
            if tank is None or not tank.consume(CONSTRUCTION_AM_PER_OWNER_TURN):
                return
            self.construction_progress += 1
            if self.construction_progress >= self.production_template(self.construction_slot_index)['build_time']:
                self.finish_auto_construction(galaxy)
                self.construction_slot_index = None
                self.construction_progress = 0
            return

        if getattr(self, '_dismantle_job', None):
            return

        # 3. If not busy, check if we need to replenish a damaged wing
        damaged_wing = None
        for wing in self.docked_units:
            if wing.current_hit_points < wing.max_hit_points:
                damaged_wing = wing
                break

        if damaged_wing:
            cost = 35
            if owner.credits >= cost:
                owner.credits -= cost
                self.replenishing_unit = damaged_wing
                self.replenish_progress = 0
                logger.debug(f"Strikecraft bay on {format_unit_for_log(self.unit)} started replenishing wing {format_unit_for_log(damaged_wing)} for {cost} credits.")
                return

        # 4. One worker chooses the first affordable empty, configured slot.
        if self.production_enabled:
            for index in self.free_slot_indices():
                slot = self.slots[index]
                template = self.production_template(index)
                if template is None:
                    continue
                self.validate_production(slot['production_template_name'], slot['turret_type_override'], slot['defense_type_override'])
                cost = template_cost(template)
                if cost.pay(owner):
                    self.construction_slot_index = index
                    self.construction_progress = 0
                    logger.debug(f"Strikecraft bay on {format_unit_for_log(self.unit)} started constructing {template['name']} in slot {index} for {cost.describe()}.")
                    return

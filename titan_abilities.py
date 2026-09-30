"""Owner-phase Titan powers and read-only effective-stat/visibility queries.

Orders reserve intent. Only ``process`` pays for and executes powers. Cooldown
deadlines belong to the hull, independently of replaceable Ability equipment.
"""
from constants import HullSize, NAVIGATION_CLEARANCE
from domain.players import are_allies, are_enemies
from geometry import Position, distance, is_point_in_circle, segment_clearance
from tactical_balance import SPECS
from titan_balance import TITAN_ABILITIES, GATHER_RADIUS, ESCORT_CAPACITY, AEGIS_RADIUS, LANCE_DAMAGE


def instance(unit, kind):
    from tactical_abilities import get_instance
    return get_instance(unit, kind)


def now(unit):
    return getattr(unit.game, 'turn_number', 1)


def source_ready(unit, kind, galaxy):
    from tactical_abilities import deployed, equipment_ready
    from dismantling import offline
    comp = unit.ability_component
    return bool(unit.hull_size == HullSize.TITAN and deployed(unit, galaxy)
                and not unit.is_disabled and not offline(unit)
                and not unit.is_hidden_in_gas_giant and comp and not comp.is_destroyed
                and instance(unit, kind) and equipment_ready(unit, SPECS[kind]))


def availability(unit, kind, galaxy, *, ignore_reservations=False, resources=True):
    from tactical_abilities import pending_casts
    if not source_ready(unit, kind, galaxy):
        return 'capability_unavailable'
    inst = instance(unit, kind)
    if inst.is_active or unit.titan_cooldowns.get(kind, 0) > now(unit):
        return 'capability_unavailable'
    if kind == 'fleet_jump':
        from unit_components.enums import HyperdriveType, JumpStatus
        drive = unit.hyperdrive_component
        if drive.drive_type not in (HyperdriveType.BASIC, HyperdriveType.ADVANCED) or drive.jump_status != JumpStatus.READY:
            return 'capability_unavailable'
        if jump_origin_blockers(unit, galaxy):
            return 'jump_inhibited'
    reserved = list(pending_casts(unit)) if not ignore_reservations else []
    if any(k == kind for k, _ in reserved):
        return 'capability_unavailable'
    if resources and unit.antimatter_component.current_amount - sum(SPECS[k].cost for k, _ in reserved) < SPECS[kind].cost:
        return 'insufficient_resources'
    return None


def jump_participants(unit, galaxy):
    from tactical_abilities import sector_for
    from dismantling import offline
    sector = sector_for(unit, galaxy)
    return [unit] + sorted((u for u in sector.units if u is not unit and u.owner == unit.owner
        and u.current_hit_points > 0 and u.hull_size != HullSize.STRIKECRAFT_WING
        and not u.is_disabled and not offline(u) and not u.is_hidden_in_gas_giant
        and u.engines_component and not u.engines_component.is_destroyed
        and u.engines_component.effective_speed > 0 and distance(unit.position, u.position) <= GATHER_RADIUS), key=lambda u: u.id)


def jump_origin_blockers(unit, galaxy):
    """Owned participants in known origin fields; destination remains conditional."""
    from tactical_abilities import sector_for
    from visibility import VisibilityService, known_inhibition_zones
    snapshot = VisibilityService.compute(galaxy, unit.owner, record_intel=False)
    zones = known_inhibition_zones(sector_for(unit, galaxy), unit.owner, snapshot)
    return [ship.id for ship in jump_participants(unit, galaxy)
            if any(is_point_in_circle(ship.position, zone) for zone in zones)]


def jump_plan(unit, galaxy, system_name, hex_coord, position):
    """Return a complete, validated relocation or an error, without mutation."""
    from tactical_abilities import sector_for, obstacles
    if system_name != unit.in_system:
        return 'out_of_range', []
    system = galaxy.systems.get(system_name)
    destination = system.hexes.get(hex_coord) if system else None
    if destination is None or position is None:
        return 'invalid_parameters', []
    if (system_name, hex_coord) not in unit.owner.sector_intel:
        return 'unexplored_destination', []
    participants = jump_participants(unit, galaxy)
    if sum(u.hull_capacity for u in participants if u is not unit) > ESCORT_CAPACITY:
        return 'insufficient_capacity', []
    origin = sector_for(unit, galaxy)
    plan = [(u, Position(position.x + u.position.x - unit.position.x,
                         position.y + u.position.y - unit.position.y)) for u in participants]
    for ship, arrival in plan:
        for sector, point in ((origin, ship.position), (destination, arrival)):
            if distance(point, sector.boundary_circle.center) > sector.boundary_circle.radius - NAVIGATION_CLEARANCE:
                return 'invalid_destination', []
            if any(is_point_in_circle(point, zone) for zone in sector.get_all_inhibition_zones()):
                return 'jump_inhibited', []
            if any(distance(point, center) < radius for center, radius in obstacles(sector, ship, include_ships=False)):
                return 'invalid_destination', []
            if any(other not in participants and other.current_hit_points > 0
                   and distance(point, other.position) < NAVIGATION_CLEARANCE for other in sector.units):
                return 'invalid_destination', []
        if any(other is not ship and distance(arrival, point) < NAVIGATION_CLEARANCE for other, point in plan):
            return 'invalid_destination', []
    return None, plan


def lance_target(unit, galaxy, target_id):
    from tactical_abilities import deployed, sector_for
    from visibility import VisibilityService, is_unit_visible
    target = galaxy.get_unit_by_id(target_id)
    if not target or not deployed(target, galaxy) or target.hull_size == HullSize.STRIKECRAFT_WING:
        return 'invalid_target'
    if not are_enemies(unit.owner, target.owner):
        return 'invalid_relation'
    if not is_unit_visible(VisibilityService.compute(galaxy, unit.owner, record_intel=False), target):
        return 'target_not_visible'
    sector = sector_for(unit, galaxy)
    if sector is not sector_for(target, galaxy) or distance(unit.position, target.position) > SPECS['siege_lance'].range:
        return 'out_of_range'
    if any(getattr(body, 'collision_radius', 0) > 0 and
           segment_clearance(unit.position, target.position, body.position) < body.collision_radius
           for body in sector.celestial_bodies):
        return 'firing_blocked'
    return None


def validate(unit, kind, galaxy, target_id=None, position=None, *, system_name=None, hex_coord=None,
             check_ready=True, ignore_reservations=False, resources=True, **unused):
    if check_ready:
        error = availability(unit, kind, galaxy, ignore_reservations=ignore_reservations, resources=resources)
        if error:
            return error
    if kind == 'fleet_jump':
        return jump_plan(unit, galaxy, system_name, hex_coord, position)[0]
    if kind == 'deep_scan':
        if system_name != unit.in_system:
            return 'out_of_range'
        system = galaxy.systems.get(system_name)
        if system is None or hex_coord not in system.hexes:
            return 'invalid_destination'
    if kind == 'siege_lance':
        return lance_target(unit, galaxy, target_id)
    return None


def effect_valid(unit, kind, galaxy):
    """Pure eligibility query; expiry and cancellation are phase mutations."""
    inst = instance(unit, kind)
    if not inst or not inst.is_active or not source_ready(unit, kind, galaxy):
        return False
    if inst.source_owner_id != unit.owner.id:
        return False
    if kind in ('deep_scan', 'siege_lance') and inst.system_name != unit.in_system:
        return False
    if kind == 'siege_lance':
        root = getattr(unit.commander_component, 'current_order', None)
        if (inst.hex_coord != unit.in_hex or inst.origin_position != unit.position
                or not root or root.public_id != inst.order_id
                or root.status.name not in ('PENDING', 'IN_PROGRESS')):
            return False
    return True


def cancel(unit, kind):
    inst = instance(unit, kind)
    if kind == 'fleet_jump' or not inst or not inst.is_active:
        return False
    inst.is_active = False
    inst.duration_remaining = 0
    if kind == 'siege_lance':
        root = getattr(unit.commander_component, 'current_order', None)
        if root and root.public_id == inst.order_id and root.status.name in ('PENDING', 'IN_PROGRESS'):
            root.fail('ability_interrupted')
    return True


def decommission(unit, component):
    """End effects before removing/replacing equipment, even if repaired at once."""
    from tactical_balance import EQUIPMENT
    for kind in TITAN_ABILITIES:
        if component is unit.ability_component or any(getattr(unit, EQUIPMENT[flag], None) is component for flag in SPECS[kind].equipment):
            cancel(unit, kind)


def reconcile(galaxy):
    from campaign_graph import iter_units
    for unit, _ in iter_units(galaxy):
        for kind in TITAN_ABILITIES:
            inst = instance(unit, kind)
            if inst and inst.is_active and (not effect_valid(unit, kind, galaxy)
                    or (kind == 'siege_lance' and lance_target(unit, galaxy, inst.target_unit_id))):
                cancel(unit, kind)


def start_owner_turn(galaxy, player, round_number):
    from campaign_graph import iter_units
    for unit, _ in iter_units(galaxy):
        if unit.owner != player:
            continue
        for kind in TITAN_ABILITIES:
            inst = instance(unit, kind)
            if not inst:
                continue
            inst.ready_round = unit.titan_cooldowns.get(kind, 0)
            inst.cooldown_remaining = max(0, inst.ready_round - round_number)
            if kind != 'siege_lance':
                inst.duration_remaining = max(0, (inst.expires_round or round_number) - round_number)
                if inst.is_active and not inst.duration_remaining:
                    cancel(unit, kind)
    reconcile(galaxy)


def _relocate(ship, system, hex_coord, position):
    if ship.in_hex != hex_coord:
        system.move_unit_between_hexes(ship, hex_coord)
    ship.position = position
    # Containment is retained, and carried units inherit their carrier's location.
    for component in (ship.hangar_component, ship.strikecraft_bay_component):
        if component:
            for child in component.docked_units:
                child.in_system, child.in_hex = ship.in_system, ship.in_hex
                _relocate(child, system, hex_coord, position)


def process(game, player):
    from campaign_graph import iter_units
    from unit_orders.base import OrderStatus
    from unit_components.enums import TurretType
    galaxy = game.galaxy
    reconcile(galaxy)
    for unit, _ in list(iter_units(galaxy)):
        if unit.owner != player or unit.hull_size != HullSize.TITAN or unit.last_titan_action_round >= game.turn_number:
            continue
        unit.last_titan_action_round = game.turn_number
        root = unit.commander_component.current_order if unit.commander_component else None
        if not root or root.status not in (OrderStatus.PENDING, OrderStatus.IN_PROGRESS):
            continue
        kind = root.parameters.get('ability_type')
        if root.order_type.name != 'USE_ABILITY' or kind not in TITAN_ABILITIES:
            continue
        inst = instance(unit, kind)
        if kind == 'siege_lance' and inst and inst.is_active and inst.order_id == root.public_id:
            if inst.charge_round >= game.turn_number:
                continue
            target = galaxy.get_unit_by_id(inst.target_unit_id)
            from tactical_abilities import combat_hit
            before = target.current_hit_points
            combat_hit(target, LANCE_DAMAGE, TurretType.BEAM, attacker=unit)
            unit.gain_experience(max(0, before - target.current_hit_points))
            inst.is_active = False
            inst.duration_remaining = 0
            root.status = OrderStatus.COMPLETED
            continue
        p = root.parameters
        error = validate(unit, kind, galaxy, p.get('target_unit_id'), p.get('target_position'),
                         system_name=p.get('target_system_name'), hex_coord=p.get('target_hex_coord'), ignore_reservations=True)
        if error:
            root.fail(error)
            continue
        plan = jump_plan(unit, galaxy, p['target_system_name'], p['target_hex_coord'], p['target_position'])[1] if kind == 'fleet_jump' else []
        if not unit.antimatter_component.consume(SPECS[kind].cost):
            root.fail('insufficient_resources')
            continue
        unit.titan_cooldowns[kind] = game.turn_number + SPECS[kind].cooldown
        inst.ready_round = unit.titan_cooldowns[kind]
        inst.cooldown_remaining = SPECS[kind].cooldown
        inst.expires_round = game.turn_number + SPECS[kind].duration
        inst.duration_remaining = SPECS[kind].duration
        inst.source_owner_id = unit.owner.id
        inst.system_name = unit.in_system
        inst.hex_coord = unit.in_hex
        inst.is_active = kind != 'fleet_jump'
        inst.target_unit_id = p.get('target_unit_id')
        inst.order_id = root.public_id
        if kind == 'fleet_jump':
            system = galaxy.systems[unit.in_system]
            for ship, arrival in plan:
                if ship is not unit and ship.commander_component:
                    ship.commander_component.clear_explicit_orders(internal=True)
                    ship.commander_component.suspend_stance_activity('Fleet Jump')
                _relocate(ship, system, p['target_hex_coord'], arrival)
            unit.hyperdrive_component.start_recharge()
        elif kind == 'deep_scan':
            inst.hex_coord = p['target_hex_coord']
            from visibility import VisibilityService
            for viewer in game.players:
                if are_allies(unit.owner, viewer):
                    VisibilityService.compute(galaxy, viewer, turn_number=game.turn_number)
        elif kind == 'siege_lance':
            inst.origin_position = Position(unit.position.x, unit.position.y)
            inst.charge_round = game.turn_number
            if unit.engines_component:
                unit.engines_component.clear_move_target()
            unit.weapons_component.clear_target()
            from turn_briefing import unit_event
            unit_event(galaxy.get_unit_by_id(inst.target_unit_id), 'combat', 'Siege Lance charging; impact next attacker End Turn', actor=unit)
            root.status = OrderStatus.IN_PROGRESS
            continue
        root.status = OrderStatus.COMPLETED
        game.visibility_dirty = True
        game.sidebar_needs_update = True


def coverage(galaxy, viewer):
    from campaign_graph import iter_units
    for source, _ in iter_units(galaxy):
        if are_allies(source.owner, viewer) and effect_valid(source, 'deep_scan', galaxy):
            inst = instance(source, 'deep_scan')
            yield inst.system_name, inst.hex_coord


def protected(unit, kind):
    from tactical_abilities import deployed, sector_for
    galaxy = getattr(unit, "in_galaxy", None)
    if not galaxy or not deployed(unit, galaxy):
        return False
    if kind == 'carrier_supremacy' and unit.hull_size != HullSize.STRIKECRAFT_WING:
        return False
    return any(are_allies(source.owner, unit.owner) and effect_valid(source, kind, galaxy)
               and (kind == 'carrier_supremacy' or distance(source.position, unit.position) <= AEGIS_RADIUS)
               for source in sector_for(unit, galaxy).units)


def incoming_multiplier(unit):
    return (0.5 if protected(unit, 'aegis_field') else 1.0) * (0.5 if protected(unit, 'carrier_supremacy') else 1.0)


def charging(unit):
    return effect_valid(unit, 'siege_lance', getattr(unit, 'in_galaxy', None))


def state_view(unit):
    result = {'core_operational': bool(unit.titan_component and not unit.titan_component.is_destroyed),
              'cooldowns': {kind: max(0, deadline - now(unit)) for kind, deadline in unit.titan_cooldowns.items()},
              'active': []}
    for kind in TITAN_ABILITIES:
        inst = instance(unit, kind)
        if inst and effect_valid(unit, kind, unit.in_galaxy):
            result['active'].append({'ability': kind, 'expires_round': inst.expires_round,
                'system_name': inst.system_name, 'hex_coord': inst.hex_coord,
                'charge_round': inst.charge_round})
    return result

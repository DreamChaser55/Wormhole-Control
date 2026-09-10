"""Authoritative tactical ability rules shared by orders, presentation and agents."""
import math

from constants import HullSize, NAVIGATION_CLEARANCE, NebulaType
from domain.players import are_allies, are_enemies
from geometry import Position, distance


from tactical_balance import (SPECS, EQUIPMENT, TRACTOR_PULL, TRACTOR_STANDOFF, TRACTOR_BREAK,
    TRACTOR_COST, TRACTOR_SPEED, SWEEP_RADIUS, SWEEP_MINES, GUARDIAN_FRACTION, GUARDIAN_CAP,
    GUARDIAN_RETAINED, RECOVERY_RANGE, CATALYST_HYDROGEN_FUEL, CATALYST_NITROGEN_COOLING,
    CATALYST_OXYGEN_SPLASH, CATALYST_DUST_SENSORS)


def sectors(galaxy):
    for system in getattr(galaxy, "systems", {}).values():
        yield from system.hexes.values()


def sector_for(obj, galaxy):
    system = galaxy.systems.get(obj.in_system) if galaxy else None
    return system.hexes.get(obj.in_hex) if system else None


def deployed(obj, galaxy):
    sector = sector_for(obj, galaxy)
    return bool(sector and obj.current_hit_points > 0 and obj in sector.units)


def find_deployable(galaxy, object_id):
    return next((d for sector in sectors(galaxy) for d in getattr(sector, 'deployables', ())
                 if d.id == object_id and d.current_hit_points > 0), None)


def combat_target(galaxy, object_id):
    return galaxy.get_unit_by_id(object_id) or find_deployable(galaxy, object_id)


def deployments(galaxy, source_id, kind):
    collection = 'catalyst_patches' if kind == 'nebula_catalyst' else 'deployables'
    return [obj for sector in sectors(galaxy) for obj in getattr(sector, collection, ())
            if obj.deploying_ship_id == source_id and (collection == 'catalyst_patches' or obj.kind == kind)]


def get_instance(unit, kind):
    from unit_components.enums import AbilityType
    comp = getattr(unit, 'ability_component', None)
    return comp.abilities.get(AbilityType(kind)) if comp else None


def equipment_ready(unit, spec):
    for flag in spec.equipment:
        comp = getattr(unit, EQUIPMENT[flag], None)
        if flag == 'has_minelayer_component':
            from unit_components.minelayer import MinelayerComponent
            comp = unit.get_component(MinelayerComponent)
        if flag == 'has_defenses':
            from unit_components.defenses import Defenses
            comp = unit.get_component(Defenses)
        if not comp or comp.is_destroyed:
            return False
        if flag == 'has_engine' and comp.speed <= 0:
            return False
    return True


def pending_casts(unit):
    """Derive reservations from explicit roots, never a separately saved counter."""
    commander = getattr(unit, 'commander_component', None)
    roots = [getattr(commander, 'current_order', None), *getattr(commander, 'orders_queue', ())]
    for order in roots:
        if order is None or order.status.name not in ('PENDING', 'IN_PROGRESS'):
            continue
        kind = order.parameters.get('ability_type')
        if order.order_type.name == 'USE_ABILITY' and kind in SPECS:
            # The root remains while an approach child activates the ability.
            inst = get_instance(unit, kind)
            if inst and inst.is_ready:
                yield kind, order.parameters.get('target_unit_id')


def availability(unit, kind, galaxy, *, ignore_reservations=False, resources=True):
    spec = SPECS[kind]
    inst = get_instance(unit, kind)
    if not deployed(unit, galaxy) or not inst or unit.ability_component.is_destroyed or unit.is_disabled:
        return 'capability_unavailable'
    if not inst.is_ready or not equipment_ready(unit, spec):
        return 'capability_unavailable'
    am = unit.antimatter_component
    reserved = list(pending_casts(unit)) if not ignore_reservations else []
    if any(k == kind for k, _ in reserved):
        return 'capability_unavailable'
    if not am or am.is_destroyed or (resources and am.current_amount - sum(SPECS[k].cost for k, _ in reserved) < spec.cost):
        return 'insufficient_resources'
    if resources and spec.cap and len(deployments(galaxy, unit.id, kind)) + sum(k == kind for k, _ in reserved) >= spec.cap:
        return 'deployment_cap_reached'
    return None


def segment_entry(start, end, center, radius):
    """First normalized contact with a closed circle, or None."""
    dx, dy = end.x-start.x, end.y-start.y
    ox, oy = start.x-center.x, start.y-center.y
    c = ox*ox + oy*oy - radius*radius
    if c <= 0:
        return 0.0
    a = dx*dx + dy*dy
    if a <= 0:
        return None
    b = 2*(ox*dx + oy*dy)
    disc = b*b - 4*a*c
    if disc < 0:
        return None
    t = (-b-math.sqrt(disc))/(2*a)
    return t if 0 <= t <= 1 else None


def sweep_fields(unit, endpoint, galaxy):
    from visibility import VisibilityService, is_minefield_visible
    snapshot = VisibilityService.compute(galaxy, unit.owner, record_intel=False)
    hits = []
    for field in sector_for(unit, galaxy).minefields:
        if field.mines_remaining <= 0 or not are_enemies(unit.owner, field.owner) or not is_minefield_visible(snapshot, field):
            continue
        entry = segment_entry(unit.position, endpoint, field.position, field.detonation_radius + SWEEP_RADIUS)
        if entry is not None:
            hits.append((entry, field.id, field))
    return [f for _, _, f in sorted(hits)]


def obstacles(sector, moving=None, *, include_ships=True):
    for body in sector.celestial_bodies:
        radius = getattr(body, 'collision_radius', 0)
        if radius > 0:
            yield body.position, radius + NAVIGATION_CLEARANCE
        elif moving is not None:
            if hasattr(body, 'can_unit_enter') and not body.can_unit_enter(moving):
                yield body.position, getattr(body, 'radius', 0) + NAVIGATION_CLEARANCE
    if include_ships:
        for unit in sector.units:
            if unit is not moving and unit.current_hit_points > 0:
                yield unit.position, NAVIGATION_CLEARANCE


def valid_placement(unit, position, galaxy):
    sector = sector_for(unit, galaxy)
    if distance(position, sector.boundary_circle.center) > sector.boundary_circle.radius - 20:
        return False
    return all(distance(position, center) >= radius for center, radius in obstacles(sector))


def incoming_link(target, kind, galaxy):
    for sector in sectors(galaxy):
        for source in sector.units:
            inst = get_instance(source, kind)
            if inst and inst.is_active and inst.target_unit_id == target.id and link_valid(source, inst, galaxy):
                return source, inst
    return None


def link_valid(source, inst, galaxy):
    kind = inst.definition.ability_type.value
    target = galaxy.get_unit_by_id(inst.target_unit_id)
    if not deployed(source, galaxy) or source.is_disabled or source.ability_component.is_destroyed or not equipment_ready(source, SPECS[kind]):
        return False
    if target is None or not deployed(target, galaxy) or sector_for(source, galaxy) is not sector_for(target, galaxy):
        return False
    if inst.source_owner_id != source.owner.id:
        return False
    limit = TRACTOR_BREAK if kind == 'tractor_tether' else SPECS[kind].range
    return distance(source.position, target.position) <= limit and (kind != 'guardian_link' or are_allies(source.owner, target.owner))


def validate(unit, kind, galaxy, target_id=None, position=None, *, approach=False, check_ready=True, ignore_reservations=False, resources=True, links=True):
    spec = SPECS[kind]
    if check_ready:
        blocker = availability(unit, kind, galaxy, ignore_reservations=ignore_reservations, resources=resources)
        if blocker:
            return blocker
    if spec.target_kind == 'unit':
        from visibility import VisibilityService, is_unit_visible
        target = galaxy.get_unit_by_id(target_id)
        snapshot = VisibilityService.compute(galaxy, unit.owner, record_intel=False)
        if target is None or target is unit or not deployed(target, galaxy) or not is_unit_visible(snapshot, target):
            return 'target_unavailable'
        if kind == 'tractor_tether':
            if not (are_allies(unit.owner, target.owner) or are_enemies(unit.owner, target.owner)):
                return 'target_unavailable'
            if target.hull_size == HullSize.STRIKECRAFT_WING or target.hull_size.value >= unit.hull_size.value or target.engines_component is None or target.engines_component.speed <= 0:
                return 'target_unavailable'
        elif not are_allies(unit.owner, target.owner):
            return 'target_unavailable'
        if links and incoming_link(target, kind, galaxy):
            return 'target_unavailable'
        if links and kind == 'guardian_link':
            cursor, seen = target, {unit.id}
            while cursor is not None:
                if cursor.id in seen:
                    return 'target_unavailable'
                seen.add(cursor.id)
                link = get_instance(cursor, kind)
                cursor = galaxy.get_unit_by_id(link.target_unit_id) if link and link.is_active else None
        if not approach and (sector_for(unit, galaxy) is not sector_for(target, galaxy) or distance(unit.position, target.position) > spec.range):
            return 'out_of_range'
    else:
        if position is None or not all(math.isfinite(v) for v in (position.x, position.y)):
            return 'invalid_value'
        sector = sector_for(unit, galaxy)
        if sector is None or distance(position, sector.boundary_circle.center) > sector.boundary_circle.radius:
            return 'out_of_range'
        if distance(unit.position, position) > spec.range:
            return 'out_of_range'
        if kind in ('ghost_fleet', 'fuel_cache') and not valid_placement(unit, position, galaxy):
            return 'path_unavailable'
        if kind == 'mine_clearing_sweep' and not sweep_fields(unit, position, galaxy):
            return 'target_unavailable'
        if kind == 'nebula_catalyst':
            from domain.celestials import Nebula
            body = galaxy.get_celestial_body_by_id(target_id)
            if not isinstance(body, Nebula) or sector_for(body, galaxy) is not sector_for(unit, galaxy) or distance(position, body.position) > body.radius:
                return 'target_unavailable'
    return None


def activate(unit, kind, galaxy, target_id=None, position=None):
    blocker = validate(unit, kind, galaxy, target_id, position, ignore_reservations=True)
    if blocker:
        return False
    from domain.deployables import Deployable, CatalystPatch
    spec, inst = SPECS[kind], get_instance(unit, kind)
    sector = sector_for(unit, galaxy)
    game = getattr(unit, 'game', None)
    now = getattr(game, 'turn_number', 1)
    if game is not None:
        galaxy.game = game
    # Validation above is mutation-free; the following operation is synchronous.
    if not unit.antimatter_component.consume(spec.cost):
        return False
    if kind in ('ghost_fleet', 'fuel_cache'):
        sector.deployables.append(Deployable(unit.owner, position, unit.in_hex, unit.in_system, kind, unit.id, galaxy))
    elif kind == 'nebula_catalyst':
        sector.catalyst_patches.append(CatalystPatch(unit.owner, position, unit.in_hex, unit.in_system, unit.id, target_id, now + spec.duration))
    elif kind == 'mine_clearing_sweep':
        remaining = SWEEP_MINES
        for field in sweep_fields(unit, position, galaxy):
            removed = min(remaining, field.mines_remaining)
            field.mines_remaining -= removed
            remaining -= removed
            if field.mines_remaining == 0:
                sector.minefields.remove(field)
            if remaining == 0:
                break
    else:
        inst.target_unit_id = target_id
        inst.is_active = True
    inst.target_body_id = target_id if kind == 'nebula_catalyst' else None
    inst.target_position = position
    inst.source_owner_id = unit.owner.id
    inst.ready_round = now + spec.cooldown
    inst.expires_round = now + spec.duration if spec.duration else None
    inst.cooldown_remaining = spec.cooldown
    inst.duration_remaining = spec.duration
    if game:
        game.visibility_dirty = True
        game.sidebar_needs_update = True
    return True


def cancel(unit, kind):
    inst = get_instance(unit, kind)
    if kind not in ('tractor_tether', 'guardian_link') or not inst or not inst.is_active:
        return False
    inst.is_active = False
    inst.target_unit_id = None
    inst.duration_remaining = 0
    return True


def start_owner_turn(galaxy, player, round_number):
    from campaign_graph import iter_units
    for unit, _ in iter_units(galaxy):
        if unit.owner != player or not unit.ability_component:
            continue
        for kind in SPECS:
            inst = get_instance(unit, kind)
            if not inst:
                continue
            inst.cooldown_remaining = max(0, (inst.ready_round or round_number) - round_number)
            inst.duration_remaining = max(0, (inst.expires_round or round_number) - round_number)
            if inst.is_active and (inst.duration_remaining == 0 or not link_valid(unit, inst, galaxy)):
                cancel(unit, kind)
    for sector in sectors(galaxy):
        sector.catalyst_patches[:] = [p for p in sector.catalyst_patches if p.owner != player or p.expires_round > round_number]


def reconcile_links(galaxy):
    from campaign_graph import iter_units
    for unit, _ in iter_units(galaxy):
        for kind in ('tractor_tether', 'guardian_link'):
            inst = get_instance(unit, kind)
            if inst and inst.is_active and not link_valid(unit, inst, galaxy):
                cancel(unit, kind)


def process_pulls(galaxy, player, round_number):
    reconcile_links(galaxy)
    sources = sorted((u for s in sectors(galaxy) for u in s.units if u.owner == player), key=lambda u: u.id)
    for source in sources:
        inst = get_instance(source, 'tractor_tether')
        if not inst or not inst.is_active or inst.last_pull_round == round_number:
            continue
        inst.last_pull_round = round_number
        target = galaxy.get_unit_by_id(inst.target_unit_id)
        gap = distance(source.position, target.position)
        length = min(TRACTOR_PULL, max(0, gap-TRACTOR_STANDOFF))
        if length <= 0:
            continue
        end = Position(target.position.x + (source.position.x-target.position.x)*length/gap,
                       target.position.y + (source.position.y-target.position.y)*length/gap)
        fraction = 1.0
        for center, radius in obstacles(sector_for(target, galaxy), target):
            contact = segment_entry(target.position, end, center, radius)
            if contact is not None:
                fraction = min(fraction, max(0, contact-1e-6))
        if fraction <= 0:
            continue
        am = source.antimatter_component
        if not am or am.is_destroyed or not am.consume(TRACTOR_COST):
            cancel(source, 'tractor_tether')
            continue
        target.position = Position(target.position.x+(end.x-target.position.x)*fraction,
                                   target.position.y+(end.y-target.position.y)*fraction)
        # Existing waypoints remain order intent; restart navigation from the displaced position.
        if target.engines_component:
            target.engines_component.clear_move_target()
        commander = target.commander_component
        if commander:
            from unit_orders.base import OrderType, OrderStatus
            def reset(order):
                if order.order_type == OrderType.MOVE:
                    for child in order.sub_orders:
                        child.cancel()
                    order.sub_orders.clear()
                    order.status = OrderStatus.PENDING
                else:
                    for child in order.sub_orders:
                        reset(child)
            for root in (commander.current_order, commander.standing_order):
                if root is not None:
                    reset(root)
    reconcile_links(galaxy)


def combat_hit(target, amount, damage_type=None, *, component_type=None, is_splash=False):
    """Route once, then retain each recipient's existing mitigation and spillover rules."""
    amount = max(0, int(amount))
    galaxy = getattr(target, 'in_galaxy', None)
    link = incoming_link(target, 'guardian_link', galaxy) if galaxy and amount else None
    if link:
        guardian, inst = link
        redirected = min(math.floor(amount * inst.redirect_fraction), inst.redirect_cap)
        amount -= redirected
        guardian.take_damage(math.floor(redirected * inst.redirect_retained), damage_type, is_splash=is_splash)
    if component_type:
        if link:
            # Linked subsystem hits apply reduction once, including any hull spillover.
            if is_splash:
                from environmental_effects import splash_damage
                amount = splash_damage(amount, target)
        spillover = target.take_component_damage(component_type, amount, damage_type, apply_reduction=True) if link else target.take_component_damage(component_type, amount, damage_type)
        if spillover > 0:
            if link:
                # take_component_damage has already applied defenses; use a hull-only debit.
                target.current_hit_points = max(0, target.current_hit_points - spillover)
                if target.current_hit_points == 0:
                    target.destroy()
            else:
                target.take_damage(spillover)
    else:
        target.take_damage(amount, damage_type, is_splash=is_splash)


def catalyst_effects(unit, galaxy):
    result = {}
    sector = sector_for(unit, galaxy)
    if not sector or not deployed(unit, galaxy) or getattr(unit, 'is_hidden_in_gas_giant', False):
        return result
    for patch in getattr(sector, 'catalyst_patches', ()):
        body = galaxy.get_celestial_body_by_id(patch.nebula_id)
        if body is None or distance(unit.position, patch.position) > patch.radius or distance(unit.position, body.position) > body.radius:
            continue
        friendly, enemy = are_allies(patch.owner, unit.owner), are_enemies(patch.owner, unit.owner)
        if friendly and body.nebula_type == NebulaType.HYDROGEN:
            result['fuel_multiplier'] = CATALYST_HYDROGEN_FUEL
        if friendly and body.nebula_type == NebulaType.NITROGEN:
            result['cooldown_reduction'] = CATALYST_NITROGEN_COOLING
        if enemy and body.nebula_type == NebulaType.OXYGEN:
            result['splash_damage_multiplier'] = CATALYST_OXYGEN_SPLASH
        if enemy and body.nebula_type == NebulaType.DUST:
            result['sensor_multiplier'] = CATALYST_DUST_SENSORS
    return result


def ability_catalog():
    from dataclasses import asdict
    from unit_components.abilities.registry import ABILITY_DEFINITIONS
    from tactical_balance import DEPLOYABLE_HP, CACHE_FUEL, CACHE_OVERHEAD, CATALYST_RADIUS
    catalog = {kind.value: {'name': d.name, 'description': d.description, 'cost': d.antimatter_cost,
        'equipment': d.required_components, 'range': d.range, 'cooldown': d.cooldown,
        'duration': d.duration, 'target_kind': d.target_kind, 'allowed_relations': d.allowed_relations,
        'approach': d.automatic_approach, 'clock': 'legacy_owner_turn_end'} for kind, d in ABILITY_DEFINITIONS.items()}
    for kind, spec in SPECS.items():
        catalog[kind].update(**asdict(spec), persistent=kind in ('ghost_fleet', 'fuel_cache'),
            clock='owner_turn_start', stacking='strongest_eligible' if kind == 'nebula_catalyst' else 'one_per_target' if spec.target_kind == 'unit' else 'independent',
            local_sector=True, approach=spec.target_kind == 'unit')
    for kind in ('ghost_fleet', 'fuel_cache'):
        catalog[kind].update(hit_points=DEPLOYABLE_HP, cap_scope='historical_deploying_ship_galaxy_wide')
    catalog['fuel_cache'].update(stored_antimatter=CACHE_FUEL, overhead=CACHE_OVERHEAD, recovery_range=RECOVERY_RANGE)
    catalog['tractor_tether'].update(pull_distance=TRACTOR_PULL, stop_distance=TRACTOR_STANDOFF,
        break_distance=TRACTOR_BREAK, ongoing_antimatter=TRACTOR_COST, speed_multiplier=TRACTOR_SPEED)
    catalog['guardian_link'].update(redirect_fraction=GUARDIAN_FRACTION, redirect_cap=GUARDIAN_CAP,
        redirected_damage_reduction=1-GUARDIAN_RETAINED, hazards_bypass=True)
    catalog['mine_clearing_sweep'].update(radius=SWEEP_RADIUS, mine_budget=SWEEP_MINES, revealed_enemies_only=True)
    catalog['nebula_catalyst'].update(radius=CATALYST_RADIUS,
        friendly_effects={'hydrogen_fuel_multiplier': CATALYST_HYDROGEN_FUEL, 'nitrogen_cooldown_reduction': CATALYST_NITROGEN_COOLING},
        enemy_effects={'oxygen_splash_multiplier': CATALYST_OXYGEN_SPLASH, 'dust_sensor_multiplier': CATALYST_DUST_SENSORS})
    return catalog

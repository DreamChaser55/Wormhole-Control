"""Authoritative wing endurance and pure servicing guidance for every controller."""
from constants import STRIKECRAFT_ENDURANCE_TURNS
from campaign_graph import is_deployed, iter_units
from domain.players import are_allies
from geometry import distance
from unit_orders.hangar import DOCKING_RANGE


def required(unit):
    wing = getattr(unit, 'strikecraft_wing_component', None)
    turns = getattr(wing, 'turns_outside', 0)
    if type(turns) is not int or turns < STRIKECRAFT_ENDURANCE_TURNS:
        return False
    galaxy = getattr(unit, 'in_galaxy', None)
    return galaxy is not None and is_deployed(unit, galaxy)


def command_blocker(unit, command_type):
    return 'wing_service_required' if command_type != 'rename_unit' and required(unit) else None


def return_blocker(unit, galaxy):
    """Check actual docking/approach feasibility without creating an order."""
    from dismantling import offline
    from antimatter_logistics import estimate_approach
    wing = unit.strikecraft_wing_component
    carrier = wing.mother_carrier if wing else None
    if (carrier is None or not is_deployed(carrier, galaxy)
            or carrier.current_hit_points <= 0 or not are_allies(unit.owner, carrier.owner)):
        return 'carrier_unavailable'
    if unit.in_system != carrier.in_system or unit.in_hex != carrier.in_hex:
        return 'carrier_out_of_sector'
    bay = carrier.strikecraft_bay_component
    if not bay or not bay.can_dock(unit) or offline(carrier) or carrier.is_disabled:
        return 'bay_unavailable'
    if unit.is_disabled or offline(unit):
        return 'wing_disabled'
    if distance(unit.position, carrier.position) <= DOCKING_RANGE:
        return None
    if not unit.engines_component or not unit.engines_component.is_operational:
        return 'engines_unavailable'
    if estimate_approach(unit, galaxy, carrier, approach_range=DOCKING_RANGE) is None:
        return 'path_unavailable'
    return None


def state_view(unit, galaxy):
    from strikecraft_abilities import round_now
    wing = unit.strikecraft_wing_component
    deployed = is_deployed(unit, galaxy)
    blocker = return_blocker(unit, galaxy) if deployed else None
    locked = wing.recovery_ready_round > round_now(galaxy)
    return dict(turns_outside=wing.turns_outside, endurance_limit=STRIKECRAFT_ENDURANCE_TURNS,
                turns_remaining=max(0, STRIKECRAFT_ENDURANCE_TURNS - wing.turns_outside),
                mother_carrier_id=wing.mother_carrier.id if wing.mother_carrier else None,
                return_required=required(unit), return_blocker=blocker,
                carrier_available=wing.mother_carrier is not None and blocker is None,
                launch_locked=locked, ready_round=wing.recovery_ready_round,
                status='returning' if required(unit) else 'deployed' if deployed else 'servicing' if locked else 'ready')


def sidebar_labels(unit, galaxy):
    state = state_view(unit, galaxy)
    labels = [f"Endurance: {state['turns_outside']}/{state['endurance_limit']} turns outside ({state['turns_remaining']} remaining)"]
    if state['return_required']:
        labels.append('Returning to refuel and rearm')
    if state['return_blocker']:
        labels.append('Return unavailable: ' + state['return_blocker'].replace('_', ' '))
    elif state['carrier_available']:
        labels.append('Carrier available for servicing')
    if state['launch_locked']:
        labels.append('Ready next owner turn')
    return labels


def expire(unit):
    unit.remove_for_endurance()


def reconcile_unit(unit, galaxy):
    if not required(unit):
        return
    if return_blocker(unit, galaxy):
        expire(unit)
        return
    from unit_orders.base import OrderType, OrderStatus
    from unit_orders.strikecraft import ReturnForServiceOrder
    commander = unit.commander_component
    root = commander.current_order if commander else None
    if commander is None:
        expire(unit)
        return
    if root is None or root.order_type != OrderType.RETURN_FOR_SERVICE or root.status != OrderStatus.IN_PROGRESS:
        commander.clear_explicit_orders(internal=True)
        commander.suspend_stance_activity('mandatory carrier servicing')
        commander._clear_weapon_target()
        from turn_briefing import unit_event
        unit_event(unit, 'problem', 'Returning to refuel and rearm', private=True)
        commander.add_order(ReturnForServiceOrder(unit, {'target_carrier_id': unit.strikecraft_wing_component.mother_carrier.id}), internal=True)
    else:
        root.update(galaxy)


def process(game, player, *, advance=False):
    """Reconcile player's deployed wings in ID order; optionally tick endurance.

    With advance=True, increment each living wing at most once for game.turn_number
    (the global round), capped at the endurance limit. Owner End Turn calls this
    before movement; later calls use advance=False and do not increment counters.

    Both modes mutate service state when required: replace explicit work with a
    mandatory return, suppress combat, update that return, or expire a wing whose
    carrier/route is unavailable. This is not an observation or load-time query.
    Return None; reconciliation errors propagate to the turn caller.
    """
    wings = sorted((unit for unit, _ in iter_units(game.galaxy)
                    if unit.owner == player and unit.strikecraft_wing_component
                    and is_deployed(unit, game.galaxy)), key=lambda unit: unit.id)
    for unit in wings:
        if getattr(unit, '_destroyed', False):
            continue
        wing = unit.strikecraft_wing_component
        if advance and wing.last_endurance_round != game.turn_number:
            wing.last_endurance_round = game.turn_number
            wing.turns_outside = min(STRIKECRAFT_ENDURANCE_TURNS, wing.turns_outside + 1)
        reconcile_unit(unit, game.galaxy)

"""Carrier-issued wing orders and shared, read-only combat modifiers."""
from constants import HullSize
from domain.players import are_enemies
from geometry import distance
from tactical_balance import (SPECS, STRIKECRAFT_ABILITIES, ATTACK_RUN_SPEED,
    ATTACK_RUN_DAMAGE, EVASIVE_INCOMING, EVASIVE_OUTGOING, RECOVERY_SPEED,
    FLAK_RADIUS, FLAK_DAMAGE, TRACKING_DAMAGE)
from tactical_abilities import deployed, sector_for, get_instance, equipment_ready


def round_now(galaxy):
    value = getattr(getattr(galaxy, 'game', None), 'turn_number', 1)
    return value if type(value) is int else 1


def source_valid(source, kind, galaxy, owner_id=None):
    return bool(source and deployed(source, galaxy)
        and not getattr(source, 'is_hidden_in_gas_giant', False)
        and not source.is_disabled and source.ability_component
        and not source.ability_component.is_destroyed
        and get_instance(source, kind)
        and (owner_id is None or source.owner.id == owner_id)
        and equipment_ready(source, SPECS[kind]))


def wing_order(wing, kind=None):
    if not getattr(wing, 'strikecraft_wing_component', None):
        return None
    commander = getattr(wing, 'commander_component', None)
    root = getattr(commander, 'current_order', None)
    if root and getattr(getattr(root, 'order_type', None), 'name', None) in ('ATTACK_RUN', 'EMERGENCY_RECOVERY') and root.status.name == 'IN_PROGRESS':
        if kind is None or root.order_type.name.lower() == kind:
            return root
    return None


def owned_wing(source, wing, galaxy):
    component = getattr(wing, 'strikecraft_wing_component', None)
    return bool(wing and component and not component.is_destroyed
        and wing.hull_size == HullSize.STRIKECRAFT_WING
        and wing.owner == source.owner and component.mother_carrier is source
        and deployed(wing, galaxy) and sector_for(wing, galaxy) is sector_for(source, galaxy))


def eligible_bombers(source, galaxy, *, include_recovering=False):
    from unit_components.enums import WingType
    sector = sector_for(source, galaxy)
    return sorted((wing for wing in getattr(sector, 'units', ())
        if owned_wing(source, wing, galaxy)
        and wing.strikecraft_wing_component.wing_type == WingType.BOMBER
        and not wing.is_disabled and wing.commander_component
        and wing.engines_component and wing.engines_component.is_operational
        and wing.weapons_component and not wing.weapons_component.is_destroyed
        and wing.weapons_component.turrets and (include_recovering or not wing_order(wing, 'emergency_recovery'))
        and distance(source.position, wing.position) <= SPECS['attack_run'].range), key=lambda wing: wing.id)


def validate_target(source, kind, galaxy, target_id, position, *, check_participants=True):
    from visibility import VisibilityService, is_unit_visible
    if kind == 'flak_barrage':
        return 'invalid_value' if target_id is not None or position is not None else None
    target = galaxy.get_unit_by_id(target_id)
    snapshot = VisibilityService.compute(galaxy, source.owner, record_intel=False)
    if not target or not deployed(target, galaxy) or not is_unit_visible(snapshot, target):
        return 'target_unavailable'
    if position is not None:
        return 'invalid_value'
    if sector_for(source, galaxy) is not sector_for(target, galaxy) or distance(source.position, target.position) > SPECS[kind].range:
        return 'out_of_range'
    if kind in ('attack_run', 'tracking_lock'):
        if not are_enemies(source.owner, target.owner):
            return 'target_unavailable'
        if (target.hull_size == HullSize.STRIKECRAFT_WING) != (kind == 'tracking_lock'):
            return 'target_unavailable'
        if kind == 'attack_run' and check_participants and not eligible_bombers(source, galaxy):
            return 'capability_unavailable'
    else:
        if not owned_wing(source, target, galaxy):
            return 'target_unavailable'
        if kind == 'emergency_recovery' and (target.is_disabled or not target.commander_component
                or not target.engines_component or not target.engines_component.is_operational
                or not source.strikecraft_bay_component.can_dock(target)):
            return 'capability_unavailable'
    return None


def issue_wing_orders(source, kind, galaxy, target_id):
    from unit_orders.strikecraft import AttackRunOrder, EmergencyRecoveryOrder
    inst = get_instance(source, kind)
    wings = eligible_bombers(source, galaxy) if kind == 'attack_run' else [galaxy.get_unit_by_id(target_id)]
    inst.participant_ids = [wing.id for wing in wings]
    for wing in wings:
        params = {'source_carrier_id': source.id, 'source_owner_id': source.owner.id,
                  'ability_type': kind, 'release_round': round_now(galaxy) + 1,
                  'expires_round': inst.expires_round}
        params['target_unit_id' if kind == 'attack_run' else 'target_carrier_id'] = target_id if kind == 'attack_run' else source.id
        commander = wing.commander_component
        commander.clear_explicit_orders()
        commander.add_order((AttackRunOrder if kind == 'attack_run' else EmergencyRecoveryOrder)(wing, params))


def effect_valid(source, kind, galaxy):
    inst = get_instance(source, kind)
    if not inst or not inst.is_active or not source_valid(source, kind, galaxy, inst.source_owner_id):
        return False
    if kind == 'flak_barrage':
        return True
    if kind in ('attack_run', 'emergency_recovery'):
        return any(wing_order(wing, kind) and wing_order(wing, kind).parameters.get('source_carrier_id') == source.id
                   for uid in inst.participant_ids if (wing := galaxy.get_unit_by_id(uid)) is not None)
    target = galaxy.get_unit_by_id(inst.target_unit_id)
    if kind == 'evasive_formation':
        return owned_wing(source, target, galaxy)
    return validate_target(source, kind, galaxy, inst.target_unit_id, None) is None


def reconcile(galaxy):
    from campaign_graph import iter_units
    for unit, _ in list(iter_units(galaxy)):
        root = wing_order(unit)
        if root:
            blocker = root.blocker(galaxy)
            if blocker:
                root.fail(blocker)
        for kind in STRIKECRAFT_ABILITIES:
            inst = get_instance(unit, kind)
            if inst and inst.is_active and not effect_valid(unit, kind, galaxy):
                inst.is_active = False
                inst.duration_remaining = 0


def evasion(wing):
    galaxy = getattr(wing, 'in_galaxy', None)
    component = getattr(wing, 'strikecraft_wing_component', None)
    source = component.mother_carrier if component else None
    if source and galaxy:
        inst = get_instance(source, 'evasive_formation')
        return bool(inst and inst.target_unit_id == wing.id and effect_valid(source, 'evasive_formation', galaxy))
    return False


def incoming_multiplier(wing):
    return EVASIVE_INCOMING if evasion(wing) else 1.0


def speed_multiplier(wing):
    root = wing_order(wing)
    if root and root.blocker(getattr(wing, 'in_galaxy', None)) is None:
        return ATTACK_RUN_SPEED if root.order_type.name == 'ATTACK_RUN' else RECOVERY_SPEED
    return 1.0


def outgoing_multiplier(source, target, turret):
    from unit_components.enums import TurretVariant
    result = EVASIVE_OUTGOING if evasion(source) else 1.0
    root = wing_order(source)
    if root:
        if root.order_type.name == 'EMERGENCY_RECOVERY':
            return 0.0
        if root.phase == 'release' and root.blocker(source.in_galaxy) is None:
            result *= ATTACK_RUN_DAMAGE
    inst = get_instance(source, 'tracking_lock')
    if inst and inst.target_unit_id == target.id and turret.variant == TurretVariant.ANTI_STRIKECRAFT:
        if effect_valid(source, 'tracking_lock', source.in_galaxy):
            result *= TRACKING_DAMAGE
    return result


def process_flak(galaxy, player, round_number):
    from tactical_abilities import sectors, combat_hit
    from unit_components.enums import TurretType
    reconcile(galaxy)
    for sector in sectors(galaxy):
        sources = sorted((u for u in sector.units if are_enemies(u.owner, player)
                          and effect_valid(u, 'flak_barrage', galaxy)), key=lambda u: u.id)
        for wing in list(sector.units):
            comp = getattr(wing, 'strikecraft_wing_component', None)
            if wing.owner != player or not comp or not deployed(wing, galaxy):
                continue
            if (comp.last_flak_round, comp.last_flak_owner_id) == (round_number, player.id):
                continue
            # Mark every wing for this movement phase, including those outside coverage.
            comp.last_flak_round, comp.last_flak_owner_id = round_number, player.id
            source = next((u for u in sources if source_valid(u, 'flak_barrage', galaxy)
                           and distance(u.position, wing.position) <= FLAK_RADIUS), None)
            if source:
                before = wing.current_hit_points
                combat_hit(wing, FLAK_DAMAGE, TurretType.MASS_DRIVER)
                source.gain_experience(max(0, before - wing.current_hit_points))


def catalogue_details():
    return {
        'attack_run': {'speed_multiplier': ATTACK_RUN_SPEED, 'salvo_multiplier': ATTACK_RUN_DAMAGE, 'replaces_wing_orders': True},
        'evasive_formation': {'incoming_multiplier': EVASIVE_INCOMING, 'outgoing_multiplier': EVASIVE_OUTGOING},
        'emergency_recovery': {'speed_multiplier': RECOVERY_SPEED, 'suppresses_weapons': True, 'replaces_wing_orders': True},
        'tracking_lock': {'damage_multiplier': TRACKING_DAMAGE, 'caster_only': True},
        'flak_barrage': {'radius': FLAK_RADIUS, 'damage': FLAK_DAMAGE, 'hostile_wings_only': True, 'stacking': 'strongest_eligible'},
    }

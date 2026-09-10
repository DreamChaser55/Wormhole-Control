"""Public tactical observations and side-effect-free command guidance."""
from dataclasses import asdict
from domain.players import are_allies, are_enemies
from tactical_abilities import SPECS, deployments, availability, validate, sectors
from visibility import VisibilityService, is_unit_visible


def visible_deployables(game, player):
    objects = [d for s in sectors(game.galaxy) for d in getattr(s, 'deployables', ())]
    if not objects:
        return []
    snapshot = VisibilityService.compute(game.galaxy, player, getattr(game, 'turn_number', 1), record_intel=False)
    return [d for d in objects if is_unit_visible(snapshot, d)]


def deployable_view(obj, viewer):
    data = {'id': obj.id, 'kind': obj.kind, 'name': obj.name, 'owner_id': obj.owner.id,
            'owner_relation': 'self' if obj.owner == viewer else 'ally' if are_allies(obj.owner, viewer) else 'enemy',
            'system_name': obj.in_system, 'hex_coord': list(obj.in_hex),
            'position': [obj.position.x, obj.position.y], 'hit_points': obj.current_hit_points,
            'persistent': True}
    if obj.kind == 'fuel_cache':
        data['antimatter'] = obj.fuel
    if are_allies(obj.owner, viewer):
        data['deploying_ship_id'] = obj.deploying_ship_id
    return data


def patch_views(game, player):
    from environmental_effects import effects_for_body
    # Public terrain in a locally visible patch, or a patch deployed by the team.
    if not any(getattr(s, 'catalyst_patches', ()) for s in sectors(game.galaxy)):
        return []
    snapshot = VisibilityService.compute(game.galaxy, player, record_intel=False)
    results = []
    for sector in sectors(game.galaxy):
        for patch in getattr(sector, 'catalyst_patches', ()):
            if not are_allies(patch.owner, player) and patch.id not in getattr(snapshot, 'visible_patch_ids', set()):
                continue
            body = game.galaxy.get_celestial_body_by_id(patch.nebula_id)
            results.append({'id': patch.id, 'owner_id': patch.owner.id, 'nebula_id': patch.nebula_id,
                'system_name': patch.in_system, 'hex_coord': list(patch.in_hex),
                'position': [patch.position.x, patch.position.y], 'radius': patch.radius,
                'expires_on_owner_round': patch.expires_round, 'baseline_effects': effects_for_body(body),
                'friendly_effects': {'hydrogen_fuel_multiplier': 0.25, 'nitrogen_cooldown_reduction': 2},
                'enemy_effects': {'oxygen_splash_multiplier': 1.35, 'dust_sensor_multiplier': 0.5}})
    return results


def enrich_states(unit, states):
    galaxy = getattr(unit, 'in_galaxy', None) or getattr(getattr(unit, 'game', None), 'galaxy', None)
    for state in states:
        kind = state['ability']
        if kind not in SPECS or galaxy is None:
            continue
        from tactical_abilities import get_instance, pending_casts
        inst = get_instance(unit, kind)
        spec = SPECS[kind]
        blocker = availability(unit, kind, galaxy)
        state.update(ready=blocker is None, unavailable_reason=blocker, target_kind=spec.target_kind,
            cooldown_remaining=inst.cooldown_remaining, duration_remaining=inst.duration_remaining,
            active=inst.is_active, activation_antimatter=spec.cost,
            ongoing_antimatter=5 if kind == 'tractor_tether' else 0,
            deployment_count=len(deployments(galaxy, unit.id, kind)) if spec.cap else 0,
            reserved_casts=sum(k == kind for k, _ in pending_casts(unit)),
            deployment_limit=spec.cap, persistent=kind in ('ghost_fleet', 'fuel_cache'))
        if inst.target_unit_id is not None:
            target = galaxy.get_unit_by_id(inst.target_unit_id)
            snapshot = VisibilityService.compute(galaxy, unit.owner, record_intel=False)
            state['target_id'] = target.id if target and is_unit_visible(snapshot, target) else None
        if kind == 'guardian_link':
            state.update(redirect_fraction=inst.redirect_fraction, redirect_cap=inst.redirect_cap, redirected_damage_reduction=1-inst.redirect_retained)
    return states


def guidance(game, player, unit, legal, options, visible_units, exact_bodies):
    from tactical_abilities import get_instance
    from unit_orders.recover_fuel import recovery_blocker
    deployables = visible_deployables(game, player)
    targets = options.get('use_ability', {}).get('targets_by_ability', {})
    for kind, spec in SPECS.items():
        if not get_instance(unit, kind):
            continue
        if spec.target_kind == 'unit':
            targets[kind] = [t.id for t in visible_units if validate(unit, kind, game.galaxy, t.id, approach=True) is None]
    if 'use_ability' in options:
        options['use_ability']['targets_by_ability'] = targets
        options['use_ability']['nebula_ids'] = [b.id for b in exact_bodies
            if b.__class__.__name__ == 'Nebula' and b.in_system == unit.in_system and b.in_hex == unit.in_hex]
    if 'use_ability' in options:
        values = options['use_ability']['values']
        for kind in list(values):
            spec = SPECS.get(kind)
            if spec and spec.target_kind == 'unit' and not targets.get(kind):
                values.remove(kind)
            elif kind == 'nebula_catalyst' and not options['use_ability']['nebula_ids']:
                values.remove(kind)
        if not values:
            legal.discard('use_ability')
    recoverable = [d.id for d in deployables if recovery_blocker(unit, d, game.galaxy) is None]
    options['recover_fuel_cache'] = {'target_ids': recoverable}
    if recoverable:
        legal.add('recover_fuel_cache')
    cancellable = [k for k in ('tractor_tether', 'guardian_link') if get_instance(unit, k) and get_instance(unit, k).is_active]
    options['cancel_ability'] = {'values': cancellable}
    if cancellable:
        legal.add('cancel_ability')
    weapons = getattr(unit, 'weapons_component', None)
    if weapons and not weapons.is_destroyed:
        enemies = [d.id for d in deployables if are_enemies(player, d.owner) and weapons.eligible_turrets_for(d)]
        if enemies:
            options.setdefault('attack', {}).setdefault('target_ids', []).extend(enemies)
            legal.add('attack')


def environmental_view(unit):
    from environmental_effects import modifiers_for_unit
    return asdict(modifiers_for_unit(unit))


def public_links(game, viewer):
    """Expose an effect only when both endpoints are visible, never a hidden source ID."""
    from tactical_abilities import get_instance, link_valid
    snapshot = None
    result = []
    for sector in sectors(game.galaxy):
        for unit in getattr(sector, 'units', ()):
            for kind in ('tractor_tether', 'guardian_link'):
                inst = get_instance(unit, kind)
                if not inst or not inst.is_active or not link_valid(unit, inst, game.galaxy):
                    continue
                if snapshot is None:
                    snapshot = VisibilityService.compute(game.galaxy, viewer, record_intel=False)
                target = game.galaxy.get_unit_by_id(inst.target_unit_id)
                if is_unit_visible(snapshot, unit) and is_unit_visible(snapshot, target):
                    result.append({'ability': kind, 'source_id': unit.id, 'target_id': target.id,
                                   'duration_remaining': inst.duration_remaining})
    return result

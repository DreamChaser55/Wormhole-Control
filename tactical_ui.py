"""Human tactical controls backed by the same gateway as automated players."""
from tactical_abilities import SPECS, deployments, get_instance


def label(text):
    return {'type': 'label', 'text': text, 'height': 23, 'object_id': '#sidebar_info_label'}


def button(text, action, data):
    return {'type': 'button', 'text': text, 'height': 28, 'object_id': '#sidebar_expand_button',
            'action_id': action, 'target_data': data}


def issue(game, command):
    from game_ai.commands import CommandGateway
    from game_ai.contracts import Command, CommandBatch
    result = CommandGateway(game).apply_batch(game.players[game.current_player_index], CommandBatch((Command.from_dict(command),)))
    if not result.accepted and getattr(game, 'gui', None):
        game.gui.show_warning_dialog('<br>'.join(e.message for e in result.errors), title='Tactical order unavailable')
    return result.accepted


def handle_action(game, action):
    from tactical_abilities import find_deployable
    kind, data = action['action'], action.get('target_data')
    if kind == 'select_deployable':
        obj = find_deployable(game.galaxy, data)
        if obj and game.is_unit_visible(obj):
            game.selected_objects = [obj]
    elif kind == 'choose_catalyst_nebula':
        game.pending_catalyst_body_id = data
    elif kind == 'cancel_tactical_ability':
        issue(game, {'type': 'cancel_ability', 'unit_ids': [data['unit_id']], 'ability': data['ability']})
    elif kind in ('recover_tactical_cache', 'attack_deployable'):
        issue(game, {'type': 'recover_fuel_cache' if kind == 'recover_tactical_cache' else 'attack',
                     'unit_ids': [data['unit_id']], 'target_id': data['target_id'], 'queue': action.get('shift_pressed', False)})
    game.sidebar_needs_update = True


def ability_panel(unit, game):
    from tactical_abilities import availability, sector_for
    data = []
    if unit.owner != game.players[game.current_player_index]:
        return data
    galaxy = game.galaxy
    for kind, spec in SPECS.items():
        inst = get_instance(unit, kind)
        if not inst:
            continue
        data.append(label(f'{spec.name}: range {spec.range:g}; cooldown {spec.cooldown}; ' +
                          (f'duration {spec.duration} owner turns' if spec.duration else 'one-shot')))
        blocker = availability(unit, kind, galaxy)
        if blocker:
            data.append(label('Unavailable: ' + blocker.replace('_', ' ')))
        if spec.cap:
            count = len(deployments(galaxy, unit.id, kind))
            noun = 'emitters' if kind == 'ghost_fleet' else 'fuel caches' if kind == 'fuel_cache' else 'patches'
            data.append(label(f'{count}/{spec.cap} {noun}' + (' - Persistent' if kind != 'nebula_catalyst' else '')))
            if count >= spec.cap:
                reason = {'ghost_fleet': 'An existing emitter must be destroyed.',
                          'fuel_cache': 'Empty or destroy an existing cache.',
                          'nebula_catalyst': 'Wait for the existing patch to expire.'}[kind]
                data.append(label('At cap: ' + reason))
        if kind in ('tractor_tether', 'guardian_link') and inst.is_active:
            data.append(button('Cancel ' + spec.name, 'cancel_tactical_ability', {'unit_id': unit.id, 'ability': kind}))
        if kind == 'nebula_catalyst' and (getattr(game, 'pending_ability', None) or (None,))[0] == kind:
            from domain.celestials import Nebula
            selected = getattr(game, 'pending_catalyst_body_id', None)
            data.append(label('Choose a nebula, then right-click its patch center.'))
            data.append(label('Friendly: hydrogen fuel 25%; nitrogen cooldown -2.'))
            data.append(label('Enemy: oxygen splash 1.35x; dust sensors 50%.'))
            data.append(label('Ordinary nebula effects remain active.'))
            for body in sector_for(unit, galaxy).celestial_bodies:
                if isinstance(body, Nebula):
                    data.append(button(('Selected: ' if selected == body.id else 'Catalyze: ') + body.name, 'choose_catalyst_nebula', body.id))
    from game_ai.tactical import visible_deployables
    from unit_orders.recover_fuel import recovery_blocker
    for cache in visible_deployables(game, unit.owner):
        if recovery_blocker(unit, cache, galaxy) is None:
            data.append(button(f'Recover cache {cache.id}: {cache.fuel:g} AM', 'recover_tactical_cache', {'unit_id': unit.id, 'target_id': cache.id}))
    return data


def deployable_panel(game, obj):
    data = [label(obj.name), label(f'HP: {obj.current_hit_points}/{obj.max_hit_points}'), label('Persistent')]
    if obj.kind == 'fuel_cache':
        data.append(label(f'Fuel: {obj.fuel:g} AM'))
    from game_ai.tactical import deployable_view
    view = deployable_view(obj, game.players[game.current_player_index])
    if 'deploying_ship_id' in view:
        data.append(label(f'Deploying ship: {view["deploying_ship_id"]}'))
    data.append(label('Select a ship and right-click this object to attack/recover.'))
    return data


def patch_panel(game, body):
    from game_ai.tactical import patch_views
    data = []
    for patch in patch_views(game, game.players[game.current_player_index]):
        if patch['nebula_id'] != body.id:
            continue
        owner = next(p for p in game.players if p.id == patch['owner_id'])
        data.append(label(f'Catalyst: {owner.name}; expires on owner round {patch["expires_on_owner_round"]}'))
        data.append(label('Friendly: hydrogen fuel 25%; nitrogen cooldown -2.'))
        data.append(label('Enemy: oxygen splash 1.35x; dust sensors 50%.'))
    return data


def draw(renderer, sector):
    import math
    import pygame
    from geometry import Position, distance
    from sector_utils import sector_radius_to_pixels, pixels_to_sector_coords
    from display_config import display_config_for
    from game_ai.tactical import patch_views
    from tactical_abilities import sweep_fields, SWEEP_MINES, SWEEP_RADIUS
    from tactical_balance import CATALYST_RADIUS
    game = renderer.game
    if not getattr(game, 'players', None):
        return
    config = display_config_for(game)

    def pixel(p):
        v = renderer._coords_to_pixels(p)
        return (int(v.x), int(v.y))

    def radius(value):
        return max(1, int(sector_radius_to_pixels(value, game.sector_zoom, display_config=config)))

    def patch_outline(center, patch_radius, body, color):
        if body is None:
            return
        # Draw the two clipped boundary arcs, using bounded memory at every zoom.
        for origin, size, other, other_size in ((center, patch_radius, body.position, body.radius), (body.position, body.radius, center, patch_radius)):
            previous = None
            for step in range(193):
                angle = step * math.tau / 192
                point = Position(origin.x + math.cos(angle)*size, origin.y + math.sin(angle)*size)
                inside = distance(point, other) <= other_size + 1e-6
                if inside and previous is not None:
                    pygame.draw.line(renderer.screen, color, pixel(previous), pixel(point), 2)
                previous = point if inside else None

    for patch in patch_views(game, game.players[game.current_player_index]):
        if patch['system_name'] == game.current_system_name and tuple(patch['hex_coord']) == game.current_sector_coord:
            owner = next(p for p in game.players if p.id == patch['owner_id'])
            patch_outline(Position(*patch['position']), patch['radius'], game.galaxy.get_celestial_body_by_id(patch['nebula_id']), owner.color)
    for source in sector.units:
        if not game.is_unit_visible(source):
            continue
        for kind in ('tractor_tether', 'guardian_link'):
            inst = get_instance(source, kind)
            target = game.galaxy.get_unit_by_id(inst.target_unit_id) if inst and inst.is_active else None
            if target and game.is_unit_visible(target):
                pygame.draw.line(renderer.screen, source.owner.color, pixel(source.position), pixel(target.position), 2)
    pending = getattr(game, 'pending_ability', None)
    actors = [u for u in game.selected_objects if getattr(u, 'ability_component', None)]
    if not pending or not actors or pending[0] not in SPECS:
        return
    unit, kind = actors[0], pending[0]
    point = pixels_to_sector_coords(Position(*pygame.mouse.get_pos()), game.sector_zoom, game.sector_pan_offset, display_config=config)
    pygame.draw.circle(renderer.screen, unit.owner.color, pixel(unit.position), radius(SPECS[kind].range), 1)
    if kind == 'mine_clearing_sweep':
        dx, dy = point.x-unit.position.x, point.y-unit.position.y
        length = math.hypot(dx, dy)
        if length > SPECS[kind].range:
            point = Position(unit.position.x+dx/length*SPECS[kind].range, unit.position.y+dy/length*SPECS[kind].range)
        if length:
            nx, ny = -dy/length*SWEEP_RADIUS, dx/length*SWEEP_RADIUS
            for sign in (-1, 1):
                pygame.draw.line(renderer.screen, unit.owner.color,
                    pixel(Position(unit.position.x+nx*sign, unit.position.y+ny*sign)), pixel(Position(point.x+nx*sign, point.y+ny*sign)), 1)
        for end in (unit.position, point):
            pygame.draw.circle(renderer.screen, unit.owner.color, pixel(end), radius(SWEEP_RADIUS), 1)
        budget = SWEEP_MINES
        for field in sweep_fields(unit, point, game.galaxy):
            removed = min(budget, field.mines_remaining)
            budget -= removed
            font = pygame.font.Font(None, 20)
            renderer.screen.blit(font.render(f'{field.mines_remaining-removed} mines remain', True, unit.owner.color), pixel(field.position))
    elif kind == 'nebula_catalyst':
        patch_outline(point, CATALYST_RADIUS, game.galaxy.get_celestial_body_by_id(getattr(game, 'pending_catalyst_body_id', None)), unit.owner.color)


def draw_deployable(renderer, obj, pixel_position):
    import pygame
    point = (int(pixel_position.x), int(pixel_position.y))
    color = obj.owner.color
    pygame.draw.rect(renderer.screen, color, (point[0]-6, point[1]-6, 12, 12), 2)
    if obj.kind == 'ghost_fleet':
        pygame.draw.circle(renderer.screen, color, point, 10, 1)
    return 13.89

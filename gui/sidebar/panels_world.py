"""Sidebar UI panel builders for StarSystem, Hex, CelestialBody, and Minefield entities."""
import typing
from entities import (
    CelestialBody, Star, Planet, Moon,
    ColonizableAsteroid, MetalAsteroid, Wormhole, DebrisField,
    AsteroidField, IceField, Nebula, Storm, Comet, Minefield
)
from galaxy import StarSystem, Hex


def object_button_style(owner) -> str:
    """Returns the CSS element ID for player-themed or neutral buttons based on owner."""
    if owner and getattr(owner, 'name', None):
        return f'#player_{owner.name.lower().replace(" ", "_")}_button'
    return '#sidebar_neutral_button'


def build_system_panel(game, sys_obj: StarSystem) -> list[dict]:
    """Constructs sidebar data payload for a selected StarSystem."""
    data = [
        {'type': 'label', 'text': f"System: {sys_obj.name}", 'object_id': '#sidebar_title_label', 'height': 30},
        {'type': 'label', 'text': f"Position: {sys_obj.position}", 'object_id': '#sidebar_info_label', 'height': 25}
    ]
    num_units = sum(len(hex_data.units) for hex_data in sys_obj.hexes.values())
    num_bodies = sum(len(hex_data.celestial_bodies) for hex_data in sys_obj.hexes.values())
    data.append({'type': 'label', 'text': f"Objects: {num_bodies} Bodies, {num_units} Units", 'object_id': '#sidebar_info_label', 'height': 25})
    data.append({'type': 'label', 'text': f"Hex Radius: {sys_obj.radius}", 'object_id': '#sidebar_info_label', 'height': 25})

    connected_systems = sorted(set(
        wh.exit_system_name
        for wh in game.galaxy.wormholes.values()
        if wh.in_system == sys_obj.name
    ))
    wormhole_text = ", ".join(connected_systems) if connected_systems else "None"
    data.append({'type': 'label', 'text': f"Wormholes: {wormhole_text}", 'object_id': '#sidebar_info_label', 'height': 25})
    return data


def build_hex_panel(game, hex_obj: Hex) -> list[dict]:
    """Constructs sidebar data payload for a selected Hex sector."""
    data = []
    coords = hex_obj.coordinates()
    system_name = game.galaxy.systems[hex_obj.in_system].name
    data.append({'type': 'label', 'text': f"Hex ({coords[0]}, {coords[1]}) in {system_name}", 'object_id': '#sidebar_title_label', 'height': 30})

    current_player = game.players[game.current_player_index] if game.players else None
    if current_player and hasattr(current_player, 'get_sector_last_intel_turn'):
        last_turn = current_player.get_sector_last_intel_turn(system_name, coords)
        if last_turn is None:
            intel_str = "Never"
        else:
            current_game_turn = getattr(game, 'turn_number', 1)
            diff = current_game_turn - last_turn
            if diff <= 0:
                intel_str = "Current turn"
            elif diff == 1:
                intel_str = "1 turn ago"
            else:
                intel_str = f"{diff} turns ago"
        data.append({'type': 'label', 'text': f"Last Intel: {intel_str}", 'object_id': '#sidebar_info_label', 'height': 25})

    visible_units = [u for u in hex_obj.units if game.is_unit_visible(u)]
    has_presence = game.hex_has_presence(system_name, coords)

    if not hex_obj.celestial_bodies and not visible_units and not has_presence:
        data.append({'type': 'label', 'text': "Contains: Nothing", 'object_id': '#sidebar_info_label', 'height': 25})
    else:
        if hex_obj.celestial_bodies:
            data.append({'type': 'label', 'text': "Bodies:", 'object_id': '#sidebar_info_label', 'height': 20})
            for b in hex_obj.celestial_bodies:
                owner = getattr(b, 'owner', None)
                data.append({
                    'type': 'button',
                    'text': b.name,
                    'object_id': object_button_style(owner),
                    'class_id': '#sidebar_expand_button',
                    'action_id': 'select_celestial_body',
                    'target_data': b.id,
                    'height': 20,
                    'indent_level': 1
                })
        if visible_units:
            data.append({'type': 'label', 'text': "Units:", 'object_id': '#sidebar_info_label', 'height': 20})
            for u in visible_units:
                owner = getattr(u, 'owner', None)
                data.append({
                    'type': 'button',
                    'text': u.name,
                    'object_id': object_button_style(owner),
                    'class_id': '#sidebar_expand_button',
                    'action_id': 'select_individual_unit',
                    'target_data': u.id,
                    'height': 20,
                    'indent_level': 1
                })

        # Minefields (only shown on owner's turn)
        current_player = game.players[game.current_player_index] if game.players else None
        friendly_minefields = [
            mf for mf in getattr(hex_obj, 'minefields', [])
            if mf.owner == current_player
        ]
        if friendly_minefields:
            data.append({'type': 'label', 'text': "Minefields:", 'object_id': '#sidebar_info_label', 'height': 20})
            for mf in friendly_minefields:
                owner = getattr(mf, 'owner', None)
                data.append({
                    'type': 'button',
                    'text': f"{mf.name} ({mf.mines_remaining} mines)",
                    'object_id': object_button_style(owner),
                    'class_id': '#sidebar_expand_button',
                    'action_id': 'select_minefield',
                    'target_data': mf.id,
                    'height': 20,
                    'indent_level': 1
                })
        if has_presence and not any(u.owner != current_player for u in visible_units):
            data.append({'type': 'label', 'text': "⚠ Enemy presence detected", 'object_id': '#sidebar_hit_points_critical_damage_label', 'height': 20})

    return data


def build_celestial_body_panel(game, body: CelestialBody) -> list[dict]:
    """Constructs sidebar data payload for a selected CelestialBody."""
    data = [
        {'type': 'label', 'text': f"{body.__class__.__name__}: {body.name}", 'object_id': '#sidebar_title_label', 'height': 30},
        {'type': 'label', 'text': f"System: {body.in_system or 'None'}", 'object_id': '#sidebar_info_label', 'height': 25}
    ]

    hex_pos_str = "N/A"
    if body.in_system and game.galaxy and body.in_system in game.galaxy.systems:
        hex_pos_str = str(body.in_hex)
    data.append({'type': 'label', 'text': f"Hex: {hex_pos_str}", 'object_id': '#sidebar_info_label', 'height': 25})
    data.append({'type': 'label', 'text': f"Sector Pos: ({body.position.x:.2f}, {body.position.y:.2f})", 'object_id': '#sidebar_info_label', 'height': 25})

    # Type-specific info
    if isinstance(body, Star):
        data.append({'type': 'label', 'text': f"Type: {body.star_type.name.capitalize()}", 'object_id': '#sidebar_info_label', 'height': 20})
        mult = getattr(body, 'harvest_multiplier', 1.0)
        data.append({'type': 'label', 'text': f"AM Harvest Multiplier: {mult:.1f}x", 'object_id': '#sidebar_info_label', 'height': 20})

    elif isinstance(body, Planet):
        data.append({'type': 'label', 'text': f"Type: {body.planet_type.name.capitalize()}", 'object_id': '#sidebar_info_label', 'height': 20})
        owner_name = body.owner.name if body.owner else "Uninhabited"
        data.append({'type': 'label', 'text': f"Owner: {owner_name}", 'object_id': '#sidebar_info_label', 'height': 25})
        data.append({'type': 'label', 'text': f"Population: {body.population:.2f} / {body.max_population:.2f}", 'object_id': '#sidebar_info_label', 'height': 25})

    elif isinstance(body, Moon):
        owner_name = body.owner.name if body.owner else "Uninhabited"
        data.append({'type': 'label', 'text': f"Owner: {owner_name}", 'object_id': '#sidebar_info_label', 'height': 25})
        data.append({'type': 'label', 'text': f"Population: {body.population:.2f} / {body.max_population:.2f}", 'object_id': '#sidebar_info_label', 'height': 25})

    elif isinstance(body, ColonizableAsteroid):
        owner_name = body.owner.name if body.owner else "Uninhabited"
        data.append({'type': 'label', 'text': f"Owner: {owner_name}", 'object_id': '#sidebar_info_label', 'height': 25})
        data.append({'type': 'label', 'text': f"Population: {body.population:.2f} / {body.max_population:.2f}", 'object_id': '#sidebar_info_label', 'height': 25})

    elif isinstance(body, MetalAsteroid):
        data.append({'type': 'label', 'text': f"Metal Yield: {body.metal_yield}", 'object_id': '#sidebar_info_label', 'height': 25})

    elif isinstance(body, Wormhole):
        data.append({'type': 'label', 'text': f"Exit System: {body.exit_system_name or 'None'}", 'object_id': '#sidebar_info_label', 'height': 25})
        data.append({'type': 'label', 'text': f"Exit Wormhole: {body.exit_wormhole_id or 'None'}", 'object_id': '#sidebar_info_label', 'height': 25})
        data.append({'type': 'label', 'text': f"Stability: {body.stability}", 'object_id': '#sidebar_info_label', 'height': 25})
        data.append({'type': 'label', 'text': f"Diameter: {body.diameter.name.capitalize()}", 'object_id': '#sidebar_info_label', 'height': 25})

    elif isinstance(body, DebrisField):
        data.append({'type': 'label', 'text': "A field of space debris.", 'object_id': '#sidebar_info_label', 'height': 20})
        data.append({'type': 'label', 'text': "Hazardous to navigation.", 'object_id': '#sidebar_info_label', 'height': 20})

    elif isinstance(body, AsteroidField):
        data.append({'type': 'label', 'text': f"Asteroid Count: {body.asteroid_count}", 'object_id': '#sidebar_info_label', 'height': 20})
        data.append({'type': 'label', 'text': "Can interfere with long-range sensors.", 'object_id': '#sidebar_info_label', 'height': 20})

    elif isinstance(body, IceField):
        data.append({'type': 'label', 'text': "A field of frozen particles.", 'object_id': '#sidebar_info_label', 'height': 20})
        data.append({'type': 'label', 'text': "May contain valuable resources.", 'object_id': '#sidebar_info_label', 'height': 20})

    elif isinstance(body, Nebula):
        data.append({'type': 'label', 'text': f"Type: {body.nebula_type.name.capitalize()}", 'object_id': '#sidebar_info_label', 'height': 20})
        data.append({'type': 'label', 'text': "Affects sensors and shields.", 'object_id': '#sidebar_info_label', 'height': 20})

    elif isinstance(body, Storm):
        data.append({'type': 'label', 'text': f"Type: {body.storm_type.name.capitalize()}", 'object_id': '#sidebar_info_label', 'height': 20})
        data.append({'type': 'label', 'text': "Damages ships over time.", 'object_id': '#sidebar_info_label', 'height': 20})

    elif isinstance(body, Comet):
        data.append({'type': 'label', 'text': "A celestial body of ice and rock.", 'object_id': '#sidebar_info_label', 'height': 20})
        data.append({'type': 'label', 'text': f"Crystal Yield: {body.crystal_yield}", 'object_id': '#sidebar_info_label', 'height': 25})

    return data


def build_minefield_panel(game, mf: Minefield) -> list[dict]:
    """Constructs sidebar data payload for a selected Minefield."""
    owner_name = mf.owner.name if mf.owner else "Unknown"
    owner_style = f'#player_{owner_name.lower().replace(" ", "_")}_label'
    data = [
        {'type': 'label', 'text': f"Minefield: {mf.name}", 'object_id': '#sidebar_title_label', 'height': 30},
        {'type': 'label', 'text': f"Owner: {owner_name}", 'object_id': owner_style, 'height': 25},
        {'type': 'label', 'text': f"Type: {mf.minefield_type.display_name}", 'object_id': '#sidebar_info_label', 'height': 25},
        {'type': 'label', 'text': f"Mines Remaining: {mf.mines_remaining}", 'object_id': '#sidebar_info_label', 'height': 25},
        {'type': 'label', 'text': f"Mine Damage: {mf.mine_damage:.0f}", 'object_id': '#sidebar_info_label', 'height': 25},
        {'type': 'label', 'text': f"Detonation Radius: {mf.detonation_radius:.0f}", 'object_id': '#sidebar_info_label', 'height': 25}
    ]

    current_player = game.players[game.current_player_index] if (getattr(game, 'players', None) and 0 <= getattr(game, 'current_player_index', 0) < len(game.players)) else None
    if mf.owner and mf.owner == current_player:
        data.append({
            'type': 'button',
            'text': "Remove minefield",
            'object_id': '#sidebar_button',
            'action_id': 'remove_minefield',
            'target_data': mf.id,
            'height': 25
        })

    return data

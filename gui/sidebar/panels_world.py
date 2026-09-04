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
    visible_minefields = [
        mf for mf in getattr(hex_obj, 'minefields', [])
        if game.is_minefield_visible(mf)
    ]

    if not hex_obj.celestial_bodies and not visible_units and not has_presence and not visible_minefields:
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

        # Minefields (friendly or revealed enemy minefields)
        if visible_minefields:
            data.append({'type': 'label', 'text': "Minefields:", 'object_id': '#sidebar_info_label', 'height': 20})
            for mf in visible_minefields:
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
    from constants import StarType, PlanetType, NebulaType, StormType

    if isinstance(body, Star):
        data.append({'type': 'label', 'text': f"Type: {body.star_type.name.capitalize()}", 'object_id': '#sidebar_info_label', 'height': 20})
        mult = getattr(body, 'harvest_multiplier', 1.0)
        data.append({'type': 'label', 'text': f"AM Harvest Multiplier: {mult:.1f}x", 'object_id': '#sidebar_info_label', 'height': 20})
        if body.star_type == StarType.BLACK_HOLE:
            data.append({'type': 'label', 'text': "⚠ Event Horizon: 15 damage/turn within 750 radius.", 'object_id': '#sidebar_status_charging_label', 'height': 20})
            data.append({'type': 'label', 'text': "Hyperspace Inhibition: 3600 radius.", 'object_id': '#sidebar_info_label', 'height': 20})
        elif body.star_type == StarType.PULSAR:
            data.append({'type': 'label', 'text': "⚠ Pulsar Radiation: Drains 5% antimatter/turn.", 'object_id': '#sidebar_status_charging_label', 'height': 20})
        elif body.star_type in (StarType.BLUE_GIANT, StarType.RED_GIANT):
            data.append({'type': 'label', 'text': "Giant Star: Collision 600 radius; Inhibition 3000.", 'object_id': '#sidebar_info_label', 'height': 20})

    elif isinstance(body, (Planet, Moon, ColonizableAsteroid)):
        if isinstance(body, Planet):
            data.append({'type': 'label', 'text': f"Type: {body.planet_type.name.capitalize()}", 'object_id': '#sidebar_info_label', 'height': 20})
            if body.planet_type == PlanetType.GAS_GIANT:
                data.append({'type': 'label', 'text': "Massive Gas Giant (Non-colonizable)", 'object_id': '#sidebar_status_charging_label', 'height': 20})
                data.append({'type': 'label', 'text': f"Antimatter Reservoir: {body.harvest_multiplier:.1f}x harvest rate", 'object_id': '#sidebar_info_label', 'height': 20})
                data.append({'type': 'label', 'text': "Collision 450 radius; Inhibition 2800.", 'object_id': '#sidebar_info_label', 'height': 20})
                return data

            p_metal = getattr(body, 'passive_metal', 0.0)
            p_crystal = getattr(body, 'passive_crystal', 0.0)
            if p_metal > 0:
                data.append({'type': 'label', 'text': f"• Passive Mineral Deposit: +{p_metal:.1f} Metal/turn", 'object_id': '#sidebar_info_label', 'height': 20})
            if p_crystal > 0:
                data.append({'type': 'label', 'text': f"• Passive Crystal Deposit: +{p_crystal:.1f} Crystal/turn", 'object_id': '#sidebar_info_label', 'height': 20})

        owner_name = body.owner.name if body.owner else "Uninhabited"
        owner_style_id = f'#player_{owner_name.lower().replace(" ", "_")}_label' if body.owner else '#sidebar_info_label'
        data.append({'type': 'label', 'text': f"Owner: {owner_name}", 'object_id': owner_style_id, 'height': 25})

        current_player = game.players[game.current_player_index] if game.players else None
        if current_player and hasattr(body, 'has_infiltrating_agent_from') and body.has_infiltrating_agent_from(current_player):
            agent = next((ag for ag in getattr(body, 'infiltrating_agents', []) if ag.owner == current_player), None)
            sab_txt = f" [SABOTAGE: {agent.active_sabotage.name}]" if (agent and agent.active_sabotage) else ""
            data.append({
                'type': 'label',
                'text': f"👁 COVERT AGENT EMBEDDED{sab_txt}",
                'object_id': '#sidebar_status_active_label',
                'height': 24
            })
        data.append({'type': 'label', 'text': f"Population: {body.population:.2f} / {body.max_population:.2f}", 'object_id': '#sidebar_info_label', 'height': 25})
        if body.owner and body.population > 0:
            cap = body.get_supported_habitat_capacity() if hasattr(body, 'get_supported_habitat_capacity') else 0
            od_cap = body.get_supported_orbital_defense_capacity() if hasattr(body, 'get_supported_orbital_defense_capacity') else 0
            active_habs = 0
            active_ods = 0
            if game.galaxy and body.in_system in game.galaxy.systems:
                sys_obj = game.galaxy.systems[body.in_system]
                hex_obj = sys_obj.hexes.get(body.in_hex)
                if hex_obj:
                    for u in hex_obj.units:
                        if u.owner == body.owner:
                            comp = getattr(u, 'civilian_habitat_component', None)
                            if comp and not comp.is_destroyed and getattr(comp, 'is_active', lambda g: False)(game.galaxy):
                                active_habs += 1
                            od_comp = getattr(u, 'orbital_defense_component', None)
                            if od_comp and not od_comp.is_destroyed and getattr(od_comp, 'is_active', lambda g: False)(game.galaxy):
                                active_ods += 1
            data.append({'type': 'label', 'text': f"Habitats Supported: {active_habs} / {cap}", 'object_id': '#sidebar_info_label', 'height': 25})
            data.append({'type': 'label', 'text': f"Orbital Defenses Supported: {active_ods} / {od_cap}", 'object_id': '#sidebar_info_label', 'height': 25})

        current_player = game.players[game.current_player_index] if game.players else None
        if current_player:
            if hasattr(body, 'has_infiltrating_agent_from') and body.has_infiltrating_agent_from(current_player):
                agent = next((ag for ag in getattr(body, 'infiltrating_agents', []) if ag.owner == current_player), None)
                sab_info = f" (Sabotage: {agent.active_sabotage.name})" if (agent and agent.active_sabotage) else ""
                data.append({'type': 'label', 'text': f"• Infiltrated: Agent Active{sab_info}", 'object_id': '#sidebar_status_active_label', 'height': 20})
            if getattr(body, 'owner', None) == current_player and hasattr(body, 'infiltrating_agents'):
                for ag in body.infiltrating_agents:
                    if ag.is_discovered and ag.owner != current_player:
                        data.append({'type': 'label', 'text': f"⚠ Discovered Enemy Agent ({ag.owner.name})", 'object_id': '#sidebar_status_charging_label', 'height': 20})

    elif isinstance(body, MetalAsteroid):
        data.append({'type': 'label', 'text': f"Metal Yield: {body.metal_yield}", 'object_id': '#sidebar_info_label', 'height': 25})

    elif isinstance(body, Wormhole):
        data.append({'type': 'label', 'text': f"Exit System: {body.exit_system_name or 'None'}", 'object_id': '#sidebar_info_label', 'height': 25})
        data.append({'type': 'label', 'text': f"Exit Wormhole: {body.exit_wormhole_id or 'None'}", 'object_id': '#sidebar_info_label', 'height': 25})
        data.append({'type': 'label', 'text': f"Stability: {body.stability}", 'object_id': '#sidebar_info_label', 'height': 25})
        data.append({'type': 'label', 'text': f"Diameter: {body.diameter.name.capitalize()}", 'object_id': '#sidebar_info_label', 'height': 25})

    elif isinstance(body, DebrisField):
        density_str = getattr(body, 'density', None)
        density_label = f"Density: {density_str.name.capitalize()} (Max Hull: {body.max_hull_size.name.capitalize()})" if density_str else "Debris Field"
        data.append({'type': 'label', 'text': density_label, 'object_id': '#sidebar_info_label', 'height': 20})
        drag_pct = int(round((1.0 - getattr(body, 'speed_multiplier', 0.75)) * 100))
        cover_pct = int(round(getattr(body, 'defense_bonus', 0.10) * 100))
        data.append({'type': 'label', 'text': f"Sublight speed drag -{drag_pct}%. Cover: +{cover_pct}% Kinetic/Missile.", 'object_id': '#sidebar_info_label', 'height': 20})
        dmg = int(getattr(body, 'hazard_damage', 2.0))
        data.append({'type': 'label', 'text': f"⚠ Navigation Hazard: {dmg} dmg when moving speed > 50.", 'object_id': '#sidebar_status_charging_label', 'height': 20})

    elif isinstance(body, AsteroidField):
        density_str = getattr(body, 'density', None)
        density_label = f"Density: {density_str.name.capitalize()} (Max Hull: {body.max_hull_size.name.capitalize()})" if density_str else "Asteroid Field"
        data.append({'type': 'label', 'text': density_label, 'object_id': '#sidebar_info_label', 'height': 20})
        data.append({'type': 'label', 'text': f"Asteroid Count: {body.asteroid_count}", 'object_id': '#sidebar_info_label', 'height': 20})
        data.append({'type': 'label', 'text': "Tactical Radar Stealth: Conceals from long-range sensors.", 'object_id': '#sidebar_info_label', 'height': 20})
        drag_pct = int(round((1.0 - getattr(body, 'speed_multiplier', 0.75)) * 100))
        data.append({'type': 'label', 'text': f"Sublight navigation drag -{drag_pct}%.", 'object_id': '#sidebar_info_label', 'height': 20})

    elif isinstance(body, IceField):
        density_str = getattr(body, 'density', None)
        density_label = f"Density: {density_str.name.capitalize()} (Max Hull: {body.max_hull_size.name.capitalize()})" if density_str else "Ice Field"
        data.append({'type': 'label', 'text': density_label, 'object_id': '#sidebar_info_label', 'height': 20})
        beam_pct = int(round(getattr(body, 'beam_defense_bonus', 0.10) * 100))
        drag_pct = int(round((1.0 - getattr(body, 'speed_multiplier', 0.80)) * 100))
        data.append({'type': 'label', 'text': f"Tactical Cover: +{beam_pct}% Beam defense (scattering).", 'object_id': '#sidebar_info_label', 'height': 20})
        data.append({'type': 'label', 'text': f"Weapon Coolant (-1 cd). Drag -{drag_pct}%.", 'object_id': '#sidebar_info_label', 'height': 20})

    elif isinstance(body, Nebula):
        data.append({'type': 'label', 'text': f"Type: {body.nebula_type.name.capitalize()}", 'object_id': '#sidebar_info_label', 'height': 20})
        data.append({'type': 'label', 'text': "Stealth: Conceals units from long-range sensors.", 'object_id': '#sidebar_info_label', 'height': 20})
        if body.nebula_type == NebulaType.HYDROGEN:
            data.append({'type': 'label', 'text': "Fuel Scooping: 0.4x AM harvest; -50% sublight AM burn.", 'object_id': '#sidebar_info_label', 'height': 20})
        elif body.nebula_type == NebulaType.NITROGEN:
            data.append({'type': 'label', 'text': "Coolant Cloud: Enhanced weapon cooling (-1 cd).", 'object_id': '#sidebar_info_label', 'height': 20})
        elif body.nebula_type == NebulaType.OXYGEN:
            data.append({'type': 'label', 'text': "Volatile Gas: +25% shield regen, +15% splash vuln.", 'object_id': '#sidebar_info_label', 'height': 20})
        elif body.nebula_type == NebulaType.DUST:
            data.append({'type': 'label', 'text': "Dense Particulate: Reduces optical vision by 30%.", 'object_id': '#sidebar_info_label', 'height': 20})

    elif isinstance(body, Storm):
        data.append({'type': 'label', 'text': f"Type: {body.storm_type.name.capitalize()} Storm", 'object_id': '#sidebar_info_label', 'height': 20})
        if body.storm_type == StormType.PLASMA:
            data.append({'type': 'label', 'text': "⚠ Plasma Hazard: 8 thermal damage/turn to ships.", 'object_id': '#sidebar_status_charging_label', 'height': 20})
        elif body.storm_type == StormType.MAGNETIC:
            data.append({'type': 'label', 'text': "⚠ Magnetic Hazard: Drains 6 AM/turn; jams radar.", 'object_id': '#sidebar_status_charging_label', 'height': 20})
        elif body.storm_type == StormType.RADIATION:
            data.append({'type': 'label', 'text': "⚠ Radiation Hazard: 4 component damage/turn.", 'object_id': '#sidebar_status_charging_label', 'height': 20})

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

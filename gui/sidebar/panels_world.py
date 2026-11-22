"""Sidebar UI panel builders for StarSystem, Hex, CelestialBody, and Minefield entities."""
from domain.celestials import (
    CelestialBody, Planet, Moon, ColonizableAsteroid, MetalAsteroid, Wormhole, Comet,
    NON_SOLID_CELESTIAL_BODIES,
)
from domain.construction_job import get_sector_construction_jobs
from domain.minefields import Minefield
from domain.players import are_enemies
from domain.units import Unit
from galaxy import StarSystem, Hex


def _is_ship_unit(unit: Unit) -> bool:
    """Returns True for mobile units (ships and wings), False for stationary stations."""
    return getattr(unit, 'engines_component', None) is not None


def _hex_section_header(title: str) -> dict:
    return {
        'type': 'label',
        'text': title,
        'object_id': '#sidebar_component_header_label',
        'height': 20,
    }


def _hex_subsection_header(title: str) -> dict:
    return {
        'type': 'label',
        'text': title,
        'object_id': '#sidebar_info_label',
        'height': 20,
        'indent_level': 1,
    }


def _hex_celestial_button(game, body: CelestialBody) -> dict:
    from planetary_intel import is_colony_body, displayed_owner, presentation_view
    owner = displayed_owner(game, body) if is_colony_body(body) else getattr(body, 'owner', None)
    stale = is_colony_body(body) and presentation_view(game, body).status == 'last_known'
    if isinstance(body, Wormhole) and getattr(body, 'exit_system_name', None):
        text = f"{body.name} → {body.exit_system_name}"
    else:
        text = body.name + (' (last known)' if stale else '')
    return {
        'type': 'button',
        'text': text,
        'object_id': object_button_style(None if stale else owner),
        'class_id': '#sidebar_expand_button',
        'action_id': 'select_celestial_body',
        'target_data': body.id,
        'height': 20,
        'indent_level': 1,
    }


def _hex_unit_button(unit: Unit, *, indent_level: int) -> dict:
    owner = getattr(unit, 'owner', None)
    return {
        'type': 'button',
        'text': unit.name,
        'object_id': object_button_style(owner),
        'class_id': '#sidebar_expand_button',
        'action_id': 'select_individual_unit',
        'target_data': unit.id,
        'height': 20,
        'indent_level': indent_level,
    }


def object_button_style(owner) -> str:
    """Returns the CSS element ID for player-themed or neutral buttons based on owner."""
    if owner and getattr(owner, 'name', None):
        return f'#player_{owner.name.lower().replace(" ", "_")}_button'
    return '#sidebar_neutral_button'


def build_system_panel(game, sys_obj: StarSystem) -> list[dict]:
    """Constructs sidebar data payload for a selected StarSystem."""
    data = [
        {'type': 'label', 'text': f"System: {sys_obj.name}", 'object_id': '#sidebar_title_label', 'height': 30,
         'sidebar_identity': f"system:{sys_obj.name}"},
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
    data.append({'type': 'label', 'text': f"Hex ({coords[0]}, {coords[1]}) in {system_name}", 'object_id': '#sidebar_title_label', 'height': 30,
                 'sidebar_identity': f"hex:{hex_obj.in_system}:{coords}"})

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

    is_unit_visible = getattr(game, 'is_unit_visible', lambda _u: True)
    is_minefield_visible = getattr(game, 'is_minefield_visible', lambda _mf: True)

    visible_units = [u for u in hex_obj.units if is_unit_visible(u)]
    visible_ships = [u for u in visible_units if _is_ship_unit(u)]
    visible_stations = [u for u in visible_units if not _is_ship_unit(u)]
    has_presence = game.hex_has_presence(system_name, coords)
    has_visible_enemy = any(
        are_enemies(current_player, getattr(u, 'owner', None))
        for u in visible_units
    ) if current_player is not None else False
    visible_deployables = [
        obj for obj in getattr(hex_obj, 'deployables', ())
        if is_unit_visible(obj)
    ]
    visible_minefields = [
        mf for mf in getattr(hex_obj, 'minefields', [])
        if is_minefield_visible(mf)
    ]
    visible_construction_jobs = [
        job for job in get_sector_construction_jobs(hex_obj, viewer=current_player)
        if is_unit_visible(job.constructor_unit)
    ]
    submerged_ships = []
    if current_player is not None:
        for body in hex_obj.celestial_bodies:
            for hidden_unit in getattr(body, 'hidden_units', ()):
                if getattr(hidden_unit, 'owner', None) == current_player:
                    submerged_ships.append(hidden_unit)

    wormholes = []
    solid_bodies = []
    resource_bodies = []
    environmental_regions = []
    for body in hex_obj.celestial_bodies:
        if isinstance(body, Wormhole):
            wormholes.append(body)
        elif isinstance(body, (MetalAsteroid, Comet)):
            resource_bodies.append(body)
        elif isinstance(body, NON_SOLID_CELESTIAL_BODIES) or not getattr(body, 'is_solid', True):
            environmental_regions.append(body)
        else:
            solid_bodies.append(body)

    if has_presence and not has_visible_enemy:
        data.append({
            'type': 'label',
            'text': "⚠ Enemy presence detected",
            'object_id': '#sidebar_hit_points_critical_damage_label',
            'height': 20,
        })

    has_any_content = bool(
        hex_obj.celestial_bodies
        or visible_units
        or submerged_ships
        or visible_construction_jobs
        or visible_deployables
        or visible_minefields
        or has_presence
    )
    if not has_any_content:
        data.append({'type': 'label', 'text': "Contains: Nothing", 'object_id': '#sidebar_info_label', 'height': 25})
        return data

    if wormholes:
        data.append(_hex_section_header("Wormholes:"))
        data.extend(_hex_celestial_button(game, body) for body in wormholes)

    if solid_bodies:
        data.append(_hex_section_header("Celestial Bodies:"))
        data.extend(_hex_celestial_button(game, body) for body in solid_bodies)

    if resource_bodies:
        data.append(_hex_section_header("Resource Bodies:"))
        data.extend(_hex_celestial_button(game, body) for body in resource_bodies)

    if environmental_regions:
        data.append(_hex_section_header("Environment:"))
        data.extend(_hex_celestial_button(game, body) for body in environmental_regions)

    if visible_units:
        data.append(_hex_section_header("Units:"))
        if visible_ships:
            data.append(_hex_subsection_header(f"Ships ({len(visible_ships)}):"))
            data.extend(_hex_unit_button(u, indent_level=2) for u in visible_ships)
        if visible_stations:
            data.append(_hex_subsection_header(f"Stations ({len(visible_stations)}):"))
            data.extend(_hex_unit_button(u, indent_level=2) for u in visible_stations)

    if submerged_ships:
        data.append(_hex_section_header("Submerged Ships:"))
        data.extend(_hex_unit_button(u, indent_level=1) for u in submerged_ships)

    if visible_construction_jobs:
        data.append(_hex_section_header("Construction Sites:"))
        for job in visible_construction_jobs:
            owner = getattr(job, 'owner', None)
            display_name = job.get_display_name(current_player)
            data.append({
                'type': 'button',
                'text': f"{display_name} ({job.progress}/{job.time_to_build}t)",
                'object_id': object_button_style(owner),
                'class_id': '#sidebar_expand_button',
                'action_id': 'select_construction_job',
                'target_data': job.constructor_unit.id,
                'height': 20,
                'indent_level': 1,
            })

    if visible_deployables:
        data.append(_hex_section_header("Deployables:"))
        for obj in visible_deployables:
            owner = getattr(obj, 'owner', None)
            data.append({
                'type': 'button',
                'text': f"{obj.name} (Persistent)",
                'object_id': object_button_style(owner),
                'class_id': '#sidebar_expand_button',
                'action_id': 'select_deployable',
                'target_data': obj.id,
                'height': 20,
                'indent_level': 1,
            })

    if visible_minefields:
        data.append(_hex_section_header("Minefields:"))
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
                'indent_level': 1,
            })

    return data


def build_celestial_body_panel(game, body: CelestialBody, *, show_rules: bool = False) -> list[dict]:
    """Constructs sidebar data payload for a selected CelestialBody."""
    from .celestial_formatting import rules_section_key
    data = [
        {'type': 'label', 'text': f"{body.__class__.__name__}: {body.name}", 'object_id': '#sidebar_title_label', 'height': 30,
         'sidebar_identity': rules_section_key(game, body)},
        {'type': 'label', 'text': f"System: {body.in_system or 'None'}", 'object_id': '#sidebar_info_label', 'height': 25}
    ]

    hex_pos_str = "N/A"
    if body.in_system and game.galaxy and body.in_system in game.galaxy.systems:
        hex_pos_str = str(body.in_hex)
    data.append({'type': 'label', 'text': f"Hex: {hex_pos_str}", 'object_id': '#sidebar_info_label', 'height': 25})
    data.append({'type': 'label', 'text': f"Sector Pos: ({body.position.x:.2f}, {body.position.y:.2f})", 'object_id': '#sidebar_info_label', 'height': 25})
    if body.in_hex is not None and body.in_system and game.galaxy and body.in_system in game.galaxy.systems:
        data.append({
            'type': 'button',
            'text': f"◀ Back to Hex {body.in_hex}",
            'object_id': '#sidebar_expand_button',
            'action_id': 'select_hex',
            'target_data': body.in_hex,
            'height': 25
        })

    from tactical_ui import patch_panel
    from .celestial_formatting import body_summary
    from constants import PlanetType
    from environmental_effects import describe_body
    for attribute in ('star_type', 'planet_type', 'nebula_type', 'storm_type'):
        subtype = getattr(body, attribute, None)
        if subtype is not None:
            data.append({'type': 'label', 'text': f'Type: {subtype.name.replace("_", " ").title()}', 'object_id': '#sidebar_info_label', 'height': 20})
    description = describe_body(body)
    data.extend(row.panel_row() for row in body_summary(body, description))
    data.extend(patch_panel(game, body))
    rules_footer = [{
        'type': 'button', 'text': '▼ Full rules' if show_rules else '▶ Full rules',
        'object_id': '#sidebar_expand_button', 'height': 25,
        'action_id': 'toggle_celestial_rules', 'target_data': body.id,
    }]
    if show_rules:
        rules_footer.extend({'type': 'label', 'text': rule, 'object_id': '#sidebar_info_label', 'height': 20}
                            for rule in description.rules)
        rules_footer.extend(patch_panel(game, body, show_rules=True))

    if isinstance(body, (Planet, Moon, ColonizableAsteroid)):
        if isinstance(body, Planet):
            if body.planet_type == PlanetType.GAS_GIANT:
                current_player = game.players[game.current_player_index] if game.players else None
                if current_player:
                    friendly_hidden = [u for u in getattr(body, 'hidden_units', []) if u.owner == current_player]
                    if friendly_hidden:
                        data.append({'type': 'label', 'text': f"Submerged Ships ({len(friendly_hidden)}):", 'object_id': '#sidebar_section_header_label', 'height': 25})
                        for u in friendly_hidden:
                            hull_name = u.hull_size.name.capitalize() if hasattr(u.hull_size, 'name') else str(u.hull_size)
                            data.append({
                                'type': 'button',
                                'text': f"🚀 {u.name} ({hull_name})",
                                'object_id': '#sidebar_expand_button',
                                'action_id': 'select_individual_unit',
                                'target_data': u.id,
                                'height': 25
                            })
                            data.append({
                                'type': 'button',
                                'text': f"Order to Leave: {u.name}",
                                'object_id': '#sidebar_action_button',
                                'action_id': 'order_unit_leave_gas_giant',
                                'target_data': u.id,
                                'height': 25
                            })
                        if len(friendly_hidden) > 1:
                            data.append({
                                'type': 'button',
                                'text': "Order All Ships to Leave",
                                'object_id': '#sidebar_action_button',
                                'action_id': 'order_all_leave_gas_giant',
                                'target_data': body.id,
                                'height': 25
                            })

                    can_enter_actors = [
                        a for a in getattr(game, 'selected_objects', [])
                        if isinstance(a, Unit) and a.owner == current_player and body.can_hide_unit(a)
                    ]
                    if can_enter_actors:
                        data.append({
                            'type': 'button',
                            'text': f"Hide Selected Ships ({len(can_enter_actors)})",
                            'object_id': '#sidebar_action_button',
                            'action_id': 'enter_gas_giant',
                            'target_data': body.id,
                            'height': 25
                        })
                return data + rules_footer

            p_metal = getattr(body, 'passive_metal', 0.0)
            p_crystal = getattr(body, 'passive_crystal', 0.0)
            if p_metal > 0:
                data.append({'type': 'label', 'text': f"Passive metal: +{p_metal:g}/turn", 'object_id': '#sidebar_effect_benefit_label', 'height': 20})
            if p_crystal > 0:
                data.append({'type': 'label', 'text': f"Passive crystal: +{p_crystal:g}/turn", 'object_id': '#sidebar_effect_benefit_label', 'height': 20})

        from planetary_intel import presentation_view, displayed_owner
        ownership = presentation_view(game, body)
        owner = displayed_owner(game, body)
        owner_name = 'Unknown' if ownership.status == 'unknown' else owner.name if owner else 'Uninhabited'
        owner_style_id = (f'#player_{owner_name.lower().replace(" ", "_")}_label'
                          if owner and ownership.status == 'current' else '#sidebar_info_label')
        data.append({'type': 'label', 'text': f"Owner: {owner_name}", 'object_id': owner_style_id, 'height': 25})
        if ownership.status != 'current':
            if ownership.status == 'last_known':
                data.append({'type': 'label', 'text': f'Last observed: turn {ownership.observed_turn}',
                             'object_id': '#sidebar_info_label', 'height': 25})
            data.append({'type': 'label', 'text': f'Population capacity: {body.max_population:g}',
                         'object_id': '#sidebar_info_label', 'height': 25})
            return data + rules_footer

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
        from planetary_warfare import colonizable, defense_view, blocker
        if colonizable(body):
            defense = defense_view(body)
            data.append({'type': 'label', 'text': f"Planetary defense: {defense['current_defense']:.1f}/{defense['maximum_defense']:.1f}", 'height': 25})
            data.append({'type': 'label', 'text': f"Readiness: {body.defense_readiness:.0%}; fortifications: {body.fortification_level}/3", 'height': 25})
            data.append({'type': 'label', 'text': 'Recovers 10% readiness per quiet round; minimum 25%.', 'height': 25})
            if body.owner == current_player and defense['next_upgrade_cost'] is not None:
                from resource_costs import ResourceCost
                cost = ResourceCost.from_dict(defense['next_upgrade_resources'])
                error = blocker(game, current_player, 'upgrade_planetary_defenses', body)
                data.append({'type': 'label', 'text': f'Upgrade cost: {cost.credits:g} credits', 'height': 25})
                data.append({'type': 'label', 'text': f'{cost.metal:g} metal / {cost.crystal:g} crystal', 'height': 25})
                data.append({'type': 'button', 'text': 'Upgrade fortifications', 'action_id': 'upgrade_planetary_defenses', 'target_data': body.id, 'height': 32, 'enabled': error is None})
                if error:
                    data.append({'type': 'label', 'text': error.replace('_', ' ').capitalize(), 'height': 25})
                    if error == 'insufficient_resources':
                        for name, amount in cost.shortfall(current_player).to_dict().items():
                            if amount:
                                data.append({'type': 'label', 'text': f'Missing: {amount:g} {name}', 'height': 25})
        data.append({'type': 'label', 'text': f"Population: {body.population:.2f} / {body.max_population:.2f}", 'object_id': '#sidebar_info_label', 'height': 25})
        if body.owner:
            from environmental_effects import colony_sensor_range
            sensor_range = colony_sensor_range(body, game.galaxy)
            data.append({'type': 'label', 'text': f'Short-range sensors: {sensor_range:g} units from surface',
                         'object_id': '#sidebar_info_label', 'height': 25})
            data.append({'type': 'label', 'text': f'Population growth: {body.population_growth_rate:.2%} per round',
                         'object_id': '#sidebar_info_label', 'height': 25})
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
        data.append({'type': 'label', 'text': f"Exit Wormhole: {body.exit_wormhole_id if body.exit_wormhole_id is not None else 'None'}", 'object_id': '#sidebar_info_label', 'height': 25})
        from wormhole_stabilization import connection_stability
        route = connection_stability(game.galaxy, body)
        data.append({'type': 'label', 'text': f"Stability: {body.stability}% natural / {route.effective_stability}% effective", 'object_id': '#sidebar_info_label', 'height': 25})
        if route.status != 'natural':
            styles = {'stabilized': '#sidebar_effect_benefit_label', 'destabilized': '#sidebar_effect_hazard_label',
                      'contested': '#sidebar_effect_restriction_label'}
            data.append({'type': 'label', 'text': route.status.title(), 'object_id': styles[route.status], 'height': 20})
        loss = route.crossing_fuel_loss
        if loss:
            data.append({'type': 'label', 'text': f'Instability drains up to {loss:g} AM per transit',
                         'object_id': '#sidebar_effect_hazard_label', 'height': 20})
        data.append({'type': 'label', 'text': f"Diameter: {body.diameter.name.capitalize()}", 'object_id': '#sidebar_info_label', 'height': 25})

    elif isinstance(body, Comet):
        data.append({'type': 'label', 'text': f"Crystal Yield: {body.crystal_yield}", 'object_id': '#sidebar_info_label', 'height': 25})

    return data + rules_footer


def build_minefield_panel(game, mf: Minefield) -> list[dict]:
    """Constructs sidebar data payload for a selected Minefield."""
    owner_name = mf.owner.name if mf.owner else "Unknown"
    owner_style = f'#player_{owner_name.lower().replace(" ", "_")}_label'
    data = [
        {'type': 'label', 'text': f"Minefield: {mf.name}", 'object_id': '#sidebar_title_label', 'height': 30,
         'sidebar_identity': f"minefield:{getattr(mf, 'id', id(mf))}"},
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


def build_construction_job_panel(game, job) -> list[dict]:
    """Constructs sidebar data payload for a selected ConstructionJob."""
    viewer = game.players[game.current_player_index] if (getattr(game, 'players', None) and 0 <= getattr(game, 'current_player_index', 0) < len(game.players)) else None
    display_title = job.get_display_name(viewer)
    owner_name = job.owner.name if job.owner else "Unknown"
    owner_style = f'#player_{owner_name.lower().replace(" ", "_")}_label'
    hull_label = job.hull_size.name.replace('_', ' ').title() if hasattr(job.hull_size, 'name') else 'Medium'
    kind_label = 'Station' if job.is_station else 'Ship'

    job_identity_id = getattr(job, 'site_id', getattr(getattr(job, 'constructor_unit', None), 'id', id(job)))
    data = [
        {'type': 'label', 'text': f"Site: {display_title}", 'object_id': '#sidebar_title_label', 'height': 30,
         'sidebar_identity': f"construction_job:{job_identity_id}"},
        {'type': 'label', 'text': f"Owner: {owner_name}", 'object_id': owner_style, 'height': 22},
        {'type': 'label', 'text': f"Hull: {hull_label} ({kind_label})", 'object_id': '#sidebar_info_label', 'height': 22},
        {'type': 'label', 'text': f"Location: ({job.position.x:.0f}, {job.position.y:.0f})", 'object_id': '#sidebar_info_label', 'height': 22},
        {'type': 'label', 'text': f"Progress: {job.progress} / {job.time_to_build} turns ({job.percent}%)", 'object_id': '#sidebar_info_label', 'height': 22},
        {
            'type': 'progress_bar',
            'progress': job.progress,
            'total': job.time_to_build,
            'height': 22
        },
        {'type': 'label', 'text': f"Turns Remaining: {max(0, job.time_to_build - job.progress)}", 'object_id': '#sidebar_info_label', 'height': 22},
        {'type': 'label', 'text': f"Builder: {job.constructor_unit.name}", 'object_id': '#sidebar_info_label', 'height': 22},
        {
            'type': 'button',
            'text': f"Select Builder ({job.constructor_unit.name})",
            'object_id': '#sidebar_expand_button',
            'action_id': 'select_constructor_unit',
            'target_data': job.constructor_unit.id,
            'height': 25
        }
    ]

    if viewer and job.owner == viewer:
        data.append({
            'type': 'button',
            'text': "Cancel Construction (Refund)",
            'object_id': '#sidebar_expand_button',
            'action_id': 'cancel_construction_job',
            'target_data': job.constructor_unit.id,
            'height': 25
        })

    return data

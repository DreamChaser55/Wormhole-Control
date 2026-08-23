"""Sidebar UI panel builders for Unit entities."""
import typing
from constants import MAX_UNIT_XP, UPKEEP_COST_PER_HULL_POINT
from entities import Unit


def hit_point_style_id(unit: Unit) -> str:
    """Returns the CSS element ID for unit hit points label based on damage level."""
    if unit.max_hit_points <= 0:
        return '#sidebar_hit_points_critical_damage_label'
    hp_percentage = unit.current_hit_points / unit.max_hit_points
    if hp_percentage > 0.75:
        return '#sidebar_hit_points_ok_label'
    elif hp_percentage > 0.40:
        return '#sidebar_hit_points_light_damage_label'
    elif hp_percentage > 0.15:
        return '#sidebar_hit_points_heavy_damage_label'
    else:
        return '#sidebar_hit_points_critical_damage_label'


def build_unit_panel(game, unit: Unit) -> list[dict]:
    """Constructs complete sidebar data payload for a selected Unit."""
    data = []
    current_player = game.players[game.current_player_index] if game.players else None
    is_owned = (unit.owner == current_player)

    if is_owned:
        data.append({
            'type': 'text_entry_line',
            'initial_text': unit.name,
            'object_id': '#unit_name_entry',
            'max_length': 30,
            'height': 30
        })
    else:
        data.append({'type': 'label', 'text': f"Unit: {unit.name}", 'object_id': '#sidebar_title_label', 'height': 30})

    data.append({'type': 'label', 'text': f"Type: {unit.__class__.__name__}", 'object_id': '#sidebar_info_label', 'height': 20})
    data.append({'type': 'label', 'text': f"Hull Size: {unit.hull_size.name.capitalize()}", 'object_id': '#sidebar_info_label', 'height': 20})
    if getattr(unit, 'template_name', None):
        data.append({'type': 'label', 'text': f"Template: {unit.template_name}", 'object_id': '#sidebar_info_label', 'height': 20})

    owner_name = unit.owner.name if unit.owner else "Neutral"
    owner_name_style_id = f'#player_{owner_name.lower().replace(" ", "_")}_label'
    data.append({'type': 'label', 'text': f"Owner: {owner_name}", 'object_id': owner_name_style_id, 'height': 25})

    if current_player and hasattr(unit, 'has_infiltrating_agent_from') and unit.has_infiltrating_agent_from(current_player):
        agent = next((ag for ag in getattr(unit, 'infiltrating_agents', []) if ag.owner == current_player), None)
        sab_txt = f" [SABOTAGE: {agent.active_sabotage.name}]" if (agent and agent.active_sabotage) else ""
        data.append({
            'type': 'label',
            'text': f"👁 COVERT AGENT EMBEDDED{sab_txt}",
            'object_id': '#sidebar_status_active_label',
            'height': 24
        })

    # --- Targeting Mode Banner (if active) ---
    pending = getattr(game, 'pending_ability', None)
    if pending and isinstance(pending, (tuple, list)) and len(pending) > 0 and isinstance(pending[0], str):
        pending_name = pending[0].replace('_', ' ').title()
        req_unit = pending[1] if len(pending) > 1 else False
        req_pos = pending[2] if len(pending) > 2 else False

        data.append({
            'type': 'label',
            'text': f"\u25b6 TARGETING: {pending_name}",
            'object_id': '#sidebar_hit_points_light_damage_label',
            'height': 24
        })
        if req_unit:
            instruction = "Right-Click target unit to cast"
        elif req_pos:
            instruction = "Right-Click target location to cast"
        else:
            instruction = "Right-Click to cast"
        data.append({
            'type': 'label',
            'text': f"{instruction} (ESC to cancel)",
            'object_id': '#sidebar_info_label',
            'height': 20
        })

    # --- Tab Buttons ---
    active_tab = getattr(game, 'selected_unit_tab', 'basic_info')
    basic_label = "[ Basic Info ]" if active_tab == 'basic_info' else "Basic Info"
    comp_label = "[ Components ]" if active_tab == 'components' else "Components"

    data.append({
        'type': 'button',
        'text': basic_label,
        'object_id': '#sidebar_tab_button_active' if active_tab == 'basic_info' else '#sidebar_tab_button',
        'action_id': 'switch_unit_sidebar_tab',
        'target_data': 'basic_info',
        'height': 25,
        'side_by_side': True
    })
    data.append({
        'type': 'button',
        'text': comp_label,
        'object_id': '#sidebar_tab_button_active' if active_tab == 'components' else '#sidebar_tab_button',
        'action_id': 'switch_unit_sidebar_tab',
        'target_data': 'components',
        'height': 25,
        'side_by_side': True
    })

    if active_tab == 'basic_info':
        data.append({'type': 'label', 'text': f"System: {unit.in_system or 'None'}", 'object_id': '#sidebar_info_label', 'height': 20})
        hex_pos_str = "N/A"
        if unit.in_system and game.galaxy and unit.in_system in game.galaxy.systems:
            hex_pos_str = str(unit.in_hex)
        data.append({'type': 'label', 'text': f"Hex: {hex_pos_str}", 'object_id': '#sidebar_info_label', 'height': 20})
        data.append({'type': 'label', 'text': f"Sector Pos: ({unit.position.x:.2f}, {unit.position.y:.2f})", 'object_id': '#sidebar_info_label', 'height': 20})

        data.append({'type': 'label', 'text': f"Hull Capacity: {unit.current_hull_usage:g}/{unit.hull_capacity:g}", 'object_id': '#sidebar_info_label', 'height': 25})
        upkeep_per_turn = unit.current_hull_usage * UPKEEP_COST_PER_HULL_POINT
        data.append({'type': 'label', 'text': f"Upkeep: {upkeep_per_turn:.2f} cr/turn", 'object_id': '#sidebar_info_label', 'height': 20})

        data.append({'type': 'label', 'text': f"Hit Points: {unit.current_hit_points}/{unit.max_hit_points}", 'object_id': hit_point_style_id(unit), 'height': 25})

        xp = unit.experience_points
        xp_text = f"Experience: {xp} / {MAX_UNIT_XP}"
        if xp >= MAX_UNIT_XP:
            xp_text += " [Veteran]"
        data.append({'type': 'label', 'text': xp_text, 'object_id': '#sidebar_info_label', 'height': 20})

        if current_player:
            if hasattr(unit, 'has_infiltrating_agent_from') and unit.has_infiltrating_agent_from(current_player):
                agent = next((ag for ag in getattr(unit, 'infiltrating_agents', []) if ag.owner == current_player), None)
                sab_info = f" (Sabotage: {agent.active_sabotage.name})" if (agent and agent.active_sabotage) else ""
                data.append({'type': 'label', 'text': f"• Infiltrated: Agent Active{sab_info}", 'object_id': '#sidebar_status_active_label', 'height': 20})
            if is_owned and hasattr(unit, 'infiltrating_agents'):
                for ag in unit.infiltrating_agents:
                    if ag.is_discovered and ag.owner != current_player:
                        data.append({'type': 'label', 'text': f"⚠ Discovered Enemy Agent ({ag.owner.name})", 'object_id': '#sidebar_status_charging_label', 'height': 20})

        # Summaries from all installed components
        data.append({'type': 'label', 'text': "Component Overview:", 'object_id': '#sidebar_section_header_label', 'height': 25})
        installed_components = list(unit.components.values())
        installed_components.sort(key=lambda c: getattr(c, 'SIDEBAR_ORDER', 100))
        for comp in installed_components:
            data.extend(comp.get_basic_sidebar_data(game))

    else:  # 'components' tab
        data.append({'type': 'label', 'text': f"Hit Points: {unit.current_hit_points}/{unit.max_hit_points}", 'object_id': hit_point_style_id(unit), 'height': 20})
        data.append({'type': 'label', 'text': "Select Component:", 'object_id': '#sidebar_section_header_label', 'height': 25})

        installed_components = list(unit.components.values())
        installed_components.sort(key=lambda c: getattr(c, 'SIDEBAR_ORDER', 100))

        components_map = {c.DISPLAY_NAME: c for c in installed_components}
        dropdown_options = list(components_map.keys())

        if dropdown_options:
            if game.selected_component_name not in dropdown_options:
                if "Commander" in dropdown_options:
                    game.selected_component_name = "Commander"
                else:
                    game.selected_component_name = dropdown_options[0]
            starting_option = game.selected_component_name
        else:
            game.selected_component_name = None
            starting_option = None

        if dropdown_options and starting_option:
            data.append({
                'type': 'drop_down_menu',
                'options_list': dropdown_options,
                'starting_option': starting_option,
                'height': 30
            })

        selected_comp = components_map.get(game.selected_component_name)
        if selected_comp:
            data.extend(selected_comp.get_sidebar_data(game))

    return data

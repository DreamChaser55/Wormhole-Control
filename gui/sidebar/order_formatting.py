"""HTML order-text formatting utilities for UI sidebar order queues."""
import typing
from geometry import Position
from entities import Order

# Styling color constants
MOVE_TYPE_COLOR = "#87CEEB"            # Cyan for Move order type
WAYPOINT_TYPE_COLOR = "#98FB98"        # Green for Waypoint order type
ATTACK_TYPE_COLOR = "#FF0000"          # Red for Attack order type
TOGGLE_INHIBITOR_TYPE_COLOR = "#A020F0" # Purple for Toggle Inhibitor type
TOGGLE_INHIBITOR_ON_COLOR = "#90EE90"   # Light Green for Inhibitor Activate
TOGGLE_INHIBITOR_OFF_COLOR = "#F08080"  # Light Red for Inhibitor Deactivate
PATROL_TYPE_COLOR = "#DAA520"           # Goldenrod for Patrol
COLONIZE_COLOR = "#FFD700"              # Gold for Colonize
LOAD_COLONISTS_COLOR = "#ADD8E6"        # Light Blue for Load Colonists
INFO_COLOR = "#D3D3D3"                  # Light Gray for general info
CONSTRUCT_COLOR = "#FF8C00"             # Dark Orange for Construct order type
REPAIR_COLOR = "#00FF7F"                # Spring Green for Repair order type
DOCK_COLOR = "#EE82EE"                  # Violet for Dock order type
DEPLOY_COLOR = "#00FFFF"                # Cyan for Deploy order type
ABILITY_COLOR = "#FF69B4"               # Hot Pink for Use Ability order type
MINE_COLOR = "#FFA500"                  # Orange for Mine
UNLOAD_COLOR = "#00FFFF"                # Cyan for Unload Resources
TRANSFER_ANTIMATTER_COLOR = "#7FFFD4"   # Aquamarine for Transfer Antimatter
TRADE_COLOR = "#FFD700"                 # Gold for Trade orders


def _target_name_html(state_data: dict) -> str:
    """Helper to format target unit name strings consistently."""
    target_name = state_data.get("target_name")
    target_unit_id = state_data.get("target_unit_id")
    lookup_attempted = state_data.get("lookup_attempted", False)
    lookup_success = state_data.get("lookup_success", False)

    if lookup_success and target_name:
        return f"<font color='{INFO_COLOR}'><i>{target_name}</i></font>"
    elif target_unit_id:
        if lookup_attempted:
            return f"<font color='{INFO_COLOR}'><i>Target ID: {target_unit_id} (Not found)</i></font>"
        else:
            return f"<font color='{INFO_COLOR}'><i>Target ID: {target_unit_id}</i></font>"
    else:
        return f"<font color='{INFO_COLOR}'><i>Unknown Target</i></font>"


def format_order_state_data(state_data: dict, galaxy: typing.Any = None) -> list[str]:
    """Formats raw order state parameters into HTML-styled text strings for sidebar display.

    Args:
        state_data (dict): Dictionary describing the order type, parameters, and progress state.
        galaxy: Optional Galaxy instance for target lookup.

    Returns:
        list[str]: List of HTML-formatted strings describing key order properties.
    """
    order_type = state_data.get("order_type")
    status = state_data.get("status")
    parameters = state_data.get("parameters", {})

    if order_type == "STANCE":
        stance = str(parameters.get("stance", "do_nothing")).replace("_", " ").title()
        return [f"<font color='{PATROL_TYPE_COLOR}'><b>Stance:</b></font> <font color='{INFO_COLOR}'>{stance}</font>"]

    if order_type == "MOVE":
        dsys = parameters.get("destination_system_name", "N/A")
        dhex = parameters.get("destination_hex_coord", "N/A")
        dpos_param = parameters.get("destination_position", None)
        dpos_str = f"({dpos_param.x:.1f}, {dpos_param.y:.1f})" if isinstance(dpos_param, Position) else "N/A"

        move_type_styled = f"<font color='{MOVE_TYPE_COLOR}'><b>Move:</b></font>"
        dsys_styled = f"<font color='{INFO_COLOR}'><i>{dsys}</i></font>" if dsys != "N/A" else f"<font color='{INFO_COLOR}'>N/A</font>"
        dhex_styled = f"<font color='{INFO_COLOR}'>{dhex}</font>"
        dpos_styled = f"<font color='{INFO_COLOR}'>{dpos_str}</font>"
        return [
            move_type_styled,
            f"  Sys: {dsys_styled}",
            f"  Hex: {dhex_styled}",
            f"  Pos: {dpos_styled}"
        ]

    elif order_type == "REACH_WAYPOINT":
        dsys = parameters.get("destination_system_name", "N/A")
        dhex = parameters.get("destination_hex_coord", "N/A")
        dpos_param = parameters.get("destination_position", None)
        dpos_str = f"({dpos_param.x:.1f}, {dpos_param.y:.1f})" if isinstance(dpos_param, Position) else "N/A"

        waypoint_type_styled = f"<font color='{WAYPOINT_TYPE_COLOR}'><b>Waypoint:</b></font>"
        dsys_styled = f"<font color='{INFO_COLOR}'><i>{dsys}</i></font>" if dsys != "N/A" else f"<font color='{INFO_COLOR}'>N/A</font>"
        dhex_styled = f"<font color='{INFO_COLOR}'>{dhex}</font>"
        dpos_styled = f"<font color='{INFO_COLOR}'>{dpos_str}</font>"
        return [
            waypoint_type_styled,
            f"  Sys: {dsys_styled}",
            f"  Hex: {dhex_styled}",
            f"  Pos: {dpos_styled}"
        ]

    elif order_type == "TOGGLE_INHIBITOR":
        turn_on = parameters.get("turn_on", False)
        action = "Activate" if turn_on else "Deactivate"
        status_color = TOGGLE_INHIBITOR_ON_COLOR if turn_on else TOGGLE_INHIBITOR_OFF_COLOR
        action_styled = f"<font color='{status_color}'>{action}</font>"
        toggle_inhibitor_type_styled = f"<font color='{TOGGLE_INHIBITOR_TYPE_COLOR}'><b>Toggle Inhibitor:</b></font>"
        return [f"{toggle_inhibitor_type_styled} {action_styled}"]

    elif order_type == "PATROL":
        patrol_type_styled = f"<font color='{PATROL_TYPE_COLOR}'><b>🔄 Patrol:</b></font>"
        waypoints = parameters.get("waypoints", [])
        curr_idx = state_data.get("current_waypoint_index", 0)

        if not waypoints and "destination_position" in parameters:
            waypoints = [{
                "system_name": parameters.get("destination_system_name", "N/A"),
                "hex_coord": parameters.get("destination_hex_coord", "N/A"),
                "position": parameters.get("destination_position", None)
            }]

        lines = [patrol_type_styled]
        for idx, wp in enumerate(waypoints):
            wsys = wp.get("system_name", "N/A")
            whex = wp.get("hex_coord", "N/A")
            wpos = wp.get("position", None)
            wpos_str = f"({wpos.x:.1f}, {wpos.y:.1f})" if isinstance(wpos, Position) else "N/A"

            prefix = "&nbsp;&nbsp;"
            if idx == curr_idx:
                prefix = "&nbsp;* "

            lines.append(f"{prefix}WP {idx+1}: <font color='{INFO_COLOR}'><i>{wsys}</i></font>:{whex}:{wpos_str}")

        prefix = "&nbsp;&nbsp;"
        if curr_idx == len(waypoints):
            prefix = "&nbsp;* "
        lines.append(f"{prefix}WP Start (Return)")
        return lines

    elif order_type == "ATTACK":
        attack_type_styled = f"<font color='{ATTACK_TYPE_COLOR}'><b>Attack:</b></font>"
        return [f"{attack_type_styled} {_target_name_html(state_data)}"]

    elif order_type == "COLONIZE":
        target_name = parameters.get("target_name", "Unknown Target")
        colonize_type_styled = f"<font color='{COLONIZE_COLOR}'><b>Colonize:</b></font>"
        target_styled = f"<font color='{INFO_COLOR}'><i>{target_name}</i></font>"
        return [f"{colonize_type_styled} {target_styled}"]

    elif order_type == "LOAD_COLONISTS":
        target_name = parameters.get("target_name", "Unknown Target")
        load_type_styled = f"<font color='{LOAD_COLONISTS_COLOR}'><b>Load Colonists:</b></font>"
        target_styled = f"<font color='{INFO_COLOR}'><i>{target_name}</i></font>"
        return [f"{load_type_styled} {target_styled}"]

    elif order_type == "MINE":
        target_id = parameters.get("target_id", "Unknown")
        mine_type_styled = f"<font color='{MINE_COLOR}'><b>Mine:</b></font>"
        target_styled = f"<font color='{INFO_COLOR}'><i>Target ID: {target_id}</i></font>"
        return [f"{mine_type_styled} {target_styled}"]

    elif order_type == "CONTINUOUS_MINE":
        target_id = parameters.get("target_id", "Unknown")
        continuous_mine_type_styled = f"<font color='{MINE_COLOR}'><b>🔁 Mine (continuously):</b></font>"
        target_styled = f"<font color='{INFO_COLOR}'><i>Target ID: {target_id}</i></font>"
        return [f"{continuous_mine_type_styled} {target_styled}"]

    elif order_type == "CONTINUOUS_RESUPPLY":
        target_id = parameters.get("target_id", "Unknown")
        target_name = parameters.get("target_name", f"Star ID: {target_id}")
        continuous_resupply_type_styled = f"<font color='{TRANSFER_ANTIMATTER_COLOR}'><b>🔁 Resupply (continuously):</b></font>"
        target_styled = f"<font color='{INFO_COLOR}'><i>{target_name}</i></font>"
        return [f"{continuous_resupply_type_styled} {target_styled}"]

    elif order_type == "TRADE":
        target_unit_id = parameters.get("target_unit_id", "Unknown")
        trade_type_styled = f"<font color='{TRADE_COLOR}'><b>Trade:</b></font>"
        target_styled = f"<font color='{INFO_COLOR}'><i>Target Habitat ID: {target_unit_id}</i></font>"
        return [f"{trade_type_styled} {target_styled}"]

    elif order_type == "CONTINUOUS_TRADE":
        continuous_trade_type_styled = f"<font color='{TRADE_COLOR}'><b>🔁 Trade (continuously)</b></font>"
        return [continuous_trade_type_styled]

    elif order_type == "UNLOAD_RESOURCES":
        target_unit_id = parameters.get("target_unit_id", "Unknown")
        unload_type_styled = f"<font color='{UNLOAD_COLOR}'><b>Unload:</b></font>"
        target_styled = f"<font color='{INFO_COLOR}'><i>Target ID: {target_unit_id}</i></font>"
        return [f"{unload_type_styled} {target_styled}"]

    elif order_type == "TRANSFER_ANTIMATTER":
        transfer_type_styled = f"<font color='{TRANSFER_ANTIMATTER_COLOR}'><b>Transfer Antimatter:</b></font>"
        return [f"{transfer_type_styled} {_target_name_html(state_data)}"]

    elif order_type == "CONSTRUCT":
        unit_template_name = parameters.get("unit_template_name", "Unknown Unit")
        target_pos = parameters.get("target_position")
        pos_str = f"({target_pos.x:.1f}, {target_pos.y:.1f})" if isinstance(target_pos, Position) else "N/A"

        construct_type_styled = f"<font color='{CONSTRUCT_COLOR}'><b>Construct:</b></font>"
        template_styled = f"<font color='{INFO_COLOR}'><i>{unit_template_name}</i></font>"
        pos_styled = f"<font color='{INFO_COLOR}'>{pos_str}</font>"
        return [
            f"{construct_type_styled} {template_styled}",
            f"  Pos: {pos_styled}"
        ]

    elif order_type == "REPAIR":
        repair_type_styled = f"<font color='{REPAIR_COLOR}'><b>Repair:</b></font>"
        return [f"{repair_type_styled} {_target_name_html(state_data)}"]

    elif order_type == "REFIT_UNIT":
        action = state_data.get("action", parameters.get("action", "ADD"))
        comp_type = state_data.get("component_type", parameters.get("component_type", "Component"))
        action_sym = f"+{comp_type}" if str(action).upper() == "ADD" else f"-{comp_type}"
        refit_type_styled = f"<font color='{CONSTRUCT_COLOR}'><b>Refit ({action_sym}):</b></font>"
        return [f"{refit_type_styled} {_target_name_html(state_data)}"]

    elif order_type == "PROTECT":
        protect_type_styled = f"<font color='#FF69B4'><b>Protect:</b></font>"
        return [f"{protect_type_styled} {_target_name_html(state_data)}"]

    elif order_type == "DOCK":
        target_name = state_data.get("target_name")
        target_carrier_id = state_data.get("target_carrier_id")

        if target_name:
            carrier_name_styled = f"<font color='{INFO_COLOR}'><i>{target_name}</i></font>"
        elif target_carrier_id:
            carrier_name_styled = f"<font color='{INFO_COLOR}'><i>Carrier ID: {target_carrier_id}</i></font>"
        else:
            carrier_name_styled = f"<font color='{INFO_COLOR}'><i>Unknown Carrier</i></font>"

        dock_type_styled = f"<font color='{DOCK_COLOR}'><b>Dock:</b></font>"
        return [f"{dock_type_styled} {carrier_name_styled}"]

    elif order_type == "DEPLOY_UNIT":
        docked_name = state_data.get("docked_name")
        docked_unit_id = state_data.get("docked_unit_id")

        if docked_name:
            unit_name_styled = f"<font color='{INFO_COLOR}'><i>{docked_name}</i></font>"
        elif docked_unit_id:
            unit_name_styled = f"<font color='{INFO_COLOR}'><i>Unit ID: {docked_unit_id}</i></font>"
        else:
            unit_name_styled = f"<font color='{INFO_COLOR}'><i>Unknown Unit</i></font>"

        deploy_type_styled = f"<font color='{DEPLOY_COLOR}'><b>Deploy:</b></font>"
        return [f"{deploy_type_styled} {unit_name_styled}"]

    elif order_type == "DEPLOY_ALL_WINGS":
        deploy_all_type_styled = f"<font color='{DEPLOY_COLOR}'><b>Deploy All Wings</b></font>"
        return [deploy_all_type_styled]

    elif order_type == "USE_ABILITY":
        ability_type_str = parameters.get("ability_type", "Unknown")
        target_unit_id = parameters.get("target_unit_id")
        target_position = parameters.get("target_position")

        target_name = None
        if target_unit_id and galaxy:
            target_unit = galaxy.get_unit_by_id(target_unit_id)
            if target_unit:
                target_name = target_unit.name

        ability_type_styled = f"<font color='{ABILITY_COLOR}'><b>Ability: {ability_type_str}</b></font>"

        lines = [ability_type_styled]
        if target_name:
            lines.append(f"  Target: <font color='{INFO_COLOR}'><i>{target_name}</i></font>")
        elif target_unit_id:
            lines.append(f"  Target: <font color='{INFO_COLOR}'><i>ID: {target_unit_id}</i></font>")

        if target_position:
            pos_str = f"({target_position.x:.1f}, {target_position.y:.1f})" if isinstance(target_position, Position) else "N/A"
            lines.append(f"  Pos: <font color='{INFO_COLOR}'>{pos_str}</font>")

        return lines

    else:
        # Default styling for other order types
        return [f"<font color='{INFO_COLOR}'>{order_type} ({status})</font>"]


def generate_order_data_html(order: Order, current_indent_level: int = 0, galaxy: typing.Any = None) -> str:
    """Helper function to recursively generate HTML string representing an order tree.

    Args:
        order (Order): The base or current order to be processed.
        current_indent_level (int): Recursion depth for HTML indentation.
        galaxy: Optional Galaxy instance for target name lookup.

    Returns:
        str: Continuous HTML string representing the formatted order hierarchy.
    """
    html_output_for_this_order_and_children = ""
    indent_html = "&nbsp;" * 4 * current_indent_level

    # Get the list of text lines for the current order
    state_data = order.get_state_data()
    order_info_lines = format_order_state_data(state_data, galaxy)

    sub_order_first_line_prefix_char = "> "

    # Process and indent each line of the current order's text
    for i, line_text in enumerate(order_info_lines):
        line_prefix_html = indent_html
        if current_indent_level > 0 and i == 0:
            line_prefix_html += sub_order_first_line_prefix_char

        html_output_for_this_order_and_children += f"{line_prefix_html}{line_text}<br>"

    # Recursively process sub-orders of *this* order
    if order.sub_orders:
        for sub_order in order.sub_orders:
            html_output_for_this_order_and_children += generate_order_data_html(sub_order, current_indent_level + 1, galaxy)

    return html_output_for_this_order_and_children

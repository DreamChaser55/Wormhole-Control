from display_config import DisplayConfig
from unittest.mock import MagicMock
import pytest
from domain.units import Unit
from geometry import Position
from constants import HullSize
from unit_components.enums import WingType
from unit_components.strikecraft import StrikecraftBayComponent, StrikecraftWingComponent
from unit_orders.hangar import DockOrder, DeployAllWingsOrder
from game import Game
from tests.support.units import ComponentPlayer


@pytest.mark.parametrize("docked_hp,launched_hp", [(30, 17), (17, 30)])
def test_strikecraft_bay_gui_data_generation(docked_hp, launched_hp):
    # Mock game
    game = MagicMock()
    game.display_config = DisplayConfig()
    player = ComponentPlayer("Player 1")
    game.players = [player]
    game.current_player_index = 0
    game.sidebar_needs_update = True
    
    # Mock system and galaxy
    system_mock = MagicMock()
    game.galaxy.systems = {"Sol": system_mock}
    
    # Create carrier unit
    carrier = Unit(
        owner=player,
        position=Position(0, 0),
        in_hex=(0, 0),
        in_system="Sol",
        name="Carrier",
        hull_size=HullSize.HUGE,
        game=game
    )
    
    # Add StrikecraftBayComponent
    strikecraft_bay = StrikecraftBayComponent(carrier, max_slots=2)
    carrier.add_component(strikecraft_bay)
    
    # Add a docked wing
    docked_wing = Unit(
        owner=player,
        position=Position(0, 0),
        in_hex=(0, 0),
        in_system="Sol",
        name="Docked Wing",
        hull_size=HullSize.STRIKECRAFT_WING,
        game=game
    )
    docked_wing_comp = StrikecraftWingComponent(docked_wing)
    docked_wing.add_component(docked_wing_comp)
    docked_wing.current_hit_points = docked_hp
    strikecraft_bay.docked_units.append(docked_wing)
    
    # Add a launched wing
    launched_wing = Unit(
        owner=player,
        position=Position(0, 0),
        in_hex=(0, 0),
        in_system="Sol",
        name="Launched Wing",
        hull_size=HullSize.STRIKECRAFT_WING,
        game=game
    )
    launched_wing_comp = StrikecraftWingComponent(launched_wing, wing_type=WingType.BOMBER)
    launched_wing.add_component(launched_wing_comp)
    launched_wing.current_hit_points = launched_hp
    strikecraft_bay.launched_units.append(launched_wing)
    
    # Setup selection
    game.selected_objects = [carrier]
    game.selected_component_name = "Strikecraft Bay"
    game.selected_unit_tab = "components"
    
    # Run update_side_bar_content
    import game as game_module
    original_profile = game_module.PROFILE
    game_module.PROFILE = False
    
    try:
        game.gui.update_side_bar_content = MagicMock()
        Game.update_side_bar_content(game)
        
        # Assert side bar content updated
        game.gui.update_side_bar_content.assert_called_once()
        data_list = game.gui.update_side_bar_content.call_args[0][0]
        
        # Check that "Docked Strikecraft Wings:" and "Launched Strikecraft Wings:" are present
        labels = [d.get("text") for d in data_list if d.get("type") == "label"]
        buttons = [d for d in data_list if d.get("type") == "button"]
        
        assert "Docked Strikecraft Wings:" in labels
        assert "Launched Strikecraft Wings:" in labels
        assert f"  - Docked Wing (Fighter, HP: {docked_hp}/30)" in labels
        assert f"  - Launched Wing (Bomber, HP: {launched_hp}/30)" in labels
        
        # Find Deploy button
        deploy_btn = next((b for b in buttons if b["action_id"] == "deploy_ship"), None)
        assert deploy_btn is not None
        assert deploy_btn["target_data"] == (carrier.id, docked_wing.id)
        
        # Find Launch All Wings button
        launch_all_btn = next((b for b in buttons if b["action_id"] == "launch_all_wings"), None)
        assert launch_all_btn is not None
        assert launch_all_btn["target_data"] == carrier.id
        
        # Find Recall button
        recall_btn = next((b for b in buttons if b["action_id"] == "recall_ship"), None)
        assert recall_btn is not None
        assert recall_btn["target_data"] == (carrier.id, launched_wing.id)
    finally:
        game_module.PROFILE = original_profile


def test_strikecraft_bay_gui_data_generation_non_owner():
    # Mock game
    game = MagicMock()
    game.display_config = DisplayConfig()
    player = ComponentPlayer("Player 1")
    enemy = ComponentPlayer("Player 2")
    game.players = [player] # Active player is player
    game.current_player_index = 0
    game.sidebar_needs_update = True
    
    # Mock system and galaxy
    system_mock = MagicMock()
    game.galaxy.systems = {"Sol": system_mock}
    
    # Create carrier unit owned by enemy
    carrier = Unit(
        owner=enemy,
        position=Position(0, 0),
        in_hex=(0, 0),
        in_system="Sol",
        name="Enemy Carrier",
        hull_size=HullSize.HUGE,
        game=game
    )
    
    # Add StrikecraftBayComponent
    strikecraft_bay = StrikecraftBayComponent(carrier, max_slots=2)
    carrier.add_component(strikecraft_bay)
    
    # Add a docked wing
    docked_wing = Unit(
        owner=enemy,
        position=Position(0, 0),
        in_hex=(0, 0),
        in_system="Sol",
        name="Enemy Wing",
        hull_size=HullSize.STRIKECRAFT_WING,
        game=game
    )
    docked_wing_comp = StrikecraftWingComponent(docked_wing)
    docked_wing.add_component(docked_wing_comp)
    strikecraft_bay.docked_units.append(docked_wing)
    
    # Setup selection
    game.selected_objects = [carrier]
    game.selected_component_name = "Strikecraft Bay"
    
    # Run update_side_bar_content
    import game as game_module
    original_profile = game_module.PROFILE
    game_module.PROFILE = False
    
    try:
        game.gui.update_side_bar_content = MagicMock()
        Game.update_side_bar_content(game)
        
        data_list = game.gui.update_side_bar_content.call_args[0][0]
        buttons = [d for d in data_list if d.get("type") == "button"]
        
        # Non-owner should see labels but NOT action buttons (like Deploy)
        assert not any(b["action_id"] == "deploy_ship" for b in buttons)
        assert not any(b["action_id"] == "launch_all_wings" for b in buttons)
    finally:
        game_module.PROFILE = original_profile


def test_recall_ship_action_handling():
    game = MagicMock()
    game.display_config = DisplayConfig()
    player = ComponentPlayer("Player 1")
    game.players = [player]
    game.current_player_index = 0
    
    carrier = Unit(
        owner=player,
        position=Position(0, 0),
        in_hex=(0, 0),
        in_system="Sol",
        name="Carrier",
        hull_size=HullSize.HUGE,
        game=game
    )
    strikecraft_bay = StrikecraftBayComponent(carrier, max_slots=2)
    carrier.add_component(strikecraft_bay)
    
    launched_wing = Unit(
        owner=player,
        position=Position(0, 0),
        in_hex=(0, 0),
        in_system="Sol",
        name="Launched Wing",
        hull_size=HullSize.STRIKECRAFT_WING,
        game=game
    )
    launched_wing_comp = StrikecraftWingComponent(launched_wing)
    launched_wing.add_component(launched_wing_comp)
    strikecraft_bay.launched_units.append(launched_wing)
    
    # Mock galaxy.get_unit_by_id
    game.galaxy.get_unit_by_id.side_effect = lambda uid: carrier if uid == carrier.id else (launched_wing if uid == launched_wing.id else None)
    
    # Trigger handle_gui_action
    action = {
        'action': 'recall_ship',
        'carrier_id': carrier.id,
        'launched_unit_id': launched_wing.id
    }
    
    # Mock Commander.add_order
    launched_wing.commander_component.add_order = MagicMock()
    
    Game.handle_gui_action(game, action)
    
    # Verify DockOrder is added to the launched wing
    launched_wing.commander_component.add_order.assert_called_once()
    order = launched_wing.commander_component.add_order.call_args[0][0]
    assert isinstance(order, DockOrder)
    assert order.parameters["target_carrier_id"] == carrier.id


def test_launch_all_wings_action_handling():
    game = MagicMock()
    game.display_config = DisplayConfig()
    player = ComponentPlayer("Player 1")
    game.players = [player]
    game.current_player_index = 0
    
    carrier = Unit(
        owner=player,
        position=Position(0, 0),
        in_hex=(0, 0),
        in_system="Sol",
        name="Carrier",
        hull_size=HullSize.HUGE,
        game=game
    )
    strikecraft_bay = StrikecraftBayComponent(carrier, max_slots=2)
    carrier.add_component(strikecraft_bay)
    
    # Mock galaxy.get_unit_by_id
    game.galaxy.get_unit_by_id.side_effect = lambda uid: carrier if uid == carrier.id else None
    
    # Trigger handle_gui_action
    action = {
        'action': 'launch_all_wings',
        'carrier_id': carrier.id
    }
    
    # Mock Commander.add_order
    carrier.commander_component.add_order = MagicMock()
    
    Game.handle_gui_action(game, action)
    
    # Verify DeployAllWingsOrder is added to the carrier
    carrier.commander_component.add_order.assert_called_once()
    order = carrier.commander_component.add_order.call_args[0][0]
    assert isinstance(order, DeployAllWingsOrder)


@pytest.mark.parametrize("wing_type", [WingType.FIGHTER, WingType.BOMBER])
@pytest.mark.parametrize("hull_hp", [30, 17])
@pytest.mark.parametrize("tab", ["basic_info", "components"])
def test_wing_gui_data_generation(wing_type, hull_hp, tab):
    # Mock game
    game = MagicMock()
    game.display_config = DisplayConfig()
    player = ComponentPlayer("Player 1")
    game.players = [player]
    game.current_player_index = 0
    game.sidebar_needs_update = True
    
    # Create wing unit
    wing = Unit(
        owner=player,
        position=Position(0, 0),
        in_hex=(0, 0),
        in_system="Sol",
        name="Test Wing",
        hull_size=HullSize.STRIKECRAFT_WING,
        game=game
    )
    # Add StrikecraftWingComponent
    wing_comp = StrikecraftWingComponent(wing, wing_type=wing_type)
    wing.add_component(wing_comp)
    wing.current_hit_points = hull_hp
    
    # Setup selection
    game.selected_objects = [wing]
    game.selected_component_name = "Strikecraft Wing"
    game.selected_unit_tab = tab
    
    # Run update_side_bar_content
    import game as game_module
    original_profile = game_module.PROFILE
    game_module.PROFILE = False
    
    try:
        game.gui.update_side_bar_content = MagicMock()
        Game.update_side_bar_content(game)
        
        # Assert side bar content updated
        game.gui.update_side_bar_content.assert_called_once()
        data_list = game.gui.update_side_bar_content.call_args[0][0]
        
        # Hull condition is shown once, alongside role and component details.
        labels = [d.get("text") for d in data_list if d.get("type") == "label"]
        assert labels.count(f"Hit Points: {hull_hp}/30") == 1
        assert not any("Active Craft" in label or "/4" in label or "/ 4" in label for label in labels)
        role = wing_type.value.capitalize()
        if tab == "components":
            assert "Strikecraft Wing [HP: 10/10]" in labels
            assert f"Role: {role}" in labels
            assert "Mother Carrier: None" in labels
        else:
            summary = next(d for d in data_list if d.get("text") == f"• Strikecraft ({role})")
            assert summary["object_id"] == "#sidebar_info_label"
    finally:
        game_module.PROFILE = original_profile

import pytest
from unittest.mock import MagicMock
from geometry import Position, distance
from entities import Unit, Player, Minefield
from constants import HullSize
from unit_components import (
    AbilityComponent,
    AbilityType,
    AntimatterStorage,
    Sensors,
    MinefieldType,
)
from unit_components.abilities.scan_for_minefields import ScanForMinefieldsAbility
from unit_components.abilities.registry import ABILITY_DEFINITIONS, ABILITY_CLASSES
from custom_unit_templates import ABILITY_REQUIRED_COMPONENTS
from gui.unit_editor_gui.catalog import ABILITY_NAMES
from visibility import VisibilityService, is_minefield_visible
from save_manager import serialize_minefield, deserialize_minefield
from gui.sidebar.panels_world import build_hex_panel, build_minefield_panel
from game_actions.selection_actions import handle_remove_minefield


class DummyHex:
    def __init__(self, q=0, r=0, in_system="Sol"):
        self.q = q
        self.r = r
        self.in_system = in_system
        self.units = []
        self.minefields = []
        self.celestial_bodies = []
        self.static_inhibition_zones = []
        self.dynamic_inhibition_zones = {}

    def coordinates(self):
        return (self.q, self.r)

    def add_unit(self, unit):
        self.units.append(unit)

    def add_minefield(self, mf):
        self.minefields.append(mf)

    def remove_minefield(self, mf):
        if mf in self.minefields:
            self.minefields.remove(mf)

    def get_all_inhibition_zones(self):
        return self.static_inhibition_zones + list(self.dynamic_inhibition_zones.values())


class DummySystem:
    def __init__(self, name="Sol"):
        self.name = name
        self.hexes = {(0, 0): DummyHex(0, 0, name)}


class DummyGalaxy:
    def __init__(self):
        self.systems = {"Sol": DummySystem("Sol")}
        self._units = {}
        self._minefields = {}

    def get_unit_by_id(self, unit_id):
        return self._units.get(unit_id)

    def get_minefield_by_id(self, mf_id):
        return self._minefields.get(mf_id)

    def remove_minefield(self, mf):
        for sys in self.systems.values():
            for hex_obj in sys.hexes.values():
                hex_obj.remove_minefield(mf)
        self._minefields.pop(mf.id, None)


class DummyGame:
    def __init__(self, players=None):
        self.players = players if players is not None else [
            Player("Player 1", (0, 255, 0)),
            Player("Player 2", (255, 0, 0))
        ]
        self.current_player_index = 0
        self.galaxy = DummyGalaxy()
        self.selected_objects = []
        self.hovered_object = None
        self.pending_ability = None
        self.current_system_name = "Sol"
        self.current_sector_coord = (0, 0)
        self.visibility = None
        self.visibility_dirty = True
        self.sidebar_needs_update = False

    def recompute_visibility(self):
        current_player = self.players[self.current_player_index] if self.players else None
        self.visibility = VisibilityService.compute(self.galaxy, current_player)
        self.visibility_dirty = False

    def is_minefield_visible(self, minefield):
        if self.visibility_dirty or self.visibility is None:
            self.recompute_visibility()
        return is_minefield_visible(self.visibility, minefield)

    def is_unit_visible(self, unit):
        return True

    def hex_has_presence(self, system_name, coords):
        return False


def test_scan_for_minefields_definition():
    """Verify static definition and registry for Scan for Minefields."""
    defn = ScanForMinefieldsAbility.DEFINITION
    assert defn.ability_type == AbilityType.SCAN_FOR_MINEFIELDS
    assert defn.name == "Scan for Minefields"
    assert defn.requires_target_position is False
    assert defn.requires_target_unit is False
    assert defn.range == 1500.0
    assert defn.cooldown == 6
    assert defn.duration == 0
    assert defn.antimatter_cost == 35
    assert defn.required_components == ["has_sensors"]
    assert "scan_for_minefields" in ABILITY_NAMES
    assert AbilityType.SCAN_FOR_MINEFIELDS in ABILITY_CLASSES
    assert AbilityType.SCAN_FOR_MINEFIELDS in ABILITY_DEFINITIONS
    assert ABILITY_REQUIRED_COMPONENTS.get("scan_for_minefields") == ["has_sensors"]


def test_scan_for_minefields_reveals_enemy_minefields_in_range():
    """Test activating Scan for Minefields reveals enemy minefields within 1500 units and ignores out-of-range ones."""
    p1 = Player("Player 1", (0, 255, 0))
    p2 = Player("Player 2", (255, 0, 0))
    game = DummyGame(players=[p1, p2])
    hex_obj = game.galaxy.systems["Sol"].hexes[(0, 0)]

    # Unit for Player 1 with Sensors, Antimatter, and AbilityComponent
    scanner_unit = Unit(
        owner=p1,
        position=Position(0, 0),
        in_hex=(0, 0),
        in_system="Sol",
        name="Scout",
        hull_size=HullSize.MEDIUM,
        game=game,
    )
    scanner_unit.add_component(Sensors(scanner_unit, short_range_radius=2000.0))
    am_comp = AntimatterStorage(scanner_unit, max_capacity=100.0)
    am_comp.current_amount = 100.0
    scanner_unit.add_component(am_comp)
    ab_comp = AbilityComponent(scanner_unit, [AbilityType.SCAN_FOR_MINEFIELDS])
    scanner_unit.add_component(ab_comp)
    hex_obj.add_unit(scanner_unit)
    game.galaxy._units[scanner_unit.id] = scanner_unit

    # Enemy minefield in range (dist = 600)
    mf_in_range = Minefield(
        owner=p2,
        position=Position(600, 0),
        in_hex=(0, 0),
        in_system="Sol",
        mines_remaining=5,
        minefield_type=MinefieldType.ANTI_SHIP,
    )
    hex_obj.add_minefield(mf_in_range)
    game.galaxy._minefields[mf_in_range.id] = mf_in_range

    # Enemy minefield out of range (dist = 1800)
    mf_out_range = Minefield(
        owner=p2,
        position=Position(1800, 0),
        in_hex=(0, 0),
        in_system="Sol",
        mines_remaining=5,
        minefield_type=MinefieldType.ANTI_SHIP,
    )
    hex_obj.add_minefield(mf_out_range)
    game.galaxy._minefields[mf_out_range.id] = mf_out_range

    # Before scan: both enemy minefields are invisible to Player 1
    assert game.is_minefield_visible(mf_in_range) is False
    assert game.is_minefield_visible(mf_out_range) is False
    assert mf_in_range.is_revealed_to(p1) is False
    assert mf_out_range.is_revealed_to(p1) is False

    # Activate Scan for Minefields
    assert ab_comp.can_use(AbilityType.SCAN_FOR_MINEFIELDS) is True
    success = ab_comp.activate(AbilityType.SCAN_FOR_MINEFIELDS, game.galaxy)
    assert success is True

    # AM consumed and cooldown set
    assert am_comp.current_amount == 65.0
    instance = ab_comp.abilities[AbilityType.SCAN_FOR_MINEFIELDS]
    assert instance.cooldown_remaining == 6

    # In-range minefield is now revealed and visible to Player 1
    assert mf_in_range.is_revealed_to(p1) is True
    assert game.is_minefield_visible(mf_in_range) is True

    # Out-of-range minefield remains hidden
    assert mf_out_range.is_revealed_to(p1) is False
    assert game.is_minefield_visible(mf_out_range) is False


def test_revealed_minefields_stay_visible_indefinitely():
    """Revealed enemy minefields stay visible even when the player moves away or turns pass."""
    p1 = Player("Player 1", (0, 255, 0))
    p2 = Player("Player 2", (255, 0, 0))
    game = DummyGame(players=[p1, p2])
    hex_obj = game.galaxy.systems["Sol"].hexes[(0, 0)]

    scanner_unit = Unit(
        owner=p1,
        position=Position(0, 0),
        in_hex=(0, 0),
        in_system="Sol",
        name="Scout",
        hull_size=HullSize.MEDIUM,
        game=game,
    )
    scanner_unit.add_component(Sensors(scanner_unit, short_range_radius=2000.0))
    am_comp = AntimatterStorage(scanner_unit, max_capacity=100.0)
    am_comp.current_amount = 100.0
    scanner_unit.add_component(am_comp)
    ab_comp = AbilityComponent(scanner_unit, [AbilityType.SCAN_FOR_MINEFIELDS])
    scanner_unit.add_component(ab_comp)
    hex_obj.add_unit(scanner_unit)

    enemy_mf = Minefield(
        owner=p2,
        position=Position(500, 0),
        in_hex=(0, 0),
        in_system="Sol",
        mines_remaining=5,
    )
    hex_obj.add_minefield(enemy_mf)

    # Scan and reveal
    ab_comp.activate(AbilityType.SCAN_FOR_MINEFIELDS, game.galaxy)
    assert game.is_minefield_visible(enemy_mf) is True

    # Move ship far away or remove it entirely
    scanner_unit.position = Position(9999, 9999)
    game.visibility_dirty = True
    assert game.is_minefield_visible(enemy_mf) is True

    # Simulate turn ticking on ability cooldown
    ab_comp.update(game.galaxy)
    instance = ab_comp.abilities[AbilityType.SCAN_FOR_MINEFIELDS]
    assert instance.cooldown_remaining == 5
    assert game.is_minefield_visible(enemy_mf) is True


def test_revealed_minefield_is_player_specific():
    """Revealing an enemy minefield for Player 1 does not make it visible to Player 3."""
    p1 = Player("Player 1", (0, 255, 0))
    p2 = Player("Player 2", (255, 0, 0))
    p3 = Player("Player 3", (0, 0, 255))
    game = DummyGame(players=[p1, p2, p3])
    hex_obj = game.galaxy.systems["Sol"].hexes[(0, 0)]

    scanner_unit = Unit(
        owner=p1,
        position=Position(0, 0),
        in_hex=(0, 0),
        in_system="Sol",
        name="Scout",
        hull_size=HullSize.MEDIUM,
        game=game,
    )
    scanner_unit.add_component(Sensors(scanner_unit, short_range_radius=2000.0))
    am_comp = AntimatterStorage(scanner_unit, max_capacity=100.0)
    am_comp.current_amount = 100.0
    scanner_unit.add_component(am_comp)
    ab_comp = AbilityComponent(scanner_unit, [AbilityType.SCAN_FOR_MINEFIELDS])
    scanner_unit.add_component(ab_comp)
    hex_obj.add_unit(scanner_unit)

    mf_p2 = Minefield(
        owner=p2,
        position=Position(500, 0),
        in_hex=(0, 0),
        in_system="Sol",
        mines_remaining=5,
    )
    hex_obj.add_minefield(mf_p2)

    # P1 scans
    ab_comp.activate(AbilityType.SCAN_FOR_MINEFIELDS, game.galaxy)

    # Check P1 perspective
    game.current_player_index = 0
    game.visibility_dirty = True
    assert game.is_minefield_visible(mf_p2) is True

    # Check P2 (owner) perspective
    game.current_player_index = 1
    game.visibility_dirty = True
    assert game.is_minefield_visible(mf_p2) is True

    # Check P3 (third party who hasn't scanned) perspective
    game.current_player_index = 2
    game.visibility_dirty = True
    assert game.is_minefield_visible(mf_p2) is False


def test_scan_fails_with_insufficient_antimatter():
    """Activation fails if antimatter is less than 35."""
    p1 = Player("Player 1", (0, 255, 0))
    game = DummyGame(players=[p1])
    unit = Unit(
        owner=p1,
        position=Position(0, 0),
        in_hex=(0, 0),
        in_system="Sol",
        name="Scout",
        hull_size=HullSize.MEDIUM,
        game=game,
    )
    unit.add_component(Sensors(unit, short_range_radius=2000.0))
    am_comp = AntimatterStorage(unit, max_capacity=100.0)
    am_comp.current_amount = 20.0  # < 35 required
    unit.add_component(am_comp)
    ab_comp = AbilityComponent(unit, [AbilityType.SCAN_FOR_MINEFIELDS])
    unit.add_component(ab_comp)

    assert ab_comp.can_use(AbilityType.SCAN_FOR_MINEFIELDS) is False
    assert ab_comp.activate(AbilityType.SCAN_FOR_MINEFIELDS, game.galaxy) is False
    assert am_comp.current_amount == 20.0


def test_save_load_preserves_revealed_minefields():
    """Verify serialize_minefield and deserialize_minefield preserve revealed_to_player_ids."""
    p1 = Player("Player 1", (0, 255, 0))
    p1.id = 1
    p2 = Player("Player 2", (255, 0, 0))
    p2.id = 2
    players_by_id = {1: p1, 2: p2}

    mf = Minefield(
        owner=p2,
        position=Position(300, 400),
        in_hex=(1, -1),
        in_system="Vega",
        mines_remaining=4,
        mine_damage=45.0,
        detonation_radius=280.0,
        minefield_type=MinefieldType.ANTI_STRIKECRAFT,
    )
    mf.id = 99
    mf.reveal_to(p1)

    serialized = serialize_minefield(mf)
    assert serialized["id"] == 99
    assert serialized["revealed_to_player_ids"] == [1]

    restored_mf = deserialize_minefield(serialized, players_by_id)
    assert restored_mf.id == 99
    assert restored_mf.is_revealed_to(p1) is True
    assert restored_mf.is_revealed_to(p2) is False
    assert restored_mf.revealed_to_player_ids == {1}


def test_hex_sidebar_shows_revealed_enemy_minefields():
    """Verify build_hex_panel displays revealed enemy minefields, and build_minefield_panel restricts remove button to owner."""
    p1 = Player("Player 1", (0, 255, 0))
    p2 = Player("Player 2", (255, 0, 0))
    game = DummyGame(players=[p1, p2])
    hex_obj = game.galaxy.systems["Sol"].hexes[(0, 0)]

    mf_p2 = Minefield(
        owner=p2,
        position=Position(100, 100),
        in_hex=(0, 0),
        in_system="Sol",
        mines_remaining=5,
    )
    hex_obj.add_minefield(mf_p2)

    # Before reveal, Player 1's hex panel contains no minefields
    game.current_player_index = 0
    game.visibility_dirty = True
    panel_p1 = build_hex_panel(game, hex_obj)
    assert not any("Minefields:" in str(item.get("text")) for item in panel_p1)

    # Reveal to Player 1
    mf_p2.reveal_to(p1)
    game.visibility_dirty = True

    # Now Player 1's hex panel includes the revealed minefield
    panel_p1_after = build_hex_panel(game, hex_obj)
    assert any("Minefields:" in str(item.get("text")) for item in panel_p1_after)
    assert any(mf_p2.name in str(item.get("text")) for item in panel_p1_after)

    # Inspect minefield panel as Player 1 (revealer, but not owner) -> NO remove button
    mf_panel_p1 = build_minefield_panel(game, mf_p2)
    assert not any(item.get("action_id") == "remove_minefield" for item in mf_panel_p1)

    # Inspect minefield panel as Player 2 (owner) -> HAS remove button
    game.current_player_index = 1
    mf_panel_p2 = build_minefield_panel(game, mf_p2)
    assert any(item.get("action_id") == "remove_minefield" for item in mf_panel_p2)


def test_revealed_minefield_removal():
    """Verify removing a revealed minefield removes it from the galaxy and hex."""
    p1 = Player("Player 1", (0, 255, 0))
    p2 = Player("Player 2", (255, 0, 0))
    game = DummyGame(players=[p1, p2])
    hex_obj = game.galaxy.systems["Sol"].hexes[(0, 0)]

    mf = Minefield(
        owner=p2,
        position=Position(100, 100),
        in_hex=(0, 0),
        in_system="Sol",
        mines_remaining=5,
    )
    hex_obj.add_minefield(mf)
    game.galaxy._minefields[mf.id] = mf
    mf.reveal_to(p1)

    # Player 2 removes the minefield
    game.current_player_index = 1
    handle_remove_minefield(game, {"minefield_id": mf.id})

    assert mf not in hex_obj.minefields
    assert game.galaxy.get_minefield_by_id(mf.id) is None

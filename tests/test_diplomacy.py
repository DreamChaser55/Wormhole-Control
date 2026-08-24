import pytest
from entities import Player, Unit, Position, Planet, Minefield, HullSize
from galaxy import Galaxy, StarSystem, Hex, CelestialBody
from game_settings import PlayerConfig, GameSettings
from visibility import VisibilityService, is_unit_visible, is_minefield_visible
from unit_components import Sensors, CloakingDevice, OrbitalDefenseComponent
from unit_components.enums import CloakingType, AbilityType
from unit_components.abilities.repair_cloud import RepairCloudAbility
from unit_components.abilities.cluster_warhead import ClusterWarheadAbility
from unit_components.abilities.capture_unit import CaptureUnitAbility
from unit_components.abilities.drain_antimatter import DrainAntimatterAbility
from unit_components.abilities.designate_target import DesignateTargetAbility
from unit_components.intelligence import IntelligenceComponent, Agent, SabotageType
from unit_orders.intelligence import InfiltrateUnitOrder, InfiltratePlanetOrder, CISweepOrder
from unit_orders.combat import ProtectOrder
from unit_orders.patrol import PatrolOrder
from save_manager import serialize_player, deserialize_player
from utils import HexCoord


def make_unit(name: str, owner: Player, system: str = "Sol", hex_coord: HexCoord = (0, 0), pos: Position = Position(0, 0), hull_size: HullSize = HullSize.MEDIUM) -> Unit:
    return Unit(owner=owner, position=pos, in_hex=hex_coord, in_system=system, name=name, hull_size=hull_size, game=None)


def test_player_diplomacy_relations():
    p1 = Player("P1", (255, 0, 0), is_human=True, team_id=1)
    p2 = Player("P2", (0, 255, 0), is_human=False, team_id=1)
    p3 = Player("P3", (0, 0, 255), is_human=False, team_id=2)

    # Ally tests
    assert p1.is_allied_with(p1) is True
    assert p1.is_allied_with(p2) is True
    assert p2.is_allied_with(p1) is True
    assert p1.is_allied_with(p3) is False
    assert p2.is_allied_with(p3) is False
    assert p1.is_allied_with(None) is False

    # Enemy tests
    assert p1.is_enemy_of(p1) is False
    assert p1.is_enemy_of(p2) is False
    assert p1.is_enemy_of(p3) is True
    assert p3.is_enemy_of(p1) is True
    assert p3.is_enemy_of(p2) is True
    assert p1.is_enemy_of(None) is False

    # Relation string
    assert p1.relation_to(p2) == "ally"
    assert p1.relation_to(p3) == "enemy"
    assert p1.relation_to(None) == "neutral"


def test_player_default_team_id_isolation():
    # Backwards compatibility: omitting team_id makes players enemies by default
    p1 = Player("P1", (255, 0, 0))
    p2 = Player("P2", (0, 255, 0))
    assert p1.team_id != p2.team_id
    assert p1.is_allied_with(p2) is False
    assert p1.is_enemy_of(p2) is True


def test_game_settings_team_validation():
    # Valid: 2 distinct teams
    settings_valid = GameSettings(
        player_configs=[
            PlayerConfig(name="P1", color=(255, 0, 0), is_human=True, team_id=1),
            PlayerConfig(name="P2", color=(0, 255, 0), is_human=False, team_id=2),
        ]
    )
    assert settings_valid.validate() == []

    # Invalid: All players on same team raises ValueError
    with pytest.raises(ValueError, match="at least two different teams"):
        GameSettings(
            player_configs=[
                PlayerConfig(name="P1", color=(255, 0, 0), is_human=True, team_id=1),
                PlayerConfig(name="P2", color=(0, 255, 0), is_human=False, team_id=1),
            ]
        )


def test_player_serialization_team_id():
    p = Player("Alice", (100, 150, 200), is_human=True, team_id=3)
    p.credits = 12345.0
    data = serialize_player(p)
    assert data["team_id"] == 3

    restored = deserialize_player(data)
    assert restored.name == "Alice"
    assert restored.team_id == 3
    assert restored.is_allied_with(p) is True


def test_allied_sensor_sharing_and_visibility():
    galaxy = Galaxy()
    sys_sol = StarSystem("Sol", (0, 0), radius=5)
    galaxy.systems["Sol"] = sys_sol

    p1 = Player("P1", (255, 0, 0), team_id=1)
    p2 = Player("P2", (0, 255, 0), team_id=1)
    p_enemy = Player("Enemy", (0, 0, 255), team_id=2)

    # Ally unit (P2) is at (1, 0) with short-range sensor (radius=200) and long-range sensor (1 hex)
    ally_unit = make_unit("Ally Scout", owner=p2, system="Sol", hex_coord=(1, 0), pos=Position(10, 10))
    sensors = Sensors(ally_unit, short_range_radius=200.0, long_range_hexes=1)
    ally_unit.components[Sensors] = sensors
    sys_sol.hexes[(1, 0)].units.append(ally_unit)

    # Enemy unit is at (1, 0) close to ally unit (dist=50) -> detailed detection
    enemy_unit1 = make_unit("Enemy Fighter", owner=p_enemy, system="Sol", hex_coord=(1, 0), pos=Position(30, 30))
    sys_sol.hexes[(1, 0)].units.append(enemy_unit1)

    # Enemy unit 2 is at (2, 0) -> in long range of ally (presence only)
    enemy_unit2 = make_unit("Enemy Cruiser", owner=p_enemy, system="Sol", hex_coord=(2, 0), pos=Position(100, 100))
    sys_sol.hexes[(2, 0)].units.append(enemy_unit2)

    # P1 computes visibility (P1 has no units of its own!)
    snapshot = VisibilityService.compute(galaxy, viewer=p1, turn_number=1)

    # P1 sees enemy_unit1 (detailed from P2's short range sensors)
    assert is_unit_visible(snapshot, enemy_unit1) is True
    # P1 sees ally unit
    assert is_unit_visible(snapshot, ally_unit) is True
    # P1 does NOT see enemy_unit2 in detail, but has presence in (2, 0)
    assert is_unit_visible(snapshot, enemy_unit2) is False
    assert ("Sol", (2, 0)) in snapshot.presence_hexes
    # Sector intel was recorded for P1 in all hexes covered by ally's long range sensors
    assert ("Sol", (2, 0)) in p1.sector_intel


def test_allied_area_cloaking():
    galaxy = Galaxy()
    sys_sol = StarSystem("Sol", (0, 0), radius=5)
    galaxy.systems["Sol"] = sys_sol

    p_viewer = Player("Viewer", (255, 0, 0), team_id=1)
    p_enemy_cloak = Player("Enemy Cloaker", (0, 255, 0), team_id=2)
    p_enemy_ally = Player("Enemy Ally", (0, 0, 255), team_id=2)

    # Viewer has long range sensor covering Hex (1, 0)
    scout = make_unit("Scout", owner=p_viewer, system="Sol", hex_coord=(0, 0), pos=Position(0, 0))
    sensors = Sensors(scout, short_range_radius=50.0, long_range_hexes=2)
    scout.components[Sensors] = sensors
    sys_sol.hexes[(0, 0)].units.append(scout)

    # Cloaker unit with Advanced Area Cloaking at (1, 0)
    cloaker = make_unit("Stealth Cruiser", owner=p_enemy_cloak, system="Sol", hex_coord=(1, 0), pos=Position(100, 100))
    cloak_comp = CloakingDevice(cloaker, device_type=CloakingType.ADVANCED, area_radius=300.0)
    cloak_comp.is_active = True
    cloaker.components[CloakingDevice] = cloak_comp
    sys_sol.hexes[(1, 0)].units.append(cloaker)

    # Enemy Ally unit inside the area cloak bubble (dist=100)
    shielded_ship = make_unit("Shielded Battleship", owner=p_enemy_ally, system="Sol", hex_coord=(1, 0), pos=Position(150, 150))
    sys_sol.hexes[(1, 0)].units.append(shielded_ship)

    snapshot = VisibilityService.compute(galaxy, viewer=p_viewer, turn_number=1)

    # Both cloaker and shielded ally should be hidden from long-range presence
    assert ("Sol", (1, 0)) not in snapshot.presence_hexes
    assert is_unit_visible(snapshot, cloaker) is False
    assert is_unit_visible(snapshot, shielded_ship) is False


def test_repair_cloud_and_cluster_warhead_allies():
    galaxy = Galaxy()
    sys_sol = StarSystem("Sol", (0, 0), radius=5)
    galaxy.systems["Sol"] = sys_sol

    p1 = Player("P1", (255, 0, 0), team_id=1)
    p2 = Player("P2", (0, 255, 0), team_id=1)
    p_enemy = Player("Enemy", (0, 0, 255), team_id=2)

    caster = make_unit("Support Cruiser", owner=p1, system="Sol", hex_coord=(0, 0), pos=Position(0, 0))
    sys_sol.hexes[(0, 0)].units.append(caster)

    ally_damaged = make_unit("Allied Frigate", owner=p2, system="Sol", hex_coord=(0, 0), pos=Position(50, 50))
    ally_damaged.max_hit_points = 100
    ally_damaged.current_hit_points = 50
    sys_sol.hexes[(0, 0)].units.append(ally_damaged)

    enemy_damaged = make_unit("Enemy Frigate", owner=p_enemy, system="Sol", hex_coord=(0, 0), pos=Position(50, 50))
    enemy_damaged.max_hit_points = 100
    enemy_damaged.current_hit_points = 50
    sys_sol.hexes[(0, 0)].units.append(enemy_damaged)

    # 1. Repair Cloud: heals self and ally, NOT enemy
    repair_ability = RepairCloudAbility()
    repair_ability._apply_repair_cloud(
        type("FakeComp", (), {"unit": caster})(),
        galaxy
    )
    assert ally_damaged.current_hit_points == 55
    assert enemy_damaged.current_hit_points == 50

    # 2. Cluster Warhead: damages enemy, NOT ally
    warhead_ability = ClusterWarheadAbility()
    warhead_ability._apply_splash_damage(
        type("FakeComp", (), {"unit": caster})(),
        galaxy,
        target_position=Position(50, 50),
        target_system_name="Sol",
        target_hex_coord=(0, 0)
    )
    assert ally_damaged.current_hit_points == 55  # untouched
    assert enemy_damaged.current_hit_points < 50   # damaged


def test_hostile_abilities_reject_allies():
    galaxy = Galaxy()
    p1 = Player("P1", (255, 0, 0), team_id=1)
    p2 = Player("P2", (0, 255, 0), team_id=1)

    caster = make_unit("Caster", owner=p1, system="Sol", hex_coord=(0, 0), pos=Position(0, 0))
    ally = make_unit("Ally", owner=p2, system="Sol", hex_coord=(0, 0), pos=Position(10, 10))
    galaxy.get_unit_by_id = lambda uid: ally if uid == ally.id else caster

    comp = type("FakeComp", (), {"unit": caster})()

    # Capture Unit
    assert CaptureUnitAbility().on_activate(comp, galaxy, target_unit_id=ally.id) is False

    # Drain Antimatter
    assert DrainAntimatterAbility().on_activate(comp, galaxy, target_unit_id=ally.id) is False

    # Designate Target
    assert DesignateTargetAbility().on_activate(comp, galaxy, target_unit_id=ally.id) is False


def test_intelligence_and_ci_sweep_diplomacy():
    galaxy = Galaxy()
    sys_sol = StarSystem("Sol", (0, 0), radius=5)
    galaxy.systems["Sol"] = sys_sol

    p1 = Player("P1", (255, 0, 0), team_id=1)
    p2 = Player("P2", (0, 255, 0), team_id=1)
    p_enemy = Player("Enemy", (0, 0, 255), team_id=2)

    spy_unit = make_unit("Spy Vessel", owner=p1, system="Sol", hex_coord=(0, 0), pos=Position(0, 0))
    intel_comp = IntelligenceComponent(spy_unit, agents_count=2, agents_capacity=2, has_counter_intelligence=True)
    spy_unit.components[IntelligenceComponent] = intel_comp
    sys_sol.hexes[(0, 0)].units.append(spy_unit)

    ally_unit = make_unit("Ally Ship", owner=p2, system="Sol", hex_coord=(0, 0), pos=Position(50, 50))
    sys_sol.hexes[(0, 0)].units.append(ally_unit)

    enemy_unit = make_unit("Enemy Ship", owner=p_enemy, system="Sol", hex_coord=(0, 0), pos=Position(60, 60))
    sys_sol.hexes[(0, 0)].units.append(enemy_unit)

    galaxy.get_unit_by_id = lambda uid: {
        spy_unit.id: spy_unit,
        ally_unit.id: ally_unit,
        enemy_unit.id: enemy_unit
    }.get(uid)

    # 1. Infiltrating ally must fail
    infiltrate_ally_order = InfiltrateUnitOrder(spy_unit, parameters={"target_unit_id": ally_unit.id})
    infiltrate_ally_order.execute(galaxy)
    assert infiltrate_ally_order.status.name == "FAILED"

    # 2. Infiltrating enemy succeeds
    infiltrate_enemy_order = InfiltrateUnitOrder(spy_unit, parameters={"target_unit_id": enemy_unit.id})
    infiltrate_enemy_order.execute(galaxy)
    assert infiltrate_enemy_order.status.name == "COMPLETED"

    # 3. Enemy agent is infiltrating ally ship. CI Sweep from P1 must discover enemy agent on ally ship
    enemy_agent = Agent(owner=p_enemy, source_unit_id=enemy_unit.id, target_type="UNIT", target_id=ally_unit.id, agent_id=999)
    enemy_agent.attached_to = ally_unit
    enemy_agent.is_discovered = False
    ally_unit.infiltrating_agents.append(enemy_agent)

    ci_order = CISweepOrder(spy_unit)
    ci_order.execute(galaxy)
    assert ci_order.status.name == "COMPLETED"
    assert enemy_agent.is_discovered is True


def test_minefield_and_orbital_defense_relations():
    p1 = Player("P1", (255, 0, 0), team_id=1)
    p2 = Player("P2", (0, 255, 0), team_id=1)
    p_enemy = Player("Enemy", (0, 0, 255), team_id=2)

    # Minefield can target enemy, cannot target ally
    mf = Minefield(owner=p1, position=Position(0, 0), in_hex=(0, 0), in_system="Sol")
    ally_ship = make_unit("Ally", owner=p2, system="Sol", hex_coord=(0, 0), pos=Position(0, 0))
    enemy_ship = make_unit("Enemy", owner=p_enemy, system="Sol", hex_coord=(0, 0), pos=Position(0, 0))

    assert mf.can_target(ally_ship) is False
    assert mf.can_target(enemy_ship) is True

    # Visibility of minefield
    assert is_minefield_visible(type("Snap", (), {"viewer": p1})(), mf) is True
    assert is_minefield_visible(type("Snap", (), {"viewer": p2})(), mf) is True
    assert is_minefield_visible(type("Snap", (), {"viewer": p_enemy})(), mf) is False

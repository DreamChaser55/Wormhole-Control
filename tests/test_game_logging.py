"""Logging configuration owns its destinations without owning callers' resources."""
from contextlib import ExitStack
import io
import logging
import sys
from types import SimpleNamespace

import pytest

import game_logging


@pytest.fixture(autouse=True)
def isolated_logging(tmp_path, monkeypatch):
    """Restore process logging and close test-owned files even after assertion failures."""
    root = logging.getLogger()
    original_handlers = root.handlers[:]
    names = (*game_logging.THIRD_PARTY_LOGGERS, "wormhole_logging_test",
             *(name + ".lifecycle_test" for name in game_logging.THIRD_PARTY_LOGGERS))
    loggers = [root, *(logging.getLogger(name) for name in names)]
    levels = {logger: logger.level for logger in loggers}
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(game_logging, "_application_handlers", [])
    for handler in original_handlers:
        root.removeHandler(handler)
    try:
        yield
    finally:
        try:
            with ExitStack() as cleanup:
                for handler in root.handlers[:]:
                    root.removeHandler(handler)
                for handler in game_logging._application_handlers:
                    # FileHandler.close flushes files; pytest may already have
                    # closed its borrowed console stream between test phases.
                    cleanup.callback(handler.close)
                game_logging._application_handlers.clear()
        finally:
            for handler in original_handlers:
                root.addHandler(handler)
            for logger, level in levels.items():
                logger.setLevel(level)


@pytest.mark.parametrize("initial_file", [False, True])
@pytest.mark.parametrize("replacement_file", [False, True])
def test_repeated_setup_closes_owned_handlers_without_duplicate_output(
    initial_file, replacement_file, capsys, tmp_path,
):
    root = logging.getLogger()
    console = sys.stderr
    game_logging.setup_logging(log_to_file=initial_file)
    for index in range(3):
        old_handlers = root.handlers[:]
        old_files = [handler.stream for handler in old_handlers
                     if isinstance(handler, logging.FileHandler)]

        game_logging.setup_logging(log_to_file=replacement_file)

        assert all(handler._closed for handler in old_handlers)
        assert all(stream.closed for stream in old_files)
        assert all(handler not in root.handlers for handler in old_handlers)
        assert len(root.handlers) == 1 + replacement_file
        assert game_logging._application_handlers == root.handlers
        assert not console.closed
        message = f"application-record-{index}"
        logging.getLogger("wormhole_logging_test").debug(message)
        assert capsys.readouterr().err.count(message) == 1
        if replacement_file:
            contents = (tmp_path / "game.log").read_text()
            assert contents.count(message) == 1
            if index:
                assert f"application-record-{index - 1}" not in contents


def test_replacement_closes_old_file_before_opening_new_one(monkeypatch):
    game_logging.setup_logging(log_to_file=True)
    old_stream = logging.getLogger().handlers[-1].stream
    file_handler_class = logging.FileHandler

    def open_after_close(*args, **kwargs):
        assert old_stream.closed
        return file_handler_class(*args, **kwargs)

    monkeypatch.setattr(logging, "FileHandler", open_after_close)
    game_logging.setup_logging(log_to_file=True)


def test_detached_owned_file_is_closed_and_released(tmp_path):
    game_logging.setup_logging(log_to_file=True)
    root = logging.getLogger()
    old_handler = root.handlers[-1]
    old_stream = old_handler.stream
    logging.getLogger("wormhole_logging_test").info("before-detach")
    root.removeHandler(old_handler)

    game_logging.setup_logging(log_to_file=False)

    assert old_stream.closed
    assert old_handler not in game_logging._application_handlers
    path = tmp_path / "game.log"
    assert "before-detach" in path.read_text()
    moved = path.rename(tmp_path / "released.log")
    moved.unlink()
    assert not moved.exists()


@pytest.mark.parametrize("existing_file", [False, True])
def test_stream_only_setup_does_not_create_or_truncate_log(tmp_path, existing_file):
    path = tmp_path / "game.log"
    if existing_file:
        path.write_text("previous run\n")
    game_logging.setup_logging(log_to_file=False)
    game_logging.setup_logging(log_to_file=False)
    logging.getLogger("wormhole_logging_test").info("console only")
    assert path.exists() == existing_file
    if existing_file:
        assert path.read_text() == "previous run\n"


@pytest.mark.parametrize("file_handler", [False, True])
def test_external_handlers_are_detached_without_closing_or_reconfiguration(
    tmp_path, file_handler,
):
    external_stream = io.StringIO()
    path = tmp_path / "external.log"
    handler = logging.FileHandler(path) if file_handler else logging.StreamHandler(external_stream)
    stream = handler.stream
    formatter = logging.Formatter("external: %(message)s")
    record_filter = logging.Filter()
    handler.setFormatter(formatter)
    handler.setLevel(logging.ERROR)
    handler.addFilter(record_filter)
    try:
        logging.getLogger().addHandler(handler)
        game_logging.setup_logging(log_to_file=True)
        game_logging.setup_logging(log_to_file=False)
        assert handler not in logging.getLogger().handlers
        assert not handler._closed
        assert not stream.closed
        assert handler.formatter is formatter
        assert handler.level == logging.ERROR
        assert handler.filters == [record_filter]
        # The original owner can use the handler again after setup detaches it.
        handler.handle(logging.LogRecord("external", logging.ERROR, __file__, 1,
                                         "still usable", (), None))
        handler.flush()
        contents = path.read_text() if file_handler else external_stream.getvalue()
        assert contents == "external: still usable\n"
    finally:
        handler.close()


@pytest.mark.parametrize("log_to_file", [False, True])
def test_third_party_http_clients_cannot_emit_debug_request_bodies(
    log_to_file, capsys, tmp_path,
):
    game_logging.setup_logging(log_to_file=log_to_file)
    game_logging.setup_logging(log_to_file=log_to_file)
    for name in game_logging.THIRD_PARTY_LOGGERS:
        assert logging.getLogger(name).getEffectiveLevel() >= logging.WARNING
        child = logging.getLogger(name + ".lifecycle_test")
        child.setLevel(logging.DEBUG)
        for level in (logging.DEBUG, logging.INFO):
            record = logging.LogRecord(child.name, level, __file__, 1,
                                       "request body: secret", (), None)
            assert all(not handler.filter(record) for handler in logging.getLogger().handlers)
            child.log(level, "request body: secret")
        child.warning("safe-provider-warning")
    logging.getLogger("wormhole_logging_test").debug("application-debug")

    outputs = [capsys.readouterr().err]
    if log_to_file:
        outputs.append((tmp_path / "game.log").read_text())
    for output in outputs:
        assert "secret" not in output
        assert output.count("safe-provider-warning") == len(game_logging.THIRD_PARTY_LOGGERS)
        assert output.count("application-debug") == 1


def test_file_open_failure_retains_owned_console_and_allows_retry(tmp_path, capsys):
    console = sys.stderr
    game_logging.setup_logging(log_to_file=True)
    old_stream = logging.getLogger().handlers[-1].stream
    # A directory at the log path fails on Windows and POSIX without permission tricks.
    game_logging.setup_logging(log_to_file=False)
    path = tmp_path / "game.log"
    path.unlink()
    path.mkdir()

    with pytest.raises(OSError):
        game_logging.setup_logging(log_to_file=True)

    assert old_stream.closed
    handlers = logging.getLogger().handlers[:]
    assert len(handlers) == 1
    assert game_logging._application_handlers == handlers
    logging.getLogger("wormhole_logging_test").warning("console survives")
    assert capsys.readouterr().err.count("console survives") == 1
    assert not console.closed
    path.rmdir()
    game_logging.setup_logging(log_to_file=True)
    assert handlers[0]._closed
    logging.getLogger("wormhole_logging_test").info("file recovered")
    assert "file recovered" in path.read_text()


def test_flush_failure_still_closes_every_owned_handler(monkeypatch):
    game_logging.setup_logging(log_to_file=True)
    old_handlers = logging.getLogger().handlers[:]
    old_stream = old_handlers[-1].stream

    def fail_flush():
        raise OSError("flush failed")

    with monkeypatch.context() as patch:
        patch.setattr(old_handlers[-1], "flush", fail_flush)
        with pytest.raises(OSError, match="flush failed"):
            game_logging.setup_logging(log_to_file=False)

    assert old_stream.closed
    assert all(handler._closed for handler in old_handlers)
    assert not game_logging._application_handlers
    assert not logging.getLogger().handlers


@pytest.mark.parametrize("fields, expected", [
    ({"name": "Scout", "id": 0}, "Scout (id:0)"),
    ({"id": 42}, "Unit (id:42)"),
    ({"name": "Scout"}, "Scout (id:unknown)"),
    ({"name": None, "id": None}, "Unit (id:unknown)"),
])
def test_incomplete_unit_diagnostics_preserve_available_identity(fields, expected):
    assert game_logging.format_unit_for_log(SimpleNamespace(**fields)) == expected
    assert game_logging.format_unit_for_log(None) == "Unit (id:unknown)"


def test_file_and_console_identify_same_named_units_after_docking_and_rename(capsys, tmp_path):
    from constants import HullSize
    from tests.support.campaigns import campaign, ship
    from unit_components.hangar import HangarComponent
    from unit_naming import rename_unit

    game = campaign()
    carrier = ship(game, "Scout")
    craft = ship(game, "Scout", hull=HullSize.TINY)
    craft.id = 0  # Valid restored ID, not a missing identity.
    carrier.add_component(HangarComponent(carrier, max_slots=1))
    game_logging.setup_logging(log_to_file=True)
    capsys.readouterr()

    assert carrier.hangar_component.dock(craft, game.galaxy)
    assert game.galaxy.get_unit_by_id(craft.id) is None
    rename_unit(craft, "Renamed Scout")
    craft.take_damage(1)
    craft.destroy()

    console = capsys.readouterr().err
    contents = (tmp_path / "game.log").read_text()
    expected = [
        f"Unit Scout (id:0) docked into carrier Scout (id:{carrier.id}).",
        "Unit 'Renamed Scout (id:0)' takes 1 damage.",
        "Unit 'Renamed Scout (id:0)' has been destroyed.",
    ]
    for output in (console, contents):
        for message in expected:
            assert output.count(message) == 1
        assert "(id:0) (id:0)" not in output
    assert craft.name == "Renamed Scout"
    assert carrier.name == "Scout"
    assert game_logging.format_unit_for_log(craft) == "Renamed Scout (id:0)"


def test_context_action_logs_every_same_named_selected_unit(capsys, monkeypatch):
    from input_processor import context_actions
    from tests.support.campaigns import campaign, ship

    game = campaign()
    first, second = ship(game, "Scout"), ship(game, "Scout")
    game.selected_objects = [first, second]
    monkeypatch.setattr(context_actions, "_get_shift_pressed", lambda: False)
    game_logging.setup_logging()
    capsys.readouterr()

    context_actions.handle_context_menu_action(game, "unknown", None)

    output = capsys.readouterr().err
    assert f"Actors: ['Scout (id:{first.id})', 'Scout (id:{second.id})']" in output


@pytest.mark.parametrize("kind", ["unit", "planet"])
def test_selection_formats_units_without_changing_celestial_labels(kind, capsys, monkeypatch):
    from constants import PlanetType
    from domain.celestials import Planet
    from geometry import Position
    from input_processor import mouse_handler
    from sector_utils import sector_coords_to_pixels
    from tests.support.campaigns import campaign, ship

    game = campaign()
    selected = ship(game, "Scout") if kind == "unit" else Planet((0, 0), "Sol", PlanetType.TERRAN)
    selected.name = "Scout"
    game.sector_view_mouse_hover_object = selected
    game.sector_zoom, game.sector_pan_offset = 1.0, Position(0, 0)
    position = sector_coords_to_pixels(Position(0, 0), 1.0, game.sector_pan_offset,
                                       display_config=game.display_config)
    monkeypatch.setattr(mouse_handler, "_get_shift_pressed", lambda: False)
    game_logging.setup_logging()
    capsys.readouterr()

    mouse_handler.handle_mouse_click(game, None, 1, position)

    output = capsys.readouterr().err
    expected = f"Selected object: Unit Scout (id:{selected.id})" if kind == "unit" else "Selected object: Planet Scout"
    assert expected in output
    assert selected.name == "Scout"
    if kind == "planet":
        assert "(id:" not in output


@pytest.mark.parametrize("source_kind", ["unit", "planet"])
@pytest.mark.parametrize("destination_kind", ["unit", "planet"])
def test_intelligence_logs_distinguish_unit_and_planet_hosts(
    source_kind, destination_kind, capsys,
):
    from constants import PlanetType
    from domain.celestials import Planet
    from geometry import Position
    from tests.support.campaigns import campaign, ship
    from unit_components.enums import SabotageType
    from unit_components.intelligence import IntelligenceComponent
    from unit_orders.base import OrderStatus
    from unit_orders.intelligence import RelocateAgentOrder, SabotageOrder

    game = campaign()
    spy = ship(game, "Scout")
    spy.add_component(IntelligenceComponent(spy, agents_count=1))

    def host(kind):
        if kind == "unit":
            return ship(game, "Scout", owner=1)
        body = Planet((0, 0), "Sol", PlanetType.TERRAN)
        body.name, body.owner, body.position = "Scout", game.players[1], Position(100, 0)
        game.galaxy.systems['Sol'].add_celestial_body(body)
        return body

    source, destination = host(source_kind), host(destination_kind)
    game_logging.setup_logging()
    capsys.readouterr()
    agent = spy.intelligence_component.deploy_agent(source)
    assert agent is not None
    sabotage = SabotageType.SENSORS if source_kind == "unit" else SabotageType.GROWTH
    order = SabotageOrder(spy, {"agent_id": agent.id, "sabotage_type": sabotage.value})
    order.execute(game.galaxy)
    assert order.status == OrderStatus.COMPLETED
    relocation = RelocateAgentOrder(spy, {"agent_id": agent.id, "target_type": destination_kind,
                                          "destination_id": destination.id})
    relocation.execute(game.galaxy)
    assert relocation.status == OrderStatus.COMPLETED

    output = capsys.readouterr().err
    source_label = f"Scout (id:{source.id})" if source_kind == "unit" else "Scout"
    destination_label = f"Scout (id:{destination.id})" if destination_kind == "unit" else "Scout"
    assert f"Agent {agent.id} commenced sabotage {sabotage.name} on {source_label}." in output
    assert f"Agent {agent.id} successfully relocated from {source_label} to {destination_label}." in output
    assert f"[Scout (id:{spy.id})]" in output


def test_trade_order_includes_identity_in_embedded_component_message(capsys):
    from constants import PlanetType
    from domain.celestials import Planet
    from tests.support.campaigns import campaign, ship
    from unit_components.civilian_habitat import CivilianHabitatComponent
    from unit_components.trade import TradeComponent
    from unit_orders.base import OrderStatus
    from unit_orders.trade import TradeOrder

    game = campaign()
    trader, habitat = ship(game, "Scout"), ship(game, "Scout")
    trader.add_component(TradeComponent(trader))
    habitat.add_component(CivilianHabitatComponent(habitat))
    planet = Planet((0, 0), "Sol", PlanetType.TERRAN)
    planet.owner, planet.population = game.players[0], 50
    game.galaxy.systems['Sol'].add_celestial_body(planet)
    game_logging.setup_logging()
    capsys.readouterr()

    order = TradeOrder(trader, {"target_unit_id": habitat.id})
    order.execute(game.galaxy)

    assert order.status == OrderStatus.COMPLETED
    output = capsys.readouterr().err
    assert (
        f"[Scout (id:{trader.id})] TRADE order completed: "
        f"Trade route established at Scout (id:{habitat.id})"
    ) in output


def test_order_logs_keep_unit_and_order_identities_distinct(capsys):
    from tests.support.campaigns import campaign, ship
    from unit_orders.inhibitor import ToggleInhibitorOrder

    game = campaign()
    unit = ship(game, "Scout")
    unit.id = 0
    order = ToggleInhibitorOrder(unit, {"turn_on": True})
    game_logging.setup_logging()
    capsys.readouterr()

    order.execute(game.galaxy)

    output = capsys.readouterr().err
    assert f"[Scout (id:0)] ToggleInhibitorOrder.execute: TOGGLE_INHIBITOR (id:{order.local_order_id})" in output
    assert f"[Scout (id:0)] TOGGLE_INHIBITOR ({order.local_order_id}): FAILED" in output
    assert "(id:0) (id:" not in output

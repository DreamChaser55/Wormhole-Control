"""Human summaries stay brief without changing shared rules or terrain mechanics."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from celestial_descriptions import describe_body
from constants import FieldDensity, NebulaType, PlanetType, StarType, StormType
from domain.celestials import AsteroidField, DebrisField, IceField, Nebula, Planet, Star, Storm, Wormhole
from gui.sidebar.celestial_formatting import body_summary, catalyst_summary, rules_section_key
from gui.sidebar.panels_world import build_celestial_body_panel
from tests.support.campaigns import campaign, ship


def summary(body):
    return {row.text: row.tone for row in body_summary(body, describe_body(body))}


@pytest.mark.parametrize('cls', [AsteroidField, IceField, DebrisField])
@pytest.mark.parametrize('density,hull,speed,cover,damage', [
    (FieldDensity.LOW, 'Large', 85, 5, 1),
    (FieldDensity.MEDIUM, 'Medium', 75, 10, 2),
    (FieldDensity.HIGH, 'Small', 65, 15, 3),
])
def test_density_summaries_keep_access_speed_cover_and_abrasion(cls, density, hull, speed, cover, damage):
    rows = summary(cls((0, 0), 'Sol', density))
    assert rows[f'Density: {density.name.title()}'] == 'neutral'
    assert rows[f'Max hull: {hull}'] == 'restriction'
    assert rows[f'Sublight speed: {speed + (5 if cls is IceField else 0)}%'] == 'restriction'
    if cls is IceField:
        assert rows[f'Beam damage taken: −{cover}%'] == 'benefit'
        assert rows['Turret cooldown reset: −1 turn when firing'] == 'benefit'
    if cls is DebrisField:
        assert rows[f'Kinetic/missile damage taken: −{cover}%'] == 'benefit'
        assert rows['Wings: any density; no drag or abrasion'] == 'benefit'
        abrasion = next(text for text in rows if text.startswith('Abrasion:'))
        assert f'{damage} base hull damage / owner turn' in abrasion
        assert 'end inside after sublight movement at post-drag speed > 50' in abrasion
        assert rows[abrasion] == 'hazard'
    else:
        assert rows['Wings: any density; no drag'] == 'benefit'
    if cls is AsteroidField:
        assert rows['Hidden from long-range sensors; short-range detection still works'] == 'benefit'


@pytest.mark.parametrize('kind,expected,tone', [
    (NebulaType.HYDROGEN, 'Sublight propulsion AM: 50%', 'benefit'),
    (NebulaType.NITROGEN, 'Turret cooldown reset: −1 turn when firing', 'benefit'),
    (NebulaType.OXYGEN, 'Cluster Warhead splash taken: 1.15×', 'hazard'),
    (NebulaType.DUST, 'Short-range sensor radius: 70%', 'restriction'),
])
def test_nebula_summaries_keep_effect_and_concealment_distinctions(kind, expected, tone):
    rows = summary(Nebula((0, 0), 'Sol', kind))
    assert rows[expected] == tone
    assert rows['Hidden from long-range sensors; short-range detection still works'] == 'benefit'
    if kind == NebulaType.HYDROGEN:
        assert rows['AM harvesting: 0.4× base rate (Harvester required)'] == 'neutral'


@pytest.mark.parametrize('kind,expected', [
    (StormType.PLASMA, '8 base hull damage / owner turn (ships & deployables)'),
    (StormType.MAGNETIC, 'AM drain: up to 6 / owner turn'),
    (StormType.RADIATION, 'Radiation: 4 damage to one random surviving component / owner turn'),
])
def test_storm_summaries_preserve_targets_and_timing(kind, expected):
    rows = summary(Storm((0, 0), 'Sol', kind))
    assert rows[expected] == 'hazard'
    assert 'Hazards apply after movement.' in rows
    if kind == StormType.MAGNETIC:
        assert rows['Wings: entry and launch blocked'] == 'restriction'
        assert rows['Long-range sensors: disabled'] == 'restriction'
        assert 'Short-range sensors work; no radar concealment' in rows


@pytest.mark.parametrize('kind', list(StarType))
def test_star_summaries_keep_harvesting_neutral_and_hazard_geometry_separate(kind):
    body = Star('Sol', kind)
    rows = summary(body)
    assert rows[f'AM harvesting: {body.harvest_multiplier:g}× base rate (Harvester required)'] == 'neutral'
    assert rows[f'Collision radius: {body.collision_radius:g}'] == 'neutral'
    assert rows[f'Jump inhibition: {body.inhibition_field_radius:g}'] == 'neutral'
    if kind == StarType.BLACK_HOLE:
        assert rows['15 base hull damage / owner turn (ships & deployables); radius 750'] == 'hazard'
    if kind == StarType.PULSAR:
        assert rows['AM drain: 5% of current fuel / owner turn; whole sector'] == 'hazard'


@pytest.mark.parametrize('kind', list(PlanetType))
def test_planet_panels_keep_traits_and_full_rules_below_actions(kind):
    game = campaign()
    body = Planet((0, 0), 'Sol', kind)
    collapsed = build_celestial_body_panel(game, body)
    assert collapsed[-1]['action_id'] == 'toggle_celestial_rules'
    if kind == PlanetType.GAS_GIANT:
        rows = summary(body)
        assert rows['Atmospheric hiding: hidden from enemy sensors'] == 'benefit'
        assert rows['Entry: Tiny–Huge ships with working Engines; no wings or stations'] == 'restriction'
        assert rows['Submerged: no outside interaction; Leave must be first in queue'] == 'restriction'
        body.hidden_units.append(ship(game))
    else:
        assert any(row['text'].startswith('Population:') for row in collapsed)
        for resource in ('metal', 'crystal'):
            value = getattr(body, f'passive_{resource}')
            if value:
                assert any(row['text'] == f'Passive {resource}: +{value:g}/turn'
                           and row['object_id'] == '#sidebar_effect_benefit_label' for row in collapsed)
    expanded = build_celestial_body_panel(game, body, show_rules=True)
    toggle_index = next(i for i, row in enumerate(expanded) if row.get('action_id') == 'toggle_celestial_rules')
    assert all(row.get('type') == 'label' for row in expanded[toggle_index + 1:])
    assert all(rule in [row['text'] for row in expanded[toggle_index + 1:]] for rule in describe_body(body).rules)
    if kind == PlanetType.GAS_GIANT:
        assert any(row.get('action_id') == 'order_unit_leave_gas_giant' for row in expanded[:toggle_index])


def test_summary_values_follow_descriptor_and_body_balance(monkeypatch):
    import constants
    body = Nebula((0, 0), 'Sol', NebulaType.HYDROGEN)
    monkeypatch.setattr(constants, 'HYDROGEN_NEBULA_AM_BURN_MOD', .37)
    body.radius = 1234.5
    rows = summary(body)
    assert 'Sublight propulsion AM: 37%' in rows
    assert 'Effect radius: 1234.5' in rows
    wormhole = Wormhole((0, 0), 'Sol', 'Beta')
    assert f'Traversal: Advanced Hyperdrive; max hull {wormhole.diameter.name.title()}' in summary(wormhole)


@pytest.mark.parametrize('body', [DebrisField((0, 0), 'Sol', FieldDensity.HIGH),
                                 Nebula((0, 0), 'Sol', NebulaType.NITROGEN),
                                 Storm((0, 0), 'Sol', StormType.MAGNETIC)])
def test_complex_descriptions_are_at_least_half_shorter(body):
    description = describe_body(body)
    assert sum(len(row.text) for row in body_summary(body, description)) <= sum(map(len, description.rules)) / 2


@pytest.mark.parametrize('kind,phrase,tone', [
    (NebulaType.HYDROGEN, 'Owner’s allies: sublight propulsion AM 25%', 'benefit'),
    (NebulaType.NITROGEN, 'Owner’s allies: turret cooldown reset −2 turns when firing', 'benefit'),
    (NebulaType.OXYGEN, 'Owner’s enemies: Cluster Warhead splash taken 1.35×', 'hazard'),
    (NebulaType.DUST, 'Owner’s enemies: short-range sensor radius 50%', 'restriction'),
])
@pytest.mark.parametrize('owner_index', [0, 1])
def test_visible_catalyst_summaries_keep_owner_relative_recipients_and_full_rules(kind, phrase, tone, owner_index):
    from domain.deployables import CatalystPatch
    from game_ai.tactical import patch_views
    from geometry import Position
    game = campaign()
    ship(game)  # Make the enemy patch locally visible too.
    body = Nebula((0, 0), 'Sol', kind)
    game.galaxy.systems['Sol'].add_celestial_body(body)
    patch = CatalystPatch(game.players[owner_index], Position(100, 0), (0, 0), 'Sol', 1, body.id, 10)
    game.galaxy.systems['Sol'].hexes[(0, 0)].catalyst_patches.append(patch)
    views = patch_views(game, game.players[0])
    assert len(views) == 1
    view = views[0]
    rows = {row.text: row.tone for row in catalyst_summary(view, patch.owner.name)}
    assert rows[phrase] == tone
    assert f'Catalyst: {patch.owner.name}' in rows
    assert f'Patch radius: {patch.radius:g}; expires owner round {patch.expires_round}' in rows
    panel = build_celestial_body_panel(game, body)
    assert any(row['text'] == phrase and row['object_id'] == f'#sidebar_effect_{tone}_label' for row in panel)
    assert not any(rule in [row['text'] for row in panel] for rule in view['rules'])
    full = build_celestial_body_panel(game, body, show_rules=True)
    assert all(rule in [row['text'] for row in full] for rule in view['rules'])
    assert patch_views(game, game.players[0]) == views


def test_celestial_toggle_uses_campaign_and_body_identity_including_zero():
    from gui.dynamic_actions import build_button_payload
    from gui.sidebar.builder import build_sidebar_data
    from gui.sidebar.view import is_section_expanded, toggle_section_expansion
    game = campaign()
    body = Storm((0, 0), 'Sol', StormType.PLASMA)
    body.id = 0
    other = Storm((0, 0), 'Sol', StormType.PLASMA)
    other.name = body.name
    gui = SimpleNamespace(game_instance=game, expanded_sections={}, sidebar_scroll_identity='body',
                          side_bar_scroll_container=SimpleNamespace(get_container=lambda: SimpleNamespace(
                              get_relative_rect=lambda: SimpleNamespace(y=-120))))
    gui.is_section_expanded = lambda key: is_section_expanded(gui, key)
    gui.toggle_section_expansion = lambda key: toggle_section_expansion(gui, key)
    game.gui = gui
    game.selected_objects = [body]
    key = rules_section_key(game, body)
    assert build_sidebar_data(game)[-1]['text'] == '▶ Full rules'
    assert build_button_payload(gui, 'toggle_celestial_rules', 0) == {'action': 'ui_handled'}
    assert gui.sidebar_scroll_anchor == ('body', 120)
    assert gui.expanded_sections == {key: True}
    assert any(row['text'] == '▼ Full rules' for row in build_sidebar_data(game))
    game.selected_objects = [other]
    assert build_sidebar_data(game)[-1]['text'] == '▶ Full rules'
    build_button_payload(gui, 'toggle_celestial_rules', 0)  # Stale button cannot toggle another body.
    assert gui.expanded_sections == {key: True}
    game.selected_objects = [body]
    assert any(row['text'] == '▼ Full rules' for row in build_sidebar_data(game))
    game.campaign_id = 'different'
    assert build_sidebar_data(game)[-1]['text'] == '▶ Full rules'


def test_summary_palette_preserves_existing_label_typography():
    theme = json.loads((Path(__file__).resolve().parents[1] / 'theme.json').read_text())
    for tone, color in [('neutral', '#A0A0B0'), ('benefit', '#50E550'),
                        ('restriction', '#FFD700'), ('hazard', '#FF8080')]:
        style = theme[f'#sidebar_effect_{tone}_label']
        assert style['prototype'] == '#sidebar_info_label'
        assert style['colours']['normal_text'] == color


@pytest.mark.filterwarnings('error:Label Rect is too small:UserWarning')
@pytest.mark.parametrize('size', [(1280, 720), (2560, 1440)])
@pytest.mark.parametrize('faction_color', [(0, 0, 255), (255, 0, 0)])
def test_toggle_preserves_viewport_and_colors_at_display_scales(game_factory, tmp_path, size, faction_color):
    import pygame
    from pygame_gui.elements import UILabel
    from display_config import DisplayConfig
    from gui.dynamic_actions import build_button_payload
    game = game_factory(display_config=DisplayConfig(*size, fullscreen=False))
    assert game.start_new_game()
    gui = game.gui
    gui.update_player_turn_theme(pygame.Color(*faction_color))
    system = next(iter(game.galaxy.systems))
    body = DebrisField((0, 0), system, FieldDensity.HIGH)
    body.id = 0
    game.selected_objects = [body]

    def refresh():
        game.sidebar_needs_update = True
        game.update_side_bar_content()
        gui.manager.update(.1)

    def toggle_button():
        return next(button for button, action in gui.dynamic_button_actions.items()
                    if action['action_id'] == 'toggle_celestial_rules')

    def capture(name):
        game.screen.fill((5, 10, 20))
        gui.manager.draw_ui(game.screen)
        pygame.image.save(game.screen.subsurface(gui.side_bar_info_panel.get_abs_rect()), str(tmp_path / f'{name}.png'))

    refresh()
    scroll = gui.side_bar_scroll_container
    theme = json.loads((Path(__file__).resolve().parents[1] / 'theme.json').read_text())
    seen = set()
    for element in gui.side_bar_dynamic_elements:
        if not isinstance(element, UILabel):
            continue
        selector = next((part for part in element.object_ids if part and part.startswith('#sidebar_effect_')), None)
        if selector:
            seen.add(selector)
            assert element.text_colour == pygame.Color(theme[selector]['colours']['normal_text'])
            assert element.font.get_rect(element.text).width <= element.get_relative_rect().width
    assert len(seen) == 4
    capture('collapsed-top')
    scroll.vert_scroll_bar.set_scroll_from_start_percentage(1)
    gui.manager.update(.1)
    before_y = toggle_button().get_abs_rect().y
    before_offset = -scroll.get_container().get_relative_rect().y
    assert game.screen.get_rect().contains(toggle_button().get_abs_rect())
    capture('collapsed-bottom')
    build_button_payload(gui, 'toggle_celestial_rules', 0)
    refresh()
    assert toggle_button().text == '▼ Full rules'
    assert -scroll.get_container().get_relative_rect().y == pytest.approx(before_offset, abs=2)
    assert toggle_button().get_abs_rect().y == pytest.approx(before_y, abs=2)
    capture('expanded-toggle')
    refresh()  # Ordinary refresh retains the same scroll position too.
    assert toggle_button().get_abs_rect().y == pytest.approx(before_y, abs=2)
    scroll.vert_scroll_bar.set_scroll_from_start_percentage(1)
    gui.manager.update(.1)
    capture('expanded-bottom')
    # Collapse while scrolled deep into the explanation; the offset clamps.
    build_button_payload(gui, 'toggle_celestial_rules', 0)
    refresh()
    assert toggle_button().text == '▶ Full rules'
    assert game.screen.get_rect().contains(toggle_button().get_abs_rect())
    assert scroll.get_container().get_relative_rect().y <= 0
    build_button_payload(gui, 'toggle_celestial_rules', 0)
    refresh()
    other = DebrisField((0, 0), system, FieldDensity.HIGH)
    other.name = body.name
    game.selected_objects = [other]
    refresh()
    assert toggle_button().text == '▶ Full rules'
    assert scroll.vert_scroll_bar.start_percentage == 0
    game.selected_objects = [body]
    refresh()
    assert toggle_button().text == '▼ Full rules'
    assert scroll.vert_scroll_bar.start_percentage == 0

    # A real action-heavy panel overflows even when collapsed. Expansion must
    # preserve a nonzero offset, and Leave buttons must remain above the rules.
    giant = Planet((0, 0), system, PlanetType.GAS_GIANT)
    for index in range(16):
        hidden = ship(game, f'Submerged {index}', system=system)
        game.galaxy.systems[system].hexes[(0, 0)].units.remove(hidden)
        hidden.is_hidden_in_gas_giant = True
        giant.hidden_units.append(hidden)
    game.selected_objects = [giant]
    refresh()
    scroll.vert_scroll_bar.set_scroll_from_start_percentage(1)
    gui.manager.update(.1)
    old_offset = -scroll.get_container().get_relative_rect().y
    old_y = toggle_button().get_abs_rect().y
    assert old_offset > 0
    for expected in ('▼ Full rules', '▶ Full rules'):
        build_button_payload(gui, 'toggle_celestial_rules', giant.id)
        refresh()
        assert toggle_button().text == expected
        assert -scroll.get_container().get_relative_rect().y == pytest.approx(old_offset, abs=2)
        assert toggle_button().get_abs_rect().y == pytest.approx(old_y, abs=2)
        leave_buttons = [button for button, action in gui.dynamic_button_actions.items()
                         if action['action_id'] == 'order_unit_leave_gas_giant']
        assert len(leave_buttons) == 16
        assert game.screen.get_rect().contains(leave_buttons[-1].get_abs_rect())

"""Searchable construction catalog bound to a captured building context."""
from html import escape
import pygame
import pygame_gui
from pygame_gui import elements

from constants import HullSize
from events import ConstructEvent
from geometry import Position
from unit_catalog import CATEGORIES, describe_template
from unit_templates import UNIT_TEMPLATES


def catalog_entries(templates, *, search='', category='All roles', hull='All hulls',
                    kind='All units', affordable=False, credits=0):
    entries = [describe_template(key, raw) for key, raw in templates.items()]
    query = search.casefold().strip()
    return sorted((entry for entry in entries
                   if (category == 'All roles' or entry['category'] == category)
                   and (hull == 'All hulls' or entry['hull_size'] == hull)
                   and (kind == 'All units' or entry['kind'] == kind)
                   and (not affordable or entry['credit_cost'] <= credits)
                   and (not query or query in ' '.join([entry['name'], entry['template_name'],
                       entry['description'], *entry['roles'], *entry['abilities']]).casefold())),
                  key=lambda entry: (entry['category'], entry['credit_cost'], entry['name']))


def details_html(entry):
    def label(value):
        names = {'intelligence_agents_count': 'Agents', 'has_counter_intelligence': 'Counter-Intelligence',
                 'cloaking_type': 'Cloak', 'cloaking_radius': 'Area radius', 'max_mining_cargo': 'Cargo capacity',
                 'hyperdrive': 'Hyperdrive', 'jump_range': 'Jump range (hexes)'}
        return escape(names.get(value, str(value).replace('_', ' ').title()))
    def values(data):
        def display(value):
            if isinstance(value, bool):
                return 'Enabled' if value else 'Disabled'
            if value is None:
                return 'None'
            return escape(str(value))
        return ', '.join(f'{label(k)}: {display(v)}' for k, v in data.items()
                         if not (k == 'cloaking_radius' and not v))
    lines = [f"<b>{escape(entry['name'])}</b>", escape(entry['description']),
             f"{label(entry['hull_size'])} {entry['kind']} · {entry['credit_cost']} credits · {entry['turns']} turns",
             f"Hull: {entry['hull_used']:.2f}/{entry['hull_capacity']:g} · HP: {entry['hit_points']} · Upkeep: {entry['upkeep']:.2f}",
             '<b>Movement</b><br>' + values(entry['movement']),
             f"Fuel capacity: {entry['fuel_capacity']:g}",
             '<b>Sensors</b><br>' + values(entry['sensors']),
             '<b>Defenses</b><br>' + values(entry['defenses'])]
    if entry['weapons']:
        lines.append('<b>Weapons</b>')
        for weapon in entry['weapons']:
            lines.append(f"{label(weapon['type'])} ({label(weapon['variant'])}): "
                         f"{weapon['damage']:g} damage, {weapon['range']:g} range, {weapon['cooldown']} turns")
    if entry['abilities']:
        lines.append('<b>Abilities</b><br>' + ', '.join(label(a) for a in entry['abilities']))
    if entry['support']:
        lines.append('<b>Equipment</b>')
        for name, data in entry['support'].items():
            lines.append(label(name.removesuffix('_component')) + (': ' + values(data) if data else ''))
    if entry['kind'] == 'wing':
        lines.append('<b>Produced automatically in a strikecraft bay. Select production on the carrier.</b>')
    return '<br><br>'.join(lines)


class UnitCatalogWindow:
    def __init__(self, gui, units, position, queue=False):
        self.gui, self.game = gui, gui.game_instance
        self.galaxy = self.game.galaxy
        self.player = self.game.players[self.game.current_player_index]
        self.units = [u for u in units if u.owner == self.player and u.constructor_component]
        self.anchors = [(u.in_system, u.in_hex) for u in self.units]
        self.position = Position(position.x, position.y)
        self.queue = queue
        self.selected_key = None
        self.entries = {}
        self._stamp = None
        width, height = min(1000, int(gui.screen_res.x)-40), min(690, int(gui.screen_res.y)-40)
        self.window = elements.UIWindow(pygame.Rect((int(gui.screen_res.x)-width)//2,
            (int(gui.screen_res.y)-height)//2, width, height), gui.manager, window_display_title='Unit Catalog', resizable=False)
        self.window.set_blocking(True)
        panel = self.window.get_container()
        w, h = panel.get_size()
        self.search = elements.UITextEntryLine(pygame.Rect(10, 10, w-20, 30), gui.manager, container=panel,
                                             placeholder_text='Search designs, roles or abilities')
        col = (w-20)//4
        self.category = elements.UIDropDownMenu(['All roles', *CATEGORIES, 'Custom'], 'All roles', pygame.Rect(10, 48, col-5, 30), gui.manager, container=panel)
        self.hull = elements.UIDropDownMenu(['All hulls', *HullSize.__members__], 'All hulls', pygame.Rect(10+col, 48, col-5, 30), gui.manager, container=panel)
        self.kind = elements.UIDropDownMenu(['All units', 'ship', 'station', 'wing'], 'All units', pygame.Rect(10+col*2, 48, col-5, 30), gui.manager, container=panel)
        self.affordability = elements.UIDropDownMenu(['All prices', 'Affordable'], 'All prices', pygame.Rect(10+col*3, 48, col, 30), gui.manager, container=panel)
        left = int(w*.40)
        self.list = elements.UISelectionList(pygame.Rect(10, 90, left-15, h-150), [], gui.manager, container=panel)
        self.details = elements.UITextBox('Select a design to inspect its equipment.', pygame.Rect(left, 90, w-left-10, h-150), gui.manager, container=panel)
        self.queue_button = elements.UIButton(pygame.Rect(10, h-48, left-15, 34), self.queue_text(), gui.manager, container=panel)
        self.build_button = elements.UIButton(pygame.Rect(left, h-48, w-left-10, 34), 'Select a design', gui.manager, container=panel)
        self.refresh()

    def queue_text(self):
        return 'Queue after orders: ' + ('Yes' if self.queue else 'No')

    def valid_context(self):
        return (self.game.galaxy is self.galaxy and self.game.players[self.game.current_player_index] is self.player
                and bool(self.units) and all(self.galaxy.get_unit_by_id(u.id) is u and u.owner is self.player
                    and u.current_hit_points > 0 and u.constructor_component and not u.constructor_component.is_destroyed
                    and (u.in_system, u.in_hex) == anchor for u, anchor in zip(self.units, self.anchors)))

    def kill(self):
        self.window.kill()

    def update(self):
        if not self.window.alive():
            return
        if not self.valid_context():
            self.kill()
            return
        stamp = (self.player.credits, tuple((key, id(raw)) for key, raw in UNIT_TEMPLATES.items()))
        if stamp != self._stamp:
            self._stamp = stamp
            self.refresh()

    @staticmethod
    def choice(widget):
        value = widget.selected_option
        return value[0] if isinstance(value, tuple) else value

    def refresh(self):
        rows = catalog_entries(UNIT_TEMPLATES, search=self.search.get_text(), category=self.choice(self.category),
            hull=self.choice(self.hull), kind=self.choice(self.kind),
            affordable=self.choice(self.affordability) == 'Affordable', credits=self.player.credits)
        self.entries = {f"{entry['name']} ({entry['credit_cost']}c)": entry for entry in rows}
        self.list.set_item_list(list(self.entries))
        entry = next((e for e in rows if e['template_name'] == self.selected_key), None)
        self.show_entry(entry)

    def show_entry(self, entry):
        self.selected_key = entry['template_name'] if entry else None
        self.build_button.disable()
        self.build_button.set_text('Select a design')
        self.details.set_text(details_html(entry) if entry else 'Select a design to inspect its equipment.')
        if entry:
            buildable = entry['kind'] != 'wing' and self.valid_context() and all(u.constructor_component.can_build(self.selected_key) for u in self.units)
            affordable = self.player.credits >= entry['credit_cost'] * len(self.units)
            self.build_button.set_text('Build in strikecraft bay' if entry['kind'] == 'wing' else
                ('Queue construction' if self.queue else 'Build') + f" ({entry['credit_cost'] * len(self.units)}c)")
            if buildable and (self.queue or affordable):
                self.build_button.enable()

    def process_event(self, event):
        self.update()
        if not self.window.alive():
            return False
        if event.type == pygame_gui.UI_WINDOW_CLOSE and event.ui_element == self.window:
            self.kill()
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.kill()
        elif event.type in (pygame_gui.UI_TEXT_ENTRY_CHANGED, pygame_gui.UI_DROP_DOWN_MENU_CHANGED) and event.ui_element in (self.search, self.category, self.hull, self.kind, self.affordability):
            self.refresh()
        elif event.type == pygame_gui.UI_SELECTION_LIST_NEW_SELECTION and event.ui_element == self.list:
            self.show_entry(self.entries.get(event.text))
        elif event.type == pygame_gui.UI_BUTTON_PRESSED:
            if event.ui_element == self.queue_button:
                self.queue = not self.queue
                self.queue_button.set_text(self.queue_text())
                self.refresh()
            elif event.ui_element == self.build_button and self.build_button.is_enabled:
                self.refresh()
                if self.valid_context() and self.selected_key and self.build_button.is_enabled:
                    self.game.event_bus.publish(ConstructEvent(self.units, self.selected_key, self.position, self.queue))
                    self.kill()
        return True

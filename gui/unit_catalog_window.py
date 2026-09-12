"""Searchable construction catalog bound to a captured building context."""
from html import escape
import pygame
import pygame_gui
from pygame_gui import elements

from constants import HullSize
from display_config import display_config_for
from events import ConstructEvent
from geometry import Position
from unit_catalog import CATEGORIES, describe_template
from unit_templates import UNIT_TEMPLATES, get_all_templates_for_player


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
             f"Initial unit name: {escape(entry['default_unit_name'])}",
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
    def __init__(self, gui, units, position):
        self.gui, self.game = gui, gui.game_instance
        self.galaxy = self.game.galaxy
        self.player = self.game.players[self.game.current_player_index]
        self.units = [u for u in units if u.owner == self.player and u.constructor_component]
        self.anchors = [(u.in_system, u.in_hex) for u in self.units]
        self.position = Position(position.x, position.y)
        self.selected_key = None
        self._details_html = None
        self.entries = {}
        self._stamp = None
        width = max(100, int(gui.screen_res.x) - 40)
        height = int(gui.screen_res.y * .88)
        self.window = elements.UIWindow(pygame.Rect(20,
            int(gui.screen_res.y * .06), width, height), gui.manager, window_display_title='Unit Catalog', resizable=False)
        self.window.set_blocking(True)
        panel = self.window.get_container()
        w, h = panel.get_size()
        scale = display_config_for(gui).text_scale
        pad, gap = max(1, int(10 * scale)), max(1, int(8 * scale))
        control_h, action_h = max(1, int(30 * scale)), max(1, int(34 * scale))
        content_w = w - 2 * pad
        filter_y = pad + control_h + gap
        content_y = filter_y + control_h + gap
        action_y = h - pad - action_h
        content_h = action_y - gap - content_y
        left_w = int((content_w - gap) * .40)
        right_x = pad + left_w + gap
        right_w = w - pad - right_x
        self.search = elements.UITextEntryLine(pygame.Rect(pad, pad, content_w, control_h), gui.manager, container=panel,
                                             placeholder_text='Search designs, roles or abilities')
        col = (content_w - 3 * gap) // 4
        self.category = elements.UIDropDownMenu(['All roles', *CATEGORIES, 'Custom'], 'All roles', pygame.Rect(pad, filter_y, col, control_h), gui.manager, container=panel)
        self.hull = elements.UIDropDownMenu(['All hulls', *HullSize.__members__], 'All hulls', pygame.Rect(pad+col+gap, filter_y, col, control_h), gui.manager, container=panel)
        self.kind = elements.UIDropDownMenu(['All units', 'ship', 'station', 'wing'], 'All units', pygame.Rect(pad+(col+gap)*2, filter_y, col, control_h), gui.manager, container=panel)
        price_x = pad + (col + gap) * 3
        self.affordability = elements.UIDropDownMenu(['All prices', 'Affordable'], 'All prices', pygame.Rect(price_x, filter_y, w-pad-price_x, control_h), gui.manager, container=panel)
        self.list = elements.UISelectionList(pygame.Rect(pad, content_y, left_w, content_h), [], gui.manager, container=panel,
                                             object_id='#unit_catalog_list')
        self.details = elements.UITextBox('Select a design to inspect its equipment.', pygame.Rect(right_x, content_y, right_w, content_h), gui.manager, container=panel)
        build_w = int((left_w - gap) * .30)
        self.build_button = elements.UIButton(pygame.Rect(pad, action_y, build_w, action_h), 'Build', gui.manager, container=panel)
        self.queue_button = elements.UIButton(pygame.Rect(pad+build_w+gap, action_y, left_w-build_w-gap, action_h), 'Queue after existing orders', gui.manager, container=panel)
        self.price_label = elements.UILabel(pygame.Rect(right_x, action_y, right_w, action_h), 'Select a design', gui.manager, container=panel)
        self.refresh()

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
        templates = get_all_templates_for_player(self.player)
        stamp = (self.player.credits, tuple((key, id(raw)) for key, raw in templates.items()))
        if stamp != self._stamp:
            self._stamp = stamp
            self.refresh()

    @staticmethod
    def choice(widget):
        value = widget.selected_option
        return value[0] if isinstance(value, tuple) else value

    def refresh(self):
        templates = get_all_templates_for_player(self.player)
        rows = catalog_entries(templates, search=self.search.get_text(), category=self.choice(self.category),
            hull=self.choice(self.hull), kind=self.choice(self.kind),
            affordable=self.choice(self.affordability) == 'Affordable', credits=self.player.credits)
        entries = {f"{entry['name']} ({entry['credit_cost']}c)": entry for entry in rows}
        if list(entries) != list(self.entries):
            scroll = self.list.scroll_bar.start_percentage if self.list.scroll_bar else 0
            self.list.set_item_list(list(entries))
            if self.list.scroll_bar:
                self.list.scroll_bar.set_scroll_from_start_percentage(scroll)
        self.entries = entries
        entry = next((e for e in rows if e['template_name'] == self.selected_key), None)
        self.show_entry(entry)

    def show_entry(self, entry):
        previous_key = self.selected_key
        self.selected_key = entry['template_name'] if entry else None
        self.build_button.disable()
        self.queue_button.disable()
        self.price_label.set_text('Select a design')
        html = details_html(entry) if entry else 'Select a design to inspect its equipment.'
        if html != self._details_html:
            scroll = self.details.scroll_bar.start_percentage if self.details.scroll_bar else 0
            self.details.set_text(html)
            if previous_key == self.selected_key and self.details.scroll_bar:
                self.details.scroll_bar.set_scroll_from_start_percentage(scroll)
            self._details_html = html
        # SelectionList has no public selection setter; restore its item state after a rebuild.
        for item in self.list.item_list:
            selected = self.entries[item['text']]['template_name'] == self.selected_key
            item['selected'] = selected
            button = item['button_element']
            if button is not None:
                button.select() if selected else button.unselect()
        if entry:
            buildable = entry['kind'] != 'wing' and self.valid_context() and all(u.constructor_component.can_build(self.selected_key) for u in self.units)
            affordable = self.player.credits >= entry['credit_cost'] * len(self.units)
            self.price_label.set_text('Produced in a strikecraft bay' if entry['kind'] == 'wing' else
                f"Total: {entry['credit_cost'] * len(self.units)} credits "
                f"({len(self.units)} {'builder' if len(self.units) == 1 else 'builders'})")
            if buildable:
                self.queue_button.enable()
                if affordable:
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
            if event.ui_element in (self.build_button, self.queue_button):
                self.refresh()
                if self.valid_context() and self.selected_key and event.ui_element.is_enabled:
                    queue = event.ui_element == self.queue_button
                    self.game.event_bus.publish(ConstructEvent(self.units, self.selected_key, self.position, queue))
                    if queue:
                        self.update()
                    else:
                        self.kill()
        return True

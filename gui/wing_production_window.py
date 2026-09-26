"""Built-in strikecraft production selection for one owned carrier."""
from html import escape

import pygame
import pygame_gui
from pygame_gui import elements

from construction_customization import TURRET_TYPES, DEFENSE_TYPES, customize_template
from display_config import display_config_for
from unit_catalog import describe_template, wing_template_names
from resource_costs import ResourceCost, resource_balances
from unit_templates import UNIT_TEMPLATES
from .unit_catalog_window import details_html

TURRET_CHOICES = {'Template Default': None, **{value.replace('_', ' ').title(): value for value in TURRET_TYPES}}
DEFENSE_CHOICES = {'Template Default': None, **{value.replace('_', ' ').title(): value for value in DEFENSE_TYPES}}


def is_open(gui):
    dialog = getattr(gui, 'wing_production_window', None)
    return bool(dialog and dialog.window.alive() is True)


class WingProductionWindow:
    def __init__(self, gui, carrier, slot_index):
        self.gui, self.game, self.carrier = gui, gui.game_instance, carrier
        self.galaxy = self.game.galaxy
        self.player = self.game.players[self.game.current_player_index]
        self.turn = self.game.turn_number
        self.bay = carrier.strikecraft_bay_component
        self.bay.validate_slot_index(slot_index)
        self.slot_index = slot_index
        slot = self.bay.slots[slot_index]
        self.selected_key = slot['production_template_name']
        self.turret_type_override = slot['turret_type_override']
        self.defense_type_override = slot['defense_type_override']
        self.entries = {}
        self._stamp = None
        self._details_html = None
        scale = display_config_for(gui).text_scale
        width, height = int(gui.screen_res.x * .85), int(gui.screen_res.y * .85)
        self.window = elements.UIWindow(
            pygame.Rect((int(gui.screen_res.x)-width)//2, (int(gui.screen_res.y)-height)//2, width, height),
            gui.manager, window_display_title=f'Slot {slot_index + 1}: Select Wing Production', resizable=False)
        self.window.set_blocking(True)
        panel = self.window.get_container()
        w, h = panel.get_size()
        pad, row = max(8, int(10*scale)), max(30, int(36*scale))
        left_w = int((w-3*pad)*.38)
        right_x = 2*pad + left_w
        self.list = elements.UISelectionList(pygame.Rect(pad, pad, left_w, h-row-3*pad), [],
                                             gui.manager, container=panel, object_id='#unit_catalog_list')
        control_w = (w-right_x-2*pad)//2
        for x, label in ((right_x, 'Turret type'), (right_x+control_w+pad, 'Defense type')):
            elements.UILabel(pygame.Rect(x, pad, control_w, row), label, gui.manager, container=panel)
        self.turret_dropdown = elements.UIDropDownMenu(
            list(TURRET_CHOICES), next(label for label, value in TURRET_CHOICES.items()
                                       if value == self.turret_type_override),
            pygame.Rect(right_x, pad+row, control_w, row), gui.manager, container=panel)
        self.defense_dropdown = elements.UIDropDownMenu(
            list(DEFENSE_CHOICES), next(label for label, value in DEFENSE_CHOICES.items()
                                        if value == self.defense_type_override),
            pygame.Rect(right_x+control_w+pad, pad+row, control_w, row), gui.manager, container=panel)
        details_y = 2*pad+2*row
        self.details = elements.UITextBox('', pygame.Rect(right_x, details_y, w-right_x-pad, h-row-2*pad-details_y),
                                         gui.manager, container=panel)
        self.select_button = elements.UIButton(pygame.Rect(pad, h-row-pad, (w-3*pad)//2, row),
                                              'Select Production', gui.manager, container=panel)
        self.cancel_button = elements.UIButton(pygame.Rect(2*pad+(w-3*pad)//2, h-row-pad, (w-3*pad)//2, row),
                                              'Cancel', gui.manager, container=panel)
        self.refresh()

    def valid_context(self):
        return (self.game.galaxy is self.galaxy and self.game.turn_number == self.turn
                and self.game.players[self.game.current_player_index] is self.player
                and self.galaxy.get_unit_by_id(self.carrier.id) is self.carrier
                and self.carrier.owner is self.player and self.carrier.current_hit_points > 0
                and self.carrier.strikecraft_bay_component is self.bay
                and self.slot_index < self.bay.max_slots
                and self.bay.production_blocker(self.slot_index) is None)

    def close(self):
        self.window.kill()
        if getattr(self.gui, 'wing_production_window', None) is self:
            self.gui.wing_production_window = None

    def update(self):
        if not self.window.alive():
            return
        if not self.valid_context():
            self.close()
            return
        stamp = (resource_balances(self.player), tuple((key, id(UNIT_TEMPLATES[key])) for key in wing_template_names()))
        if stamp != self._stamp:
            self._stamp = stamp
            self.refresh()

    def refresh(self):
        self.entries = {key: describe_template(key, UNIT_TEMPLATES[key]) for key in wing_template_names()}
        self.labels = {f"{entry['name']} ({entry['credit_cost']} credits)": key
                       for key, entry in self.entries.items()}
        self.labels = {'No production': None, **self.labels}
        self.list.set_item_list(list(self.labels))
        self.show_selection()

    def show_selection(self):
        entry = self.entries.get(self.selected_key)
        self.select_button.disable()
        html = 'Select a wing design.'
        if self.selected_key is None:
            html = ('No production: this slot will build no new wings. Applying clears its design and equipment overrides; '
                    'any existing wing remains and can still be replenished. The bay-wide pause setting is preserved.')
            if self.valid_context():
                self.select_button.enable()
        if entry:
            try:
                template = customize_template(UNIT_TEMPLATES[self.selected_key],
                                              self.turret_type_override, self.defense_type_override)
                entry = describe_template(self.selected_key, template)
            except ValueError as error:
                html = escape(str(error))
            else:
                html = (f"<b>Combat role: {escape(entry['wing_type'].title())}</b><br><br>"
                        'Turret type applies to all turrets. Defense type combines total defense strength '
                        'into the chosen type. Template Default uses the selected design\'s presets.<br><br>'
                        + details_html(entry)
                        + '<br><br>Selection is free and applies to future builds. '
                          'Types change; statistics, variants, costs and build time stay the same. '
                          'The bay pays when construction starts; existing wings are unchanged.')
                cost = ResourceCost.from_dict(entry['resource_cost'])
                if not cost.affordable(self.player):
                    html += f'<br><br>Waiting for resources before production can start. Missing: {cost.shortfall(self.player).describe()}.'
                if self.valid_context() and self.bay.can_set_production(
                        self.slot_index, self.selected_key, self.turret_type_override, self.defense_type_override):
                    self.select_button.enable()
        if html != self._details_html:
            self._details_html = html
            self.details.set_text(html)
        # Match the existing catalogue's selection restoration after list rebuilds.
        for item in self.list.item_list:
            selected = self.labels[item['text']] == self.selected_key
            item['selected'] = selected
            button = item['button_element']
            if button is not None:
                button.select() if selected else button.unselect()

    def process_event(self, event):
        self.update()
        if not self.window.alive():
            return
        if (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE
                or event.type == pygame_gui.UI_WINDOW_CLOSE and event.ui_element == self.window):
            self.close()
        elif event.type == pygame_gui.UI_SELECTION_LIST_NEW_SELECTION and event.ui_element == self.list:
            self.selected_key = self.labels.get(event.text)
            self.show_selection()
        elif event.type == pygame_gui.UI_DROP_DOWN_MENU_CHANGED:
            if event.ui_element == self.turret_dropdown:
                self.turret_type_override = TURRET_CHOICES[event.text]
                self.show_selection()
            elif event.ui_element == self.defense_dropdown:
                self.defense_type_override = DEFENSE_CHOICES[event.text]
                self.show_selection()
        elif event.type == pygame_gui.UI_BUTTON_PRESSED:
            if event.ui_element == self.cancel_button:
                self.close()
            elif event.ui_element == self.select_button and self.select_button.is_enabled:
                from game_ai.commands import CommandGateway
                from game_ai.contracts import Command, CommandBatch
                result = CommandGateway(self.game).apply_batch(self.player, CommandBatch((
                    Command('set_wing_production', (self.carrier.id,), slot_index=self.slot_index, template_name=self.selected_key,
                            turret_type_override=self.turret_type_override if self.selected_key is not None else None,
                            defense_type_override=self.defense_type_override if self.selected_key is not None else None, queue=False),)))
                if result.accepted:
                    self.close()
                else:
                    self._details_html = '<br>'.join(escape(error.message) for error in result.errors)
                    self.details.set_text(self._details_html)

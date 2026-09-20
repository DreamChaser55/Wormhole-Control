"""Built-in strikecraft production selection for one owned carrier."""
from html import escape

import pygame
import pygame_gui
from pygame_gui import elements

from display_config import display_config_for
from unit_catalog import describe_template, wing_template_names
from unit_templates import UNIT_TEMPLATES
from .unit_catalog_window import details_html


def is_open(gui):
    dialog = getattr(gui, 'wing_production_window', None)
    return bool(dialog and dialog.window.alive() is True)


class WingProductionWindow:
    def __init__(self, gui, carrier):
        self.gui, self.game, self.carrier = gui, gui.game_instance, carrier
        self.galaxy = self.game.galaxy
        self.player = self.game.players[self.game.current_player_index]
        self.turn = self.game.turn_number
        self.bay = carrier.strikecraft_bay_component
        self.selected_key = self.bay.production_template_name
        self.entries = {}
        self._stamp = None
        self._details_html = None
        scale = display_config_for(gui).text_scale
        width, height = int(gui.screen_res.x * .85), int(gui.screen_res.y * .85)
        self.window = elements.UIWindow(
            pygame.Rect((int(gui.screen_res.x)-width)//2, (int(gui.screen_res.y)-height)//2, width, height),
            gui.manager, window_display_title='Select Wing Production', resizable=False)
        self.window.set_blocking(True)
        panel = self.window.get_container()
        w, h = panel.get_size()
        pad, row = max(8, int(10*scale)), max(30, int(36*scale))
        left_w = int((w-3*pad)*.38)
        right_x = 2*pad + left_w
        self.list = elements.UISelectionList(pygame.Rect(pad, pad, left_w, h-row-3*pad), [],
                                             gui.manager, container=panel, object_id='#unit_catalog_list')
        self.details = elements.UITextBox('', pygame.Rect(right_x, pad, w-right_x-pad, h-row-3*pad),
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
                and not self.bay.is_destroyed and not self.bay.constructing)

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
        stamp = tuple((key, id(UNIT_TEMPLATES[key])) for key in wing_template_names())
        if stamp != self._stamp:
            self._stamp = stamp
            self.refresh()

    def refresh(self):
        self.entries = {key: describe_template(key, UNIT_TEMPLATES[key]) for key in wing_template_names()}
        self.labels = {f"{entry['name']} ({entry['credit_cost']} credits)": key
                       for key, entry in self.entries.items()}
        self.list.set_item_list(list(self.labels))
        self.show_selection()

    def show_selection(self):
        entry = self.entries.get(self.selected_key)
        self.select_button.disable()
        html = 'Select a wing design.'
        if entry:
            html = (f"<b>Combat role: {escape(entry['wing_type'].title())}</b><br><br>"
                    + details_html(entry)
                    + '<br><br>Selection is free and applies template presets to future builds. '
                      'The bay pays when construction starts; existing wings are unchanged.')
            if self.valid_context() and self.bay.can_set_production(self.selected_key):
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
        elif event.type == pygame_gui.UI_BUTTON_PRESSED:
            if event.ui_element == self.cancel_button:
                self.close()
            elif event.ui_element == self.select_button and self.selected_key:
                from game_ai.commands import CommandGateway
                from game_ai.contracts import Command, CommandBatch
                result = CommandGateway(self.game).apply_batch(self.player, CommandBatch((
                    Command('set_wing_production', (self.carrier.id,), template_name=self.selected_key),)))
                if result.accepted:
                    self.close()
                else:
                    self.details.set_text('<br>'.join(escape(error.message) for error in result.errors))

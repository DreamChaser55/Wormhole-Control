"""Troop amount and assault preview modal, committing through the shared gateway."""
from html import escape

import pygame
import pygame_gui
from pygame_gui.elements import UIWindow, UILabel, UITextBox, UITextEntryLine, UIButton

from display_config import display_config_for
from planetary_warfare import assault_preview, blocker, command_options, exact_body


def is_open(gui):
    dialog = getattr(gui, 'planetary_window', None)
    return bool(dialog and dialog.window.alive() is True)


class PlanetaryWindow:
    def __init__(self, gui, unit, body, kind, queue=False):
        self.gui, self.game, self.unit = gui, gui.game_instance, unit
        self.body_id, self.kind, self.queue = body.id, kind, queue
        screen = gui.manager.get_root_container().get_rect()
        scale = display_config_for(gui).text_scale
        width, height = min(screen.width - 24, round(630 * scale)), min(screen.height - 24, round(430 * scale))
        self.window = UIWindow(pygame.Rect((screen.width-width)//2, (screen.height-height)//2, width, height),
                               gui.manager, window_display_title='Recruit troops' if kind == 'recruit_troops' else 'Invade colony')
        self.window.set_blocking(True)
        w, h = self.window.get_container().get_size()
        pad, row = round(14 * scale), round(34 * scale)
        UILabel(pygame.Rect(pad, pad, w-2*pad, row), f'{unit.name} → {body.name}', gui.manager, container=self.window)
        self.amount = UITextEntryLine(pygame.Rect(pad, pad+row+6, w-2*pad, row), gui.manager, container=self.window)
        choices = command_options(self.game, unit.owner, unit, [body])[kind]['targets']
        self.amount.set_text(str(max(1, choices[0]['max_amount'] if choices else unit.troop_transport_component.troops)))
        self.preview = UITextBox('', pygame.Rect(pad, pad+2*row+12, w-2*pad, h-4*row-3*pad-18), gui.manager, container=self.window)
        button_y = h-row-pad
        button_width = (w-4*pad)//3
        self.submit = UIButton(pygame.Rect(pad, button_y, button_width, row), 'Queue' if queue else 'Issue order', gui.manager, container=self.window)
        self.append = UIButton(pygame.Rect(2*pad+button_width, button_y, button_width, row), 'Queue order', gui.manager, container=self.window)
        if queue:
            self.append.hide()
        self.cancel = UIButton(pygame.Rect(3*pad+2*button_width, button_y, button_width, row), 'Cancel', gui.manager, container=self.window)
        self.refresh()

    def refresh(self):
        body = exact_body(self.game, self.unit.owner, self.body_id)
        try:
            amount = int(self.amount.get_text())
            if amount <= 0:
                raise ValueError
        except ValueError:
            self.preview.set_text('Enter a positive whole troop count.')
            self.submit.disable()
            self.append.disable()
            return
        if body is None:
            self.preview.set_text('Colony unavailable.')
            self.submit.disable()
            self.append.disable()
            return
        error = blocker(self.game, self.unit.owner, self.kind, body, self.unit, amount)
        if self.kind == 'recruit_troops':
            from planetary_balance import TROOP_CREDIT_COST, TROOP_POPULATION_COST
            text = f'Recruit {amount} troops for {amount*TROOP_CREDIT_COST:g} credits and {amount*TROOP_POPULATION_COST:g} population.<br>At least one population must remain.'
        else:
            preview = assault_preview(body, amount)
            text = (f'Success chance: <b>{preview["success_probability"]:.1%}</b><br>'
                    f'Losses on success: {preview["success_casualties"]} troops; on defeat: {preview["defeat_casualties"]}.<br>'
                    f'Antimatter: {preview["antimatter_cost"]:g}. Survivors return aboard.<br>'
                    'Odds are recomputed at arrival; defenses may change. Hostile ships do not block landing.')
        from planetary_balance import INVASION_RANGE
        text += f'<br><br>Approaches within {INVASION_RANGE:g} of the surface; resolves at End Turn. One planetary action per ship per round.'
        if error:
            text += '<br><br>Currently unavailable: ' + escape(error.replace('_', ' ')) + '. Queued recruitment may supply missing troops.'
        self.preview.set_text(text)
        self.submit.enable()
        self.append.enable()

    def close(self):
        self.window.kill()
        self.gui.planetary_window = None

    def process_event(self, event):
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.close()
        elif event.type == pygame_gui.UI_WINDOW_CLOSE and event.ui_element == self.window:
            self.close()
        elif event.type == pygame_gui.UI_TEXT_ENTRY_CHANGED and event.ui_element == self.amount:
            self.refresh()
        elif event.type == pygame_gui.UI_BUTTON_PRESSED:
            if event.ui_element == self.cancel:
                self.close()
            elif event.ui_element in (self.submit, self.append):
                from game_ai.commands import CommandGateway
                from game_ai.contracts import Command, CommandBatch
                try:
                    amount = int(self.amount.get_text())
                    command = Command.from_dict(dict(type=self.kind, unit_ids=[self.unit.id], target_id=self.body_id,
                                                     amount=amount, queue=self.queue or event.ui_element == self.append))
                except ValueError:
                    self.refresh()
                    return
                result = CommandGateway(self.game).apply_batch(self.game.players[self.game.current_player_index], CommandBatch((command,)))
                if result.accepted:
                    self.close()
                else:
                    self.preview.set_text('<br>'.join(escape(e.message) for e in result.errors))

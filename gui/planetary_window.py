"""Choose colonists or troops and preview the mission before issuing an order."""
from html import escape
import math

import pygame
import pygame_gui
from pygame_gui.elements import UIWindow, UILabel, UITextBox, UITextEntryLine, UIButton

from display_config import display_config_for
from planetary_warfare import assault_preview, blocker, command_options, exact_body
from planetary_intel import current_ownership
from unit_components.colony import exportable_population, loading_reserve


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
                               gui.manager, window_display_title={
                                   'recruit_troops': 'Recruit troops',
                                   'invade_planet': 'Invade colony',
                                   'load_colonists': 'Load Colonists',
                               }[kind])
        self.window.set_blocking(True)
        w, h = self.window.get_container().get_size()
        pad, row = round(14 * scale), round(34 * scale)
        UILabel(pygame.Rect(pad, pad, w-2*pad, row), f'{unit.name} → {body.name}', gui.manager, container=self.window)
        self.amount = UITextEntryLine(pygame.Rect(pad, pad+row+6, w-2*pad, row), gui.manager, container=self.window)
        if kind == 'load_colonists':
            maximum = self._load_limit(body)
            self.amount.set_text(f'{min(25, maximum):g}' if maximum > 0 else '')
        else:
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

    def _load_limit(self, body):
        colony = self.unit.colony_component
        remaining = max(0, colony.max_cargo - colony.population_cargo)
        if current_ownership(self.game.galaxy, self.unit.owner, body):
            return min(remaining, exportable_population(body))
        return remaining

    def _read_amount(self):
        amount = float(self.amount.get_text()) if self.kind == 'load_colonists' else int(self.amount.get_text())
        if not math.isfinite(amount) or amount <= 0:
            raise ValueError
        return amount

    def refresh(self):
        if self.game.players[self.game.current_player_index] != self.unit.owner:
            self.close()
            return
        body = exact_body(self.game, self.unit.owner, self.body_id)
        try:
            amount = self._read_amount()
        except ValueError:
            self.preview.set_text('Enter a positive population amount.' if self.kind == 'load_colonists'
                                  else 'Enter a positive whole troop count.')
            self.submit.disable()
            self.append.disable()
            return
        if body is None:
            self.preview.set_text('Colony unavailable.')
            self.submit.disable()
            self.append.disable()
            return
        if self.kind == 'load_colonists':
            limit = self._load_limit(body)
            confirmed = current_ownership(self.game.galaxy, self.unit.owner, body)
            text = (f'Load {amount:g} colonists. Available now: {limit:g}.<br>'
                    f'The colony retains at least {loading_reserve(body):g} population.' if confirmed else
                    f'Load {amount:g} colonists. Available cargo space: {limit:g}.<br>'
                    'The ship will wait for current sensor contact before checking how many colonists can depart.')
            if amount > limit:
                text += '<br>Enter a smaller amount.'
                self.submit.disable()
                self.append.disable()
            else:
                self.submit.enable()
                self.append.enable()
            self.preview.set_text(text)
            return
        error = blocker(self.game, self.unit.owner, self.kind, body, self.unit, amount)
        if self.kind == 'recruit_troops':
            from planetary_balance import TROOP_CREDIT_COST, TROOP_POPULATION_COST
            text = f'Recruit {amount} troops for {amount*TROOP_CREDIT_COST:g} credits and {amount*TROOP_POPULATION_COST:g} population.<br>At least one population must remain.'
        else:
            current = current_ownership(self.game.galaxy, self.unit.owner, body)
            preview = assault_preview(body if current else None, amount)
            odds = f'<b>{preview["success_probability"]:.1%}</b>' if current else 'Unknown until sensor contact returns'
            text = (f'Success chance: {odds}<br>'
                    f'Losses on success: {preview["success_casualties"]} troops; on defeat: {preview["defeat_casualties"]}.<br>'
                    f'Antimatter: {preview["antimatter_cost"]:g}. Survivors return aboard.<br>'
                    'Odds are recomputed at arrival; defenses may change. Hostile ships do not block landing.')
        from planetary_balance import INVASION_RANGE
        text += f'<br><br>Approaches within {INVASION_RANGE:g} of the surface; resolves at End Turn. One planetary action per ship per round.'
        from planetary_intel import ownership_view
        view = ownership_view(self.game, self.unit.owner, body)
        if view.status == 'last_known':
            text += (f'<br>Last observed: turn {view.observed_turn}. Orders wait at action range for sensor contact.'
                     ' Population and defenses require current contact.')
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
                    amount = self._read_amount()
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

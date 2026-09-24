"""Human dismantling preview using the same evaluator and gateway as AI."""
from html import escape
import pygame
import pygame_gui
from pygame_gui.elements import UIWindow, UITextBox, UIButton
from display_config import display_config_for
from campaign_graph import find_unit
from dismantling import evaluate
from gui.theme_loader import preload_rich_text_fonts


def is_open(gui):
    dialog = getattr(gui, 'dismantling_window', None)
    return bool(dialog and dialog.window.alive() is True)


class DismantlingWindow:
    def __init__(self, gui, unit, target, queue=False):
        preload_rich_text_fonts(gui.manager)
        self.gui, self.game, self.unit = gui, gui.game_instance, unit
        self.target_id, self.queue = target.id, queue
        screen = gui.manager.get_root_container().get_rect()
        scale = display_config_for(gui).text_scale
        width, height = min(screen.width - 24, round(660 * scale)), min(screen.height - 24, round(470 * scale))
        self.window = UIWindow(pygame.Rect((screen.width-width)//2, (screen.height-height)//2, width, height),
                               gui.manager, window_display_title='Dismantle unit')
        self.window.set_blocking(True)
        w, h = self.window.get_container().get_size()
        pad, row = round(14 * scale), round(34 * scale)
        self.preview = UITextBox('', pygame.Rect(pad, pad, w-2*pad, h-row-3*pad), gui.manager, container=self.window)
        bw = (w-4*pad)//3
        self.submit = UIButton(pygame.Rect(pad, h-row-pad, bw, row), 'Dismantle', gui.manager, container=self.window)
        self.append = UIButton(pygame.Rect(2*pad+bw, h-row-pad, bw, row), 'Queue', gui.manager, container=self.window)
        self.cancel = UIButton(pygame.Rect(3*pad+2*bw, h-row-pad, bw, row), 'Cancel', gui.manager, container=self.window)
        self.refresh()

    def refresh(self):
        preview = evaluate(self.unit, find_unit(self.game.galaxy, self.target_id), self.game.galaxy)
        lines = [f'<b>{escape(self.unit.name)}</b> will dismantle:']
        for member in preview.members:
            lines.append(f"{escape(member['name'])}: {member['turns']} turns, approximately {member['estimated_refund']:.2f} credits")
            if member['cargo_lost']:
                labels = {'current_amount': 'Antimatter', 'raw_metal_cargo': 'Raw metal',
                          'raw_crystal_cargo': 'Raw crystal', 'population_cargo': 'Colonists', 'troops': 'Troops'}
                cargo = ', '.join(f'{escape(labels.get(k, k))}: {v:g}' for k, v in member['cargo_lost'].items())
                lines.append('Discarded cargo: ' + cargo)
        lines.append(f'<br>Total: {preview.duration} owner turns; estimated return {preview.refund:.2f} credits.')
        if preview.waiting:
            lines.append('Waiting for paid bay work to finish. Newly completed docked wings will be included.')
        lines.append('<br>Targets go offline when work begins. All docked craft at that time are included. '
                     'Damage before completion reduces the payout. Cancellation returns no salvage. '
                     'New wing construction remains paused until explicitly resumed.')
        if preview.blocker:
            lines.append('<br>Unavailable: ' + escape(preview.blocker.replace('_', ' ')))
        for button in (self.submit, self.append):
            button.disable() if preview.blocker else button.enable()
        self.preview.set_text('<br>'.join(lines))

    def close(self):
        self.window.kill()
        self.gui.dismantling_window = None

    def process_event(self, event):
        if ((event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE)
                or (event.type == pygame_gui.UI_WINDOW_CLOSE and event.ui_element == self.window)):
            self.close()
        elif event.type == pygame_gui.UI_BUTTON_PRESSED:
            if event.ui_element == self.cancel:
                self.close()
            elif event.ui_element in (self.submit, self.append):
                from game_ai.commands import CommandGateway
                from game_ai.contracts import Command, CommandBatch
                command = Command('dismantle_unit', (self.unit.id,), target_id=self.target_id,
                                  queue=self.queue or event.ui_element == self.append)
                result = CommandGateway(self.game).apply_batch(self.game.players[self.game.current_player_index], CommandBatch((command,)))
                if result.accepted:
                    self.close()
                else:
                    self.preview.set_text('<br>'.join(escape(e.message) for e in result.errors))

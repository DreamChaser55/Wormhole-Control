"""Human presentation of the same frozen briefing used by automated players."""
from html import escape
from typing import Any

import pygame
import pygame_gui

from player_controller import PlayerController
from turn_briefing import BriefingState, entry_text
from app_preferences import AppPreferences, TurnSummaryMode


def is_open(gui):
    window = getattr(gui, "turn_briefing_window", None)
    return isinstance(window, TurnBriefingWindow) and window.window.alive()


def close_briefing(gui: Any, *, acknowledge: bool = False) -> None:
    dialog = getattr(gui, "turn_briefing_window", None)
    if isinstance(dialog, TurnBriefingWindow):
        if acknowledge:
            dialog.player.briefing.acknowledged = True
        dialog.window.kill()
    gui.turn_briefing_window = None


def show_briefing(gui: Any, player: Any, *, automatic: bool = True) -> None:
    state = getattr(player, "briefing", None)
    if player is None or player.controller != PlayerController.HUMAN or not isinstance(state, BriefingState):
        return
    if automatic:
        mode = getattr(gui.game_instance, "preferences", AppPreferences()).turn_summary_mode
        if state.acknowledged or mode == TurnSummaryMode.NEVER:
            return
        if mode == TurnSummaryMode.AUTOMATIC and not (state.current.entries or state.current.omitted_count):
            return
    if is_open(gui) and gui.turn_briefing_window.player is player:
        return
    close_briefing(gui)
    gui.hide_ingame_menu()
    gui.game_instance.is_dragging_camera = False
    gui.game_instance.is_dragging_selection_box = False
    gui.turn_briefing_window = TurnBriefingWindow(gui, player)


def summary_html(summary):
    lines = [f"Since End Turn {summary.from_turn}" if summary.from_turn else "Since campaign start"]
    last_category = None
    for entry in summary.entries:
        if entry.category != last_category:
            lines.append(f"<b>{escape(entry.category.title())}</b>")
            last_category = entry.category
        lines.append(escape(entry_text(entry)))
    if not summary.entries:
        lines.append("No important events.")
    if summary.omitted_count:
        lines.append(f"{summary.omitted_count} additional events omitted by the retention limit.")
    lines.append("<b>Economy — net change</b>")
    lines.extend(f"{key.title()}: {value:+g}" for key, value in summary.economy)
    return "<br><br>".join(lines)


class TurnBriefingWindow:
    def __init__(self, gui, player):
        self.gui, self.player = gui, player
        width = min(int(gui.screen_res.x) - 24, int(780 * gui.scale_x))
        height = min(int(gui.screen_res.y) - 24, int(580 * gui.scale_y))
        self.window = pygame_gui.elements.UIWindow(
            pygame.Rect((gui.screen_res.x - width) // 2, (gui.screen_res.y - height) // 2, width, height),
            manager=gui.manager, window_display_title=f"Turn {player.briefing.current.to_turn} — {player.name} briefing",
            object_id="#turn_briefing_window", resizable=False)
        self.window.set_blocking(True)
        content_width, content_height = self.window.get_container().get_size()
        pad = max(8, int(14 * gui.scale_x))
        button_height = max(28, int(38 * gui.scale_y))
        self.text = pygame_gui.elements.UITextBox(
            html_text=summary_html(player.briefing.current),
            relative_rect=pygame.Rect(pad, pad, content_width - 2 * pad, content_height - button_height - 3 * pad),
            manager=gui.manager, container=self.window, object_id="#turn_briefing_text")
        button_width = max(100, int(155 * gui.scale_x))
        self.continue_button = pygame_gui.elements.UIButton(
            pygame.Rect(content_width - button_width - pad, content_height - button_height - pad, button_width, button_height),
            "Continue", manager=gui.manager, container=self.window)
        self.comms_button = pygame_gui.elements.UIButton(
            pygame.Rect(pad, content_height - button_height - pad, button_width, button_height),
            "Open Comms", manager=gui.manager, container=self.window)

    def owns(self, element):
        while element is not None:
            if element is self.window:
                return True
            if not hasattr(element, "get_container"):
                return False
            parent = element.get_container()
            if parent is element:
                return False
            element = parent
        return False

    def process_event(self, event):
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            close_briefing(self.gui, acknowledge=True)
            return
        element = getattr(event, "ui_element", None)
        if event.type == pygame_gui.UI_WINDOW_CLOSE and element is self.window:
            close_briefing(self.gui, acknowledge=True)
            return
        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            if element is self.continue_button or element is self.window.close_window_button:
                close_briefing(self.gui, acknowledge=True)
                return
            if element is self.comms_button:
                close_briefing(self.gui, acknowledge=True)
                self.gui.open_communications_window()
                return
        # Filter queued background widget events before UIManager sees them.
        if element is not None and not self.owns(element):
            return
        if event.type in (pygame.TEXTINPUT, pygame.TEXTEDITING):
            return
        self.gui.manager.process_events(event)

"""Private automated-turn dashboard, rendered solely from allowlisted progress."""

from __future__ import annotations

import math
from time import perf_counter

import pygame

from display_config import display_config_for
from game_ai.progress import AITurnProgress, TURN_PHASES
from game_ai.runtime import get_runtime_config
from player_controller import PlayerController
from utils import resource_path


INK = (213, 228, 239)
MUTED = (130, 156, 175)
DIM = (66, 87, 105)
CYAN = (100, 203, 230)
GREEN = (111, 220, 167)
AMBER = (240, 193, 104)
RED = (244, 133, 137)

METRICS = (
    ("input_tokens", "INPUT TOKENS"), ("output_tokens", "OUTPUT TOKENS"),
    ("total_tokens", "TOTAL TOKENS"), ("cached_input_tokens", "CACHED INPUT"),
    ("uncached_input_tokens", "UNCACHED INPUT"), ("reasoning_tokens", "REASONING OUTPUT"),
)
ATTEMPT_OUTCOMES = {
    "accepted": "Accepted", "rejected": "Revise", "invalid_output": "Invalid output",
    "failed": "Failed", "commit_failed": "Commit error",
}


def duration(seconds: float) -> str:
    seconds = max(0.0, seconds)
    return f"{int(seconds // 60)}m {seconds % 60:04.1f}s" if seconds >= 60 else f"{seconds:.1f}s"


def token_count(value: int | None) -> str:
    return "—" if value is None else f"{value:,}"


class AITurnRenderer:
    """Fixed logical layout scales to DisplayConfig; fonts and backdrop are cached."""

    def __init__(self, game):
        self.game = game
        self.screen = game.screen
        config = display_config_for(game)
        self.scale = min(config.width / 1280, config.height / 720)
        self.origin = ((config.width - 1280 * self.scale) / 2,
                       (config.height - 720 * self.scale) / 2)
        self._fonts = {}
        self._fallback_key = None
        self._fallback_started = 0.0
        self._background = None

    def _font(self, size, bold=False):
        key = (size, bold)
        if key not in self._fonts:
            name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
            self._fonts[key] = pygame.font.Font(
                resource_path(f"fonts/dejavu-sans/{name}"), max(1, round(size * self.scale)))
        return self._fonts[key]

    def _point(self, x, y):
        return round(self.origin[0] + x * self.scale), round(self.origin[1] + y * self.scale)

    def _rect(self, x, y, width, height):
        return pygame.Rect(*self._point(x, y), round(width * self.scale), round(height * self.scale))

    def _text(self, text, x, y, size=18, color=INK, *, bold=False, right=False, width=None):
        font = self._font(size, bold)
        if width is not None:
            limit = width * self.scale
            if font.size(text)[0] > limit:
                while text and font.size(text + "…")[0] > limit:
                    text = text[:-1]
                text += "…"
        image = font.render(text, True, color)
        rect = image.get_rect(topright=self._point(x, y)) if right else image.get_rect(topleft=self._point(x, y))
        self.screen.blit(image, rect)
        return rect

    def _backdrop(self):
        if self._background is None:
            self._background = pygame.Surface(self.screen.get_size())
            self._background.fill((4, 9, 16))
            spacing = max(16, round(40 * self.scale))
            for x in range(0, self.screen.get_width(), spacing):
                pygame.draw.line(self._background, (9, 19, 29), (x, 0), (x, self.screen.get_height()))
            for y in range(0, self.screen.get_height(), spacing):
                pygame.draw.line(self._background, (9, 19, 29), (0, y), (self.screen.get_width(), y))
            panel = self._rect(80, 32, 1120, 656)
            pygame.draw.rect(self._background, (10, 20, 31), panel, border_radius=round(8 * self.scale))
            pygame.draw.rect(self._background, (46, 76, 95), panel, max(1, round(self.scale)),
                             border_radius=round(8 * self.scale))
        self.screen.blit(self._background, (0, 0))

    def _fallback(self):
        player = self.game.current_player
        now = perf_counter()
        key = (getattr(self.game, "campaign_id", ""), getattr(player, "agent_id", ""),
               getattr(self.game, "turn_number", 1), player.controller)
        if self._fallback_key != key:
            self._fallback_key, self._fallback_started = key, now
        codex = player.controller == PlayerController.CODEX
        config = get_runtime_config(getattr(player, "ai_reasoning_effort", None))
        return AITurnProgress(
            str(key[0]), str(key[1]), 0, str(getattr(player, "name", "Automated player")),
            int(key[2]), "External controller" if codex else config.model,
            "unavailable" if codex else config.reasoning_effort,
            "waiting_for_codex" if codex else "scheduled", self._fallback_started,
            self._fallback_started, now,
        )

    def _name(self, name):
        size = next((size for size in (30, 28, 26, 24, 22)
                     if self._font(size, True).size(name)[0] <= 2080 * self.scale), 22)
        font = self._font(size, True)
        remaining = name
        for row in range(2):
            line = remaining
            while line and font.size(line)[0] > 1056 * self.scale:
                line = line[:-1]
            self._text(line if row == 0 else remaining, 112, 78 + row * 35, size, bold=True, width=1056)
            remaining = remaining[len(line):].lstrip()
            if not remaining:
                break

    def _timeline(self, progress, accent):
        if progress.phase == "waiting_for_codex":
            self._text("EXTERNAL CONTROLLER", 112, 290, 16, MUTED)
            self._text("Waiting for commands from Codex", 112, 314, 16, MUTED)
            return
        keys = [key for key, _ in TURN_PHASES]
        active = progress.phase
        if active == "cancelling":
            active = "requesting"
        elif active == "error":
            active = next((key for key, _ in reversed(progress.phase_durations) if key in keys), "preparing")
        index = keys.index(active) if active in keys else 0
        short_labels = ("Scheduled", "Observation", "AI plan", "Check & apply", "Resolution", "Complete")
        durations = dict(progress.phase_durations)
        for i, (key, _) in enumerate(TURN_PHASES):
            x = 200 + i * 176
            color = GREEN if i < index else accent if i == index else DIM
            if i < len(TURN_PHASES) - 1:
                pygame.draw.line(self.screen, GREEN if i < index else DIM,
                                 self._point(x + 10, 289), self._point(x + 166, 289), max(1, round(self.scale)))
            pygame.draw.circle(self.screen, color, self._point(x, 289), max(3, round(6 * self.scale)),
                               0 if i <= index else max(1, round(self.scale)))
            label_width = self._font(15).size(short_labels[i])[0] / self.scale
            self._text(short_labels[i], x - label_width / 2, 303, 15, color)
            elapsed = durations.get(key)
            if key == progress.phase and key != "complete":
                elapsed = (elapsed or 0.0) + progress.phase_elapsed_seconds
            if elapsed is not None:
                self._text(duration(elapsed), x, 324, 12, MUTED, right=True)

    def _statistics(self, progress):
        self._text("REPORTED TOKEN USE", 112, 348, 14, MUTED, bold=True)
        if progress.attempts:
            latency = sum(item.latency_seconds for item in progress.attempts)
            count = len(progress.attempts)
            noun = "request" if count == 1 else "requests"
            detail = f"{count} completed {noun} · request time {duration(latency)}"
        else:
            detail = "Unavailable for Codex" if progress.phase == "waiting_for_codex" else "Available after response"
        self._text(detail, 1168, 348, 14, MUTED, right=True, width=700)
        for i, (field, label) in enumerate(METRICS):
            x, y = 112 + (i % 3) * 356, 374 + (i // 3) * 54
            pygame.draw.rect(self.screen, (15, 30, 44), self._rect(x, y, 344, 48),
                             border_radius=max(1, round(3 * self.scale)))
            self._text(label, x + 12, y + 3, 11, MUTED, bold=True)
            value, partial = progress.reported_total(field)
            text = token_count(value) + (" · partial" if partial else "")
            self._text(text, x + 12, y + 19, 20, INK, width=320)

    def _attempts(self, progress):
        self._text("REQUEST HISTORY", 112, 491, 14, MUTED, bold=True)
        # Every usage column is a subset/breakdown, not an additional charge.
        columns = (
            (208, "Request", None), (354, "Result", None), (446, "Time", None),
            (554, "Input", "input_tokens"), (662, "Output", "output_tokens"),
            (770, "Total", "total_tokens"), (878, "Cached", "cached_input_tokens"),
            (1000, "Uncached", "uncached_input_tokens"), (1164, "Reasoning", "reasoning_tokens"),
        )
        for x, label, _ in columns:
            self._text(label, x, 515, 12, MUTED, right=True)
        for i, attempt in enumerate(progress.attempts):
            y = 538 + i * 19
            label = "Initial" if attempt.attempt_index == 0 else f"Repair {attempt.attempt_index}"
            self._text(label, 112, y, 12)
            outcome = ATTEMPT_OUTCOMES.get(attempt.status, "Finished")
            color = GREEN if attempt.status == "accepted" else RED if attempt.status in {"failed", "commit_failed"} else AMBER
            self._text(outcome, 354, y, 12, color, right=True, width=140)
            self._text(duration(attempt.latency_seconds), 446, y, 12, right=True, width=88)
            for x, _, field in columns[3:]:
                self._text(token_count(attempt.token_count(field)), x, y, 12, right=True, width=100)
        if progress.phase == "waiting_for_codex":
            self._text("Codex inference statistics are not available to the game.", 112, 544, 15, MUTED)
        elif progress.phase in {"scheduled", "preparing", "requesting", "cancelling"}:
            y = 538 + len(progress.attempts) * 19
            label = "Initial" if not progress.repair_attempt else f"Repair {progress.repair_attempt}"
            self._text(label, 112, y, 12, CYAN)
            self._text("Available after response", 390, y, 12, MUTED)
        elif not progress.attempts:
            self._text("No completed requests.", 112, 544, 15, MUTED)

    def draw(self, progress: AITurnProgress | None = None):
        progress = progress if progress is not None else self._fallback()
        self._backdrop()
        accent = (RED if progress.phase == "error" else GREEN if progress.phase == "complete"
                  else AMBER if progress.repair_attempt or progress.phase == "cancelling" else CYAN)
        self._text("AUTOMATED TURN", 112, 50, 14, CYAN, bold=True)
        self._text(f"ROUND {progress.turn_number}", 1168, 50, 14, MUTED, right=True)
        self._name(progress.player_name)
        self._text(f"{progress.model}   ·   Reasoning: {progress.reasoning_effort.title()}",
                   112, 151, 16, MUTED, width=1056)
        pygame.draw.line(self.screen, (40, 67, 85), self._point(112, 180), self._point(1168, 180))
        center = self._point(125, 209)
        if progress.phase in {"complete", "error"}:
            pygame.draw.circle(self.screen, accent, center, max(3, round(7 * self.scale)))
        else:
            rect = self._rect(114, 198, 22, 22)
            angle = progress.sampled_at * 4
            pygame.draw.arc(self.screen, accent, rect, angle, angle + math.pi * 1.4, max(2, round(2 * self.scale)))
        self._text(progress.phase_label, 150, 190, 25, accent, bold=True, width=1010)
        if progress.phase == "error":
            detail = progress.safe_error
        elif progress.phase == "complete":
            detail = "Turn resolved. Returning to the next player."
        elif progress.phase == "waiting_for_codex":
            detail = "Codex is controlling this player."
        elif progress.phase == "cancelling":
            detail = "Waiting for the previous request to release the AI service."
        else:
            detail = "Token use is reported when each AI response finishes."
        self._text(detail, 112, 228, 14, MUTED, width=1056)
        self._text(f"Turn elapsed  {duration(progress.elapsed_seconds)}", 112, 252, 15)
        timing = f"Repairs {progress.repair_attempt}/{progress.repair_limit}"
        if progress.phase not in {"complete", "error"}:
            timing = f"Phase {duration(progress.phase_elapsed_seconds)}   ·   {timing}"
        self._text(timing, 1168, 252, 15, MUTED, right=True)
        self._timeline(progress, accent)
        self._statistics(progress)
        self._attempts(progress)
        footer = ("Enter — continue now · Continuing automatically" if progress.phase == "complete"
                  else "E — skip this AI turn" if progress.phase == "error"
                  else "The map returns on the next human turn.")
        self._text(footer, 112, 665, 13, accent, width=1056)

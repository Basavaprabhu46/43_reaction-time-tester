import array
import math

import pygame

from .round import Round

# Game Engine

WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
GRAY = (90, 90, 90)
GREEN = (40, 180, 90)
BLUE = (50, 90, 170)
RED = (200, 50, 50)
DARK = (30, 30, 40)

DIFFICULTIES = {
    "easy": {"label": "Easy", "min_wait_ms": 1500, "max_wait_ms": 3500, "rounds": 3},
    "medium": {"label": "Medium", "min_wait_ms": 1000, "max_wait_ms": 3000, "rounds": 5},
    "hard": {"label": "Hard", "min_wait_ms": 500, "max_wait_ms": 2000, "rounds": 7},
}


def _tone_bytes(freq, duration_ms, volume=0.4, sample_rate=44100, channels=1):
    n = max(1, int(sample_rate * duration_ms / 1000))
    buf = array.array("h")
    for i in range(n):
        t = i / sample_rate
        # 10 ms fade in/out to avoid clicks.
        fade = min(1.0, i / (sample_rate * 0.01), (n - i) / (sample_rate * 0.01))
        sample = int(volume * 32767 * math.sin(2 * math.pi * freq * t) * max(0.0, fade))
        if channels == 2:
            buf.append(sample)
            buf.append(sample)
        else:
            buf.append(sample)
    return buf.tobytes()


def _make_beep(freq, duration_ms, volume=0.4):
    """Build a single sine beep matching the current mixer format."""
    try:
        init = pygame.mixer.get_init()
        sample_rate = init[0] if init else 44100
        channels = init[2] if init and len(init) > 2 else 1
        raw = _tone_bytes(freq, duration_ms, volume, sample_rate, channels)
        return pygame.mixer.Sound(buffer=raw)
    except Exception:
        return None


def _make_jingle(notes, volume=0.4):
    """Build a multi-note jingle from [(freq, duration_ms), ...]."""
    try:
        init = pygame.mixer.get_init()
        sample_rate = init[0] if init else 44100
        channels = init[2] if init and len(init) > 2 else 1
        raw = b"".join(
            _tone_bytes(freq, dur, volume, sample_rate, channels) for freq, dur in notes
        )
        return pygame.mixer.Sound(buffer=raw)
    except Exception:
        return None


class GameEngine:
    def __init__(self, width, height, rounds_total=5, min_wait_ms=1000, max_wait_ms=3000):
        self.width = width
        self.height = height

        self.rounds_total = rounds_total
        self.min_wait_ms = min_wait_ms
        self.max_wait_ms = max_wait_ms
        self.difficulty = "custom"

        self.round = Round(self.min_wait_ms, self.max_wait_ms)
        self.reaction_times = []

        self.result_shown_at = None
        self.result_pause_ms = 800  # brief pause on the result screen between rounds
        self.false_start_pause_ms = 1000  # pause on false-start warning before retry

        self.font = pygame.font.SysFont("Arial", 30)
        self.big_font = pygame.font.SysFont("Arial", 46)
        self.small_font = pygame.font.SysFont("Arial", 22)
        self.game_over = False
        self.should_quit = False

        self._init_sounds()

    # -- sound ---------------------------------------------------------
    def _init_sounds(self):
        self.sound_enabled = False
        self.go_sound = None
        self.false_start_sound = None
        self.game_over_sound = None
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=44100, size=-16, channels=1)
            self.go_sound = _make_beep(880, 200)
            self.false_start_sound = _make_beep(196, 400)
            self.game_over_sound = _make_jingle(
                [(523, 150), (659, 150), (784, 300)]
            )
            self.sound_enabled = any(
                s is not None
                for s in (self.go_sound, self.false_start_sound, self.game_over_sound)
            )
        except Exception:
            self.sound_enabled = False

    def _play(self, sound):
        if self.sound_enabled and sound is not None:
            try:
                sound.play()
            except Exception:
                pass

    # -- flow ----------------------------------------------------------
    def reset(self, difficulty="medium"):
        """Restart the session, optionally with a named difficulty."""
        if difficulty in DIFFICULTIES:
            cfg = DIFFICULTIES[difficulty]
            self.min_wait_ms = cfg["min_wait_ms"]
            self.max_wait_ms = cfg["max_wait_ms"]
            self.rounds_total = cfg["rounds"]
            self.difficulty = difficulty
        else:
            self.difficulty = "custom"
        self.reaction_times = []
        self.round = Round(self.min_wait_ms, self.max_wait_ms)
        self.game_over = False
        self.result_shown_at = None
        self.should_quit = False

    def handle_event(self, event):
        if self.game_over:
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_1:
                    self.reset("easy")
                elif event.key == pygame.K_2:
                    self.reset("medium")
                elif event.key == pygame.K_3:
                    self.reset("hard")
                elif event.key in (pygame.K_q, pygame.K_ESCAPE):
                    self.should_quit = True
            return
        is_click = event.type == pygame.MOUSEBUTTONDOWN
        is_space = event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE
        if not (is_click or is_space):
            return
        # Ignore repeats while the result / false-start message is showing.
        if self.round.state not in ("waiting", "go"):
            return
        reaction_ms = self.round.register_input()
        self.result_shown_at = pygame.time.get_ticks()
        if self.round.state == "false_start":
            self._play(self.false_start_sound)
        elif self.round.state == "result" and reaction_ms is not None:
            self.reaction_times.append(reaction_ms)

    def handle_input(self):
        # Reserved for continuously-held-key input; every action here
        # is a discrete click/keypress, handled in handle_event.
        pass

    def update(self):
        if self.game_over:
            return

        was_waiting = self.round.state == "waiting"
        self.round.update()
        if was_waiting and self.round.state == "go":
            self._play(self.go_sound)

        if self.round.state not in ("result", "false_start"):
            return
        now = pygame.time.get_ticks()
        if self.result_shown_at is None:
            self.result_shown_at = now
        pause = (
            self.false_start_pause_ms
            if self.round.state == "false_start"
            else self.result_pause_ms
        )
        if now - self.result_shown_at >= pause:
            if self.round.state == "false_start":
                # False start: retry the same round, don't advance the count.
                self.round = Round(self.min_wait_ms, self.max_wait_ms)
                self.result_shown_at = None
            else:
                self._start_next_round()

    def _start_next_round(self):
        if len(self.reaction_times) >= self.rounds_total:
            self.game_over = True
            self._play(self.game_over_sound)
            print("Session complete! Reaction times (ms):", self.reaction_times)
            print("Average:", self.average_reaction_ms(), "ms")
            return
        self.round = Round(self.min_wait_ms, self.max_wait_ms)
        self.result_shown_at = None

    def average_reaction_ms(self):
        if not self.reaction_times:
            return 0
        return round(sum(self.reaction_times) / len(self.reaction_times))

    # -- rendering -----------------------------------------------------
    def render(self, screen):
        if self.game_over:
            self._render_game_over(screen)
            return

        if self.round.state == "waiting":
            bg = GRAY
            message = "Wait for green..."
        elif self.round.state == "go":
            bg = GREEN
            message = "Click now!"
        elif self.round.state == "false_start":
            bg = RED
            message = "Too soon!"
        else:
            bg = BLUE
            message = f"{self.round.reaction_ms} ms"

        screen.fill(bg)

        text_surf = self.big_font.render(message, True, WHITE)
        text_rect = text_surf.get_rect(center=(self.width // 2, self.height // 2))
        screen.blit(text_surf, text_rect)

        if self.round.state == "false_start":
            hint = self.small_font.render("Wait for green, then click", True, WHITE)
            hint_rect = hint.get_rect(
                center=(self.width // 2, self.height // 2 + 45)
            )
            screen.blit(hint, hint_rect)

        round_num = min(len(self.reaction_times) + 1, self.rounds_total)
        round_text = self.font.render(
            f"Round {round_num}/{self.rounds_total}", True, WHITE
        )
        screen.blit(round_text, (10, 10))

        avg_text = self.font.render(f"Avg: {self.average_reaction_ms()} ms", True, WHITE)
        screen.blit(avg_text, (self.width - 190, 10))

    def _render_game_over(self, screen):
        screen.fill(DARK)
        title = self.big_font.render("Session Complete!", True, WHITE)
        title_rect = title.get_rect(center=(self.width // 2, 50))
        screen.blit(title, title_rect)

        y = 110
        if not self.reaction_times:
            empty = self.small_font.render("No valid reactions recorded.", True, WHITE)
            screen.blit(empty, (60, y))
            y += 30
        for i, ms in enumerate(self.reaction_times, start=1):
            line = self.small_font.render(f"Round {i}: {ms} ms", True, WHITE)
            screen.blit(line, (60, y))
            y += 28

        avg = self.small_font.render(
            f"Average: {self.average_reaction_ms()} ms over {len(self.reaction_times)} rounds",
            True, WHITE,
        )
        screen.blit(avg, (60, y + 8))
        y += 44

        options = [
            "Play again:  1-Easy  2-Medium  3-Hard",
            "Press Q / Esc to quit",
        ]
        for opt in options:
            surf = self.small_font.render(opt, True, WHITE)
            rect = surf.get_rect(center=(self.width // 2, y + 10))
            screen.blit(surf, rect)
            y += 28

        diff_label = DIFFICULTIES.get(self.difficulty, {}).get("label", self.difficulty)
        diff_surf = self.small_font.render(f"Difficulty: {diff_label}", True, WHITE)
        screen.blit(diff_surf, (10, self.height - 32))

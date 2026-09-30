import random
import pygame


class Round:
    """One wait-for-green -> click round.

    States: "waiting" -> "go" -> "result", plus "false_start".

    - "waiting": grey screen, green hasn't appeared yet.
    - "go": screen is green, waiting for a genuine reaction.
    - "result": valid reaction recorded.
    - "false_start": input arrived during "waiting", no time recorded.
    """

    def __init__(self, min_wait_ms=1000, max_wait_ms=3000):
        self.wait_delay_ms = random.randint(min_wait_ms, max_wait_ms)
        self.state = "waiting"  # "waiting" -> "go" -> "result" (+ "false_start")
        self.start_time = pygame.time.get_ticks()
        self.go_time = None
        self.reaction_ms = None

    def update(self):
        if self.state == "waiting":
            now = pygame.time.get_ticks()
            if now - self.start_time >= self.wait_delay_ms:
                self.state = "go"
                self.go_time = now

    def register_input(self):
        """Record a click/Space press.

        Returns:
            int: reaction time in ms measured from ``go_time`` when the
                input arrived in "go" state (transitions to "result").
            None: false start (transitions "waiting" -> "false_start") or
                a duplicate input while already in "result"/"false_start"
                (state unchanged, caller should ignore).
        """
        now = pygame.time.get_ticks()
        if self.state == "waiting":
            # Reacted before "go" -> false start, no time recorded.
            self.state = "false_start"
            self.reaction_ms = None
            return None
        if self.state == "go":
            # Genuine reaction, measured from the moment "go" happened.
            self.reaction_ms = now - self.go_time
            self.state = "result"
            return self.reaction_ms
        # Already resolved ("result"/"false_start"): ignore repeats.
        return None

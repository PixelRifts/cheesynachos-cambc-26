import random

from bot import Bot
from cambc import Controller, Direction, EntityType, Environment, Position
from helpers import DIRECTIONS

class Core(Bot):
    def __init__(self, rc: Controller):
        super().__init__(rc)
        self.core = rc.get_position()
        self.count = 0

    def start_turn(self):
        pass

    def turn(self):
        threshold = 2 + self.rc.get_current_round() // 100
        # (ti, ax) = self.rc.get_global_resources()
        # if ti > 5000: threshold = 2 + self.rc.get_current_round() // 80
        if self.count < threshold:
            spawn_pos = self.rc.get_position().add(random.choice(DIRECTIONS))
            if self.rc.can_spawn(spawn_pos):
                self.rc.spawn_builder(spawn_pos)
                self.count += 1

    def end_turn(self):
        pass

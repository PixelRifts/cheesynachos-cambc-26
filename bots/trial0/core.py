import random

from bot import Bot
from cambc import Controller, Direction, EntityType, Environment, Position


DIRECTIONS = [d for d in Direction if d != Direction.CENTRE]

class Core(Bot):
    def __init__(self, rc: Controller):
        super().__init__(rc)
        self.core = rc.get_position()
        self.count = 0

    def start_turn(self):
        # TODO: senses update
        pass

    def turn(self):
        if self.count < 1:
            spawn_pos = self.rc.get_position().add(random.choice(DIRECTIONS))
            if self.rc.can_spawn(spawn_pos):
                self.rc.spawn_builder(spawn_pos)
                self.count += 1

    def end_turn(self):
        # Compute symmetry if time left
        pass
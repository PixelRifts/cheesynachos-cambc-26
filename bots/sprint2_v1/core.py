import random

from bot import Bot
from cambc import Controller, Direction, EntityType, Environment, Position
from helpers import DIRECTIONS

class Core(Bot):
    def __init__(self, rc: Controller):
        super().__init__(rc)
        self.core = rc.get_position()
        self.count = 0
        self.burst_attack = 0

    def start_turn(self):
        # TODO: senses update
        pass

    def turn(self):
        (ti, ax) = self.rc.get_global_resources()

        if (self.rc.get_current_round() % 100 == 50) and (ti > self.rc.get_builder_bot_cost()[0]*6):
            self.burst_attack = 6

        if self.burst_attack > 0:
            spawn_pos = self.rc.get_position()
            if self.rc.can_spawn(spawn_pos):
                self.rc.spawn_builder(spawn_pos)
                self.burst_attack -= 1
        else:
            # spawn_to_threshold
            threshold = self.rc.get_current_round() // 50
            if self.rc.get_current_round() > 1500:
                threshold = 4 + self.rc.get_current_round() // 10
            elif self.rc.get_current_round() > 500:
                threshold = 4 + self.rc.get_current_round() // 25
            else:
                threshold = 4 + self.rc.get_current_round() // 50
            
            if self.count < threshold:
                spawn_pos = self.rc.get_position().add(random.choice(DIRECTIONS))
                if self.rc.can_spawn(spawn_pos):
                    self.rc.spawn_builder(spawn_pos)
                    self.count += 1

    def end_turn(self):
        # Compute symmetry if time left
        pass

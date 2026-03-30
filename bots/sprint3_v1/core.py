import random

from bot import Bot
from cambc import Controller, Direction, EntityType, Environment, Position
from helpers import DIRECTIONS
from collections import deque

class Core(Bot):
    def __init__(self, rc: Controller):
        super().__init__(rc)
        self.core = rc.get_position()
        self.count = 0
        self.bias_dir = None
        self.ti_tracker = deque(maxlen=24)

    def start_turn(self):
        (ti, ax) = self.rc.get_global_resources()
        self.ti_tracker.append(ti)

        self.bias_dir = None
        for t in self.rc.get_nearby_tiles():
            if not self.rc.is_in_vision(t): continue
            if self.rc.get_tile_env(t) == Environment.ORE_TITANIUM:
                bldg = self.rc.get_tile_building_id(t)
                if bldg is None:
                    self.bias_dir = self.rc.get_position().direction_to(t)

    def turn(self):
        threshold = 2 #+ self.rc.get_current_round() // 80
        if self.rc.get_current_round() > 100:
            threshold = 4 + self.rc.get_current_round() // 80

        if self.count < threshold:
            if self.bias_dir is not None:
                spawn_pos = self.rc.get_position().add(self.bias_dir)
            else:
                spawn_pos = self.rc.get_position().add(random.choice(DIRECTIONS))
            if self.rc.can_spawn(spawn_pos):
                self.rc.spawn_builder(spawn_pos)
                self.count += 1

    def end_turn(self):
        pass

    def ti_ever_increased(self) -> bool:
        it = iter(self.ti_tracker)
        prev = next(it, None)

        for cur in it:
            if cur > prev:
                return True
            prev = cur

        return False

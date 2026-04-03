import random

from bot import Bot
from cambc import Controller, Direction, EntityType, Environment, Position
from helpers import DIRECTIONS, DIRECTIONS_ORDERED, DIRECTIONS_INDEX
from collections import deque

class Core(Bot):
    def __init__(self, rc: Controller):
        super().__init__(rc)
        self.core = rc.get_position()
        self.econ_count = 0
        self.rush_count = 0
        self.healer_count = 0
        self.ti_tracker = deque(maxlen=24)
        self.ore_dir = None
        map_center = Position(self.rc.get_map_width() // 2, self.rc.get_map_height() // 2)
        self.rush_dir = self.rc.get_position().direction_to(map_center)

    def start_turn(self):
        (ti, ax) = self.rc.get_global_resources()
        self.ti_tracker.append(ti)
        self.ore_dir = None

        for t in self.rc.get_nearby_tiles():
            if not self.rc.is_in_vision(t): continue
            if self.rc.get_tile_env(t) == Environment.ORE_TITANIUM:
                bldg = self.rc.get_tile_building_id(t)
                if bldg is None:
                    best_dir = self.rc.get_position().direction_to(t)
                    if best_dir != self.rush_dir:
                        self.ore_dir = best_dir
                    else:
                        next_idx = (DIRECTIONS_INDEX[best_dir] + 1) % 8
                        self.ore_dir = DIRECTIONS_ORDERED[next_idx]
                    return

    def turn(self):
        turn = self.rc.get_current_round()

        if self.sees_enemy_builder_bot() and self.healer_count < 2:
            if self.spawn_healer():
                self.healer_count += 1
                return
        
        target = 2 + turn // 80
        if self.econ_count + self.rush_count < target:        
            if 2*self.econ_count <= self.rush_count:
                self.spawn_econ()
                self.econ_count += 1
                return
            self.spawn_rush()
            self.rush_count += 1
            return

    def spawn_econ(self):
        if self.ore_dir is not None:
            spawn_pos = self.rc.get_position().add(self.ore_dir)
        else:
            spawn_pos = self.rc.get_position().add(random.choice(DIRECTIONS))
        if self.rc.can_spawn(spawn_pos):
            self.rc.spawn_builder(spawn_pos)

    def spawn_rush(self):
        spawn_pos = self.rc.get_position().add(self.rush_dir)
        if self.rc.can_spawn(spawn_pos):
            self.rc.spawn_builder(spawn_pos)

    def spawn_healer(self) -> bool:
        spawn_pos = self.rc.get_position()
        if self.rc.can_spawn(spawn_pos):
            self.rc.spawn_builder(spawn_pos)
            return True
        return False

    def sees_enemy_builder_bot(self) -> bool:
        for t in self.rc.get_nearby_tiles():
            bb = self.rc.get_tile_builder_bot_id(t)
            if bb is None:
                continue
            if self.rc.get_team(bb) != self.rc.get_team():
                return True
        return False

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

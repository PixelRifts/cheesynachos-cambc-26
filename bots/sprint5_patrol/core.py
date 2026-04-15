import random

from bot import Bot
from cambc import Controller, Direction, EntityType, Environment, Position
from helpers import *
from collections import deque

AXIONITE_STOCKPILE_THRESHOLD_ROUND = 1200
AXIONITE_MIN_STOCKPILE = 41

class Core(Bot):
    def __init__(self, rc: Controller):
        super().__init__(rc)
        self.core = rc.get_position()
        self.econ_count = 0
        self.rush_count = 0
        self.healer_count = 0
        self.ti_tracker = deque(maxlen=24)
        self.active_rescue_ops = deque(maxlen=8)
        self.ore_dir = None
        map_center = Position(self.rc.get_map_width() // 2, self.rc.get_map_height() // 2)
        self.rush_dir = self.rc.get_position().direction_to(map_center)

    def mark_rescue_operation(self, bldg_id: int):
        if bldg_id in self.active_rescue_ops:
            self.active_rescue_ops.remove(bldg_id)
        self.active_rescue_ops.append(bldg_id)

    def start_turn(self):
        ti, ax = self.rc.get_global_resources()
        if self.rc.get_current_round() < AXIONITE_STOCKPILE_THRESHOLD_ROUND:
            excess = ax - AXIONITE_MIN_STOCKPILE
            if excess > 0:
                self.rc.convert(excess)
            ti, ax = self.rc.get_global_resources()

        print(len(self.active_rescue_ops))
        
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
                        self.ore_dir = best_dir.rotate_left()
                    return

    def turn(self):
        turn = self.rc.get_current_round()

        # For first enemy spotted -> spawn healer immediately.
        # For subsequent enemies, spawn healer if we have one and if we need one.
        if self.healer_count < 1:
            if self.sees_enemy_builder_bot() or self.sees_conveyor_belt():
                print("Enemy builder / converyor belt spotted!")
                self.spawn_healer()
        elif self.healer_needed():
            if self.healer_needed(): print("Healer needed!")
            else: print("Enemy builder bot spotted!")
            self.spawn_healer()
        
        target = 3 + turn // 40
        if self.ti_tracker[-1] > (self.rc.get_builder_bot_cost()[0]*4): target = 3 + turn // 30

        print(target, self.econ_count, self.rush_count)
        if self.econ_count + self.rush_count < target:        
            if self.econ_count <= 2*self.rush_count:
                self.spawn_econ()
                return
            if not self.spawn_rush():
                self.spawn_econ()
            return

    def spawn_econ(self):
        if self.ore_dir is not None:
            spawn_pos = self.rc.get_position().add(self.ore_dir)
            if not self.rc.can_spawn(spawn_pos):
                spawn_pos = self.rc.get_position().add(random.choice(DIRECTIONS))
        else:
            spawn_pos = self.rc.get_position().add(random.choice(DIRECTIONS))

        if self.rc.can_spawn(spawn_pos):
            self.rc.spawn_builder(spawn_pos)
            self.econ_count += 1

    def spawn_rush(self):
        spawn_pos = self.rc.get_position().add(self.rush_dir)
        if self.rc.can_spawn(spawn_pos):
            self.rc.spawn_builder(spawn_pos)
            self.rush_count += 1
            return True
        return False

    def spawn_healer(self):
        print("Spawning healer bot!")
        spawn_pos = self.rc.get_position()
        print("builderbot cost", self.rc.get_builder_bot_cost())
        if self.rc.can_spawn(spawn_pos):
            self.rc.spawn_builder(spawn_pos)
            self.healer_count += 1
        else:
            print("Failed to spawn healer bot!")

    def healer_needed(self) -> bool:
        for bldg in self.rc.get_nearby_buildings():
            if self.rc.get_team(bldg) != self.rc.get_team():
                continue
            if (self.rc.get_entity_type(bldg) == EntityType.ROAD):
                continue

            # bldg_pos = self.rc.get_position(bldg)
            hp = self.rc.get_hp(bldg)
            
            hp_threshold = 9 if bldg in self.active_rescue_ops else 13  # DONOT CHANGE !!!
            if hp < hp_threshold:
                print(f"Building {bldg} needs healing!")
                self.mark_rescue_operation(bldg)
                return True

        return False
    
    def sees_enemy_builder_bot(self) -> bool:
        for t in self.rc.get_nearby_tiles():
            if not self.rc.is_in_vision(t):
                continue

            bb = self.rc.get_tile_builder_bot_id(t)
            if bb is None:
                continue
            if self.rc.get_team(bb) != self.rc.get_team():
                return True

        return False
    
    def sees_conveyor_belt(self):
        for bldg in self.rc.get_nearby_buildings():
            if self.rc.get_team(bldg) != self.rc.get_team():
                continue
            if self.rc.get_entity_type(bldg) == EntityType.CONVEYOR:
                return True
        return False

    def end_turn(self):
        pass
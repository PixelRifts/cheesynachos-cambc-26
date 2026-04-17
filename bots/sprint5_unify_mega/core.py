import random

from bot import Bot
from cambc import Controller, Direction, EntityType, Environment, Position
from helpers import *
from collections import deque

AXIONITE_STOCKPILE_THRESHOLD_ROUND = 1200
AXIONITE_MIN_STOCKPILE = 41
TITANIUM_MAINTAIN_AMOUNT = 1000

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
            if excess > 0 and ti < TITANIUM_MAINTAIN_AMOUNT:
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
            if self.sees_enemy_builder_bot() or self.sees_conveyor():
                print("Enemy builder or conveyor spotted!")
                self.spawn_healer()
                return
        bldg = self.healer_needed()
        if bldg is not None:
            print("Healer needed for building", bldg)
            if self.spawn_healer():
                self.mark_rescue_operation(bldg)
                return
        
        if self.rush_count < 1:
            self.spawn_rush()
            return
        
        ti = self.rc.get_global_resources()[0]
        bbcost = self.rc.get_builder_bot_cost()[0]
        harcost = self.rc.get_harvester_cost()[0]
        if ti > (bbcost+harcost)*self.econ_count:
            self.spawn_builder()

        target = 4 + turn // 50
        print(target, self.econ_count, self.rush_count)

        if self.econ_count + self.rush_count < target:
            self.spawn_builder()
        
    def spawn_builder(self):
        ti = self.rc.get_global_resources()[0]
        e_r = 1
        e_c = 1
        if ti < 500:
            e_r = 3
        elif ti < 1000:
            e_r = 2
        elif ti < 1500:
            e_r = 1
        else:
            e_c = 2
        if e_c * self.econ_count <= e_r * self.rush_count:
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
        spawn_pos = self.rc.get_position()
        if self.rc.can_spawn(spawn_pos):
            self.rc.spawn_builder(spawn_pos)
            self.healer_count += 1
            return True
        return False

    def healer_needed(self):
        for bldg in self.rc.get_nearby_buildings():
            if self.rc.get_team(bldg) != self.rc.get_team():
                continue
            if (self.rc.get_entity_type(bldg) == EntityType.ROAD):
                continue

            # bldg_pos = self.rc.get_position(bldg)
            hp = self.rc.get_hp(bldg)

            # Effective HP logic - Didnt Work.
            # effective_hp = hp
            # if self.rc.is_in_vision(bldg_pos):
            #     bb_here = self.rc.get_tile_builder_bot_id(bldg_pos)
            #     if bb_here is not None and self.rc.get_team(bb_here) == self.rc.get_team():
            #         effective_hp += 4
            # for d in DIRECTIONS:
            #     adj = bldg_pos.add(d)
            #     if not self.rc.is_in_vision(adj):
            #         continue
            #     bb = self.rc.get_tile_builder_bot_id(adj)
            #     if bb is None:
            #         continue
            #     if self.rc.get_team(bb) == self.rc.get_team():
            #         effective_hp += 4

            hp_threshold = 9 if bldg in self.active_rescue_ops else 13  # DONOT CHANGE !!!
            if hp < hp_threshold:
                return bldg

        return None
    
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
    
    def sees_conveyor(self) -> bool:
        for t in self.rc.get_nearby_tiles():
            if not self.rc.is_in_vision(t):
                continue

            bldg = self.rc.get_tile_building_id(t)
            if bldg is None:
                continue
            if self.rc.get_team(bldg) == self.rc.get_team() and self.rc.get_entity_type(bldg) == EntityType.CONVEYOR:
                return True

        return False

    def end_turn(self):
        pass
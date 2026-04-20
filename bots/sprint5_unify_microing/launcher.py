import random
import sys

from enum import Enum
from bot import Bot
from cambc import Controller, Direction, EntityType, Environment, Position, GameConstants
from helpers import *

LAUNCHER_INACTIVITY_DELETION = 40
TI_DANGEROUSLY_LOW_THRESHOLD = 20

class Launcher(Bot):
    def __init__(self, rc: Controller):
        super().__init__(rc)
        buildings = rc.get_nearby_buildings()
        # for b in buildings:
        #     if rc.get_entity_type(b) == EntityType.CORE:
        #         self.core_pos = rc.get_position(b)
        #         self.type = Defence.CORELAUNCHER
        #         break

        self.inactive_counter = 0
            

    def start_turn(self):
        my_pos = self.rc.get_position()
        self.inactivity_counter = 0
        self.fading = False
        protecting_harvester = False
        for d in DIRECTIONS:
            p = my_pos.add(d)
            if not is_in_map(p, self.rc.get_map_width(), self.rc.get_map_height()): continue
            bldg = self.rc.get_tile_building_id(p)
            entt = None if bldg is None else self.rc.get_entity_type(bldg)
            allied = False if bldg is None else self.rc.get_team(bldg) == self.rc.get_team()
            if entt in ENTITY_TRANSPORT and not allied:
                self.fading = False
        pass

    def turn(self):
        if self.fading:
            self.inactive_counter += 1
            if self.inactive_counter > 10:
                self.rc.self_destruct()
        self.far()

    def far(self):
        my_pos = self.rc.get_position()
        
        allied_positions = []
        additionally_weight = {}
        bldgs = self.rc.get_nearby_buildings()
        for bldg in bldgs:
            if self.rc.get_team(bldg) == self.rc.get_team():
                entt = self.rc.get_entity_type(bldg)
                if entt == EntityType.LAUNCHER and bldg > self.rc.get_id():
                    valid = True
                    valid_posns = []
                    turret_pos = self.rc.get_position(bldg)
                    for d in DIRECTIONS:
                        p = turret_pos.add(d)
                        if not is_in_map(p, self.rc.get_map_width(), self.rc.get_map_height()): continue
                        if not self.rc.is_in_vision(p): continue
                        bb_there = self.rc.get_tile_builder_bot_id(turret_pos)
                        if bb_there is not None and self.rc.get_team(bb_there) != self.rc.get_team():
                            valid = False
                            break
                        valid_posns.append(p)

                    if valid:
                        for p in valid_posns:
                            dist_weight = turret_pos.distance_squared(my_pos)
                            additionally_weight[p] = max(additionally_weight.get(p, 0), 10000 + dist_weight)
                    else:
                        allied_positions.append(self.rc.get_position(bldg))
                elif entt not in ENTITY_TRIVIAL:
                    allied_positions.append(self.rc.get_position(bldg))
            
        nearby_tiles = self.rc.get_nearby_tiles()
        bots = [my_pos.add(d) for d in DIRECTIONS]

        # --- enemy data ---
        enemy_data = []
        for enemy_pos in bots:
            if not is_in_map(enemy_pos, self.rc.get_map_width(), self.rc.get_map_height()): continue
            if not self.rc.is_in_vision(enemy_pos): continue
            bot = self.rc.get_tile_builder_bot_id(enemy_pos)
            if bot is None: continue
            if self.rc.get_team(bot) == self.rc.get_team(): continue

            if allied_positions:
                min_dist_to_ally = min(enemy_pos.distance_squared(ap) for ap in allied_positions)
            else:
                min_dist_to_ally = 0

            enemy_score = -min_dist_to_ally * 2
            enemy_data.append((bot, enemy_pos, enemy_score))

        if not enemy_data: return
        enemy_data.sort(key=lambda x: x[2], reverse=True)

        # --- tile scoring ---
        if allied_positions:
            tile_ally_min = {
                pos: min(pos.distance_squared(ap) for ap in allied_positions)
                for pos in nearby_tiles
            }
        else:
            tile_ally_min = {pos: 0 for pos in nearby_tiles}

        tile_base_score = {
            pos: tile_ally_min[pos]*3 + additionally_weight.get(pos, 0)
            for pos in nearby_tiles
        }

        # sort tiles by score (highest first)
        sorted_tiles = sorted(nearby_tiles, key=lambda p: tile_base_score[p], reverse=True)

        # --- try best tiles first ---
        for bot, enemy_pos, enemy_score in enemy_data:
            for pos in sorted_tiles:
                if self.rc.can_launch(enemy_pos, pos):
                    self.rc.launch(self.rc.get_position(bot), pos)
                    self.inactive_counter = 0
                    return
                else:
                    self.inactive_counter = 0
                    print("couldnt launch", enemy_pos, " to ", pos)
    

    def end_turn(self):
        # Compute symmetry if time left
        pass

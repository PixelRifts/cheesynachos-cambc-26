import random
import sys

from enum import Enum
from bot import Bot
from cambc import Controller, Direction, EntityType, Environment, Position, GameConstants
from helpers import DIRECTIONS

class Defence(Enum):
    CORELAUNCHER = "AwayFromCore"
    OTHER = "Defence"

class Launcher(Bot):
    def __init__(self, rc: Controller):
        buildings = rc.get_nearby_buildings()
        self.type = Defence.OTHER
        # for b in buildings:
        #     if rc.get_entity_type(b) == EntityType.CORE:
        #         self.core_pos = rc.get_position(b)
        #         self.type = Defence.CORELAUNCHER
        #         break

        super().__init__(rc)

    def start_turn(self):
        # TODO: senses update
        pass

    def turn(self):
        allied_positions = []
        for bldg in self.rc.get_nearby_buildings():
            if self.rc.get_team(bldg) == self.rc.get_team():
                allied_positions.append(self.rc.get_position())

        if self.type == Defence.OTHER:
            self.far(allied_positions)
        # else:
        #     self.core()

    def far(self, allied_positions: list[Position]):
        my_pos = self.rc.get_position()
        nearby_tiles = self.rc.get_nearby_tiles()
        bots = self.rc.get_nearby_units(2)

        if allied_positions:
            tile_ally_min = {
                pos: min(pos.distance_squared(ap) for ap in allied_positions)
                for pos in nearby_tiles
            }
        else:
            tile_ally_min = { pos: 0 for pos in nearby_tiles }
        
        tile_base_score = {
            pos: my_pos.distance_squared(pos) + tile_ally_min[pos]
            for pos in nearby_tiles
        }

        enemy_data = []
        for bot in bots:
            if self.rc.get_team(bot) == self.rc.get_team(): continue
            if self.rc.get_entity_type(bot) != EntityType.BUILDER_BOT: continue

            enemy_pos = self.rc.get_position(bot)

            if allied_positions:
                min_dist_to_ally = min(enemy_pos.distance_squared(ap) for ap in allied_positions)
            else:
                min_dist_to_ally = 0

            enemy_data.append((bot, enemy_pos, -min_dist_to_ally * 2))

        if not enemy_data: return

        best_bot = None
        best_tile = None
        best_score = float('-inf')
        
        for bot, enemy_pos, enemy_score in enemy_data:
            for pos in nearby_tiles:
                if not self.rc.can_launch(enemy_pos, pos):
                    continue
                score = tile_base_score[pos] + enemy_score
                if score > best_score:
                    best_score = score
                    best_bot = bot
                    best_tile = pos



        if best_bot is not None and best_tile is not None:
            self.rc.launch(self.rc.get_position(best_bot), best_tile)
    

    def core(self):
        bots = self.rc.get_nearby_units(2)
        for bot in bots:
            best_tile = None
            
            if(self.rc.get_team(bot) == self.rc.get_team()):
                continue

            enemy_pos = self.rc.get_position(bot)
            max_dist = float('-inf')
            nearby_tiles = self.rc.get_nearby_tiles();
            for pos in nearby_tiles:
                if self.rc.can_launch(enemy_pos, pos):
                    score = self.core_pos.distance_squared(pos)


                    if score > max_dist:
                        max_dist = score
                        best_tile = pos

            # Launch at the single best tile found for this bot
            if best_tile:
                self.rc.launch(enemy_pos, best_tile)
                break

    def end_turn(self):
        # Compute symmetry if time left
        pass

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
        allied_structs = []
        for bldg in self.rc.get_nearby_buildings():
            if self.rc.get_team(bldg) == self.rc.get_team():
                allied_structs.append(bldg)

        
        if self.type == Defence.OTHER:
            self.far(allied_structs)
        # else:
        #     self.core()

    def far(self, allied_structs: list[Position]):
        bots = self.rc.get_nearby_units()
        nearby_tiles = self.rc.get_nearby_tiles()
        best_bot = None
        best_tile = None
        best_score = float('-inf')

        for bot in bots:
            if self.rc.get_team(bot) == self.rc.get_team():
                continue
            if self.rc.get_entity_type(bot) != EntityType.BUILDER_BOT:
                continue

            enemy_pos = self.rc.get_position(bot)

            # how dangerous this enemy is
            min_dist_enemy_to_ally = float('inf')
            for ally in allied_structs:
                ally_pos = self.rc.get_position(ally)
                d = enemy_pos.distance_squared(ally_pos)
                if d < min_dist_enemy_to_ally:
                    min_dist_enemy_to_ally = d

            # invert so closer = higher score
            enemy_score = -min_dist_enemy_to_ally

            for pos in nearby_tiles:
                if not self.rc.can_launch(enemy_pos, pos):
                    continue
                dist_self = self.rc.get_position().distance_squared(pos)

                min_dist_ally = float('inf')
                for ally in allied_structs:
                    ally_pos = self.rc.get_position(ally)
                    d = pos.distance_squared(ally_pos)
                    if d < min_dist_ally:
                        min_dist_ally = d

                tile_score = dist_self + min_dist_ally

                score = tile_score + enemy_score * 2

                if score > best_score:
                    best_score = score
                    best_bot = bot
                    best_tile = pos

        if best_bot is not None and best_tile is not None:
            self.rc.launch(self.rc.get_position(best_bot), best_tile)
    

    def core(self):
        bots = self.rc.get_nearby_units()
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

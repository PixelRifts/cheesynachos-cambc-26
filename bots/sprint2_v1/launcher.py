import random
import sys

from enum import Enum
from bot import Bot
from cambc import Controller, Direction, EntityType, Environment, Position
from helpers import DIRECTIONS

class Defence(Enum):
    CORELAUNCHER = "AwayFromCore"
    OTHER = "Defence"

class Launcher(Bot):
    def __init__(self, rc: Controller):
        buildings = rc.get_nearby_buildings()
        self.type = Defence.OTHER
        for b in buildings:
            if rc.get_entity_type(b) == EntityType.CORE:
                self.core_pos = rc.get_position(b)
                self.type = Defence.CORELAUNCHER
                break

        super().__init__(rc)

    def start_turn(self):
        # TODO: senses update
        pass

    def turn(self):
        if self.type == Defence.OTHER:
            self.far()
        else:
            self.core()

    def far(self):
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
                    rel_x = pos[0] - enemy_pos[0]
                    rel_y = pos[1] - enemy_pos[1]
                
                    score = max((rel_x), (rel_y))

                    if score > max_dist:
                        max_dist = score
                        best_tile = pos

            # Launch at the single best tile found for this bot
            if best_tile:
                self.rc.launch(enemy_pos, best_tile)
                break

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
                    rel_x = self.core_pos[0] - pos[0]
                    rel_y = self.core_pos[1] - pos[1]
                
                    score = max((rel_x), (rel_y))

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

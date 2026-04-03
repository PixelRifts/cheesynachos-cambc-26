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

        self.far(allied_structs)
        # else:
        #     self.core()

    def far(self, allied_structs: list[Position]):
        my_pos = self.rc.get_position()

        # --- Phase 1: pick nearest valid enemy builder bot ---
        target_bot = None
        best_dist = float('inf')

        for bot in self.rc.get_nearby_units():
            if self.rc.get_team(bot) != self.rc.get_team() and \
            self.rc.get_entity_type(bot) == EntityType.BUILDER_BOT:

                enemy_pos = self.rc.get_position(bot)
                d = my_pos.distance_squared(enemy_pos)

                if d < best_dist:
                    best_dist = d
                    target_bot = bot

        if target_bot is None:
            print('no suitable')
            return

        enemy_pos = self.rc.get_position(target_bot)

        # --- Phase 2: pick best launch tile for that bot ---
        dx = enemy_pos.x - my_pos.x
        dy = enemy_pos.y - my_pos.y
        test_dx = -1
        test_dy = -1

        best_tile = None
        best_score = float('-inf')

        for pos in self.rc.get_nearby_tiles():
            if not self.rc.can_launch(enemy_pos, pos):
                continue

            rel_x = pos.x - enemy_pos.x
            rel_y = pos.y - enemy_pos.y

            
            align = rel_x * dx + rel_y * dy

            if align <= 0: continue

            perp = abs(rel_x * dy - rel_y * dx)

            score = align * 4 - perp

            if score > best_score:
                best_score = score
                best_tile = pos

        print(target_bot, '...', best_tile, '...', dx,',',dy)
        if best_tile is not None:
            self.rc.launch(enemy_pos, best_tile)

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

import random
import sys

from enum import Enum
from bot import Bot
from cambc import Controller, Direction, EntityType, Environment, Position, GameConstants
from helpers import *

priorities = {
    EntityType.BUILDER_BOT: 60,
    EntityType.CORE: 5,
    EntityType.GUNNER: 100,
    EntityType.SENTINEL: 100,
    EntityType.BREACH: 100,
    EntityType.LAUNCHER: 100,
    EntityType.CONVEYOR: 10,
    EntityType.SPLITTER: 20,
    EntityType.ARMOURED_CONVEYOR: 10,
    EntityType.BRIDGE: 10,
    EntityType.HARVESTER: -100,
    EntityType.FOUNDRY: 100,
    EntityType.ROAD: 1,
    EntityType.BARRIER: 8,
    EntityType.MARKER: -100,
}

# TODO prioritize transport that is deemed "critical"

class Sentinel(Bot):
    def __init__(self, rc: Controller):
        super().__init__(rc)
        self.best_target = None

        self.attack_dmg = GameConstants.SENTINEL_DAMAGE
        self.inactive_counter = 0

    def start_turn(self):
        self.best_target = None

        if self.rc.get_ammo_amount() == 0:
            self.inactive_counter += 1
        else:
            self.inactive_counter = 0
        if self.inactive_counter > 50:
            self.rc.self_destruct()
        
        attackables = self.rc.get_attackable_tiles()
        priority = -100000
        for p in attackables:
            e = self.rc.get_tile_building_id(p)
            bb = self.rc.get_tile_builder_bot_id(p)
            
            valid = False
            score = -chebyshev_distance(p, self.rc.get_position())
            if e is not None:
                if bb is not None and self.rc.get_team(bb) == self.rc.get_team():
                    continue
                if self.rc.get_team(e) == self.rc.get_team():
                    continue
                entt = self.rc.get_entity_type(e)
                
                score = priorities[entt]
                if score < 0: continue
                
                score -= ((self.rc.get_hp(e) / self.attack_dmg) * 10)
                valid = True

            if bb is not None:
                if self.rc.get_team(bb) == self.rc.get_team():
                    continue
                score =  priorities[EntityType.BUILDER_BOT]
                score -= ((self.rc.get_hp(bb) / self.attack_dmg) * 10)
                print(score)
                valid = True
                
            if valid and score > priority and self.rc.can_fire(p):
                priority = score
                self.best_target = p

        pass

    def turn(self):
        if self.best_target is not None:
            self.rc.fire(self.best_target)
        pass

    def end_turn(self):
        # Compute symmetry if time left
        pass

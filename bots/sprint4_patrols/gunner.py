import random
import sys

from enum import Enum
from bot import Bot
from cambc import Controller, Direction, EntityType, Environment, Position, GameConstants
from helpers import *

ROTATION_PENALTY = 15
PRIORITIES = {
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
    EntityType.BARRIER: 1,
    EntityType.MARKER: 1,
}

# TODO prioritize transport that is deemed "critical"

class Gunner(Bot):
    def __init__(self, rc: Controller):
        super().__init__(rc)
        self.best_target = None
        self.picked_rotation = rc.get_direction()
        print('gunner spawned', file=sys.stderr)

        self.attack_dmg = GameConstants.GUNNER_DAMAGE

    def start_turn(self):
        self.best_target = None
        self.picked_rotation = None

        my_pos = self.rc.get_position()
        my_dir = self.rc.get_direction()
        
        attackables = self.rc.get_attackable_tiles()
        priority = -100000
        for p in attackables:
            e = self.rc.get_tile_building_id(p)
            bb = self.rc.get_tile_builder_bot_id(p)

            if e is not None:
                if self.rc.get_team(e) == self.rc.get_team():
                    continue
                entt = self.rc.get_entity_type(e)
                
                score = PRIORITIES[entt]
                if score < 0: continue
                
                score -= ((self.rc.get_hp(e) / self.attack_dmg) * 10)

                if score > priority and self.rc.can_fire(p):
                    priority = score
                    self.best_target = p
            if bb is not None:
                if self.rc.get_team(bb) == self.rc.get_team():
                    continue
                score =  PRIORITIES[EntityType.BUILDER_BOT]
                score -= ((self.rc.get_hp(bb) / self.attack_dmg) * 10)
                
                if score > priority and self.rc.can_fire(p):
                    priority = score
                    self.best_target = p


        if self.best_target is not None: return
        rotation_fan = [
            my_dir.rotate_left(), my_dir.rotate_right(),
            my_dir.rotate_left().rotate_left(), my_dir.rotate_right().rotate_right(),
            my_dir.rotate_left().rotate_left().rotate_left(), my_dir.rotate_right().rotate_right().rotate_right(),
            my_dir.opposite(),
        ]

        best_score = -100000
        for d in rotation_fan:
            it = 3 if d in CARDINAL_DIRECTIONS else 2

            p = my_pos
            for i in range(1, it+1):
                p = p.add(d)
                self.rc.draw_indicator_dot(p, 255, 0, 0)
                e = self.rc.get_tile_building_id(p)
                bb = self.rc.get_tile_builder_bot_id(p)
                env = self.rc.get_tile_env(p)
                if env == Environment.WALL: break
                
                # --- buildings ---
                if e is not None:
                    if self.rc.get_team(e) != self.rc.get_team():
                        entt = self.rc.get_entity_type(e)

                        base = PRIORITIES[entt]
                        if not (bb is not None and self.rc.get_team(bb) == self.rc.get_team()) and base > 0:
                            base -= (self.rc.get_hp(e) / self.attack_dmg) * 10
                            score = base
                            if score > best_score:
                                best_score = score
                                self.picked_rotation = d

                # --- builder bots ---
                if bb is not None:
                    if self.rc.get_team(bb) != self.rc.get_team():
                        base = PRIORITIES[EntityType.BUILDER_BOT]
                        base -= (self.rc.get_hp(bb) / self.attack_dmg) * 10
                        score = base
                        if score > best_score:
                            best_score = score
                            self.picked_rotation = d
                
                is_allied_blocker = (e is not None and self.rc.get_team(e) == self.rc.get_team()) or \
                    (bb is not None and self.rc.get_team(bb) == self.rc.get_team())
                if (is_allied_blocker and not (e is not None and self.rc.get_entity_type(e) in ENTITY_TRIVIAL)) or\
                    (e is not None and self.rc.get_entity_type(e) == EntityType.HARVESTER): break

    def turn(self):
        if self.picked_rotation is not None and self.picked_rotation != self.rc.get_direction():
            self.rc.rotate(self.picked_rotation)
            return
        
        if self.best_target is not None and self.rc.can_fire(self.best_target):
            self.rc.fire(self.best_target)
            return

    def end_turn(self):
        pass
import random
import sys

from enum import Enum
from bot import Bot
from cambc import Controller, Direction, EntityType, Environment, Position
from helpers import DIRECTIONS

class Defence(Enum):
    CORELAUNCHER = "AwayFromCore"
    OTHER = "Defence"

priorities = {
    EntityType.BUILDER_BOT: 60,
    EntityType.CORE: 50,
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

class SimpleShooter(Bot):
    def __init__(self, rc: Controller):
        super().__init__(rc)
        self.best_target = None

    def start_turn(self):
        self.best_target = None

        attackables = self.rc.get_attackable_tiles()
        priority = -100000
        for p in attackables:
            e = self.rc.get_tile_building_id(p)
            bb = self.rc.get_tile_builder_bot_id(p)

            if e is not None:
                if self.rc.get_team(e) == self.rc.get_team():
                    continue
                entt = self.rc.get_entity_type(e)
                if priorities[entt] < 0: continue
                if priorities[entt] > priority and self.rc.can_fire(p):
                    priority = priorities[entt]
                    self.best_target = p
            if bb is not None:
                if self.rc.get_team(bb) == self.rc.get_team():
                    continue
                if priorities[EntityType.BUILDER_BOT] < 0: continue
                if priorities[EntityType.BUILDER_BOT] > priority and self.rc.can_fire(p):
                    priority = priorities[EntityType.BUILDER_BOT]
                    self.best_target = p

        pass

    def turn(self):
        if self.best_target is not None:
            self.rc.fire(self.best_target)
        pass

    def end_turn(self):
        # Compute symmetry if time left
        pass

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
    EntityType.HARVESTER: 10,
    EntityType.FOUNDRY: 100,
    EntityType.ROAD: 1,
    EntityType.BARRIER: 1,
    EntityType.MARKER: -10,
}

class SimpleShooter(Bot):
    def __init__(self, rc: Controller):
        super().__init__(rc)
        self.best_target = None

    def start_turn(self):
        self.best_target = None

        entities = self.rc.get_nearby_entities()
        priority = -100000
        for e in entities:
            if self.rc.get_team(e) == self.rc.get_team():
                continue
            entt = self.rc.get_entity_type(e)
            if priorities[entt] > priority:
                priority = priorities[entt]
                self.best_target = self.rc.get_position(e)
        pass

    def turn(self):
        if self.best_target is not None:
            if self.rc.can_fire(self.best_target):
                self.rc.fire(self.best_target)
        pass

    def end_turn(self):
        # Compute symmetry if time left
        pass

import random

from cambc import Controller, Direction, EntityType, Environment, Position

import pathfind
import sense

from helpers import RANDOM_SEED
from core import Core
from builder import BuilderBot
from launcher import Launcher
from simple_shooter import SimpleShooter


class Player:
    def __init__(self):
        self.brain = None
        pass

    def run(self, rc: Controller):
        entt = rc.get_entity_type()

        if self.brain is None:
            random.seed(RANDOM_SEED + rc.get_id())
            if entt == EntityType.CORE:
                self.brain = Core(rc)
            elif entt == EntityType.LAUNCHER:
                self.brain = Launcher(rc)
            elif entt == EntityType.GUNNER:
                self.brain = SimpleShooter(rc)
            elif entt == EntityType.SENTINEL:
                self.brain = SimpleShooter(rc)
            elif entt == EntityType.BREACH:
                self.brain = SimpleShooter(rc) # TODO account for splash
            elif entt == EntityType.BUILDER_BOT:
                self.brain = BuilderBot(rc)
        
        self.brain.start_turn()
        self.brain.turn()
        self.brain.end_turn()

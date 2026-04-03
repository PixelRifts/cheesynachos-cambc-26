import random

from cambc import Controller, Direction, EntityType, Environment, Position

import pathfind

from helpers import RANDOM_SEED
from core import Core
from builder import BuilderBot
from launcher import Launcher
# from simple_shooter import SimpleShooter
# from launcher import Launcher

class Player:
    def __init__(self):
        self.brain = None
        pass

    def run(self, rc: Controller):
        if self.brain is None:
            entt = rc.get_entity_type()
            random.seed(RANDOM_SEED + rc.get_id())
            if entt == EntityType.CORE:
                self.brain = Core(rc)
            elif entt == EntityType.BUILDER_BOT:
                self.brain = BuilderBot(rc)
            elif entt == EntityType.LAUNCHER:
                self.brain = Launcher(rc)
        
        self.brain.start_turn()
        self.brain.turn()
        self.brain.end_turn()

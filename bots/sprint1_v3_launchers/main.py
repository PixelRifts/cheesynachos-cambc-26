import random

from cambc import Controller, Direction, EntityType, Environment, Position

from launcher import Launcher
import pathfind
import sense

from helpers import RANDOM_SEED
from core import Core
from builder import BuilderBot


class Player:
    def __init__(self):
        self.brain = None
        random.seed(RANDOM_SEED)
        pass

    def run(self, rc: Controller):
        etype = rc.get_entity_type()

        if self.brain is None:
            if etype == EntityType.CORE:
                self.brain = Core(rc)
            elif etype == EntityType.LAUNCHER:
                self.brain = Launcher(rc)
            elif etype == EntityType.BUILDER_BOT:
                self.brain = BuilderBot(rc)
        
        self.brain.start_turn()
        self.brain.turn()
        self.brain.end_turn()

import random

from cambc import Controller, Direction, EntityType, Environment, Position

import pathfind
import gc

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
        gc.disable()
        if self.brain is None:
            start = rc.get_cpu_time_elapsed()
            entt = rc.get_entity_type()
            random.seed(RANDOM_SEED + rc.get_id())
            if entt == EntityType.CORE:
                self.brain = Core(rc)
            elif entt == EntityType.BUILDER_BOT:
                self.brain = BuilderBot(rc)
            elif entt == EntityType.LAUNCHER:
                self.brain = Launcher(rc)
            elif entt == EntityType.GUNNER:
                self.brain = SimpleShooter(rc)
            elif entt == EntityType.SENTINEL:
                self.brain = SimpleShooter(rc)
            print('total init time =', rc.get_cpu_time_elapsed()-start)
        
        
        start = rc.get_cpu_time_elapsed()
        self.brain.start_turn()
        print('start turn time =', rc.get_cpu_time_elapsed()-start)
        start = rc.get_cpu_time_elapsed()
        self.brain.turn()
        print('main turn time =', rc.get_cpu_time_elapsed()-start)
        
        self.brain.end_turn()
        
        
import random

import cProfile
import sys
import pstats

from cambc import Controller, Direction, EntityType, Environment, Position

import pathfind
import gc

from helpers import RANDOM_SEED
from core import Core
from builder import BuilderBot
from launcher import Launcher
from sentinel import Sentinel
from gunner import Gunner

profiler = cProfile.Profile()

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
                self.brain = Gunner(rc)
            elif entt == EntityType.SENTINEL:
                self.brain = Sentinel(rc)
            print('total init time =', rc.get_cpu_time_elapsed()-start)
        
        proffed = False
        if rc.get_entity_type() == EntityType.BUILDER_BOT:
            profiler.enable()
            proffed = True

        start = rc.get_cpu_time_elapsed()
        self.brain.start_turn()
        print('start turn time =', rc.get_cpu_time_elapsed()-start)
        

        start = rc.get_cpu_time_elapsed()
        self.brain.turn()
        print('main turn time =', rc.get_cpu_time_elapsed()-start)

        self.brain.end_turn()
        
        if proffed:
            profiler.disable()
            # stats = pstats.Stats(profiler, stream=sys.stderr)
            # stats.sort_stats("cumtime").print_stats()

            if rc.get_current_round() % 100 == 0:
                profiler.dump_stats("profile.prof")
        
        
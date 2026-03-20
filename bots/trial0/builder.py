import sys
import pathfind
import random

import sense
import visualize
from helpers import DIRECTIONS, cardinal_direction_to

from enum import Enum
from bot import Bot
from cambc import Controller, Direction, EntityType, Environment, Position, GameConstants

EXPLORE_TIMEOUT = 8

class BotJob(Enum):
    ECONOMY = "Economy"
    DEFENCE = "Defence"

class BotState(Enum):
    # States for Econ Job
    ECON_EXPLORE = "Explore" # Random Movement until things of importance are seen
    ECON_TARGET  = "Target"  # Unclaimed ore spotted, Moving towards it
    ECON_CONNECT = "Connect" # Connecting Unclaimed ore to core
    ECON_ENSURE  = "Ensure"  # Ensuring validity of conveyor path

    # States for Defece Job
    DEF_CORE_DEFENCE = "Core Defence"
    DEF_TODO = "Todo"

class BuilderBot(Bot):
    def __init__(self, rc: Controller):
        super().__init__(rc)
        self.job = BotJob.ECONOMY
        self.state = BotState.ECON_EXPLORE
        self.sense = sense.Sense(rc)
        
        buildings = rc.get_nearby_buildings(3)
        for b in buildings:
            if rc.get_entity_type(b) == EntityType.CORE:
                self.core_pos = rc.get_position(b)
                break
        
        self.explore_dir = self.core_pos.direction_to(rc.get_position())
        self.explore_timeout = EXPLORE_TIMEOUT
        self.explore_ore_target = None
        self.state_turn_counter = 0
        self.pathfind_target = None

    def start_turn(self):
        self.sense.update()

    def turn(self):
        match self.state:
            case BotState.ECON_EXPLORE:
                self.econ_explore()
            case BotState.ECON_TARGET:
                self.econ_target()
            case BotState.ECON_CONNECT:
                self.econ_connect()
            case BotState.ECON_ENSURE:
                self.econ_ensure()

            case BotState.DEF_CORE_DEFENCE:
                self.def_core_defence()
            case BotState.DEF_TODO:
                pass
        
        # pathfind.cardinal_pathfind_to(self.rc, Position(6, 7), False)

    def end_turn(self):
        # Compute symmetry if time left
        # DEBUG: sensing
        # visualize.visualize_map_minimal(self.rc, self.sense)
        self.state_turn_counter += 1

    # Econ Turns
    def econ_explore(self):
        # Check for ore
        if self.sense.in_vision_nearest_ore is not None and \
                not self.sense.get_building_type(self.sense.in_vision_nearest_ore) == EntityType.HARVESTER:
           self.state_turn_counter = 0
           self.state = BotState.ECON_TARGET
           
           self.explore_ore_target = self.sense.in_vision_nearest_ore
           self.pathfind_target = self.sense.in_vision_nearest_ore
           return

        # Actual Movement
        self.explore_timeout -= 1
        if self.explore_timeout == 0:
            self.explore_timeout = EXPLORE_TIMEOUT
            self.explore_dir = biased_random_dir(self.rc)
            
        next_pos = self.rc.get_position().add(self.explore_dir)
        if not pathfind.is_in_map(next_pos, self.rc.get_map_width(), self.rc.get_map_height()):
            self.explore_dir = biased_random_dir(self.rc)
            return

        if self.rc.can_move(self.explore_dir):
            self.rc.move(self.explore_dir)
        elif self.rc.is_tile_empty(next_pos):
            if self.rc.can_build_road(next_pos):
                self.rc.build_road(next_pos)
                self.rc.move(self.explore_dir)
        else:
            self.explore_dir = biased_random_dir(self.rc)

    def econ_target(self):
        if self.sense.get_building_type(self.explore_ore_target) == EntityType.HARVESTER:
            self.state_turn_counter = 0
            self.state = BotState.ECON_EXPLORE

        if not self.rc.get_position().distance_squared(self.explore_ore_target) == 0:
            pathfind.fast_pathfind_to(self.rc, self.pathfind_target)
        else:
            self.state_turn_counter = 0
            self.state = BotState.ECON_CONNECT
    
            # Replace with finding good spot nearest core
            d1 = self.core_pos.direction_to(self.explore_ore_target)
            p1 = self.core_pos.add(d1)
            d2 = p1.direction_to(self.explore_ore_target)
            p2 = self.core_pos.add(d2)
            
            self.explore_first_turn_flag = True
            self.pathfind_target = p2
            
        pass
    
    def econ_connect(self):
        if self.state_turn_counter != 2:
            if pathfind.cardinal_pathfind_to(self.rc, self.pathfind_target, False):
                self.state_turn_counter = 0
                self.state = BotState.ECON_EXPLORE
        else:
            if self.rc.can_build_harvester(self.explore_ore_target):
                self.rc.build_harvester(self.explore_ore_target)
        if self.state_turn_counter == 1:
            # One away from ore
            if self.rc.get_entity_type(self.rc.get_tile_building_id(self.explore_ore_target)) == EntityType.ROAD:
                self.rc.destroy(self.explore_ore_target)
        pass

    def econ_ensure(self):
        pass

    def def_core_defence(self):
        pass




# TODO Move to helpers.py
def biased_random_dir(rc: Controller) -> Direction:
    c = random.randint(0, 10)
    if c < 3:
        return rc.get_position().direction_to(Position(rc.get_map_width() // 2, rc.get_map_height() // 2))
    return random.choice(DIRECTIONS)

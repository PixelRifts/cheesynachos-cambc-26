import sys
import pathfind
import random

from helpers import is_friendly_transport, is_pos_editable, is_pos_pathable, get_building_type, is_adjacent, is_adjacent_with_diag, cardinal_direction_to, biased_random_dir, is_in_map, guess_symmetry, get_symmetric, DIRECTIONS, CARDINAL_DIRECTIONS

from enum import Enum
from bot import Bot
from cambc import Controller, Direction, EntityType, Environment, Position, GameConstants

BOT_EXPLORE_TIMEOUT = 8

class BotState(Enum):
    ECON_EXPLORE = "Explore"
    ECON_TARGET  = "Target"
    ECON_CONNECT = "Connect"

class BuilderBot(Bot):
    def __init__(self, rc: Controller):
        super().__init__(rc)
        
        self.core_pos = self.rc.get_position()
        buildings = rc.get_nearby_buildings(3)
        for b in buildings:
            if rc.get_entity_type(b) == EntityType.CORE:
                self.core_pos = rc.get_position(b)
                break
        self.map_center_pos = Position(self.rc.get_map_width() // 2, self.rc.get_map_height() // 2)

        self.switch_state(BotState.ECON_EXPLORE)
        self.econ_explore_dir = rc.get_position().direction_to(self.map_center_pos)

    def reset_state_variables(self):
        self.pathfind_target: Position = None
        self.econ_explore_dir: Direction = Direction.CENTRE
        self.econ_explore_timeout: int = BOT_EXPLORE_TIMEOUT
        self.econ_target_ore: Position = None
        
        # Some states want sub-states
        self.state_custom_sub_state: int = 0
        # self.
    
    def switch_state(self, state: BotState):
        self.state = state
        self.state_turn_counter = 0
        self.reset_state_variables()

    def start_turn(self):
        pass
    
    def turn(self):
        match self.state:
            case BotState.ECON_EXPLORE:
                self.econ_explore()
            case BotState.ECON_TARGET:
                self.econ_target()
            case BotState.ECON_CONNECT:
                self.econ_connect()
    
    def econ_explore(self):
        # Possibly Find and Target Ore TITANIUM
        for pos in self.rc.get_nearby_tiles():
            env = self.rc.get_tile_env(pos)
            if env == Environment.ORE_TITANIUM:
                (should_connect, dir) = self.should_connect_to_ore(pos)
                if should_connect:
                    self.switch_state(BotState.ECON_TARGET)
                    self.econ_target_ore = pos
                    self.pathfind_target = pos.add(dir)

        # Timeout direction switch
        self.econ_explore_timeout -= 1
        if self.econ_explore_timeout == 0:
            self.econ_explore_timeout = BOT_EXPLORE_TIMEOUT
            self.econ_explore_dir = biased_random_dir(self.rc)

        # Actual Move
        next_pos = self.rc.get_position().add(self.econ_explore_dir)
        if not is_in_map(next_pos, self.rc.get_map_width(), self.rc.get_map_height()):
            self.econ_explore_dir = biased_random_dir(self.rc)
            return

        if self.rc.can_move(self.econ_explore_dir):
            self.rc.move(self.econ_explore_dir)
        elif self.rc.is_tile_empty(next_pos):
            if self.rc.can_build_road(next_pos):
                self.rc.build_road(next_pos)
                if self.rc.can_move(self.econ_explore_dir):
                    self.rc.move(self.econ_explore_dir)
        else:
            self.econ_explore_dir = biased_random_dir(self.rc)
        

    def econ_target(self):
        (should_connect, dir) = self.should_connect_to_ore(self.econ_target_ore)
        if not should_connect:
            self.switch_state(BotState.ECON_EXPLORE)
            self.econ_explore_dir = biased_random_dir(self.rc)
            return

        if is_adjacent(self.rc.get_position(), self.econ_target_ore):
            if not self.rc.is_tile_empty(self.econ_target_ore) and get_building_type(self.rc, self.econ_target_ore) != EntityType.HARVESTER:
                if self.rc.can_destroy(self.econ_target_ore):
                    self.rc.destroy(self.econ_target_ore)
            if self.rc.can_build_harvester(self.econ_target_ore):
                self.rc.build_harvester(self.econ_target_ore)

            self.switch_state(BotState.ECON_CONNECT)
            self.pathfind_target = self.core_pos
        else:
            pathfind.fast_pathfind_to(self.rc, self.pathfind_target)

    def econ_connect(self):
        # if self.state_custom_sub_state == 0:
        #     new_conveyor_pos = self.rc.get_position()
        #     if self.rc.can_destroy(new_conveyor_pos):
        #         self.rc.destroy(new_conveyor_pos)
        #     the_dir = cardinal_direction_to(new_conveyor_pos, self.core_pos)
        #     if self.rc.can_build_conveyor(new_conveyor_pos, the_dir):
        #         self.rc.build_conveyor(new_conveyor_pos, the_dir)
        #         self.state_custom_sub_state = 1

        if pathfind.cardinal_pathfind_to(self.rc, self.pathfind_target, True):
            self.switch_state(BotState.ECON_EXPLORE)
            self.econ_explore_dir = biased_random_dir(self.rc)

    def end_turn(self):
        pass

    def should_connect_to_ore(self, pos: Position) -> (bool, Direction):
        if pos is None: return (False, Direction.CENTRE)
        if not self.rc.is_in_vision(pos): return (True, Direction.CENTRE)
        
        bldg = self.rc.get_tile_building_id(pos)
        has_free_side = False
        already_siphoned = False
        ret: Direction = None
        for d in CARDINAL_DIRECTIONS:
            p = pos.add(d)
            if not is_in_map(p, self.rc.get_map_width(), self.rc.get_map_height()): continue
            if not self.rc.is_in_vision(p): continue
            if is_friendly_transport(self.rc, p):
                already_siphoned = True
                break
            if self.rc.is_tile_empty(p) or is_pos_editable(self.rc, p):
                has_free_side = True
                ret = d
                break
        return (has_free_side and not already_siphoned, ret)

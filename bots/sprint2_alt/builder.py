import sys
import pathfind
import random

from helpers import is_adjacent, is_adjacent_with_diag, cardinal_direction_to, biased_random_dir, is_in_map, guess_symmetry, get_symmetric, DIRECTIONS, CARDINAL_DIRECTIONS

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
        self.switch_state(BotState.ECON_EXPLORE)

    def reset_state_variables(self):
        self.pathfind_target: Position = None
        self.econ_explore_dir: Direction = Direction.CENTRE
        self.econ_explore_timeout: int = 0
    
    def switch_state(self, state: BotState):
        self.state = BotState.ECON_EXPLORE
        self.state_turn_counter = 0
        self.reset_state_variables()

    def start_turn(self):
        pass
    
    def turn(self):
        pathfind.fast_pathfind_to(self.rc, Position(37, 2))

    def end_turn(self):
        pass

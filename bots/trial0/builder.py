
import pathfind
import random

from enum import Enum
from bot import Bot
from cambc import Controller, Direction, EntityType, Environment, Position

DIRECTIONS = [d for d in Direction if d != Direction.CENTRE]

class BotJob(Enum):
    ECONOMY = "Economy"
    DEFENCE = "Defence"

class BotState(Enum):
    # States for Econ Job
    ECON_EXPLORE = "Explore"
    ECON_CONNECT = "Connect"
    ECON_ENSURE  = "Ensure"

    # States for Defece Job
    DEF_CORE_DEFENCE = "Core Defence"
    DEF_TODO = "Todo"

class BuilderBot(Bot):
    def __init__(self, rc: Controller):
        super().__init__(rc)
        self.core = rc.get_position()
        self.job = BotJob.ECONOMY
        self.state = BotState.ECON_EXPLORE

        self.explore_dir = random.choice(DIRECTIONS)

    def start_turn(self):
        # TODO: senses update
        pass

    def turn(self):
        match self.state:
            case BotState.ECON_EXPLORE:
                self.econ_explore()
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
        pass

    # Econ Turns
    def econ_explore(self):
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
    
    def econ_connect(self):
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
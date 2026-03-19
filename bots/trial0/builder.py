
import pathfind

from bot import Bot
from cambc import Controller, Direction, EntityType, Environment, Position

class BuilderBot(Bot):
    def __init__(self, rc: Controller):
        super().__init__(rc)
        self.core = rc.get_position()

    def start_turn(self):
        # TODO: senses update
        pass

    def turn(self):
        pathfind.cardinal_pathfind_to(self.rc, Position(6, 7), False)
        
        for d in Direction:
            check_pos = self.rc.get_position().add(d)
            if self.rc.can_build_harvester(check_pos):
                self.rc.build_harvester(check_pos)
                break
            

    def end_turn(self):
        # Compute symmetry if time left
        pass
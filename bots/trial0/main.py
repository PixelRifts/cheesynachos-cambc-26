import random

from cambc import Controller, Direction, EntityType, Environment, Position

import pathfind
import sense


DIRECTIONS = [d for d in Direction if d != Direction.CENTRE]

class Player:
    def __init__(self):
        self.count = 0
        pass

    def run(self, rc: Controller):
        etype = rc.get_entity_type()
        
        start_turn(rc)
        if etype == EntityType.CORE:
            if self.count < 12:
                run_core(rc)
                self.count += 1
                
        elif etype == EntityType.BUILDER_BOT:
            run_builder(rc)
        end_turn(rc)


def start_turn(rc: Controller):
    pass

def end_turn(rc: Controller):
    pass

def run_core(rc: Controller):
    spawn_pos = rc.get_position().add(random.choice(DIRECTIONS))
    if rc.can_spawn(spawn_pos):
        rc.spawn_builder(spawn_pos)

def run_builder(rc: Controller):
    # if we are adjacent to an ore tile, build a harvester on it
    # for d in Direction:
    #     check_pos = rc.get_position().add(d)
    #     if rc.can_build_harvester(check_pos):
    #         rc.build_harvester(check_pos)
    #         break
    
    # # move in a random direction
    # move_dir = random.choice(DIRECTIONS)
    # move_pos = rc.get_position().add(move_dir)

    # # we need to place a conveyor or road to stand on, before we can move onto a tile
    # if rc.can_build_road(move_pos):
    #     rc.build_road(move_pos)
    # if rc.can_move(move_dir):
    #     rc.move(move_dir)

    # # place a marker on an adjacent tile with the current round number
    # marker_pos = rc.get_position().add(random.choice(DIRECTIONS))
    # if rc.can_place_marker(marker_pos):
    #     rc.place_marker(marker_pos, rc.get_current_round())
    pathfind.pathfind_to(rc, Position(6, 5))

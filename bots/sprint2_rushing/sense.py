import sys
import math
import random

from helpers import get_symmetric, Symmetry
from collections import deque
from typing import Optional, List
from enum import Enum
from cambc import Controller, Environment, Position, Direction, EntityType

_BUILDING_OFFSET = 4

_ENTITY_TYPE_TO_VALUE = {
    EntityType.CORE: 4,
    EntityType.GUNNER: 5,
    EntityType.SENTINEL: 6,
    EntityType.BREACH: 7,
    EntityType.LAUNCHER: 8,
    EntityType.CONVEYOR: 9,
    EntityType.SPLITTER: 10,
    EntityType.ARMOURED_CONVEYOR: 11,
    EntityType.BRIDGE: 12,
    EntityType.HARVESTER: 13,
    EntityType.FOUNDRY: 14,
    EntityType.ROAD: 15,
    EntityType.BARRIER: 16,
    EntityType.MARKER: 17,
}
_VALUE_TO_ENTITY_TYPE = {v: k for k, v in _ENTITY_TYPE_TO_VALUE.items()}

_ENV_TYPE_TO_VALUE = {
    Environment.EMPTY: 0,
    Environment.WALL: 1,
    Environment.ORE_TITANIUM: 2,
    Environment.ORE_AXIONITE: 3,
}


class SenseState:
    def __init__(self):
        pass

    def setup(self, rc: Controller):
        self.width = rc.get_map_width()
        self.height = rc.get_map_height()
        
        self.nearest_enemy_transport: Position = None
        self.min_enemy_transport_dist = 1000000

        self.enemy_core_found: Position = None
        self.symmetries_possible = [ Symmetry.ROTATIONAL, Symmetry.HORIZONTAL, Symmetry.VERTICAL ]
        self.grid: List[List[Optional[int]]] = [
            [None for _ in range(self.width)] 
            for _ in range(self.height)
        ]
        self.env_grid: List[List[Optional[int]]] = [
            [None for _ in range(self.width)] 
            for _ in range(self.height)
        ]
        self.ti_tracker = deque(maxlen=10)
    
    def reset_frame(self, rc: Controller):
        self.nearest_enemy_transport: Position = None
        self.min_enemy_transport_dist = 1000000
        self.am_seeing_sentinel = False

sense_state = SenseState()

def update_sense(rc: Controller):
    (ti, ax) = rc.get_global_resources()
    sense_state.ti_tracker.append(ti)
    sense_state.reset_frame(rc)
    for pos in rc.get_nearby_tiles():
        update_tile(rc, pos)

def update_tile(rc: Controller, pos: Position):
    bldg = rc.get_tile_building_id(pos)
    if bldg is not None:
        entt = rc.get_entity_type(bldg)
        allied = rc.get_team(bldg) == rc.get_team()
        if not allied:
            if entt == EntityType.CORE:
                sense_state.enemy_core_found = pos
            if entt == EntityType.CONVEYOR or entt == EntityType.SPLITTER or entt == EntityType.BRIDGE:
                d = pos.distance_squared(rc.get_position())
                if d < sense_state.min_enemy_transport_dist:
                    sense_state.min_enemy_transport_dist = d
                    sense_state.nearest_enemy_transport = pos
        else:
            if entt == EntityType.SENTINEL:
                sense_state.am_seeing_sentinel = True

    env = rc.get_tile_env(pos)
    dist = rc.get_position().distance_squared(pos)
    sense_state.env_grid[pos.y][pos.x] = _ENV_TYPE_TO_VALUE[env]

    # Eliminate symmetries
    if len(sense_state.symmetries_possible) > 1:
        to_elim = []
        for sym in sense_state.symmetries_possible:
            test = get_symmetric(pos, rc.get_map_width(), rc.get_map_height(), sym)
            env_here = sense_state.env_grid[test.y][test.x]
            if env_here is not None:
                if env_here != _ENV_TYPE_TO_VALUE[env]:
                    to_elim.append(sym)
        sense_state.symmetries_possible = [x for x in sense_state.symmetries_possible if x not in to_elim]

def ti_ever_increased() -> bool:
    it = iter(sense_state.ti_tracker)
    prev = next(it, None)

    for cur in it:
        if cur > prev:
            return True
        prev = cur

    return False
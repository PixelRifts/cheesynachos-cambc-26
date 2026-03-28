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
        self.attack_replace_blacklist = set()
        self.feed_graph: Dict[Position, Set[Position]] = {}
        self.reverse_feed_graph: Dict[Position, Set[Position]] = {}

    def reset_frame(self, rc: Controller):
        self.nearest_enemy_transport: Position = None
        self.min_enemy_transport_dist = 1000000

sense_state = SenseState()

def draw_feed_graph(rc: Controller):
    drawn_nodes = set()

    for src, dsts in sense_state.feed_graph.items():
        # if src not in drawn_nodes:
            # rc.draw_indicator_dot(src, 0, 255, 0)
            # drawn_nodes.add(src)

        for dst in dsts:
            # if dst not in drawn_nodes:
                # rc.draw_indicator_dot(dst, 0, 150, 255)
                # drawn_nodes.add(dst)

            rc.draw_indicator_line(src, dst, 255, 255, 0)

def update_sense(rc: Controller):
    # sense_state.feed_graph.clear()
    # sense_state.reverse_feed_graph.clear()

    (ti, ax) = rc.get_global_resources()
    sense_state.ti_tracker.append(ti)
    sense_state.reset_frame(rc)

    nearby_tiles = rc.get_nearby_tiles()
    for pos in nearby_tiles:
        remove_edges_from(pos)

    for pos in nearby_tiles:
        update_tile(rc, pos)
    
    for unit in rc.get_nearby_units():
        p = rc.get_position(unit)
        if not rc.is_in_vision(p): continue
        entt = rc.get_entity_type(unit)
        allied = rc.get_team(unit) == rc.get_team()
        if allied and (entt == EntityType.SENTINEL or entt == EntityType.GUNNER):
            sense_state.attack_replace_blacklist.update(get_feeders_of(p))

def update_tile(rc: Controller, pos: Position):
    bldg = rc.get_tile_building_id(pos)

    if bldg is not None:
        entt = rc.get_entity_type(bldg)
        allied = rc.get_team(bldg) == rc.get_team()
        if not allied:
            if entt == EntityType.CORE:
                sense_state.enemy_core_found = pos
            elif entt == EntityType.CONVEYOR or entt == EntityType.SPLITTER or entt == EntityType.BRIDGE:
                d = pos.distance_squared(rc.get_position())
                if d < sense_state.min_enemy_transport_dist:
                    sense_state.min_enemy_transport_dist = d
                    sense_state.nearest_enemy_transport = pos
        
        if entt == EntityType.CONVEYOR or entt == EntityType.SPLITTER or entt == EntityType.BRIDGE:
            outputs = get_outputs(rc, pos, entt, bldg)
            for out in outputs:
                if out is not None:
                    add_edge(pos, out)

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



def add_edge(src: Position, dst: Position):
    sense_state.feed_graph.setdefault(src, set()).add(dst)
    sense_state.reverse_feed_graph.setdefault(dst, set()).add(src)

def remove_edges_from(src: Position):
    if src in sense_state.feed_graph:
        for dst in sense_state.feed_graph[src]:
            if dst in sense_state.reverse_feed_graph:
                sense_state.reverse_feed_graph[dst].discard(src)
                if not sense_state.reverse_feed_graph[dst]:
                    del sense_state.reverse_feed_graph[dst]
        del sense_state.feed_graph[src]


def get_outputs(rc: Controller, pos: Position, etype: EntityType, bldg: int):
    if etype == EntityType.CONVEYOR:
        d = rc.get_direction(bldg)
        return [pos.add(d)]

    elif etype == EntityType.BRIDGE:
        return [rc.get_bridge_target(bldg)]

    elif etype == EntityType.SPLITTER:
        primary = rc.get_direction(bldg)
        return [
            pos.add(primary),
            pos.add(primary.rotate_left().rotate_left()),
            pos.add(primary.rotate_right().rotate_right()),
        ]

    return []

def get_feeders_of(pos: Position):
    result = set()
    stack = [pos]

    while stack:
        cur = stack.pop()
        for src in sense_state.reverse_feed_graph.get(cur, []):
            if src not in result:
                result.add(src)
                stack.append(src)

    return result



def ti_ever_increased() -> bool:
    it = iter(sense_state.ti_tracker)
    prev = next(it, None)

    for cur in it:
        if cur > prev:
            return True
        prev = cur

    return False

def eliminate_next_symmetry():
    if len(sense_state.symmetries_possible) > 1:
        del sense_state.symmetries_possible[0]


from array import array

from helpers import *

from typing import Optional, Set, Dict
from enum import Enum
from cambc import Controller, Environment, Position, Direction, EntityType

_ENVIRONMENT_TO_VALUE = {
    None: 0,
    Environment.EMPTY: 1,
    Environment.WALL: 2,
    Environment.ORE_AXIONITE: 3,
    Environment.ORE_TITANIUM: 4,
}
_VALUE_TO_ENVIRONMENT = {v: k for k, v in _ENVIRONMENT_TO_VALUE.items()}

_ENTITY_TYPE_TO_VALUE = {
    None: 0,
    EntityType.CORE: 2,
    EntityType.GUNNER: 3,
    EntityType.SENTINEL: 4,
    EntityType.BREACH: 5,
    EntityType.LAUNCHER: 6,
    EntityType.CONVEYOR: 7,
    EntityType.SPLITTER: 8,
    EntityType.ARMOURED_CONVEYOR: 9,
    EntityType.BRIDGE: 10,
    EntityType.HARVESTER: 11,
    EntityType.FOUNDRY: 12,
    EntityType.ROAD: 13,
    EntityType.BARRIER: 14,
    EntityType.MARKER: 15,
}
_VALUE_TO_ENTITY_TYPE = {v: k for k, v in _ENTITY_TYPE_TO_VALUE.items()}

class Sense:
    def __init__(self, rc: Controller):
        self.rc = rc

        self.map_width = rc.get_map_width()
        self.map_height = rc.get_map_height()
        self.size = self.map_width * self.map_height

        self.map = array('H', [0] * self.size)
        self.env_index: Dict[int, Set[Position]] = {v: set() for v in _ENVIRONMENT_TO_VALUE.values()}
        self.entt_index: Dict[int, Set[Position]] = {v: set() for v in _ENTITY_TYPE_TO_VALUE.values()}
        self.ally_builders:  Set[Position] = set()
        self.enemy_builders: Set[Position] = set()
        self.enemy_core_found: Position = None

        if self.map_width > self.map_height:
            self.symmetries_possible = [ Symmetry.HORIZONTAL, Symmetry.ROTATIONAL, Symmetry.VERTICAL ]
        elif self.map_height > self.map_width:
            self.symmetries_possible = [ Symmetry.VERTICAL, Symmetry.ROTATIONAL, Symmetry.HORIZONTAL ]
        else:
            self.symmetries_possible = [ Symmetry.ROTATIONAL, Symmetry.HORIZONTAL, Symmetry.VERTICAL ]
        
    def idx(self, p: Position) -> int:
        return p.x + self.map_width * p.y

    def set_env(self, p: Position, env: Environment):
        i = self.idx(p)
        env_id = _ENVIRONMENT_TO_VALUE[env]
        self.env_index[env_id].add(p)
        self.map[i] = (env_id << 8) | (self.map[i] & 0xFF)

    def set_entt(self, p: Position, entity: EntityType, allied: bool):
        i = self.idx(p)
        entt_type_id = _ENTITY_TYPE_TO_VALUE[entity]
        self.entt_index[entt_type_id].add(p)
        self.map[i] = (self.map[i] & 0xFF00) | (entt_type_id << 1) | allied

    def set_entt_and_env(self, p: Position, entity: EntityType, env: Environment, allied: bool):
        i = self.idx(p)

        entt_type_id = _ENTITY_TYPE_TO_VALUE[entity]
        env_id = _ENVIRONMENT_TO_VALUE[env]
        self.entt_index[entt_type_id].add(p)
        self.env_index[env_id].add(p)

        self.map[i] = (env_id << 8) | (entt_type_id << 1) | allied

    def get_env(self, p: Position):
        return _VALUE_TO_ENVIRONMENT[(self.map[self.idx(p)] >> 8) & 0xFF]

    def get_entity(self, pos: Position):
        return _VALUE_TO_ENTITY_TYPE.get((self.map[self.idx(pos)] >> 1) & 0x7F)
    
    def is_allied(self, pos: Position):
        return self.map[self.idx(pos)] & 1

    def is_seen(self, pos: Position):
        return self.map[self.idx(pos)] != 0

    def update(self):
        for s in self.env_index.values():
            s.clear()
        for s in self.entt_index.values():
            s.clear()
        self.ally_builders.clear()
        self.enemy_builders.clear()
        
        nearby_tiles = self.rc.get_nearby_tiles()
        for t in nearby_tiles:
            # Save Env and Buildings
            env = self.rc.get_tile_env(t)
            bldg = self.rc.get_tile_building_id(t)
            entt = None if bldg is None else self.rc.get_entity_type(bldg)
            allied = True if bldg is None else self.rc.get_team(bldg) == self.rc.get_team()
            self.set_entt_and_env(t, entt, env, allied)

            # Special cases
            if not allied and entt == EntityType.CORE and self.enemy_core_found is None:
                enemy_core_found = self.rc.get_position(bldg)

            # Save Builder Bots
            bb = self.rc.get_tile_builder_bot_id(t)
            if bb is not None:
                if self.rc.get_team(bb) == self.rc.get_team():
                    self.ally_builders.add(t)
                else:
                    self.enemy_builders.add(t)

            # Crack Symmetry
            if len(self.symmetries_possible) > 1:
                to_elim = []
                for sym in self.symmetries_possible:
                    test = get_symmetric(t, self.map_width, self.map_height, sym)
                    env_here = self.get_env(test)
                    if env_here != None:
                        if env_here != _ENVIRONMENT_TO_VALUE[env]:
                            to_elim.append(sym)
                self.symmetries_possible = [x for x in self.symmetries_possible if x not in to_elim]
            

    def visualize(self):
        for i, val in enumerate(self.map):
            if val == 0:
                continue

            x = i % self.map_width
            y = i // self.map_width
            pos = Position(x, y)

            env = (val >> 8) & 0xFF
            ent = (val >> 1) & 0x7F
            allied = val & 1

            # simple coloring
            if env:
                self.rc.draw_indicator_dot(pos, 0, 255, 0)

            if ent:
                if allied:
                    self.rc.draw_indicator_dot(pos, 0, 0, 255)
                else:
                    self.rc.draw_indicator_dot(pos, 255, 0, 0)

            # optional: draw grid connections
            if x + 1 < self.map_width:
                self.rc.draw_indicator_line(
                    pos,
                    Position(x+1, y+1),
                    50, 50, 50
                )
            if y + 1 < self.map_height:
                self.rc.draw_indicator_line(
                    pos,
                    Position(x, y+1),
                    50, 50, 50
                )

from array import array

from helpers import *

from collections import deque
from typing import Optional, Set, Dict
from enum import Enum
from cambc import Controller, Environment, Position, Direction, EntityType

ENVIRONMENT_TO_VALUE = {
    None: 0,
    Environment.EMPTY: 1,
    Environment.WALL: 2,
    Environment.ORE_AXIONITE: 3,
    Environment.ORE_TITANIUM: 4,
}
_VALUE_TO_ENVIRONMENT = {v: k for k, v in ENVIRONMENT_TO_VALUE.items()}

ENTITY_TYPE_TO_VALUE = {
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
_VALUE_TO_ENTITY_TYPE = {v: k for k, v in ENTITY_TYPE_TO_VALUE.items()}

DIRECTION_TO_VALUE = {
    None: 0,
    Direction.CENTRE: 0,
    Direction.NORTH: 1,
    Direction.NORTHEAST: 2,
    Direction.EAST: 3,
    Direction.SOUTHEAST: 4,
    Direction.SOUTH: 5,
    Direction.SOUTHWEST: 6,
    Direction.WEST: 7,
    Direction.NORTHWEST: 8,
}
_VALUE_TO_DIRECTION = {v: k for k, v in DIRECTION_TO_VALUE.items()}

TURRET_ATTACK_COSTS = {
    EntityType.GUNNER:   10,
    EntityType.SENTINEL: 6,
    EntityType.BREACH:   40,
    EntityType.LAUNCHER: 10
}

class Sense:
    def __init__(self, rc: Controller):
        self.rc = rc

        self.map_width = rc.get_map_width()
        self.map_height = rc.get_map_height()
        self.size = self.map_width * self.map_height
        self.nearby_tiles = []

        self.map = array('H', [0] * self.size)
        self.env_index: Dict[int, Set[Position]] = {v: set() for v in ENVIRONMENT_TO_VALUE.values()}
        self.entt_index: Dict[int, Set[Position]] = {v: set() for v in ENTITY_TYPE_TO_VALUE.values()}
        self.ally_builders:  Set[Position] = set()
        self.enemy_builders: Set[Position] = set()
        self.transport_attack_blacklist: Set[Position] = set()
        self.feed_graph: Dict[Position, Set[Position]] = {}
        self.reverse_feed_graph: Dict[Position, Set[Position]] = {}
        self.enemy_core_found: Position = None
        self.heal_targets: Set[Position] = set()
        self.enemy_turrets: Set[Position] = set()
        
        self.ti_tracker = deque(maxlen=16)
        self.ax_tracker = deque(maxlen=16)
        
        self.turret_cost_map = array('i', [0] * self.size)
    
        self.symmetries_possible = [ Symmetry.ROTATIONAL, Symmetry.HORIZONTAL, Symmetry.VERTICAL ]
        if self.map_width > self.map_height:
            self.symmetries_possible = [ Symmetry.HORIZONTAL, Symmetry.ROTATIONAL, Symmetry.VERTICAL ]
        elif self.map_height > self.map_width:
            self.symmetries_possible = [ Symmetry.VERTICAL, Symmetry.ROTATIONAL, Symmetry.HORIZONTAL ]
        
        self.flow_tracking = False
        
    def config(self, flow_tracking: bool):
        self.flow_tracking = flow_tracking

    def idx(self, p: Position) -> int:
        return p.x + self.map_width * p.y

    def set_env(self, p: Position, env: Environment):
        i = self.idx(p)
        env_id = ENVIRONMENT_TO_VALUE[env]
        self.env_index[env_id].add(p)
        self.map[i] = (env_id << 13) | (self.map[i] & 0x1FFF)
        
    def set_entt(self, p: Position, dir: Direction, entity: EntityType, allied: bool):
        i = self.idx(p)
        
        entt_type_id = ENTITY_TYPE_TO_VALUE[entity]
        dir_id = DIRECTION_TO_VALUE[dir]
        self.entt_index[entt_type_id].add(p)

        self.map[i] = (self.map[i] & 0xE000) | (entt_type_id << 5) | (dir_id << 1) | allied

    def set_entt_and_env(self, p: Position, dir: Direction, entity: EntityType, env: Environment, allied: bool):
        i = self.idx(p)

        entt_type_id = ENTITY_TYPE_TO_VALUE[entity]
        env_id = ENVIRONMENT_TO_VALUE[env]
        dir_id = DIRECTION_TO_VALUE[dir]
        self.entt_index[entt_type_id].add(p)
        self.env_index[env_id].add(p)

        self.map[i] = (env_id << 13) | (entt_type_id << 5) | (dir_id << 1) | allied

    def get_env(self, p: Position):
        return _VALUE_TO_ENVIRONMENT[self.map[self.idx(p)] >> 13]

    def get_entity(self, pos: Position):
        return _VALUE_TO_ENTITY_TYPE.get((self.map[self.idx(pos)] >> 5) & 0xFF)
    
    def get_direction(self, pos: Position):
        return _VALUE_TO_DIRECTION.get((self.map[self.idx(pos)] >> 1) & 0xF)

    def is_allied(self, pos: Position):
        return self.map[self.idx(pos)] & 1
    
    def is_seen(self, pos: Position):
        return self.map[self.idx(pos)] != 0

    def ti_trend(self, alpha=0.3, cap=50):
        if len(self.ti_tracker) < 2: return 0
        ema = 0
        prev = self.ti_tracker[0]
        for x in self.ti_tracker:
            d = x - prev
            if d < -cap: d = -cap
            if d > cap: d = cap
            ema = alpha * d + (1 - alpha) * ema
            prev = x
        return ema

    def ax_trend(self, alpha=0.3):
        if len(self.ax_tracker) < 2: return 0
        ema = 0
        prev = self.ax_tracker[0]
        for x in self.ax_tracker:
            d = x - prev
            ema = alpha * d + (1 - alpha) * ema
            prev = x
        return ema
    
    def update(self):
        my_pos = self.rc.get_position()
        ti, ax = self.rc.get_global_resources()
        self.ti_tracker.append(ti)
        self.ax_tracker.append(ax)

        for s in self.env_index.values():  s.clear()
        for s in self.entt_index.values(): s.clear()
        self.ally_builders.clear()
        self.enemy_builders.clear()
        self.heal_targets.clear()
        
        self.transport_attack_blacklist.clear()
        self.enemy_turrets.clear()
        
        self.nearby_tiles = self.rc.get_nearby_tiles()
        # TODO: Do some generation tracking to not have to do a full iter on nearby tiles again
        if self.flow_tracking:
            for t in self.nearby_tiles:
                self.remove_edges_from(t)
        
        for t in self.nearby_tiles:
            already_seen = self.is_seen(t)
            
            # Save Env and Buildings
            env = self.rc.get_tile_env(t)
            bldg = self.rc.get_tile_building_id(t)
            entt = None if bldg is None else self.rc.get_entity_type(bldg)
            allied = False if bldg is None else self.rc.get_team(bldg) == self.rc.get_team()
            dir = self.rc.get_direction(bldg) if entt in ENTITY_DIRECTIONAL else Direction.CENTRE

            # Compare with old if turret and update costs
            old_entt = self.get_entity(t)
            old_dir = self.get_direction(t)
            old_allied = self.is_allied(t)
            if (old_entt in ENTITY_TURRET or entt in ENTITY_TURRET) and\
                (old_entt != entt or old_dir != dir) and\
                (not old_allied or not allied):
                if old_entt in ENTITY_TURRET and not old_allied:
                    self.add_turret_attack_costs(t, old_entt, old_dir, -1)
                if entt in ENTITY_TURRET and not allied:
                    self.add_turret_attack_costs(t, entt, dir, 1)
                    # print(self.turret_cost_map, file=sys.stderr)

            # Commit information about tile
            self.set_entt_and_env(t, dir, entt, env, allied)

            # Heal targets
            if allied and self.rc.get_hp(bldg) < self.rc.get_max_hp(bldg)-4:
                self.heal_targets.add(t)
            
            # Enemy Infra
            if not allied and entt in ENTITY_TURRET:
                self.enemy_turrets.add(t)

            # Special cases
            if not allied and entt == EntityType.CORE and self.enemy_core_found is None:
                self.enemy_core_found = self.rc.get_position(bldg)
            
            # Flow Tracking
            if self.flow_tracking:
                if entt in ENTITY_TRANSPORT:
                    outputs = self.get_outputs(self.rc, t, entt, bldg)
                    for out in outputs:
                        if out is not None: self.add_edge(t, out)

            # Save Builder Bots
            bb = self.rc.get_tile_builder_bot_id(t)
            if bb is not None:
                if self.rc.get_team(bb) == self.rc.get_team():
                    if self.rc.get_id() != bb:
                        self.ally_builders.add(t)
                else:
                    self.enemy_builders.add(t)

            if not already_seen:
                # Crack Symmetry
                if len(self.symmetries_possible) > 1:
                    to_elim = []
                    for sym in self.symmetries_possible:
                        test = get_symmetric(t, self.map_width, self.map_height, sym)
                        env_here = self.get_env(test)
                        if env_here != None:
                            if env_here != env:
                                to_elim.append(sym)
                    self.symmetries_possible = [x for x in self.symmetries_possible if x not in to_elim]
        
        if self.flow_tracking:
            for u in self.entt_index[ENTITY_TYPE_TO_VALUE[EntityType.GUNNER]]:
                if self.is_allied(u):
                    self.transport_attack_blacklist.update(self.get_feeders_of(u))
            for u in self.entt_index[ENTITY_TYPE_TO_VALUE[EntityType.SENTINEL]]:
                if self.is_allied(u):
                    self.transport_attack_blacklist.update(self.get_feeders_of(u))

    # Feed Graph stuff

    def add_edge(self, src: Position, dst: Position):
        self.feed_graph.setdefault(src, set()).add(dst)
        self.reverse_feed_graph.setdefault(dst, set()).add(src)

    def remove_edges_from(self, src: Position):
        if src in self.feed_graph:
            for dst in self.feed_graph[src]:
                if dst in self.reverse_feed_graph:
                    self.reverse_feed_graph[dst].discard(src)
                    if not self.reverse_feed_graph[dst]:
                        del self.reverse_feed_graph[dst]
            del self.feed_graph[src]

    def get_outputs(self, rc: Controller, pos: Position, entt: EntityType, bldg: int):
        if entt == EntityType.CONVEYOR or entt == EntityType.ARMOURED_CONVEYOR:
            d = rc.get_direction(bldg)
            return [pos.add(d)]

        elif entt == EntityType.BRIDGE:
            return [rc.get_bridge_target(bldg)]

        elif entt == EntityType.SPLITTER:
            primary = rc.get_direction(bldg)
            return [
                pos.add(primary),
                pos.add(primary.rotate_left().rotate_left()),
                pos.add(primary.rotate_right().rotate_right()),
            ]

        return []
    
    def get_feeders_of(self, pos: Position):
        result = set()
        stack = [pos]

        while stack:
            cur = stack.pop()
            for src in self.reverse_feed_graph.get(cur, []):
                if src not in result:
                    result.add(src)
                    stack.append(src)

        return result

    # Turret Avoidance
    def add_turret_attack_costs(self, p: Position, e: EntityType, dir: Direction, mult: int):
        tiles = self.rc.get_attackable_tiles_from(p, dir, e) if e != EntityType.LAUNCHER else [p.add(d) for d in DIRECTIONS]
        
        cost = TURRET_ATTACK_COSTS.get(e, 0) * mult
        for t in tiles:
            if not is_in_map(t, self.map_width, self.map_height): continue
            self.turret_cost_map[self.idx(t)] += cost
            
    # Misc

    def eliminate_next_symmetry(self):
        if len(self.symmetries_possible) > 1:
            del self.symmetries_possible[0]

    def visualize(self):
        for src, dsts in self.feed_graph.items():
            for dst in dsts:
                self.rc.draw_indicator_line(src, dst, 255, 255, 0)
        
        # for i, val in enumerate(self.map):
        #     if val == 0:
        #         continue

        #     x = i % self.map_width
        #     y = i // self.map_width
        #     pos = Position(x, y)

        #     env = (val >> 8) & 0xFF
        #     ent = (val >> 1) & 0x7F
        #     allied = val & 1

        #     # simple coloring
        #     if env:
        #         self.rc.draw_indicator_dot(pos, 0, 255, 0)

        #     if ent:
        #         if allied:
        #             self.rc.draw_indicator_dot(pos, 0, 0, 255)
        #         else:
        #             self.rc.draw_indicator_dot(pos, 255, 0, 0)

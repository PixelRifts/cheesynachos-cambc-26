from array import array

from helpers import *

from collections import deque
from typing import Optional, Set, Dict
from enum import Enum
from cambc import Controller, Environment, Position, Direction, EntityType, GameConstants

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


_OFFSETS = (
    (-1,-1),(0,-1),(1,-1),
    (-1, 0),       (1, 0),
    (-1, 1),(0, 1),(1, 1),
)

class Sense:
    def __init__(self, rc: Controller):
        self.rc = rc

        self.map_width = rc.get_map_width()
        self.map_height = rc.get_map_height()
        self.size = self.map_width * self.map_height
        self.nearby_tiles = []

        self.map = array('H', [0] * self.size)
        self.reachable = 0 # Bitint bitmask
        self.ally_builders:  set[Position] = set()
        self.enemy_builders: set[Position] = set()
        self.transport_attack_blacklist: set[Position] = set()
        self.feed_graph: Dict[Position, set[Position]] = {}
        self.reverse_feed_graph: Dict[Position, set[Position]] = {}
        self.enemy_core_found: Position = None
        self.nearest_enemy_bb: Position = None
        self.nearest_enemy_cheby_dist = float('inf')

        self.heal_targets: list[Position] = []
        self.enemy_turrets: list[Position] = []
        self.enemy_launchers: list[Position] = []
        self.ally_turrets: list[Position] = []
        self.ally_launchers: list[Position] = []
        self.enemy_transports: list[Position] = []
        self.bridges: list[Position] = []
        self.conveyors: list[Position] = []
        self.ally_transports: list[Position] = []
        self.ores: list[Position] = []
        self.harvesters: list[Position] = []
        
        self.last_nearby_set: set[Position] = set()
        self.tile_bldg_cache = {}
        self.my_pos = None

        self.ti_tracker = deque(maxlen=16)
        self.ax_tracker = deque(maxlen=16)
        
        self.turret_cost_map = array('i', [0] * self.size)
        
        self.symmetries_possible = [ Symmetry.ROTATIONAL, Symmetry.HORIZONTAL, Symmetry.VERTICAL ]
        if self.map_width > self.map_height:
            self.symmetries_possible = [ Symmetry.HORIZONTAL, Symmetry.ROTATIONAL, Symmetry.VERTICAL ]
        elif self.map_height > self.map_width:
            self.symmetries_possible = [ Symmetry.VERTICAL, Symmetry.ROTATIONAL, Symmetry.HORIZONTAL ]
        
        self.flow_tracking = True
        
    def config(self, flow_tracking: bool):
        self.flow_tracking = flow_tracking

    def idx(self, p: Position) -> int:
        return p.x + self.map_width * p.y

    def set_env(self, p: Position, env: Environment):
        i = self.idx(p)
        env_id = ENVIRONMENT_TO_VALUE[env]
        self.map[i] = (env_id << 13) | (self.map[i] & 0x1FFF)
        
    def set_entt(self, p: Position, dir: Direction, entity: EntityType, allied: bool):
        i = self.idx(p)
        
        entt_type_id = ENTITY_TYPE_TO_VALUE[entity]
        dir_id = DIRECTION_TO_VALUE[dir]
        
        self.map[i] = (self.map[i] & 0xE000) | (entt_type_id << 5) | (dir_id << 1) | allied

    def set_entt_and_env(self, p: Position, dir: Direction, entity: EntityType, env: Environment, allied: bool):
        i = self.idx(p)

        entt_type_id = ENTITY_TYPE_TO_VALUE[entity]
        env_id = ENVIRONMENT_TO_VALUE[env]
        dir_id = DIRECTION_TO_VALUE[dir]
        
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

    def is_reachable(self, p: Position) -> bool:
        return (self.reachable >> (p.y * self.map_width + p.x)) & 1


    def get_env_idxd(self, idx: int):
        return _VALUE_TO_ENVIRONMENT[self.map[idx] >> 13]

    def get_entity_idxd(self, idx: int):
        return _VALUE_TO_ENTITY_TYPE.get((self.map[idx] >> 5) & 0xFF)
    
    def get_direction_idxd(self, idx: int):
        return _VALUE_TO_DIRECTION.get((self.map[idx] >> 1) & 0xF)

    def is_allied_idxd(self, idx: int):
        return self.map[idx] & 1
    
    def is_seen_idxd(self, idx: int):
        return self.map[idx] != 0
    
    def is_reachable_idxd(self, idx: int) -> bool:
        return (self.reachable >> idx) & 1

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
        self.my_pos = self.rc.get_position()
        ti, ax = self.rc.get_global_resources()
        self.ti_tracker.append(ti)
        self.ax_tracker.append(ax)

        self.reachable |= (1 << (self.my_pos.x + self.my_pos.y * self.map_width))

        self.ally_builders.clear()
        self.enemy_builders.clear()
        self.heal_targets.clear()
        self.transport_attack_blacklist.clear()
        self.enemy_turrets.clear()
        self.enemy_launchers.clear()
        self.ally_turrets.clear()
        self.ally_launchers.clear()
        self.enemy_transports.clear()
        self.bridges.clear()
        self.conveyors.clear()
        self.ally_transports.clear()
        self.ores.clear()
        self.harvesters.clear()
        self.nearest_enemy_bb = None
        self.nearest_enemy_cheby_dist = float('inf')
        
        self.nearby_tiles = self.rc.get_nearby_tiles()
        nearby_set       = set(self.nearby_tiles)
        new_tiles        = nearby_set - self.last_nearby_set
        continuing_tiles = nearby_set & self.last_nearby_set
        departed_tiles   = self.last_nearby_set - nearby_set
        self.last_nearby_set = nearby_set
        
        for t in new_tiles:
            self._process_tile(t)

        for t in continuing_tiles:
            if self.flow_tracking:
                self.remove_edges_from(t)
            self._process_tile_incremental(t)

        self._update_reachability(new_tiles)
        
        if self.flow_tracking:
            for u in self.ally_turrets:
                if self.is_allied(u) and self.get_entity(u) != EntityType.LAUNCHER:
                    self.transport_attack_blacklist.update(self.get_feeders_of(u))
    
    def _process_tile(self, t):
        env    = self.rc.get_tile_env(t)
        bldg   = self.rc.get_tile_building_id(t)
        entt   = None if bldg is None else self.rc.get_entity_type(bldg)
        allied = False if bldg is None else self.rc.get_team(bldg) == self.rc.get_team()
        dir    = self.rc.get_direction(bldg) if entt in ENTITY_DIRECTIONAL else Direction.CENTRE

        self.tile_bldg_cache[t] = bldg
        already_seen = self.is_seen(t)
        if already_seen:
            old_entt = self.get_entity(t)
            old_dir = self.get_direction(t)
            old_allied = self.is_allied(t)

            if (old_entt in ENTITY_TURRET or entt in ENTITY_TURRET) and (old_entt != entt or old_dir != dir) and (not old_allied or not allied):
                if old_entt in ENTITY_TURRET and not old_allied:
                    self.add_turret_attack_costs(t, old_entt, old_dir, -1)
                if entt in ENTITY_TURRET and not allied:
                    self.add_turret_attack_costs(t, entt, dir, 1)
            if old_entt != entt or old_dir != dir or old_allied != allied:
                self.set_entt_and_env(t, dir, entt, env, allied)
        else:
            self.set_entt_and_env(t, dir, entt, env, allied)

            if entt in ENTITY_TURRET and not allied:
                self.add_turret_attack_costs(t, entt, dir, 1)

            # Symmetry Crack if never seen before
            if len(self.symmetries_possible) > 1:
                to_elim = []
                for sym in self.symmetries_possible:
                    test = get_symmetric(t, self.map_width, self.map_height, sym)
                    env_here = self.get_env(test)
                    if env_here != None:
                        if env_here != env:
                            to_elim.append(sym)
                self.symmetries_possible = [x for x in self.symmetries_possible if x not in to_elim]

        self._categorize(t, entt, env, allied, bldg)
        
        # HP can always change, so still check heal targets
        if allied and bldg is not None:
            if self.rc.get_hp(bldg) < self.rc.get_max_hp(bldg):
                self.heal_targets.append(t)
        
        # Rebuild flow edges from cache
        if self.flow_tracking and entt in ENTITY_TRANSPORT:
            outputs = self.get_outputs(self.rc, t, entt, bldg)
            for out in outputs:
                if out is not None:
                    self.add_edge(t, out)
        
        self._check_builder_bot(t)

    def _process_tile_incremental(self, t):
        bldg        = self.rc.get_tile_building_id(t)
        cached_bldg = self.tile_bldg_cache.get(t)
        
        if bldg == cached_bldg:
            # Entity unchanged so pull everything from cache
            entt   = self.get_entity(t)
            allied = self.is_allied(t)
            env    = self.get_env(t)
            
            # Rebuild per-tick lists from cache (no extra API calls)
            self._categorize(t, entt, env, allied, bldg)

            # HP can always change, so still check heal targets
            if allied and bldg is not None:
                if self.rc.get_hp(bldg) < self.rc.get_max_hp(bldg):
                    self.heal_targets.append(t)

            # Rebuild flow edges from cache
            if self.flow_tracking and entt in ENTITY_TRANSPORT:
                outputs = self.get_outputs(self.rc, t, entt, bldg)
                for out in outputs:
                    if out is not None:
                        self.add_edge(t, out)
            
            self._check_builder_bot(t)
        else:
            # Something changed so fall back to full processing
            self._process_tile(t)

    def _categorize(self, t, entt, env, allied, bldg):
        if env in ENVIRONMENT_ORE:
            self.ores.append(t)

        if not allied and entt == EntityType.CORE and self.enemy_core_found is None:
            self.enemy_core_found = self.rc.get_position(bldg)

        if entt == EntityType.HARVESTER:
            self.harvesters.append(t)
        
        if entt == EntityType.BRIDGE:
            self.bridges.append(t)
        elif entt == EntityType.CONVEYOR:
            self.conveyors.append(t)
        
        if not allied:
            if entt in ENTITY_TURRET:
                self.enemy_turrets.append(t)
                if entt == EntityType.LAUNCHER:
                    self.enemy_launchers.append(t)
            elif entt in ENTITY_TRANSPORT:
                self.enemy_transports.append(t)
        else:
            self.reachable |= (1 << (t.x + t.y * self.map_width))

            if entt in ENTITY_TURRET:
                self.ally_turrets.append(t)
                if entt == EntityType.LAUNCHER:
                    self.ally_launchers.append(t)
            elif entt in ENTITY_TRANSPORT:
                self.ally_transports.append(t)
                

    def _check_builder_bot(self, t):
        bb = self.rc.get_tile_builder_bot_id(t)
        if bb is not None:
            if self.rc.get_team(bb) == self.rc.get_team():
                if self.rc.get_id() != bb:
                    self.ally_builders.add(t)
                    if self.rc.get_hp(bb) < self.rc.get_max_hp(bb):
                        self.heal_targets.append(t)
            else:
                self.enemy_builders.add(t)
                dist = chebyshev_distance(t, self.my_pos)
                if dist < self.nearest_enemy_cheby_dist:
                    self.nearest_enemy_cheby_dist = dist
                    self.nearest_enemy_bb = t

    def _update_reachability(self, new_tiles):
        reachable = self.reachable
        get_env   = self.get_env
        offsets   = _OFFSETS
        map_w     = self.map_width
        map_h     = self.map_height

        new_walkable = set()
        nw_add = new_walkable.add
        for t in new_tiles:
            env = get_env(t)
            if env != Environment.WALL:
                nw_add(t)
        if not new_walkable: return

        queue    = deque()
        q_append = queue.append
        in_queue = set()
        iq_add   = in_queue.add

        for t in new_walkable:
            tx, ty = t
            for dx, dy in offsets:
                nx = tx + dx
                ny = ty + dy
                if 0 <= nx < map_w and 0 <= ny < map_h:
                    if (reachable >> (nx + ny * map_w)) & 1:
                        q_append(t)
                        iq_add(t)
                        break
        if not queue: return

        popleft = queue.popleft
        while queue:
            cur = popleft()
            cx, cy = cur
            reachable |= (1 << (cx + cy * map_w))
            for dx, dy in offsets:
                nx = cx + dx
                ny = cy + dy
                nb = (nx, ny)
                if nb in new_walkable and nb not in in_queue:
                    iq_add(nb)
                    q_append(nb)

        self.reachable = reachable
        
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
        tiles = get_turret_tiles(self.rc, e, p, dir)
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

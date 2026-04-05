import sys

from sense import Sense
from helpers import *
from collections import deque
from cambc import Controller, Direction, EntityType, Environment, Position, GameConstants

# Implement BUG + BFS Pathfinding
from heapq import heappush, heappop

BARRIER_COST = 20
DEBUG_DRAW = True
H_WEIGHT = 1.5

class PFState:
    def __init__(self):
        self.closed_set = set()
        self.reset()

    def reset(self):
        # incremental A*
        self.astar_active = False
        self.goal = None
        self.best_node = None
        self.best_h = 10000000000000

        self.open_set = []
        self.closed_set.clear()
        self.came_from = {}
        self.g_score = {}
        self.failed = False
        self.past_pos = None
        
        self.result_path = []
        self.computed_this_turn = False

pf_state = PFState()
def clear():
    pf_state.computed_this_turn = False

# Fast Pathfind

def fast_pathfind_to(rc: Controller, sense: Sense, target: Position, ignore_builder_at_tgt=False):
    if target is None: return False
    cur = rc.get_position()
    if cur == target: return True

    # start / restart A*
    if (not pf_state.astar_active and not pf_state.result_path) or pf_state.goal != target\
        or (pf_state.past_pos is not None and pf_state.past_pos != rc.get_position()):
        pf_state.reset()
        pf_state.astar_active = True
        pf_state.goal = target

        pf_state.g_score[cur] = 0
        heappush(pf_state.open_set, (0, cur))
        if pf_state.computed_this_turn: return False

    # continue A* for a limited budget
    if pf_state.astar_active:
        step_astar_internal(rc, sense, max_expansions=50, ignore_builder_at_tgt=ignore_builder_at_tgt)
        pf_state.computed_this_turn = True

    if not pf_state.astar_active and pf_state.failed:
        pf_state.result_path = []
        return

    if pf_state.result_path:
        # follow path it
        next_pos = pf_state.result_path[0]
        d = cur.direction_to(next_pos)

        moved = False
        if rc.can_destroy(next_pos) and should_destroy(rc, next_pos):
            rc.destroy(next_pos)
        if rc.can_move(d):
            rc.move(d)
            moved = True
        elif rc.can_build_road(next_pos):
            rc.build_road(next_pos)
            if rc.can_move(d):
                rc.move(d)
                pf_state.past_pos = rc.get_position()
                moved = True
        
        if not moved:
            env = sense.get_env(next_pos)
            entt = sense.get_entity(next_pos)
            allied = sense.is_allied(next_pos)
            if not is_entt_pathable(entt, allied) or env == Environment.WALL or \
                (rc.is_in_vision(next_pos) and rc.get_tile_builder_bot_id(next_pos) is not None and rc.get_tile_builder_bot_id(next_pos) != rc.get_id()):
                pf_state.reset()
        else:
            pf_state.result_path.pop(0)
            
        if rc.get_position() == target: return True


def step_astar_internal(rc: Controller, sense: Sense, max_expansions: int, ignore_builder_at_tgt=False):
    expansions = 0
    open_set = pf_state.open_set
    closed_set = pf_state.closed_set
    came_from = pf_state.came_from
    g_score = pf_state.g_score
    goal = pf_state.goal

    map_w = sense.map_width
    map_h = sense.map_height
    
    while open_set and expansions < max_expansions:
        _, current = heappop(open_set)
        if current in pf_state.closed_set:
            continue
        pf_state.closed_set.add(current)

        if current == goal:
            if DEBUG_DRAW: rc.draw_indicator_dot(current, 0, 255, 0)
            path = reconstruct_path(came_from, current)
            pf_state.result_path = path
            pf_state.result_path.pop(0)
            if pf_state.result_path:
                if DEBUG_DRAW: rc.draw_indicator_line(rc.get_position(), pf_state.result_path[0], 0, 255, 0)

            for i in range(len(pf_state.result_path) - 1):
                if DEBUG_DRAW: rc.draw_indicator_line(
                    pf_state.result_path[i],
                    pf_state.result_path[i + 1],
                    0, 255, 0
                )
            pf_state.astar_active = False
            return

        for d in DIRECTIONS:
            nxt = current.add(d)
            cost = 1

            if not is_in_map(nxt, map_w, map_h): continue
            if sense.is_seen(nxt):
                env = sense.get_env(nxt)
                entt = sense.get_entity(nxt)
                allied = sense.is_allied(nxt)
                if env == Environment.WALL: continue
                
                if not (ignore_builder_at_tgt and nxt is pf_state.goal):
                    if rc.is_in_vision(nxt) and rc.get_tile_builder_bot_id(nxt) is not None: continue

                if not is_entt_pathable(entt, allied):
                    if allied and entt == EntityType.BARRIER:
                        cost = BARRIER_COST
                    else: continue
            
            tentative = g_score[current] + cost
            if nxt in g_score and tentative >= g_score[nxt]: continue
            h = chebyshev_distance(nxt, goal)
            if h < pf_state.best_h:
                pf_state.best_h = h
                pf_state.best_node = nxt

            came_from[nxt] = current
            g_score[nxt] = tentative
            heappush(
                open_set,
                (tentative + H_WEIGHT * chebyshev_distance(nxt, goal), nxt)
            )
            
            if DEBUG_DRAW: rc.draw_indicator_dot(nxt, 255, 0, 0)

        expansions += 1

    if not open_set:
        # no path exists
        pf_state.astar_active = False
        pf_state.failed = True
        if pf_state.best_node in came_from:
            path = reconstruct_path(came_from, pf_state.best_node)
            pf_state.result_path = path
            pf_state.result_path.pop(0)

# Cardinal Pathfind

def cardinal_pathfind_to(rc: Controller, sense: Sense, target: Position, going_home: bool) -> bool:
    cur = rc.get_position()
    if cur == target: return True

    # start / restart A*
    if (not pf_state.astar_active and not pf_state.result_path) or pf_state.goal != target:
        pf_state.reset()
        pf_state.astar_active = True
        pf_state.goal = target

        pf_state.g_score[cur] = 0
        heappush(pf_state.open_set, (0, cur))
        if pf_state.computed_this_turn: return False

    # continue A* for a limited budget
    if pf_state.astar_active:
        step_cardinal_astar_internal(rc, sense, max_expansions=50)
        pf_state.computed_this_turn = True
    
    if not pf_state.astar_active and pf_state.failed:
        pf_state.result_path = []
        return

    if pf_state.result_path:
        next_pos = pf_state.result_path[0]
        d = cur.direction_to(next_pos)
        
        # Possibly fix conveyor this bot is standing on
        conveyor_dir = d
        entt = sense.get_entity(cur)
        needs_fix = (entt is None or \
            not (
                entt == EntityType.CONVEYOR and
                rc.get_direction(rc.get_tile_building_id(cur)) == conveyor_dir
            )
        )
        print(needs_fix)

        if needs_fix:
            print('hi')
            if entt is not None:
                print('hi2')
                allied = sense.is_allied(cur)
                if allied:
                    print('hi ally')
                    if rc.can_destroy(cur): rc.destroy(cur)
                else:
                    print('hi bad')
                    if rc.can_fire(cur):
                        print('fired')
                        rc.fire(cur)
                
            if rc.can_build_conveyor(cur, d):
                print('built conveyor')
                rc.build_conveyor(cur, d)
                needs_fix = False
        if needs_fix: return False

        # Figure out new conveyor direction
        if going_home:
            if 1 < len(pf_state.result_path):
                conv_next = pf_state.result_path[1]
                conveyor_dir = next_pos.direction_to(conv_next)
            else:
                conveyor_dir = d
        else:
            conveyor_dir = d.opposite()

        # Actually move
        moved = False
        allied = sense.is_allied(next_pos)
        if allied:
            if rc.can_destroy(next_pos): rc.destroy(next_pos)
        else:
            if rc.can_fire(next_pos): rc.fire(next_pos)
        if rc.can_build_conveyor(next_pos, conveyor_dir):
            rc.build_conveyor(next_pos, conveyor_dir)
        if rc.can_move(d):
            rc.move(d)
            moved = True
        
        # Possibly recompute if blocked
        if not moved:
            env = sense.get_env(next_pos)
            entt = sense.get_entity(next_pos)
            allied = sense.is_allied(next_pos)
            if not is_entt_pathable(entt, allied) or env == Environment.WALL:
                pf_state.reset()
        else:
            pf_state.result_path.pop(0)
            
        if rc.get_position() == target: return True


def step_cardinal_astar_internal(rc: Controller, sense: Sense, max_expansions: int):
    expansions = 0
    open_set = pf_state.open_set
    came_from = pf_state.came_from
    g_score = pf_state.g_score
    goal = pf_state.goal

    map_w = sense.map_width
    map_h = sense.map_height
    
    while open_set and expansions < max_expansions:
        _, current = heappop(open_set)
        if current in pf_state.closed_set:
            continue
        pf_state.closed_set.add(current)

        if current == goal:
            if DEBUG_DRAW: rc.draw_indicator_dot(current, 0, 255, 0)
            path = reconstruct_path(came_from, current)
            pf_state.result_path = path
            pf_state.result_path.pop(0)
            if pf_state.result_path:
                if DEBUG_DRAW: rc.draw_indicator_line(rc.get_position(), pf_state.result_path[0], 0, 255, 0)

            for i in range(len(pf_state.result_path) - 1):
                if DEBUG_DRAW: rc.draw_indicator_line(
                    pf_state.result_path[i],
                    pf_state.result_path[i + 1],
                    0, 255, 0
                )
            pf_state.astar_active = False
            return

        for d in CARDINAL_DIRECTIONS:
            nxt = current.add(d)
            cost = 1

            if not is_in_map(nxt, map_w, map_h): continue
            if sense.is_seen(nxt):
                env = sense.get_env(nxt)
                entt = sense.get_entity(nxt)
                allied = sense.is_allied(nxt)
                if env == Environment.WALL: continue
                if rc.is_in_vision(nxt) and rc.get_tile_builder_bot_id(nxt) is not None and nxt != pf_state.goal: continue
                if allied and entt in ENTITY_TRANSPORT: continue

                if not is_entt_pathable(entt, allied):
                    if allied and entt == EntityType.BARRIER:
                        cost = BARRIER_COST
                    else: continue
                
            tentative = g_score[current] + cost
            if nxt in g_score and tentative >= g_score[nxt]: continue
            
            came_from[nxt] = current
            g_score[nxt] = tentative
            heappush(
                open_set,
                (tentative + H_WEIGHT * manhattan_distance(nxt, goal), nxt)
            )
            if DEBUG_DRAW: rc.draw_indicator_dot(nxt, 255, 0, 0)

        expansions += 1
    
    if not open_set:
        # no path exists
        pf_state.astar_active = False
        pf_state.failed = True




def get_path():
    return pf_state.result_path

def reconstruct_path(came_from, current):
    path = [current]
    while current in came_from:
        current = came_from[current]
        path.append(current)
    path.reverse()
    return path

# Helpers

def is_tile_within_n_cardinal_steps(rc: Controller, start: Position, end: Position, n: int):
    if start == end: return True
    if manhattan_distance(start, end) > n: return False

    q = deque([(start, 0)])
    visited = {start}

    while q:
        pos, dist = q.popleft()

        if dist == n:
            continue

        for d in CARDINAL_DIRECTIONS:
            nxt = pos.add(d)
            if nxt in visited: continue
            
            if not cardinal_virtually_navvable(rc, nxt, d): continue
            if nxt == end: return True
            
            visited.add(nxt)
            q.append((nxt, dist + 1))

    return False

def simple_step(rc: Controller, d: Direction):
    p = rc.get_position().add(d)
    if rc.can_move(d):
        rc.move(d)
    elif rc.can_build_road(p):
        rc.build_road(p)
        if rc.can_move(d):
            rc.move(d)

def cardinal_virtually_navvable(rc: Controller, pos: Position, incoming_dir: Direction) -> bool:
    if not is_in_map(pos, rc.get_map_width(), rc.get_map_height()):
        return False
    if not rc.is_in_vision(pos):
        return True
    
    if CARDINAL_DIRECTIONS.__contains__(incoming_dir):
        return cardinal_unit_virtually_navvable(rc, pos)
    else:
        (dx, dy) = incoming_dir.opposite().delta()
        prev = pos.add(incoming_dir.opposite())
        test0 = prev.add(Direction.WEST  if dx == 1 else Direction.EAST)
        test1 = prev.add(Direction.NORTH if dy == 1 else Direction.SOUTH)

        if not cardinal_unit_virtually_navvable(rc, test0) and not cardinal_unit_virtually_navvable(rc, test1):
            return False
        return cardinal_unit_virtually_navvable(rc, pos)

def cardinal_unit_virtually_navvable(rc: Controller, pos: Position, non_conveyor: bool = False) -> bool:
    if not is_in_map(pos, rc.get_map_width(), rc.get_map_height()) or not rc.is_in_vision(pos):
        return False
    
    bldg = rc.get_tile_building_id(pos)
    if bldg is not None:
        allied = rc.get_team(bldg) == rc.get_team()
        if rc.get_entity_type(bldg) == EntityType.BARRIER and allied:
            return True
        if rc.get_entity_type(bldg) in ENTITY_TRANSPORT and allied:
            return False
    
    return (rc.get_tile_builder_bot_id(pos) is not None) or is_pos_pathable(rc, pos)

def cardinal_actually_navvable(rc: Controller, pos: Position) -> bool:
    if not is_in_map(pos, rc.get_map_width(), rc.get_map_height()) or not rc.is_in_vision(pos):
        return False
    return is_pos_pathable(rc, pos) and not is_friendly_transport(rc, pos)


def virtually_navvable(rc: Controller, pos: Position) -> bool:
    if not is_in_map(pos, rc.get_map_width(), rc.get_map_height()) or not rc.is_in_vision(pos):
        return False
    if rc.get_tile_env(pos) == Environment.WALL: return False
    
    bldg = rc.get_tile_building_id(pos)
    if bldg is not None:
        allied = rc.get_team(bldg) == rc.get_team()
        if rc.get_entity_type(bldg) == EntityType.BARRIER and allied:
            return True
    
    return (rc.get_tile_builder_bot_id(pos) is not None) or is_pos_pathable(rc, pos)

def actually_navvable(rc: Controller, pos: Position) -> bool:
    if not is_in_map(pos, rc.get_map_width(), rc.get_map_height()) or not rc.is_in_vision(pos):
        return False
    return is_pos_pathable(rc, pos)

def should_destroy(rc: Controller, pos: Position) -> bool:
    bldg = rc.get_tile_building_id(pos)
    if bldg is None: return False
    entt = rc.get_entity_type(bldg)
    # TODO maybe add more things that should be destroyed here
    return entt == EntityType.MARKER or entt == EntityType.BARRIER

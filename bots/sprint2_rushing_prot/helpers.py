import sys
import math
import random

import pathfind
from typing import Optional
from enum import Enum
from cambc import Controller, Environment, Position, Direction, EntityType

# Constants

RANDOM_SEED = 15

DIRECTIONS = [d for d in Direction if d != Direction.CENTRE]

CARDINAL_DIRECTIONS = [Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST]

DIRECTIONS_ORDERED = [
    Direction.NORTH, Direction.NORTHEAST, Direction.EAST, Direction.SOUTHEAST,
    Direction.SOUTH, Direction.SOUTHWEST, Direction.WEST, Direction.NORTHWEST
]

DIRECTIONS_ORDERED_CARDINALS_FIRST = [
    Direction.NORTH, Direction.EAST,
    Direction.SOUTH, Direction.WEST,
    Direction.NORTHEAST, Direction.SOUTHEAST,
    Direction.SOUTHWEST, Direction.NORTHWEST,
]

DIRECTIONS_INDEX = {d: i for i, d in enumerate(DIRECTIONS_ORDERED)}

# Major Helpers

def is_in_map(pos: Position, width, height) -> bool:
    return pos.x >= 0 and pos.x < width and pos.y >= 0 and pos.y < height

def get_building_type(rc: Controller, p: Position) -> Optional[EntityType]:
    bldg = rc.get_tile_building_id(p)
    if bldg is None: return None
    return rc.get_entity_type(bldg)

# Direction Helpers

def degrees_between(d1, d2):
    if d1 == Direction.CENTRE or d2 == Direction.CENTRE:
        return 0

    diff = abs(DIRECTIONS_INDEX[d1] - DIRECTIONS_INDEX[d2])
    if diff > 4:
        diff = 8 - diff

    return diff * 45

def cardinal_direction_to(me: Position, other: Position) -> Direction:
    dx = other.x - me.x
    dy = other.y - me.y

    if dx == 0 and dy == 0:
        return Direction.CENTRE

    if abs(dx) > abs(dy):
        return Direction.EAST if dx > 0 else Direction.WEST
    else:
        return Direction.SOUTH if dy > 0 else Direction.NORTH

def biased_random_dir(rc: Controller) -> Direction:
    c = random.randint(0, 10)
    if c < 3:
        return rc.get_position().direction_to(Position(rc.get_map_width() // 2, rc.get_map_height() // 2))
    return random.choice(DIRECTIONS)

def get_furthest_tile_in_dir(rc: Controller, pos: Position, dir: Direction) -> Position:
    width = rc.get_map_width()
    height = rc.get_map_height()

    (dx, dy) = dir.delta()

    if dx > 0:
        steps_x = (width - 1 - pos.x) // dx
    elif dx < 0:
        steps_x = pos.x // (-dx)
    else:
        steps_x = float('inf')

    if dy > 0:
        steps_y = (height - 1 - pos.y) // dy
    elif dy < 0:
        steps_y = pos.y // (-dy)
    else:
        steps_y = float('inf')

    steps = min(steps_x, steps_y)
    if math.isinf(steps): return pos
    return Position(pos.x + dx * steps, pos.y + dy * steps)

# Quick entity checks

def is_friendly_transport(rc: Controller, pos: Position) -> bool:
    if rc.is_tile_empty(pos): return False
    bldg = rc.get_tile_building_id(pos)
    if bldg is None: return False
    allied = rc.get_team(bldg) == rc.get_team()
    entt = rc.get_entity_type(bldg)
    return allied and (entt == EntityType.CONVEYOR or entt == EntityType.SPLITTER or entt == EntityType.BRIDGE)

def is_enemy_transport(rc: Controller, pos: Position) -> bool:
    if rc.is_tile_empty(pos): return False
    bldg = rc.get_tile_building_id(pos)
    if bldg is None: return False
    allied = rc.get_team(bldg) == rc.get_team()
    entt = rc.get_entity_type(bldg)
    return not allied and (entt == EntityType.CONVEYOR or entt == EntityType.SPLITTER or entt == EntityType.BRIDGE)

def is_friendly_turret(rc: Controller, pos: Position) -> bool:
    if rc.is_tile_empty(pos): return False
    bldg = rc.get_tile_building_id(pos)
    if bldg is None: return False
    allied = rc.get_team(bldg) == rc.get_team()
    entt = rc.get_entity_type(bldg)
    return allied and (entt == EntityType.GUNNER or entt == EntityType.SENTINEL or entt == EntityType.BREACH or entt == EntityType.LAUNCHER)

def is_friendly_bot(rc: Controller, pos: Position) -> bool:
    if rc.is_tile_empty(pos): return False
    bb = rc.get_tile_builder_bot_id(pos)
    if bb is None: return False
    allied = rc.get_team(bb) == rc.get_team()
    return allied

# Quick Position Checks

def is_pos_pathable(rc: Controller, pos: Position) -> bool:
    if rc.is_tile_empty(pos) or rc.is_tile_passable(pos): return True
    env = rc.get_tile_env(pos)
    if env == Environment.WALL: return False
    
    bldg = rc.get_tile_building_id(pos)
    if bldg is None: return True
    entt = rc.get_entity_type(bldg)
    allied = rc.get_team() == rc.get_team(bldg)
    return is_entt_pathable(entt, allied)

def is_pos_editable(rc: Controller, pos: Position) -> bool:
    if rc.is_tile_empty(pos): return True
    env = rc.get_tile_env(pos)
    if env == Environment.WALL: return False
    
    bldg = rc.get_tile_building_id(pos)
    if bldg is None: return True
    allied = rc.get_team() == rc.get_team(bldg)
    return allied

def is_pos_turretable(rc: Controller, pos: Position) -> bool:
    if rc.is_tile_empty(pos): return True
    env = rc.get_tile_env(pos)
    if env == Environment.WALL: return False
    
    bldg = rc.get_tile_building_id(pos)
    if bldg is None: return True
    allied = rc.get_team() == rc.get_team(bldg)
    entt = rc.get_entity_type(bldg)
    return is_enemy_transport(rc, pos) or (allied and entt == EntityType.ROAD or entt == EntityType.MARKER)

def is_entt_pathable(entt: EntityType, allied: bool) -> bool:
    if entt == EntityType.CONVEYOR or entt == EntityType.SPLITTER or entt == EntityType.BRIDGE or entt == EntityType.ROAD or entt == EntityType.MARKER:
        return True
    if allied:
        if entt == EntityType.CORE:
            return True
    return False

def try_destroy(rc: Controller, me: Position, p: Position) -> bool:
    bldg = rc.get_tile_building_id(p)
    if bldg is None:
        return pathfind.fast_pathfind_to(rc, me)

    entt = get_building_type(rc, p)
    allied = rc.get_team(bldg) == rc.get_team()
    already_connected = False

    if allied:
        if rc.get_position() == p:
            pathfind.fast_pathfind_to(rc, p.add(get_best_empty_adj(rc, p, me)))
        if not is_adjacent_with_diag(rc.get_position(), p):
            pathfind.fast_pathfind_to(rc, p)
        if rc.can_destroy(p):
            rc.destroy(p)
    elif not allied:
        if rc.get_position() != p:
            pathfind.fast_pathfind_to(rc, p)
        if rc.can_fire(p):
            rc.fire(p)
    return False
        

# Adjacency Checks

def is_adjacent(a: Position, b: Position, debug: bool = False) -> bool:
    dx = abs(a.x - b.x)
    dy = abs(a.y - b.y)
    if debug: print(dx, dy, dx + dy == 1, file=sys.stderr)
    return dx + dy == 1

def is_adjacent_with_diag(a: Position, b: Position, debug: bool = False) -> bool:
    dx = abs(a.x - b.x)
    dy = abs(a.y - b.y)
    if debug: print(dx, dy, dx + dy == 1, file=sys.stderr)
    return dx <= 1 and dy <= 1

def manhattan_distance(a: Position, b: Position) -> int:
    dx = abs(a.x - b.x)
    dy = abs(a.y - b.y)
    return dx + dy

def get_best_placable_adj_with_diag(rc: Controller, a: Position, b: Position) -> Direction:
    best_dist = 1000000
    best_dir = Direction.CENTRE
    for d in DIRECTIONS:
        p = a.add(d)
        if not is_in_map(p, rc.get_map_width(), rc.get_map_height()): continue
        if not rc.is_in_vision(p): continue
        bb = rc.get_tile_builder_bot_id(p)
        if bb is not None: continue
        if not (is_pos_turretable(rc, p) and not is_enemy_transport(rc, p)): continue
        dist = p.distance_squared(b)
        if dist < best_dist:
            best_dist = dist
            best_dir = d
    return best_dir

def get_empty_adj_with_diag(rc: Controller, a: Position) -> Direction:
    for d in DIRECTIONS:
        p = a.add(d)
        if not is_in_map(p, rc.get_map_width(), rc.get_map_height()): continue
        if not rc.is_in_vision(p): continue
        bb = rc.get_tile_builder_bot_id(p)
        if bb is not None: continue
        if is_pos_pathable(rc, p): return d
    return Direction.CENTRE

def get_empty_adj(rc: Controller, a: Position) -> Direction:
    for d in CARDINAL_DIRECTIONS:
        p = a.add(d)
        if not is_in_map(p, rc.get_map_width(), rc.get_map_height()): continue
        if not rc.is_in_vision(p): continue
        if is_friendly_transport(rc, p): continue
        bb = rc.get_tile_builder_bot_id(p)
        if bb is not None: continue
        if is_pos_pathable(rc, p): return d
    return Direction.CENTRE

def get_best_empty_adj(rc: Controller, a: Position, b: Position) -> Direction:
    best_dist = 1000000
    best_dir = Direction.CENTRE
    for d in CARDINAL_DIRECTIONS:
        p = a.add(d)
        if not is_in_map(p, rc.get_map_width(), rc.get_map_height()): continue
        if not rc.is_in_vision(p): continue
        if not is_pos_pathable(rc, p): continue
        if is_friendly_transport(rc, p): continue
        bb = rc.get_tile_builder_bot_id(p)
        if bb is not None: continue
        dist = p.distance_squared(b)
        if dist < best_dist:
            best_dist = dist
            best_dir = d
    return best_dir

def get_best_empty_adj_with_diag(rc: Controller, a: Position, b: Position) -> Direction:
    best_dist = 1000000
    best_dir = Direction.CENTRE
    for d in DIRECTIONS:
        p = a.add(d)
        if not is_in_map(p, rc.get_map_width(), rc.get_map_height()): continue
        if not rc.is_in_vision(p): continue
        if not is_pos_pathable(rc, p): continue
        if is_friendly_transport(rc, p): continue
        bb = rc.get_tile_builder_bot_id(p)
        if bb is not None: continue
        dist = p.distance_squared(b)
        if dist < best_dist:
            best_dist = dist
            best_dir = d
    return best_dir

# Symmetry

class Symmetry(Enum):
    ROTATIONAL = 'rotational'
    VERTICAL = 'vertical'
    HORIZONTAL = 'horizontal'

def guess_symmetry(width: int, height: int) -> Symmetry:
    if width > height: return Symmetry.HORIZONTAL
    elif height > width: return Symmetry.VERTICAL
    return Symmetry.ROTATIONAL

def get_symmetric(pos: Position, width: int, height: int, sym: Symmetry) -> Position:
    match sym:
        case Symmetry.ROTATIONAL: return Position(width - 1 - pos.x, height - 1 - pos.y)
        case Symmetry.VERTICAL:   return Position(pos.x,             height - 1 - pos.y)
        case Symmetry.HORIZONTAL: return Position(width - 1 - pos.x, pos.y             )
    assert False
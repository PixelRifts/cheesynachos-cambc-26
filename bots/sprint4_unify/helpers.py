import sys
import math
import random

from sense import *

from typing import Optional
from enum import Enum
from cambc import Controller, Environment, Position, Direction, EntityType

RANDOM_SEED = 1278

ENTITY_TRANSPORT   = { EntityType.CONVEYOR, EntityType.BRIDGE, EntityType.SPLITTER, EntityType.ARMOURED_CONVEYOR }
ENTITY_TURRET      = { EntityType.GUNNER, EntityType.SENTINEL, EntityType.BREACH, EntityType.LAUNCHER }
ENTITY_TRIVIAL     = { None, EntityType.ROAD, EntityType.MARKER }
ENTITY_CORE        = { EntityType.CORE }
ENTITY_REPLACABLE  = { EntityType.BARRIER }
ENTITY_UNWALKABLE  = { EntityType.HARVESTER, EntityType.FOUNDRY, EntityType.BARRIER } | ENTITY_TURRET
ENTITY_WALKABLE    = ENTITY_TRIVIAL | ENTITY_TRANSPORT
ENTITY_DIRECTIONAL = { EntityType.CONVEYOR, EntityType.ARMOURED_CONVEYOR, EntityType.SPLITTER, EntityType.GUNNER, EntityType.SENTINEL, EntityType.BREACH }
ENTITY_GUNNER_PASS = { None, EntityType.MARKER }

ENTITY_VALID_BLOCKAGE_ANY = { EntityType.BARRIER, EntityType.HARVESTER } | ENTITY_TURRET
ENTITY_VALID_BLOCKAGE_FRIENDLY = ENTITY_TURRET | ENTITY_TRANSPORT

    
def is_in_map(pos: Position, width, height) -> bool:
    return pos.x >= 0 and pos.x < width and pos.y >= 0 and pos.y < height

def dist_to_nearest_target(x: Position, target_tiles: list[Position]):
    best = 10000000000
    for t in target_tiles:
        d = t.distance_squared(x)
        if d < best:
            best = d
            if best == 0:
                break
    return best

def get_ti_cost(rc: Controller, entt: EntityType) -> int:
    match entt:
        case EntityType.BUILDER_BOT: return rc.get_builder_bot_cost()[0]
        case EntityType.CORE: return 0
        case EntityType.GUNNER: return rc.get_gunner_cost()[0]
        case EntityType.SENTINEL: return rc.get_sentinel_cost()[0]
        case EntityType.BREACH: return rc.get_breach_cost()[0]
        case EntityType.LAUNCHER: return rc.get_launcher_cost()[0]
        case EntityType.CONVEYOR: return rc.get_conveyor_cost()[0]
        case EntityType.SPLITTER: return rc.get_splitter_cost()[0]
        case EntityType.ARMOURED_CONVEYOR: return rc.get_armoured_conveyor_cost()[0]
        case EntityType.BRIDGE: return rc.get_bridge_cost()[0]
        case EntityType.HARVESTER: return rc.get_harvester_cost()[0]
        case EntityType.FOUNDRY: return rc.get_foundry_cost()[0]
        case EntityType.ROAD: return rc.get_road_cost()[0]
        case EntityType.BARRIER: return rc.get_barrier_cost()[0]
        case EntityType.MARKER: return 0

# Symmetry Functions:

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

def reflect(pos: Position, pivot: Position) -> Position:
    return Position(2 * pivot.x - pos.x, 2 * pivot.y - pos.y)

# Quick Pos Checks

def is_pos_pathable(rc: Controller, pos: Position) -> bool:
    if rc.is_tile_empty(pos) or rc.is_tile_passable(pos): return True
    env = rc.get_tile_env(pos)
    if env == Environment.WALL: return False
    
    bldg = rc.get_tile_building_id(pos)
    entt = rc.get_entity_type(bldg)
    allied = rc.get_team() == rc.get_team(bldg)
    return is_entt_pathable(entt, allied)

def is_pos_conveyorable(rc: Controller, pos: Position) -> bool:
    if rc.is_tile_empty(pos): return True
    env = rc.get_tile_env(pos)
    if env == Environment.WALL: return False
    
    bldg = rc.get_tile_building_id(pos)
    allied = rc.get_team() == rc.get_team(bldg)
    entt = rc.get_entity_type(bldg)
    return (not allied and entt in ENTITY_TRANSPORT) or (entt in ENTITY_TRIVIAL)

def is_pos_editable(rc: Controller, pos: Position) -> bool:
    if rc.is_tile_empty(pos): return True
    env = rc.get_tile_env(pos)
    if env == Environment.WALL: return False
    
    bldg = rc.get_tile_building_id(pos)
    allied = rc.get_team() == rc.get_team(bldg)
    return allied

def is_pos_turretable(rc: Controller, pos: Position) -> bool:
    if rc.is_tile_empty(pos): return True
    env = rc.get_tile_env(pos)
    if env == Environment.WALL: return False
    
    bldg = rc.get_tile_building_id(pos)
    allied = rc.get_team() == rc.get_team(bldg)
    entt = rc.get_entity_type(bldg)
    return (not allied and entt in ENTITY_WALKABLE) or (allied and entt in ENTITY_TRIVIAL)

def is_entt_pathable(entt: EntityType, allied: bool) -> bool:
    if entt in ENTITY_WALKABLE: return True
    if allied: return entt in ENTITY_CORE
    return False

# Quick Entity Checks

def is_friendly_transport(rc: Controller, pos: Position) -> bool:
    if rc.is_tile_empty(pos): return False
    bldg = rc.get_tile_building_id(pos)
    if bldg is None: return False
    allied = rc.get_team(bldg) == rc.get_team()
    entt = rc.get_entity_type(bldg)
    return allied and entt in ENTITY_TRANSPORT

def is_enemy_transport(rc: Controller, pos: Position) -> bool:
    if rc.is_tile_empty(pos): return False
    bldg = rc.get_tile_building_id(pos)
    if bldg is None: return False
    allied = rc.get_team(bldg) == rc.get_team()
    entt = rc.get_entity_type(bldg)
    return not allied and entt in ENTITY_TRANSPORT


# Adjacency Stuff

def get_best_placable_adj_ignorebb(rc: Controller, a: Position, b: Position) -> Direction:
    best_dist = 1000000
    best_dir = Direction.CENTRE
    for d in CARDINAL_DIRECTIONS:
        p = a.add(d)
        if not is_in_map(p, rc.get_map_width(), rc.get_map_height()): continue
        if not rc.is_in_vision(p): continue
        if not (is_pos_turretable(rc, p) and not is_enemy_transport(rc, p)): continue
        dist = p.distance_squared(b)
        if dist < best_dist:
            best_dist = dist
            best_dir = d
    return best_dir

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

def get_best_pathable_adj_with_diag(rc: Controller, pos: Position, heu: Position) -> Direction:
    best_dist = 1000000
    best_dir = Direction.CENTRE
    for d in DIRECTIONS:
        p = pos.add(d)
        if not is_in_map(p, rc.get_map_width(), rc.get_map_height()): continue
        if not rc.is_in_vision(p): continue
        
        if not is_pos_pathable(rc, p): continue
        if is_friendly_transport(rc, p): continue
        bb = rc.get_tile_builder_bot_id(p)
        if bb is not None: continue
        dist = p.distance_squared(heu)
        if dist < best_dist:
            best_dist = dist
            best_dir = d
    return best_dir

def get_empty_adj(rc: Controller, a: Position) -> Direction:
    for d in CARDINAL_DIRECTIONS:
        p = a.add(d)
        if not is_in_map(p, rc.get_map_width(), rc.get_map_height()): continue
        if not rc.is_in_vision(p): continue
        if is_friendly_transport(rc, p): continue
        # bb = rc.get_tile_builder_bot_id(p)
        # if bb is not None: continue
        if is_pos_pathable(rc, p): return d
    return Direction.CENTRE

def get_best_empty_adj(rc: Controller, a: Position, b: Position) -> Direction:
    best_score = -1000000
    best_dir = Direction.CENTRE
    for d in CARDINAL_DIRECTIONS:
        p = a.add(d)
        if not is_in_map(p, rc.get_map_width(), rc.get_map_height()): continue
        if not rc.is_in_vision(p): continue
        if not is_pos_pathable(rc, p): continue
        if is_friendly_transport(rc, p): continue
        # bb = rc.get_tile_builder_bot_id(p)
        # if bb is not None and rc.get_id(): continue

        score = -p.distance_squared(b) + (-100 if rc.get_entity_type(rc.get_tile_building_id(p)) == EntityType.BARRIER else 0)
        if score > best_score:
            best_score = score
            best_dir = d
    return best_dir

def get_best_empty_adj_with_diag(rc: Controller, a: Position, b: Position) -> Direction:
    best_score = -1000000
    best_dir = Direction.CENTRE
    for d in DIRECTIONS:
        p = a.add(d)
        if not is_in_map(p, rc.get_map_width(), rc.get_map_height()): continue
        if not rc.is_in_vision(p): continue
        if not is_pos_pathable(rc, p): continue
        if is_friendly_transport(rc, p): continue
        # bb = rc.get_tile_builder_bot_id(p)
        # if bb is not None and rc.get_id(): continue

        score = -p.distance_squared(b) + (-100 if rc.get_entity_type(rc.get_tile_building_id(p)) == EntityType.BARRIER else 0)
        if score > best_score:
            best_score = score
            best_dir = d
    return best_dir


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
    return abs(a.x - b.x) + abs(a.y - b.y)

def chebyshev_distance(a, b):
    return max(abs(a.x - b.x), abs(a.y - b.y))

# Direction Helpers

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

def degrees_between(d1, d2):
    if d1 == Direction.CENTRE or d2 == Direction.CENTRE:
        return 0

    diff = abs(DIRECTIONS_ORDERED[d1] - DIRECTIONS_ORDERED[d2])
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

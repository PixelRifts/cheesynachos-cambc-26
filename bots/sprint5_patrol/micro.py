import sys
import sense
import pathfind
import random
import heapq

from bot import Bot
from helpers import *
from procedure import *

from cambc import Controller, Direction, EntityType, Environment, Position, GameConstants, ResourceType

DISTANCE_SCORE_LUT = [ 0, -10, -15, -18, -20 ]

def score_attack_poi(rc: Controller, sense: sense.Sense, poi: Position) -> int:
    my_pos = rc.get_position()
    score = 0
    
    # TODO: Change to A* path length
    distance_index = min(chebyshev_distance(my_pos, poi), len(DISTANCE_SCORE_LUT) - 1)
    score += DISTANCE_SCORE_LUT[distance_index]

    for d in DIRECTIONS:
        p = poi.add(d)
        if not is_in_map(p, sense.map_width, sense.map_height): continue
        if sense.get_env(p) == Environment.WALL: continue
        if sense.get_entity(p) not in ENTITY_TURRET: continue
        score += 15
    
    return score

def poi_attack_plan(rc: Controller, sense: sense.Sense, poi: Position) -> tuple[Position, Position, EntityType, Direction]:
    my_pos = rc.get_position()
    target_pos = poi
    selected_entity = EntityType.SENTINEL
    selected_entity_dir = Direction.CENTRE
    replace_from = target_pos.add(get_best_pathable_adj_with_diag(rc, target_pos, my_pos))

    for d in DIRECTIONS:
        p = poi.add(d)
        if not is_in_map(p, sense.map_width, sense.map_height): continue
        if sense.get_env(p) == Environment.WALL: continue
        if sense.get_entity(p) in ENTITY_TURRET: continue
        selected_entity = EntityType.GUNNER
        break

    # When barriers are included here, uncomment this
    # if selected_entity in ENTITY_TURRET:
    selected_entity_dir = compute_best_turret_dir(rc, sense, poi, selected_entity)

    return target_pos, replace_from, selected_entity, selected_entity_dir

PRIORITIES = {
    None: 0,
    EntityType.BUILDER_BOT: 60,
    EntityType.CORE: 5,
    EntityType.GUNNER: 100,
    EntityType.SENTINEL: 100,
    EntityType.BREACH: 100,
    EntityType.LAUNCHER: 100,
    EntityType.CONVEYOR: 10,
    EntityType.SPLITTER: 20,
    EntityType.ARMOURED_CONVEYOR: 10,
    EntityType.BRIDGE: 10,
    EntityType.HARVESTER: 0,
    EntityType.FOUNDRY: 100,
    EntityType.ROAD: 1,
    EntityType.BARRIER: 1,
    EntityType.MARKER: 1,
}

def compute_best_turret_dir(rc: Controller, sense: sense.Sense, poi: Position, entt: EntityType) -> Direction:
    max_dir = Direction.NORTH
    max_dir_score = -1000000

    feed_dirs = []
    for d in CARDINAL_DIRECTIONS:
        p = poi.add(d)
        if sense.get_entity(p) == EntityType.HARVESTER or \
          (sense.get_entity(p) == EntityType.CONVEYOR and sense.get_direction(p) == d.opposite()) or \
          (sense.get_entity(p) == EntityType.SPLITTER and sense.get_direction(p) != d):
            feed_dirs.append(d)
    
    for d in DIRECTIONS:
        # if this is the only direction that feeds this turret
        if len(feed_dirs) == 1 and feed_dirs[0] == d: continue

        attackables = rc.get_attackable_tiles_from(poi, d, entt)
        score = 0
        for t in attackables:
            if sense.is_allied(t): continue
            score += PRIORITIES[sense.get_entity(t)]
            if rc.is_in_vision(t):
                bb = rc.get_tile_builder_bot_id(t)
                if bb is not None:
                    score += PRIORITIES[EntityType.BUILDER_BOT] * (1 if rc.get_team(bb) == rc.get_team() else -1)
        
        if score > max_dir_score:
            max_dir_score = score
            max_dir = d
    
    return max_dir

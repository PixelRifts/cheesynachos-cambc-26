import sys
import sense
import pathfind
import random
import heapq

from bot import Bot
from helpers import *
from procedure import *

from cambc import Controller, Direction, EntityType, Environment, Position, GameConstants, ResourceType

ENTITY_MICRO_USE_GUNNERS_TO_DISABLE = { EntityType.CORE } | ENTITY_TURRET


DISTANCE_SCORE_LUT = [ 30, 20, 15, 12, 10 ]


def score_attack_poi(rc: Controller, sense: sense.Sense, poi: Position, core_pos: Position) -> (int, bool):
    my_pos = rc.get_position()
    score = 0
    
    # TODO: Change to A* path length
    distance_index = min(chebyshev_distance(my_pos, poi), len(DISTANCE_SCORE_LUT) - 1)
    score += DISTANCE_SCORE_LUT[distance_index]

    is_empty = rc.is_tile_empty(poi) or sense.is_allied(poi) or sense.get_entity(poi) == EntityType.MARKER
    if is_empty: score += 100
    if poi in sense.enemy_builders: return 0, True

    # Axionite not secured penalty
    roundnum = rc.get_current_round()
    aggression = min(1.0, roundnum / 1000)
    if sense.ax_trend() == 0.0:
        aggression = aggression / 1.5
    if sense.ti_trend() < 5.0:
        aggression = aggression / 1.2

    # Core Distance Penalty
    if not is_empty:
        dist = chebyshev_distance(poi, core_pos)
        dist_penalty = dist * 2.5 * (1 - aggression)
        if dist_penalty > 50: return 0, True
        score -= dist_penalty
    
    # Distance to nearby enemies penalty
    for bb in sense.enemy_builders:
        dist = chebyshev_distance(bb, poi)
        dist_bonus = min(dist, 8) * (1 - aggression)
        score += dist_bonus

    # Hp loss penalty
    if not is_empty:
        expected_hp_loss = sense.turret_cost_map[sense.idx(poi)] 
        if expected_hp_loss * 0.5 > rc.get_hp(): return 0, True
        score -= expected_hp_loss * 2

    # Less HP
    if not is_empty:
        bbd = GameConstants.BUILDER_BOT_ATTACK_DAMAGE
        ticks_required = (rc.get_hp(rc.get_tile_building_id(poi)) + bbd - 1) // bbd
        score -= ticks_required * 5
    
    for d in DIRECTIONS:
        p1 = poi.add(d)
        if not is_in_map(p1, sense.map_width, sense.map_height): continue
        if sense.get_env(p1) == Environment.WALL: continue
        p1entt = sense.get_entity(p1)
        p1enemy = not sense.is_allied(p1)
        if p1entt == EntityType.LAUNCHER and p1enemy: return 0, True
        if p1entt == EntityType.HARVESTER: continue
        if p1entt in ENTITY_MICRO_USE_GUNNERS_TO_DISABLE and p1enemy: score += 15
        if p1 in sense.enemy_builders: score += 20
        
        p2 = p1.add(d)
        if not is_in_map(p2, sense.map_width, sense.map_height): continue
        if sense.get_env(p2) == Environment.WALL: continue
        p2entt = sense.get_entity(p2)
        if p2entt == EntityType.HARVESTER: continue
        if p2entt in ENTITY_MICRO_USE_GUNNERS_TO_DISABLE and not sense.is_allied(p2): score += 10
        if p2 in sense.enemy_builders: score += 20
        
        if d not in CARDINAL_DIRECTIONS: continue
        
        p3 = p2.add(d)
        if not is_in_map(p3, sense.map_width, sense.map_height): continue
        if sense.get_env(p3) == Environment.WALL: continue
        p3entt = sense.get_entity(p3)
        if p3entt in ENTITY_MICRO_USE_GUNNERS_TO_DISABLE and not sense.is_allied(p3): score += 6
        if p3 in sense.enemy_builders: score += 10
    
    return score, False

def score_defence_poi(rc: Controller, sense: sense.Sense, poi: Position) -> (int, bool):
    my_pos = rc.get_position()
    score = 0
    
    # TODO: Change to A* path length
    distance_index = min(chebyshev_distance(my_pos, poi), len(DISTANCE_SCORE_LUT) - 1)
    score += DISTANCE_SCORE_LUT[distance_index]

    is_empty = rc.is_tile_empty(poi) or sense.is_allied(poi) or sense.get_entity(poi) == EntityType.MARKER
    if is_empty: score += 100
    if poi in sense.enemy_builders: return 0, True

    # Axionite not secured penalty
    roundnum = rc.get_current_round()
    aggression = min(1.0, roundnum / 1000)
    if sense.ax_trend() == 0.0:
        aggression = aggression / 1.5
    if sense.ti_trend() < 5.0:
        aggression = aggression / 1.2

    # Distance to nearby enemies penalty
    for bb in sense.enemy_builders:
        dist = chebyshev_distance(bb, poi)
        dist_bonus = min(dist, 8) * (1 - aggression)
        score += dist_bonus

    # Hp loss penalty
    if not is_empty:
        expected_hp_loss = sense.turret_cost_map[sense.idx(poi)] 
        if expected_hp_loss * 0.5 > rc.get_hp(): return 0, True
        score -= expected_hp_loss * 2

    # Less HP
    if not is_empty:
        bbd = GameConstants.BUILDER_BOT_ATTACK_DAMAGE
        ticks_required = (rc.get_hp(rc.get_tile_building_id(poi)) + bbd - 1) // bbd
        score -= ticks_required * 5
    
    for d in DIRECTIONS:
        p1 = poi.add(d)
        if not is_in_map(p1, sense.map_width, sense.map_height): continue
        if sense.get_env(p1) == Environment.WALL: continue
        p1entt = sense.get_entity(p1)
        p1enemy = not sense.is_allied(p1)
        if p1entt == EntityType.LAUNCHER and p1enemy: return 0, True
        if p1entt == EntityType.HARVESTER: continue
        if p1entt in ENTITY_MICRO_USE_GUNNERS_TO_DISABLE and p1enemy: score += 15
        if p1 in sense.enemy_builders: score += 20
        
        p2 = p1.add(d)
        if not is_in_map(p2, sense.map_width, sense.map_height): continue
        if sense.get_env(p2) == Environment.WALL: continue
        p2entt = sense.get_entity(p2)
        if p2entt == EntityType.HARVESTER: continue
        if p2entt in ENTITY_MICRO_USE_GUNNERS_TO_DISABLE and not sense.is_allied(p2): score += 10
        if p2 in sense.enemy_builders: score += 20
        
        if d not in CARDINAL_DIRECTIONS: continue
        
        p3 = p2.add(d)
        if not is_in_map(p3, sense.map_width, sense.map_height): continue
        if sense.get_env(p3) == Environment.WALL: continue
        p3entt = sense.get_entity(p3)
        if p3entt in ENTITY_MICRO_USE_GUNNERS_TO_DISABLE and not sense.is_allied(p3): score += 6
        if p3 in sense.enemy_builders: score += 10
    
    return score, False

def poi_attack_plan(rc: Controller, sense: sense.Sense, poi: Position, enemy_core_pos: Position) -> tuple[Position, Position, EntityType, Direction]:
    my_pos = rc.get_position()
    target_pos = poi
    selected_entity = EntityType.SENTINEL
    selected_entity_dir = Direction.CENTRE
    replace_from = target_pos.add(get_best_pathable_adj_with_diag(rc, target_pos, my_pos))

    for d in DIRECTIONS:
        p1 = poi.add(d)
        if not is_in_map(p1, sense.map_width, sense.map_height): continue
        if sense.get_env(p1) == Environment.WALL: continue
        if sense.get_entity(p1) in ENTITY_MICRO_USE_GUNNERS_TO_DISABLE and not sense.is_allied(p1):
            selected_entity = EntityType.GUNNER
            break
        if p1 in sense.enemy_builders:
            selected_entity = EntityType.GUNNER
            break
        
        p2 = p1.add(d)
        if not is_in_map(p2, sense.map_width, sense.map_height): continue
        if sense.get_env(p2) == Environment.WALL: continue
        if sense.get_entity(p2) in ENTITY_MICRO_USE_GUNNERS_TO_DISABLE and not sense.is_allied(p2):
            selected_entity = EntityType.GUNNER
            break
        if p2 in sense.enemy_builders:
            selected_entity = EntityType.GUNNER
            break
        
        if d not in CARDINAL_DIRECTIONS: continue
        
        p3 = p2.add(d)
        if not is_in_map(p3, sense.map_width, sense.map_height): continue
        if sense.get_env(p3) == Environment.WALL: continue
        if sense.get_entity(p3) in ENTITY_MICRO_USE_GUNNERS_TO_DISABLE and not sense.is_allied(p3):
            selected_entity = EntityType.GUNNER
            break

    # When barriers are included here, uncomment this
    # if selected_entity in ENTITY_TURRET:
    # selected_entity_dir = compute_best_turret_dir(rc, sense, poi, selected_entity, enemy_core_pos)

    return target_pos, replace_from, selected_entity, None

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
    EntityType.ROAD: 0,
    EntityType.BARRIER: 1,
    EntityType.MARKER: 1,
}

def compute_best_turret_dir(rc: Controller, sense: sense.Sense, poi: Position, entt: EntityType, enemy_core_pos: Position) -> Direction:
    max_dir = None
    max_dir_score = -1000000

    feed_dirs = []
    for d in CARDINAL_DIRECTIONS:
        p = poi.add(d)
        if not is_in_map(p, sense.map_width, sense.map_height): continue
        if not sense.is_seen(p): continue
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
            rc.draw_indicator_dot(t, 255, 0,0)
            
            tentt = sense.get_entity(t)
            if not sense.is_allied(t) and tentt is not None:
                score += PRIORITIES[tentt]
                print('added ', tentt, t)
            
            if rc.is_in_vision(t):
                bb = rc.get_tile_builder_bot_id(t)
                if bb is not None and rc.get_team(bb) != rc.get_team():
                    score += PRIORITIES[EntityType.BUILDER_BOT]
                    print('added ', bb, t)
            
        print(d, score)
        if score < 20: continue
        if score > max_dir_score:
            max_dir_score = score
            max_dir = d
    if max_dir == None:
        max_dir = poi.direction_to(enemy_core_pos)
    
    return max_dir

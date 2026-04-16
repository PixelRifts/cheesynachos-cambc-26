import pathfind
from sense import *

from cambc import Controller, Environment, Position, Direction, EntityType, GameConstants

def try_destroy(rc: Controller, sense: Sense, me: Position, p: Position, ti_min: int = 0) -> bool:
    # print('trying to destroy', p)
    if not sense.is_seen(p):
        pathfind.fast_pathfind_to(rc, sense, p)
        return False
    
    ti, ax = rc.get_global_resources()
    
    if not rc.is_in_vision(p):
        # print(p, 'is out of vision')
        pathfind.fast_pathfind_to(rc, sense, p)
        return False
    
    bldg = rc.get_tile_building_id(p)
    if bldg is None:
        if me is None: return True
        if ti < ti_min:
            # print('not enough ti to justify moving out of the way ', ti, ti_min)
            pathfind.fast_pathfind_to(rc, sense, p)
            return False
        # print('moving back to ', me)
        return pathfind.fast_pathfind_to(rc, sense, me)

    entt = sense.get_entity(p)
    allied = sense.is_allied(p)
    already_connected = False

    if entt in ENTITY_UNWALKABLE:
        if allied:
            # print('unwalkable allied', p)
            if rc.get_position() == p:
                # print('1 ', p)
                pathfind.fast_pathfind_to(rc, sense, p.add(get_best_empty_adj(rc, p, me)))
            if not is_adjacent_with_diag(rc.get_position(), p):
                # print('2 ', p)
                pathfind.fast_pathfind_to(rc, sense, p)
            if rc.can_destroy(p) and ti >= ti_min:
                # print('destroying ', p, 'bcoz', ti, ti_min)
                rc.destroy(p)
        else:
            print('cant destroy', p)
    else:
        if allied:
            # print('walkable allied', p)
            if not is_adjacent_with_diag(rc.get_position(), p):
                # print('2 ', p)
                pathfind.fast_pathfind_to(rc, sense, p)
            if rc.can_destroy(p) and ti >= ti_min:
                # print('destroying ', p, 'bcoz', ti, ti_min)
                rc.destroy(p)
            else:
                print(ti, ti_min)
        else:
            # print('walkable enemy', p)
            if rc.get_position() != p:
                # print('pathing to ', p)
                pathfind.fast_pathfind_to(rc, sense, p)
                if rc.get_position() != p: return False
            
            if rc.can_fire(p) and bb_should_fire(rc, sense):
                # print('firing', p)
                rc.fire(p)

    return False

def bb_should_fire(rc: Controller, sense: Sense):
    be_conservative = sense.ti_tracker[-1] < 50
    if be_conservative:
        cur = rc.get_position()
        bldg = rc.get_tile_building_id(cur)
        required_turns = (rc.get_hp(bldg) + GameConstants.BUILDER_BOT_ATTACK_DAMAGE - 1) // GameConstants.BUILDER_BOT_ATTACK_DAMAGE
        return sense.nearest_enemy_cheby_dist >= required_turns
    return True

def is_getting_ammo(rc: Controller, sense: Sense, pos: Position):
    for d in CARDINAL_DIRECTIONS:
        p = pos.add(d)
        if not is_in_map(p, sense.map_width, sense.map_height): continue
        if not rc.is_in_vision(p): continue
        env = sense.get_env(p)
        if env == Environment.WALL: continue
        entt = sense.get_entity(p)
        
        if entt == EntityType.HARVESTER and env == Environment.ORE_TITANIUM: return True
        bldg = rc.get_tile_building_id(p)
        dir = sense.get_direction(p)
        if bldg is None: continue
        if entt == EntityType.CONVEYOR          and dir == d.opposite() and rc.get_stored_resource(bldg) in RESOURCE_ALLOWED_AMMO: return True
        if entt == EntityType.ARMOURED_CONVEYOR and dir == d.opposite() and rc.get_stored_resource(bldg) in RESOURCE_ALLOWED_AMMO: return True
        if entt == EntityType.SPLITTER          and dir != d            and rc.get_stored_resource(bldg) in RESOURCE_ALLOWED_AMMO: return True

    return False
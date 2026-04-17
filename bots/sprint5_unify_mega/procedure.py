import pathfind
from sense import *

from cambc import Controller, Environment, Position, Direction, EntityType

def try_destroy(rc: Controller, sense: Sense, me: Position, p: Position, ti_min: int = 0) -> bool:
    if not sense.is_seen(p):
        pathfind.fast_pathfind_to(rc, sense, p)
        return False
    
    ti, ax = rc.get_global_resources()
    
    if not rc.is_in_vision(p):
        pathfind.fast_pathfind_to(rc, sense, p)
        return False
    
    bldg = rc.get_tile_building_id(p)
    if bldg is None:
        if me is None: return True
        if ti < ti_min:
            pathfind.fast_pathfind_to(rc, sense, p)
            return False
        return pathfind.fast_pathfind_to(rc, sense, me)

    entt = sense.get_entity(p)
    allied = sense.is_allied(p)
    already_connected = False

    if entt in ENTITY_UNWALKABLE:
        if allied:
            if rc.get_position() == p:
                pathfind.fast_pathfind_to(rc, sense, p.add(get_best_empty_adj(rc, p, me)))
            if not is_adjacent_with_diag(rc.get_position(), p):
                pathfind.fast_pathfind_to(rc, sense, p)
            if rc.can_destroy(p) and ti >= ti_min:
                rc.destroy(p)
        else:
            print('cant destroy', p)
    else:
        if allied:
            if not is_adjacent_with_diag(rc.get_position(), p):
                pathfind.fast_pathfind_to(rc, sense, p)
            if rc.can_destroy(p) and ti >= ti_min:
                rc.destroy(p)
        else:
            if rc.get_position() != p:
                pathfind.fast_pathfind_to(rc, sense, p)
                if rc.get_position() != p: return False
            if rc.can_fire(p):
                rc.fire(p)

    return False
